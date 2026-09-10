from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic.core.case import Case
from vidrensic.media.scenes import create_contact_sheet


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("integer must be positive")
    return result


def _positive_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected seconds") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("seconds must be positive")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-scenes",
        description="Create a bounded derived contact sheet for visual video triage.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=_positive_int, default=24, help="requested visual samples")
    parser.add_argument("--thumb-width", type=_positive_int, default=320, help="thumbnail width in pixels")
    parser.add_argument("--timeout", type=_positive_float, default=180.0, help="ffmpeg timeout in seconds")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    manifest = args.out.with_suffix(args.out.suffix + ".json")

    for reserved in (args.out, manifest):
        if reserved.exists() or reserved.is_symlink():
            parser.error(f"output already exists: {reserved}")

    case = Case.load(args.case) if args.case else None
    details = {
        "source": str(args.source),
        "output": str(args.out),
        "manifest": str(manifest),
        "samples": args.samples,
        "thumb_width": args.thumb_width,
        "timeout": args.timeout,
    }
    job = None
    if case:
        job = case.jobs.create("media.scene-sampling", details)
        case.jobs.start(job.job_id)
        case.audit.append(
            "media.scene-sampling.started",
            {**details, "job_id": job.job_id},
            actor=case.examiner,
        )

    try:
        report = create_contact_sheet(
            args.source,
            args.out,
            sample_count=args.samples,
            thumbnail_width=args.thumb_width,
            timeout=args.timeout,
        )
        report.write_json(manifest)
    except (OSError, RuntimeError, ValueError) as exc:
        try:
            if args.out.exists() and not args.out.is_symlink():
                args.out.unlink()
        except OSError:
            pass
        try:
            if manifest.exists() and not manifest.is_symlink():
                manifest.unlink()
        except OSError:
            pass
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.scene-sampling.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to create contact sheet: {exc}", file=sys.stderr)
        return 2

    checkpoint = {
        "contact_sheet": str(report.output),
        "manifest": str(manifest),
        "source_sha256": report.source_sha256,
        "source_sha512": report.source_sha512,
        "output_sha256": report.output_sha256,
        "output_sha512": report.output_sha512,
        "output_size_bytes": report.output_size_bytes,
        "sample_count": report.requested_sample_count,
        "approximate_interval_seconds": report.approximate_interval_seconds,
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.scene-sampling.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Contact sheet created")
    print()
    print(f"Artifact     {report.artifact.name}")
    print(f"Duration     {report.duration_seconds:.3f} seconds")
    print(f"Samples      {report.requested_sample_count}")
    print(f"Interval     {report.approximate_interval_seconds:.3f} seconds")
    print(f"Grid         {report.columns} × {report.rows}")
    print("Derived      Yes — visual triage only")
    print(f"Sheet        {report.output.expanduser().resolve()}")
    print(f"Manifest     {manifest.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
