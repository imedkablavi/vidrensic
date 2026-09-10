from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic.core.case import Case
from vidrensic.export import export_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic export",
        description="Create and verify a byte-for-byte forensic evidence copy.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("master", "review"), default="master")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    case = Case.load(args.case) if args.case else None
    details = {
        "source": str(args.source),
        "destination": str(args.out),
        "manifest": str(args.manifest),
        "profile": args.profile,
    }
    job = None
    if case:
        job = case.jobs.create("evidence.export", details)
        case.jobs.start(job.job_id)
        case.audit.append("evidence.export.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = export_evidence(
            args.source,
            args.out,
            args.manifest,
            profile=args.profile,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "evidence.export.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to export evidence: {exc}", file=sys.stderr)
        return 2

    if case and job:
        case.jobs.checkpoint(
            job.job_id,
            {
                "manifest": str(args.manifest),
                "source_sha256": report["source"]["sha256"],
                "destination_sha256": report["destination"]["sha256"],
                "size_bytes": report["destination"]["size_bytes"],
            },
        )
        case.jobs.complete(job.job_id)
        case.audit.append(
            "evidence.export.finished",
            {
                **details,
                "job_id": job.job_id,
                "source_sha256": report["source"]["sha256"],
                "destination_sha256": report["destination"]["sha256"],
                "size_bytes": report["destination"]["size_bytes"],
            },
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print("Export complete")
    print()
    print(f"Artifact     {args.out.name}")
    print(f"Profile      {args.profile.title()}")
    print("Integrity    Verified")
    print(f"Manifest     {args.manifest.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
