from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.media.proxy import ProxyIntegrityError, transcode_proxy_with_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-proxy",
        description="Create a controlled H.264/AAC MP4 review proxy from recovered video.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
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
        "profile": "review-h264-aac",
    }
    job = None
    if case:
        job = case.jobs.create("media.proxy", details)
        case.jobs.start(job.job_id)
        case.audit.append("media.proxy.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = transcode_proxy_with_manifest(args.source, args.out, args.manifest)
    except (OSError, RuntimeError, ValueError, ProxyIntegrityError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.proxy.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to create review proxy: {exc}", file=sys.stderr)
        return 2

    checkpoint = {
        "destination": str(report.destination),
        "manifest": str(args.manifest),
        "source_sha256": report.source_sha256,
        "destination_sha256": report.destination_sha256,
        "source_size_bytes": report.source_size_bytes,
        "destination_size_bytes": report.destination_size_bytes,
        "decode_smoke_tested": report.decode_smoke_tested,
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.proxy.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Review proxy created")
    print()
    print("Profile      H.264/AAC MP4")
    print("Source       Unmodified")
    print("Derived      Yes — review proxy only")
    print("Decode QC    Passed")
    print(f"Output       {report.destination.expanduser().resolve()}")
    print(f"Manifest     {args.manifest.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
