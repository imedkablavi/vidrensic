from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.media.repair import RepairIntegrityError, remux_video_with_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-repair",
        description="Create a verified non-destructive derived repair copy.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=("remux",), default="remux")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.out.exists() or args.out.is_symlink():
        parser.error(f"output already exists: {args.out}")
    if args.manifest.exists() or args.manifest.is_symlink():
        parser.error(f"manifest already exists: {args.manifest}")

    case = Case.load(args.case) if args.case else None
    details = {
        "source": str(args.source),
        "destination": str(args.out),
        "manifest": str(args.manifest),
        "mode": args.mode,
    }
    job = None
    if case:
        job = case.jobs.create("media.repair", details)
        case.jobs.start(job.job_id)
        case.audit.append("media.repair.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = remux_video_with_manifest(args.source, args.out, args.manifest)
    except (OSError, RuntimeError, ValueError, RepairIntegrityError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.repair.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to repair media: {exc}", file=sys.stderr)
        return 2

    checkpoint = {
        "destination": str(report.destination),
        "manifest": str(args.manifest),
        "source_sha256": report.source_sha256,
        "destination_sha256": report.destination_sha256,
        "source_size_bytes": report.source_size_bytes,
        "destination_size_bytes": report.destination_size_bytes,
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.repair.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Repair complete")
    print()
    print(f"Mode         {args.mode}")
    print("Operation    Stream-copy remux")
    print("Source       Unmodified")
    print("Verification Source/output hashed and output re-probed")
    print(f"Output       {report.destination.expanduser().resolve()}")
    print(f"Manifest     {args.manifest.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
