from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.core.models import EvidenceStatus
from vidrensic.media.forensic_scan_engine import run_forensic_scan


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected positive number") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected positive integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return result


def _exit_code(status: EvidenceStatus) -> int:
    return 0 if status is EvidenceStatus.PASS else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-forensic-scan",
        description="Run a conservative composite forensic scan over one recovered video artifact.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", choices=("quick", "standard", "deep"), default="standard")
    parser.add_argument("--expected-duration", type=_positive_float)
    parser.add_argument("--timeout", type=_positive_float)
    parser.add_argument("--decoder-errors", action="store_true")
    parser.add_argument("--window-seconds", type=_positive_float, default=4.0)
    parser.add_argument("--max-windows", type=_positive_int, default=512)
    parser.add_argument("--case", type=Path)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    case = Case.load(args.case) if args.case else None
    details = {
        "source": str(args.source),
        "output": str(args.out),
        "profile": args.profile,
        "expected_duration": args.expected_duration,
        "timeout": args.timeout,
        "decoder_errors": args.decoder_errors,
    }
    job = None
    if case:
        job = case.jobs.create("media.forensic-scan", details)
        case.jobs.start(job.job_id)
        case.audit.append("media.forensic-scan.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = run_forensic_scan(
            args.source,
            profile=args.profile,
            expected_duration=args.expected_duration,
            timeout=args.timeout,
            decoder_errors=args.decoder_errors,
            decoder_window_seconds=args.window_seconds,
            decoder_max_windows=args.max_windows,
        )
        output = report.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.forensic-scan.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to run forensic scan: {exc}", file=sys.stderr)
        return 2

    checkpoint = {
        "report": str(output),
        "status": report.status.value,
        "confidence": report.confidence_level,
        "interval_count": len(report.evidence_intervals),
        "sha256_before": report.sha256_before,
        "sha256_after": report.sha256_after,
        "finding_count": len(report.findings),
        "fail_count": sum(item.severity == "FAIL" for item in report.findings),
        "review_count": sum(item.severity == "REVIEW" for item in report.findings),
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.forensic-scan.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return _exit_code(report.status)

    print("Forensic media scan complete")
    print()
    print(f"Artifact     {report.artifact.name}")
    print(f"Profile      {report.profile}")
    print(f"Verdict      {report.status.value}")
    print(f"Confidence   {report.confidence_level}")
    print(f"Intervals    {len(report.evidence_intervals):,}")
    print(f"SHA-256      {report.sha256_after}")
    print(f"Findings     {len(report.findings):,}")
    for finding in report.findings[:20]:
        print(f"  [{finding.severity}] {finding.code}: {finding.message}")
    if len(report.findings) > 20:
        print(f"  … and {len(report.findings) - 20} more")
    print(f"Report       {output.expanduser().resolve()}")
    return _exit_code(report.status)


if __name__ == "__main__":
    raise SystemExit(main())
