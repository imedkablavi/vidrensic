from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic import __product__, __version__
from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.acquisition.linux import require_safe_source
from vidrensic.acquisition.receipt import build_acquisition_receipt
from vidrensic.cli import main as legacy_main
from vidrensic.core.case import Case
from vidrensic.core.doctor import run_doctor
from vidrensic.core.units import parse_byte_size
from vidrensic.crypto import KeyMaterial, decrypt_aes_file
from vidrensic.plugins.wfs.recovery import recover_segment
from vidrensic.profiler.triage import triage_source
from vidrensic.ui import confidence_label, detection_name, heading, label, path, success, warning
from vidrensic.validation import create_private_case_manifest, load_corpus, run_corpus


EXTENDED_COMMANDS = (
    "analyze <source> --out <report>",
    "acquire verify <source> --output <image> --map <map> --receipt <report>",
    "recover wfs <source> --starts <n,...> --stop-fragment <n> --out <dir> --label <name>",
    "validate corpus <manifest> --out <report>",
    "validate private-case <source> --out <manifest> --case-id <id> --family <family>",
)


def _byte_size(value: str) -> int:
    try:
        return parse_byte_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _integer(value: str) -> int:
    try:
        return int(value, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected an integer") from exc


def _csv_ints(value: str) -> list[int]:
    try:
        result = [int(part.strip(), 0) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected comma-separated integer values") from exc
    if not result:
        raise argparse.ArgumentTypeError("at least one integer is required")
    if len(set(result)) != len(result):
        raise argparse.ArgumentTypeError("duplicate values are not allowed")
    return result


def _hex_bytes(value: str, *, expected: int | None = None) -> bytes:
    try:
        result = bytes.fromhex(value.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected hexadecimal bytes") from exc
    if expected is not None and len(result) != expected:
        raise argparse.ArgumentTypeError(f"expected exactly {expected} bytes")
    return result


def _doctor(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="vidrensic doctor", description="Check system readiness")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = run_doctor()
    data = report.to_dict()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0 if report.core_ready else 2

    heading("System check", f"{__product__} {__version__}")
    if report.core_ready:
        success("Ready")
    else:
        warning("Attention required")
    label("Core services", "Ready" if data["core_ready"] else "Unavailable")
    available = sum(1 for tool in data["tools"] if tool["available"])
    label("External tools", f"{available} available")
    if not report.core_ready:
        print("Run the setup guide and check the missing system components.")
    return 0 if report.core_ready else 2


def _analyze(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic analyze",
        description="Run a read-only first-pass analysis and recommend the next forensic step.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-size", type=_byte_size, default=4 * 1024 * 1024)
    parser.add_argument("--sample-count", type=int, default=5)
    parser.add_argument("--hitmap-size", type=_byte_size, default=512 * 1024 * 1024)
    parser.add_argument("--full-hitmap", action="store_true")
    parser.add_argument("--hitmap-chunk-size", type=_byte_size, default=16 * 1024 * 1024)
    parser.add_argument("--max-offsets", type=int, default=128)
    parser.add_argument("--minimum-confidence", type=float, default=0.60)
    parser.add_argument("--minimum-margin", type=float, default=0.15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

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
    payload = report.to_dict()
    detection = report.format_detection
    results = detection.get("results", [])
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 3 if detection["requires_review"] else 0

    best = results[0] if results else None
    heading("Analysis complete", report.source.name)
    label("Detection", detection_name(None if best is None else best.get("plugin")))
    label("Confidence", confidence_label(None if best is None else best.get("confidence")))
    label("Assessment", "Review required" if detection["requires_review"] else "Ready for next step")
    if report.source_info.get("size_bytes") is not None:
        label("Source size", f"{report.source_info['size_bytes']:,} bytes")
    filesystems = report.storage.get("filesystems", [])
    if filesystems:
        label("Storage", f"{len(filesystems)} filesystem finding(s)")

    if detection["requires_review"]:
        warning("No automatic format decision was made. Review the analysis before recovery.")
    else:
        success("The source is ready for the next analysis step.")

    if report.recommended_actions:
        print()
        label("Next step", _friendly_action(report.recommended_actions[0]))
    path("Report", args.out)
    return 3 if detection["requires_review"] else 0


def _friendly_action(action: str) -> str:
    text = action.lower()
    if "profile wfs" in text:
        return "Profile the WFS layout"
    if "scan the target date" in text:
        return "Scan the target date and review recording candidates"
    if "dhav" in text and "demultiplex" in text:
        return "Review DHAV channel and timestamp structure"
    if "master sector" in text:
        return "Review the recorder profile evidence"
    if "wider/full physical hit map" in text:
        return "Expand the physical scan"
    if "filesystem" in text:
        return "Review storage findings"
    return action.split(";", 1)[0].strip().rstrip(".").capitalize()


def _decrypt_aes(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic decrypt aes",
        description="Known-key AES transformation with an auditable receipt.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("cbc", "ctr"), required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--key-encoding", choices=("raw", "hex"), default="raw")
    parser.add_argument("--iv-hex", required=True)
    parser.add_argument("--padding", choices=("none", "pkcs7"), default="none")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--case", type=Path)
    args = parser.parse_args(argv)

    try:
        iv = _hex_bytes(args.iv_hex, expected=16)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    key = KeyMaterial.from_file(args.key_file, encoding=args.key_encoding)
    case = Case.load(args.case) if args.case else None
    details = {
        "input": str(args.input),
        "output": str(args.output),
        "mode": args.mode,
        "padding": args.padding,
        "receipt": str(args.receipt),
        "key_source_label": key.source_label,
        "key_fingerprint_sha256": key.fingerprint_sha256,
        "iv_hex": iv.hex(),
    }
    job = None
    if case:
        job = case.jobs.create("crypto.decrypt.aes", details)
        case.jobs.start(job.job_id)
        case.audit.append("crypto.decrypt.started", {**details, "job_id": job.job_id}, actor=case.examiner)
    try:
        receipt = decrypt_aes_file(
            args.input,
            args.output,
            key_material=key,
            iv=iv,
            mode=args.mode,
            padding_mode=args.padding,
            receipt_path=args.receipt,
        )
    except Exception as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "crypto.decrypt.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        raise

    if case and job:
        case.jobs.checkpoint(
            job.job_id,
            {
                "output_sha256": receipt.output_sha256,
                "output_bytes": receipt.output_bytes,
                "receipt": str(args.receipt),
            },
        )
        case.jobs.complete(job.job_id)
        case.audit.append(
            "crypto.decrypt.finished",
            {
                **details,
                "job_id": job.job_id,
                "input_sha256": receipt.input_sha256,
                "output_sha256": receipt.output_sha256,
                "output_bytes": receipt.output_bytes,
            },
            actor=case.examiner,
        )
    heading("Transformation complete", args.input.name)
    path("Receipt", args.receipt)
    return 0


def _acquire_verify(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic acquire verify",
        description="Verify an acquisition and write a forensic receipt.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map", dest="mapfile", type=Path, required=True)
    parser.add_argument("--offset", type=_byte_size, default=0)
    parser.add_argument("--size", type=_byte_size)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--return-code", type=int, action="append", default=[])
    parser.add_argument("--skip-output-hash", action="store_true")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    source_info = require_safe_source(args.source)
    plan = AcquisitionPlan(
        source=args.source,
        output=args.output,
        mapfile=args.mapfile,
        offset=args.offset,
        size=args.size,
    )
    receipt = build_acquisition_receipt(
        plan,
        source_info,
        tuple(args.return_code),
        hash_output=not args.skip_output_hash,
    )
    receipt.write_json(args.receipt)
    if args.case:
        case = Case.load(args.case)
        case.audit.append(
            "acquisition.verified",
            {
                "source": str(args.source),
                "output": str(args.output),
                "mapfile": str(args.mapfile),
                "receipt": str(args.receipt),
                "status": receipt.status,
                "reasons": list(receipt.reasons),
                "output_sha256": receipt.output_sha256,
                "map_sha256": receipt.map_sha256,
            },
            actor=case.examiner,
        )
    if args.json:
        print(json.dumps(receipt.to_dict(), indent=2, sort_keys=True))
        return 0 if receipt.status == "COMPLETE" else 3

    heading("Verification complete", args.output.name)
    if receipt.status == "COMPLETE":
        success("Ready")
        label("Result", "Verified")
    else:
        warning("Review required")
        label("Result", "Needs review")
    path("Receipt", args.receipt)
    return 0 if receipt.status == "COMPLETE" else 3


def _recover_wfs(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic recover wfs",
        description="Recover WFS recording candidates using the bounded global strategy.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--starts", type=_csv_ints, required=True)
    parser.add_argument("--stop-fragment", type=_integer, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--data-offset", type=_byte_size, default=0)
    parser.add_argument("--fragment-size", type=_byte_size, default=2 * 1024 * 1024)
    parser.add_argument("--near", type=int, default=32)
    parser.add_argument("--far", type=int, default=4096)
    parser.add_argument("--strategy", choices=("global", "local"), default="global")
    parser.add_argument("--candidate-top", type=int, default=4)
    parser.add_argument("--beam-width", type=int, default=24)
    parser.add_argument("--max-hypotheses", type=int, default=64)
    parser.add_argument("--max-combinations", type=int, default=250_000)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    require_safe_source(args.source)
    case = Case.load(args.case) if args.case else None
    details = {
        "source": str(args.source),
        "starts": args.starts,
        "stop_fragment": args.stop_fragment,
        "output": str(args.out),
        "label": args.label,
        "data_offset": args.data_offset,
        "fragment_size": args.fragment_size,
        "near": args.near,
        "far": args.far,
        "strategy": args.strategy,
        "candidate_top": args.candidate_top,
        "beam_width": args.beam_width,
        "max_hypotheses": args.max_hypotheses,
        "max_combinations": args.max_combinations,
    }
    job = None
    if case:
        job = case.jobs.create("wfs.recover", details)
        case.jobs.start(job.job_id)
        case.audit.append("wfs.recovery.started", {**details, "job_id": job.job_id}, actor=case.examiner)
    try:
        candidates, manifest = recover_segment(
            args.source,
            args.starts,
            args.stop_fragment,
            args.out,
            label=args.label,
            data_offset=args.data_offset,
            fragment_size=args.fragment_size,
            near=args.near,
            far=args.far,
            strategy=args.strategy,
            candidate_top=args.candidate_top,
            beam_width=args.beam_width,
            max_hypotheses=args.max_hypotheses,
            max_combinations=args.max_combinations,
        )
    except Exception as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "wfs.recovery.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        raise

    if case and job:
        case.jobs.checkpoint(job.job_id, {"manifest": str(manifest), "candidate_count": len(candidates)})
        case.jobs.complete(job.job_id)
        case.audit.append(
            "wfs.recovery.finished",
            {
                **details,
                "job_id": job.job_id,
                "manifest": str(manifest),
                "candidate_count": len(candidates),
                "statuses": [item.status for item in candidates],
            },
            actor=case.examiner,
        )

    if args.json:
        payload = {
            "manifest": str(manifest),
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "candidate_id": item.candidate_id,
                    "status": item.status,
                    "strategy": item.reconstruction_strategy,
                    "fragment_count": len(item.fragments),
                    "native_bytes": item.native_bytes,
                    "output": str(item.native_output),
                }
                for item in candidates
            ],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    heading("Recovery complete", args.label)
    label("Candidates", len(candidates))
    review = sum(1 for item in candidates if item.status == "REVIEW")
    if review:
        warning(f"{review} candidate(s) require review")
    else:
        success("Candidate set ready for review")
    path("Manifest", manifest)
    return 0


def _validate_private_case(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic validate private-case",
        description="Prepare owner-only staging metadata for a restricted recorder fixture.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument(
        "--family",
        choices=("wfs", "dhav", "hikvision", "annexb", "mpegps", "generic"),
        required=True,
    )
    parser.add_argument("--manufacturer")
    parser.add_argument("--model")
    parser.add_argument("--firmware")
    parser.add_argument("--note", action="append", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        manifest = create_private_case_manifest(
            args.source,
            args.out,
            case_id=args.case_id,
            family=args.family,
            manufacturer=args.manufacturer,
            model=args.model,
            firmware=args.firmware,
            notes=args.note,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    if args.json:
        print(
            json.dumps(
                {
                    "manifest": str(manifest.path.expanduser().resolve()),
                    "case_id": manifest.case_id,
                    "family": manifest.family,
                    "source_sha256": manifest.source_sha256,
                    "source_size_bytes": manifest.source_size_bytes,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    heading("Validation case prepared", manifest.case_id)
    success("Source metadata secured")
    label("Family", manifest.family.upper())
    path("Manifest", manifest.path)
    return 0


def _validate_corpus(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic validate corpus",
        description="Run a deterministic validation corpus against declared ground truth.",
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    corpus = load_corpus(args.manifest)
    report = run_corpus(corpus)
    report.write_json(args.out)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0 if report.status == "PASS" else 3

    heading("Validation complete", corpus.corpus_id)
    label("Cases", len(corpus.cases))
    label("Passed", report.passed)
    label("Failed", report.failed)
    if report.status == "PASS":
        success("All declared checks passed")
    else:
        warning("Review the validation report")
    path("Report", args.out)
    return 0 if report.status == "PASS" else 3


def _product_help() -> int:
    heading("Vidrensic", "Forensic video evidence")
    print("Start here")
    print("  analyze <source> --out <report>   Analyze a recorder source")
    print("  acquire verify ...                Verify an acquired image")
    print("  recover wfs ...                   Recover WFS candidates")
    print("  validate corpus ...               Run declared validation")
    print()
    print("Case and system")
    print("  case ...                           Manage a case")
    print("  source ...                         Inspect a source")
    print("  profile ...                        Build source findings")
    print("  formats ...                        Review format capabilities")
    print("  profiles ...                       Review recorder profiles")
    print("  qc ...                             Review recovered media")
    print()
    print(f"For the complete command reference: {__product__.lower()} --advanced-help")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        return _product_help()
    if args in (["--help"], ["-h"]):
        return _product_help()
    if args == ["--advanced-help"]:
        try:
            legacy_main(["--help"])
        except SystemExit:
            pass
        return 0
    if args == ["--version"]:
        return legacy_main(args)
    if args[0] == "analyze":
        return _analyze(args[1:])
    if args[0] == "doctor":
        return _doctor(args[1:])
    if args[:2] == ["decrypt", "aes"]:
        return _decrypt_aes(args[2:])
    if args[:2] == ["acquire", "verify"]:
        return _acquire_verify(args[2:])
    if args[:2] == ["recover", "wfs"]:
        return _recover_wfs(args[2:])
    if args[:2] == ["validate", "private-case"]:
        return _validate_private_case(args[2:])
    if args[:2] == ["validate", "corpus"]:
        return _validate_corpus(args[2:])
    return legacy_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
