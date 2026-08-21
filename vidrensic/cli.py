from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
from pathlib import Path
import json
import shlex
import sys

from vidrensic import __product__, __version__
from vidrensic.acquisition.ddrescue import AcquisitionPlan, execute_plan
from vidrensic.acquisition.linux import inspect_source, require_safe_source
from vidrensic.acquisition.smart import capture_smart
from vidrensic.core.case import Case
from vidrensic.core.jobs import JobStatus
from vidrensic.core.units import parse_byte_size
from vidrensic.media.qc import fast_three_point_check, full_decode_check
from vidrensic.plugins.capabilities import FormatOperation
from vidrensic.plugins.defaults import default_plugin_registry
from vidrensic.plugins.dhav import demux_dhav_range
from vidrensic.plugins.wfs.layout import infer_wfs_fragment_alignment
from vidrensic.plugins.wfs.recovery import recover_segment
from vidrensic.profiler.hitmap import scan_signature_hitmap
from vidrensic.profiler.source import profile_source
from vidrensic.profiler.storage import profile_storage
from vidrensic.profiler.triage import triage_source
from vidrensic.profiles import default_profile_registry


def _int_auto(value: str) -> int:
    try:
        return parse_byte_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _csv_ints(value: str) -> list[int]:
    try:
        result = [int(part.strip(), 0) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integer values") from exc
    if not result:
        raise argparse.ArgumentTypeError("at least one integer is required")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("duplicate fragment values are not allowed")
    return result


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def _job_status(value: str) -> JobStatus:
    try:
        return JobStatus(value.upper())
    except ValueError as exc:
        choices = ", ".join(item.value for item in JobStatus)
        raise argparse.ArgumentTypeError(f"status must be one of: {choices}") from exc


def default_registry():
    return default_plugin_registry()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vidrensic",
        description="Vidrensic — DVR/NVR evidence reconstruction and video forensics",
    )
    parser.add_argument("--version", action="version", version=f"{__product__} {__version__}")
    sub = parser.add_subparsers(dest="command")

    case_cmd = sub.add_parser("case", help="create and verify forensic cases")
    case_sub = case_cmd.add_subparsers(dest="case_command")
    create = case_sub.add_parser("create", help="create a new case")
    create.add_argument("case_id")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--examiner")
    verify = case_sub.add_parser("verify-audit", help="verify case audit hash chain")
    verify.add_argument("case", type=Path)
    verify.add_argument("--expected-tail-hash")

    jobs = sub.add_parser("jobs", help="inspect persistent case jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command")
    jobs_list = jobs_sub.add_parser("list")
    jobs_list.add_argument("--case", type=Path, required=True)
    jobs_list.add_argument("--status", type=_job_status)
    jobs_list.add_argument("--kind")
    jobs_list.add_argument("--limit", type=int, default=100)
    jobs_show = jobs_sub.add_parser("show")
    jobs_show.add_argument("job_id")
    jobs_show.add_argument("--case", type=Path, required=True)

    source_cmd = sub.add_parser("source", help="inspect evidence sources")
    source_sub = source_cmd.add_subparsers(dest="source_command")
    inspect = source_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--json", action="store_true")
    smart = source_sub.add_parser("smart", help="capture SMART/device identity as evidence metadata")
    smart.add_argument("path", type=Path)
    smart.add_argument("--out", type=Path)
    smart.add_argument("--case", type=Path)

    triage = sub.add_parser(
        "triage",
        help="run read-only first-pass triage for an unknown DVR/NVR source",
    )
    triage.add_argument("source", type=Path)
    triage.add_argument("--out", type=Path, required=True)
    triage.add_argument("--sample-size", type=_int_auto, default=4 * 1024 * 1024)
    triage.add_argument("--sample-count", type=int, default=5)
    triage.add_argument("--hitmap-size", type=_int_auto, default=512 * 1024 * 1024)
    triage.add_argument("--full-hitmap", action="store_true")
    triage.add_argument("--hitmap-chunk-size", type=_int_auto, default=16 * 1024 * 1024)
    triage.add_argument("--max-offsets", type=int, default=128)
    triage.add_argument("--minimum-confidence", type=float, default=0.60)
    triage.add_argument("--minimum-margin", type=float, default=0.15)
    triage.add_argument("--case", type=Path)

    profile_cmd = sub.add_parser("profile", help="build bounded evidence/source hypotheses")
    profile_sub = profile_cmd.add_subparsers(dest="profile_command")
    profile_generic = profile_sub.add_parser("source", help="sample an unknown DVR/NVR source")
    profile_generic.add_argument("source", type=Path)
    profile_generic.add_argument("--sample-size", type=_int_auto, default=4 * 1024 * 1024)
    profile_generic.add_argument("--sample-count", type=int, default=5)
    profile_generic.add_argument("--out", type=Path, required=True)
    profile_generic.add_argument("--case", type=Path)
    profile_storage_cmd = profile_sub.add_parser(
        "storage",
        help="map MBR/GPT and known filesystems without mounting them",
    )
    profile_storage_cmd.add_argument("source", type=Path)
    profile_storage_cmd.add_argument("--out", type=Path, required=True)
    profile_storage_cmd.add_argument("--case", type=Path)
    profile_hitmap = profile_sub.add_parser(
        "hitmap",
        help="stream physical signature counts/offset samples with bounded memory",
    )
    profile_hitmap.add_argument("source", type=Path)
    profile_hitmap.add_argument("--range-start", type=_int_auto, default=0)
    profile_hitmap.add_argument("--range-size", type=_int_auto)
    profile_hitmap.add_argument("--chunk-size", type=_int_auto, default=16 * 1024 * 1024)
    profile_hitmap.add_argument("--max-offsets", type=int, default=256)
    profile_hitmap.add_argument("--out", type=Path, required=True)
    profile_hitmap.add_argument("--case", type=Path)
    profile_wfs = profile_sub.add_parser(
        "wfs-layout",
        help="rank WFS fragment-alignment hypotheses in a bounded range",
    )
    profile_wfs.add_argument("source", type=Path)
    profile_wfs.add_argument("--range-start", type=_int_auto, default=0)
    profile_wfs.add_argument("--range-size", type=_int_auto, default=64 * 1024 * 1024)
    profile_wfs.add_argument("--fragment-size", type=_int_auto, default=2 * 1024 * 1024)
    profile_wfs.add_argument("--sector-size", type=_int_auto, default=512)
    profile_wfs.add_argument("--top", type=int, default=8)
    profile_wfs.add_argument("--out", type=Path, required=True)
    profile_wfs.add_argument("--case", type=Path)

    acquire = sub.add_parser("acquire", help="plan or execute ddrescue acquisition")
    acquire_sub = acquire.add_subparsers(dest="acquire_command")
    for name in ("plan", "run"):
        action = acquire_sub.add_parser(name)
        action.add_argument("source", type=Path)
        action.add_argument("--output", type=Path, required=True)
        action.add_argument("--map", dest="mapfile", type=Path, required=True)
        action.add_argument("--offset", type=_int_auto, default=0)
        action.add_argument("--size", type=_int_auto)
        action.add_argument("--retry-passes", type=int, default=0)
        action.add_argument("--direct", action="store_true")
        if name == "run":
            action.add_argument("--case", type=Path)
            action.add_argument("--allow-write-enabled-source", action="store_true")

    plugins = sub.add_parser("plugins", help="compatibility alias for format plugins")
    plugins_sub = plugins.add_subparsers(dest="plugins_command")
    plugins_sub.add_parser("list")

    formats = sub.add_parser("formats", help="inspect and rank supported storage/container families")
    formats_sub = formats.add_subparsers(dest="formats_command")
    formats_list = formats_sub.add_parser("list", help="show capability matrix")
    formats_list.add_argument("--json", action="store_true")
    formats_detect = formats_sub.add_parser("detect", help="rank format-family evidence")
    formats_detect.add_argument("source", type=Path)
    formats_detect.add_argument("--minimum-confidence", type=float, default=0.60)
    formats_detect.add_argument("--minimum-margin", type=float, default=0.15)
    formats_detect.add_argument("--json", action="store_true")

    profiles = sub.add_parser("profiles", help="inspect model/firmware variant profiles")
    profiles_sub = profiles.add_subparsers(dest="profiles_command")
    profiles_list = profiles_sub.add_parser("list")
    profiles_list.add_argument("--json", action="store_true")
    profiles_match = profiles_sub.add_parser("match")
    profiles_match.add_argument("--vendor")
    profiles_match.add_argument("--model")
    profiles_match.add_argument("--firmware")
    profiles_match.add_argument("--family")
    profiles_match.add_argument("--json", action="store_true")
    profiles_load = profiles_sub.add_parser("validate-pack", help="validate an external JSON profile pack")
    profiles_load.add_argument("path", type=Path)

    scan = sub.add_parser("scan", help="scan proprietary recording boundaries")
    scan.add_argument("source", type=Path)
    scan.add_argument("--plugin", default="auto")
    scan.add_argument("--date", type=_date, required=True)
    scan.add_argument("--data-offset", type=_int_auto, default=0)
    scan.add_argument("--json", action="store_true")

    recover = sub.add_parser("recover", help="reconstruct proprietary recordings")
    recover_sub = recover.add_subparsers(dest="recover_command")
    recover_wfs = recover_sub.add_parser("wfs", help="recover one WFS recording boundary")
    recover_wfs.add_argument("source", type=Path)
    recover_wfs.add_argument("--starts", type=_csv_ints, required=True)
    recover_wfs.add_argument("--stop-fragment", type=_int_auto, required=True)
    recover_wfs.add_argument("--out", type=Path, required=True)
    recover_wfs.add_argument("--label", required=True)
    recover_wfs.add_argument("--data-offset", type=_int_auto, default=0)
    recover_wfs.add_argument("--near", type=int, default=32)
    recover_wfs.add_argument("--far", type=int, default=4096)
    recover_wfs.add_argument("--case", type=Path)
    recover_dhav = recover_sub.add_parser(
        "dhav",
        help="carve validated DHAV frames and demultiplex physical channel streams",
    )
    recover_dhav.add_argument("source", type=Path)
    recover_dhav.add_argument("--out", type=Path, required=True)
    recover_dhav.add_argument("--start", type=_int_auto, default=0)
    recover_dhav.add_argument("--stop", type=_int_auto)
    recover_dhav.add_argument("--include-unvalidated", action="store_true")
    recover_dhav.add_argument("--case", type=Path)

    qc = sub.add_parser("qc", help="validate recovered video without hiding uncertainty")
    qc_sub = qc.add_subparsers(dest="qc_command")
    qc_fast = qc_sub.add_parser("fast", help="decode beginning/middle/end; never returns PASS")
    qc_fast.add_argument("path", type=Path)
    qc_fast.add_argument("--expected-duration", type=float)
    qc_fast.add_argument("--report", type=Path)
    qc_fast.add_argument("--case", type=Path)
    qc_full = qc_sub.add_parser("full", help="full video decode and timing validation")
    qc_full.add_argument("path", type=Path)
    qc_full.add_argument("--expected-duration", type=float)
    qc_full.add_argument("--ambiguous", action="store_true")
    qc_full.add_argument("--unresolved", action="store_true")
    qc_full.add_argument("--timeout", type=float)
    qc_full.add_argument("--report", type=Path)
    qc_full.add_argument("--case", type=Path)

    return parser


def _plan_from_args(args: argparse.Namespace) -> AcquisitionPlan:
    return AcquisitionPlan(
        source=args.source,
        output=args.output,
        mapfile=args.mapfile,
        offset=args.offset,
        size=args.size,
        retry_passes=args.retry_passes,
        direct=args.direct,
    )


def _source_to_dict(info) -> dict:
    result = asdict(info)
    result["path"] = str(info.path)
    result["mounted_at"] = list(info.mounted_at)
    result["safe_for_forensic_read"] = info.safe_for_forensic_read
    return result


def _job_to_dict(job) -> dict:
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status.value,
        "created_utc": job.created_utc,
        "updated_utc": job.updated_utc,
        "parameters": job.parameters,
        "checkpoint": job.checkpoint,
        "progress_current": job.progress_current,
        "progress_total": job.progress_total,
        "progress_fraction": job.progress_fraction,
        "error": job.error,
    }


def _detection_to_dict(result) -> dict:
    return {
        "plugin": result.plugin,
        "confidence": result.confidence,
        "reasons": list(result.reasons),
        "metadata": result.metadata,
    }


def _print_qc(report) -> int:
    print(f"status={report.decision.status.value}")
    print(f"mode={report.mode}")
    print(f"path={report.path}")
    for reason in report.decision.reasons:
        print(f"reason={reason}")
    return 1 if report.decision.status.value == "FAIL" else 0


def _case_job_start(case: Case | None, kind: str, details: dict):
    if case is None:
        return None
    job = case.jobs.create(kind, details)
    return case.jobs.start(job.job_id)


def _profile_job(case: Case | None, kind: str, details: dict):
    job = _case_job_start(case, kind, details)
    if case and job:
        case.audit.append(f"{kind}.started", {**details, "job_id": job.job_id}, actor=case.examiner)
    return job


def _finish_profile_job(case: Case | None, job, event: str, details: dict, output: Path) -> None:
    if case and job:
        case.jobs.checkpoint(job.job_id, {"output": str(output)})
        case.jobs.complete(job.job_id)
        case.audit.append(event, {**details, "job_id": job.job_id}, actor=case.examiner)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "case" and args.case_command == "create":
        case = Case.create(args.root, args.case_id, examiner=args.examiner)
        print(case.root)
        return 0

    if args.command == "case" and args.case_command == "verify-audit":
        case = Case.load(args.case)
        ok, result = case.audit.verify(expected_tail_hash=args.expected_tail_hash)
        print(result)
        return 0 if ok else 1

    if args.command == "jobs" and args.jobs_command == "list":
        case = Case.load(args.case)
        rows = case.jobs.list(status=args.status, kind=args.kind, limit=args.limit)
        print(json.dumps([_job_to_dict(job) for job in rows], indent=2, sort_keys=True))
        return 0

    if args.command == "jobs" and args.jobs_command == "show":
        case = Case.load(args.case)
        print(json.dumps(_job_to_dict(case.jobs.get(args.job_id)), indent=2, sort_keys=True))
        return 0

    if args.command == "source" and args.source_command == "inspect":
        info = inspect_source(args.path)
        data = _source_to_dict(info)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            for key, value in data.items():
                print(f"{key}={value}")
        return 0 if info.exists else 1

    if args.command == "source" and args.source_command == "smart":
        case = Case.load(args.case) if args.case else None
        details = {"source": str(args.path), "output": str(args.out) if args.out else None}
        job = _case_job_start(case, "source.smart", details)
        try:
            snapshot = capture_smart(args.path)
            if args.out:
                snapshot.write_json(args.out)
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "source.smart.failed",
                    {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        if case and job:
            case.jobs.checkpoint(
                job.job_id,
                {"captured": snapshot.captured, "output": details["output"]},
            )
            case.jobs.complete(job.job_id)
            case.audit.append(
                "source.smart.finished",
                {
                    **details,
                    "job_id": job.job_id,
                    "captured": snapshot.captured,
                    "smart_passed": snapshot.smart_passed,
                    "model": snapshot.model,
                    "serial": snapshot.serial,
                },
                actor=case.examiner,
            )
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
        return 0 if snapshot.captured else 2

    if args.command == "triage":
        case = Case.load(args.case) if args.case else None
        details = {
            "source": str(args.source),
            "output": str(args.out),
            "sample_size": args.sample_size,
            "sample_count": args.sample_count,
            "hitmap_size": None if args.full_hitmap else args.hitmap_size,
            "hitmap_chunk_size": args.hitmap_chunk_size,
            "max_offsets": args.max_offsets,
            "minimum_confidence": args.minimum_confidence,
            "minimum_margin": args.minimum_margin,
        }
        job = _profile_job(case, "triage", details)
        try:
            report = triage_source(
                args.source,
                sample_size=args.sample_size,
                sample_count=args.sample_count,
                hitmap_size=None if args.full_hitmap else args.hitmap_size,
                hitmap_chunk_size=args.hitmap_chunk_size,
                max_offsets_per_signature=args.max_offsets,
                minimum_confidence=args.minimum_confidence,
                minimum_margin=args.minimum_margin,
            )
            report.write_json(args.out)
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "triage.failed",
                    {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        _finish_profile_job(case, job, "triage.finished", details, args.out)
        print(args.out.resolve())
        return 0

    if args.command == "profile" and args.profile_command in (
        "source",
        "storage",
        "hitmap",
        "wfs-layout",
    ):
        case = Case.load(args.case) if args.case else None
        details = {"source": str(args.source), "mode": args.profile_command, "output": str(args.out)}
        job = _profile_job(case, f"profile.{args.profile_command}", details)
        try:
            if args.profile_command == "source":
                report = profile_source(
                    args.source,
                    sample_size=args.sample_size,
                    sample_count=args.sample_count,
                )
            elif args.profile_command == "storage":
                report = profile_storage(args.source)
            elif args.profile_command == "hitmap":
                report = scan_signature_hitmap(
                    args.source,
                    range_start=args.range_start,
                    range_size=args.range_size,
                    chunk_size=args.chunk_size,
                    max_offsets_per_signature=args.max_offsets,
                )
            else:
                report = infer_wfs_fragment_alignment(
                    args.source,
                    range_start=args.range_start,
                    range_size=args.range_size,
                    fragment_size=args.fragment_size,
                    sector_size=args.sector_size,
                    top=args.top,
                )
            report.write_json(args.out)
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "profile.failed",
                    {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        _finish_profile_job(case, job, "profile.finished", details, args.out)
        print(args.out.resolve())
        return 0

    if args.command == "acquire" and args.acquire_command == "plan":
        plan = _plan_from_args(args)
        for command in (plan.first_pass_command(), plan.retry_command()):
            if command is not None:
                print(shlex.join(command))
        return 0

    if args.command == "acquire" and args.acquire_command == "run":
        plan = _plan_from_args(args)
        case = Case.load(args.case) if args.case else None
        details = {
            "source": str(plan.source),
            "output": str(plan.output),
            "mapfile": str(plan.mapfile),
            "offset": plan.offset,
            "size": plan.size,
            "retry_passes": plan.retry_passes,
            "direct": plan.direct,
            "write_enabled_override": args.allow_write_enabled_source,
        }
        job = _case_job_start(case, "acquisition.ddrescue", details)
        if case and job:
            details["job_id"] = job.job_id
            case.audit.append("acquisition.started", details, actor=case.examiner)
        try:
            results = execute_plan(
                plan,
                allow_write_enabled_source=args.allow_write_enabled_source,
            )
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "acquisition.failed",
                    {**details, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        return_codes = [result.returncode for result in results]
        success = bool(return_codes) and all(code == 0 for code in return_codes)
        if case and job:
            if success:
                case.jobs.complete(job.job_id)
            else:
                case.jobs.fail(job.job_id, f"ddrescue return codes: {return_codes}")
            case.audit.append(
                "acquisition.finished",
                {**details, "return_codes": return_codes, "success": success},
                actor=case.examiner,
            )
        return 0 if success else 1

    if args.command == "plugins" and args.plugins_command == "list":
        registry = default_registry()
        for name in registry.names():
            plugin = registry.get(name)
            print(f"{plugin.name}\t{plugin.display_name}\t{plugin.descriptor.support_level.name}")
        return 0

    if args.command == "formats" and args.formats_command == "list":
        registry = default_registry()
        rows = [descriptor.to_dict() for descriptor in registry.descriptors()]
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            for row in rows:
                operations = ",".join(row["operations"]) or "none"
                print(
                    f"{row['family_id']:<10} {row['support_level']:<12} "
                    f"{row['topology']:<28} ops={operations}"
                )
        return 0

    if args.command == "formats" and args.formats_command == "detect":
        registry = default_registry()
        report = registry.detection_report(
            args.source,
            minimum_confidence=args.minimum_confidence,
            minimum_margin=args.minimum_margin,
        )
        payload = {
            "source": str(report.source),
            "requires_review": report.requires_review,
            "reason": report.reason,
            "margin": report.margin,
            "results": [_detection_to_dict(item) for item in report.results],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"requires_review={report.requires_review}")
            print(f"reason={report.reason}")
            for result in report.results:
                print(f"{result.plugin:<10} confidence={result.confidence:.2f}")
                for reason in result.reasons:
                    print(f"  - {reason}")
        return 3 if report.requires_review else 0

    if args.command == "profiles" and args.profiles_command == "list":
        registry = default_profile_registry()
        rows = [profile.to_dict() for profile in registry.all()]
        if args.json:
            print(json.dumps(rows, indent=2, sort_keys=True))
        else:
            for row in rows:
                print(
                    f"{row['profile_id']:<32} family={row['family_id']:<10} "
                    f"state={row['validation_state']}"
                )
        return 0

    if args.command == "profiles" and args.profiles_command == "match":
        registry = default_profile_registry()
        rows = registry.match(
            vendor=args.vendor,
            model=args.model,
            firmware=args.firmware,
            family_id=args.family,
        )
        payload = [{"score": score, **profile.to_dict()} for score, profile in rows]
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for row in payload:
                print(f"{row['score']:.2f}\t{row['profile_id']}\t{row['variant']}")
        return 0

    if args.command == "profiles" and args.profiles_command == "validate-pack":
        registry = default_profile_registry()
        loaded = registry.load_pack(args.path)
        print(f"valid_profiles={len(loaded)}")
        for profile in loaded:
            print(f"{profile.profile_id}\t{profile.family_id}\t{profile.validation_state}")
        return 0

    if args.command == "scan":
        require_safe_source(args.source)
        registry = default_registry()
        if args.plugin == "auto":
            report = registry.detection_report(args.source)
            if report.requires_review:
                print(f"automatic format selection blocked: {report.reason}", file=sys.stderr)
                for result in report.results:
                    print(f"  {result.plugin}: {result.confidence:.2f}", file=sys.stderr)
                return 3
            plugin = registry.get(report.best.plugin)
        else:
            plugin = registry.get(args.plugin)

        if not plugin.descriptor.supports_operation(FormatOperation.DATE_SCAN):
            print(
                f"format family '{plugin.name}' was selected but DATE_SCAN is not implemented; "
                f"support level={plugin.descriptor.support_level.name}",
                file=sys.stderr,
            )
            print(
                "use 'vidrensic formats list' to inspect implemented operations for each family",
                file=sys.stderr,
            )
            return 4

        boundaries = plugin.scan_date(
            args.source,
            args.date,
            data_offset=args.data_offset,
        )
        if args.json:
            payload = [
                {
                    "label": item.label,
                    "timestamp": item.timestamp.isoformat(),
                    "start_fragments": list(item.start_fragments),
                    "data_offset": item.data_offset,
                    "metadata": item.metadata,
                }
                for item in boundaries
            ]
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for item in boundaries:
                starts = ",".join(str(value) for value in item.start_fragments)
                print(f"{item.label}\tcount={len(item.start_fragments)}\tstarts={starts}")
        return 0

    if args.command == "recover" and args.recover_command == "wfs":
        require_safe_source(args.source)
        case = Case.load(args.case) if args.case else None
        details = {
            "source": str(args.source),
            "starts": args.starts,
            "stop_fragment": args.stop_fragment,
            "output": str(args.out),
            "label": args.label,
            "data_offset": args.data_offset,
            "near": args.near,
            "far": args.far,
        }
        job = _case_job_start(case, "wfs.recover", details)
        if case and job:
            details["job_id"] = job.job_id
            case.audit.append("wfs.recovery.started", details, actor=case.examiner)
        try:
            candidates, manifest = recover_segment(
                args.source,
                args.starts,
                args.stop_fragment,
                args.out,
                label=args.label,
                data_offset=args.data_offset,
                near=args.near,
                far=args.far,
            )
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "wfs.recovery.failed",
                    {**details, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        if case and job:
            case.jobs.checkpoint(
                job.job_id,
                {"manifest": str(manifest), "candidate_count": len(candidates)},
            )
            case.jobs.complete(job.job_id)
            case.audit.append(
                "wfs.recovery.finished",
                {
                    **details,
                    "manifest": str(manifest),
                    "candidate_count": len(candidates),
                    "statuses": [candidate.status for candidate in candidates],
                },
                actor=case.examiner,
            )
        print(f"manifest={manifest}")
        for candidate in candidates:
            print(
                f"{candidate.candidate_id}\tstatus={candidate.status}\t"
                f"fragments={len(candidate.fragments)}\tbytes={candidate.native_bytes}\t"
                f"output={candidate.native_output}"
            )
        return 0

    if args.command == "recover" and args.recover_command == "dhav":
        require_safe_source(args.source)
        case = Case.load(args.case) if args.case else None
        details = {
            "source": str(args.source),
            "output": str(args.out),
            "start": args.start,
            "stop": args.stop,
            "include_unvalidated": args.include_unvalidated,
        }
        job = _case_job_start(case, "dhav.recover", details)
        if case and job:
            details["job_id"] = job.job_id
            case.audit.append("dhav.recovery.started", details, actor=case.examiner)
        try:
            manifest = demux_dhav_range(
                args.source,
                args.out,
                start=args.start,
                stop=args.stop,
                include_unvalidated=args.include_unvalidated,
            )
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "dhav.recovery.failed",
                    {**details, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        if case and job:
            case.jobs.checkpoint(job.job_id, {"manifest": str(manifest)})
            case.jobs.complete(job.job_id)
            case.audit.append(
                "dhav.recovery.finished",
                {**details, "manifest": str(manifest)},
                actor=case.examiner,
            )
        print(f"manifest={manifest}")
        return 0

    if args.command == "qc" and args.qc_command in ("fast", "full"):
        case = Case.load(args.case) if args.case else None
        details = {
            "path": str(args.path),
            "mode": args.qc_command,
            "expected_duration": args.expected_duration,
        }
        job = _case_job_start(case, f"media.qc.{args.qc_command}", details)
        if case and job:
            details["job_id"] = job.job_id
            case.audit.append("media.qc.started", details, actor=case.examiner)
        try:
            if args.qc_command == "fast":
                report = fast_three_point_check(
                    args.path,
                    expected_duration=args.expected_duration,
                )
            else:
                report = full_decode_check(
                    args.path,
                    expected_duration=args.expected_duration,
                    reconstruction_ambiguous=args.ambiguous,
                    reconstruction_unresolved=args.unresolved,
                    timeout=args.timeout,
                )
            if args.report:
                report.write_json(args.report)
        except Exception as exc:
            if case and job:
                case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
                case.audit.append(
                    "media.qc.failed",
                    {**details, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        if case and job:
            case.jobs.checkpoint(
                job.job_id,
                {
                    "status": report.decision.status.value,
                    "report": str(args.report) if args.report else None,
                },
            )
            case.jobs.complete(job.job_id)
            case.audit.append(
                "media.qc.finished",
                {
                    **details,
                    "status": report.decision.status.value,
                    "reasons": list(report.decision.reasons),
                    "report": str(args.report) if args.report else None,
                },
                actor=case.examiner,
            )
        return _print_qc(report)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
