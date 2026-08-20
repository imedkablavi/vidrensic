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
from vidrensic.core.case import Case
from vidrensic.plugins.registry import PluginRegistry
from vidrensic.plugins.wfs import WFSPlugin
from vidrensic.plugins.wfs.recovery import recover_segment


def _int_auto(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid integer: {value}") from exc


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


def default_registry() -> PluginRegistry:
    return PluginRegistry([WFSPlugin()])


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

    source_cmd = sub.add_parser("source", help="inspect evidence sources")
    source_sub = source_cmd.add_subparsers(dest="source_command")
    inspect = source_sub.add_parser("inspect")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--json", action="store_true")

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

    plugins = sub.add_parser("plugins", help="inspect format plugins")
    plugins_sub = plugins.add_subparsers(dest="plugins_command")
    plugins_sub.add_parser("list")

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

    if args.command == "source" and args.source_command == "inspect":
        info = inspect_source(args.path)
        data = _source_to_dict(info)
        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
        else:
            for key, value in data.items():
                print(f"{key}={value}")
        return 0 if info.exists else 1

    if args.command == "acquire" and args.acquire_command == "plan":
        plan = _plan_from_args(args)
        for command in (plan.first_pass_command(), plan.retry_command()):
            if command is not None:
                print(shlex.join(command))
        return 0

    if args.command == "acquire" and args.acquire_command == "run":
        plan = _plan_from_args(args)
        case = Case.load(args.case) if args.case else None
        if case:
            case.audit.append(
                "acquisition.started",
                {
                    "source": str(plan.source),
                    "output": str(plan.output),
                    "mapfile": str(plan.mapfile),
                    "offset": plan.offset,
                    "size": plan.size,
                    "retry_passes": plan.retry_passes,
                    "direct": plan.direct,
                    "write_enabled_override": args.allow_write_enabled_source,
                },
                actor=case.examiner,
            )
        try:
            results = execute_plan(
                plan,
                allow_write_enabled_source=args.allow_write_enabled_source,
            )
        except Exception as exc:
            if case:
                case.audit.append(
                    "acquisition.failed",
                    {"error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        return_codes = [result.returncode for result in results]
        if case:
            case.audit.append(
                "acquisition.finished",
                {"return_codes": return_codes, "output": str(plan.output)},
                actor=case.examiner,
            )
        return 0 if return_codes and all(code == 0 for code in return_codes) else 1

    if args.command == "plugins" and args.plugins_command == "list":
        registry = default_registry()
        for name in registry.names():
            plugin = registry.get(name)
            print(f"{plugin.name}\t{plugin.display_name}")
        return 0

    if args.command == "scan":
        require_safe_source(args.source)
        registry = default_registry()
        if args.plugin == "auto":
            detection, plugin = registry.detect_best(args.source)
            if detection.confidence < 0.50:
                print(
                    f"automatic format detection confidence too low: {detection.confidence:.2f}",
                    file=sys.stderr,
                )
                for reason in detection.reasons:
                    print(f"  - {reason}", file=sys.stderr)
                return 3
        else:
            plugin = registry.get(args.plugin)
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
                frags = ",".join(str(value) for value in item.start_fragments)
                print(f"{item.label}\tcount={len(item.start_fragments)}\tfragments={frags}")
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
        if case:
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
            if case:
                case.audit.append(
                    "wfs.recovery.failed",
                    {**details, "error": f"{type(exc).__name__}: {exc}"},
                    actor=case.examiner,
                )
            raise
        if case:
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

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
