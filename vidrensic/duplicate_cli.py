from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.media.duplicates import (
    DEFAULT_FRAME_MATCH_THRESHOLD,
    DEFAULT_SAMPLE_COUNT,
    DEFAULT_SIMILARITY_THRESHOLD,
    DuplicateAnalysisError,
    analyze_media_set,
)


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("integer must be positive")
    return result


def _threshold(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected decimal threshold") from exc
    if not 0 < result <= 1:
        raise argparse.ArgumentTypeError("threshold must be in (0, 1]")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-duplicates",
        description="Find exact and visually near-duplicate video candidates.",
    )
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--samples", type=_positive_int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--threshold", type=_threshold, default=DEFAULT_SIMILARITY_THRESHOLD)
    parser.add_argument(
        "--frame-threshold",
        type=_threshold,
        default=DEFAULT_FRAME_MATCH_THRESHOLD,
        help="per-frame similarity needed to count as matched",
    )
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.out.exists() or args.out.is_symlink():
        parser.error(f"output already exists: {args.out}")

    case = Case.load(args.case) if args.case else None
    details = {
        "sources": [str(path) for path in args.sources],
        "output": str(args.out),
        "samples": args.samples,
        "threshold": args.threshold,
        "frame_threshold": args.frame_threshold,
    }
    job = None
    if case:
        job = case.jobs.create("media.duplicate-analysis", details)
        case.jobs.start(job.job_id)
        case.audit.append(
            "media.duplicate-analysis.started",
            {**details, "job_id": job.job_id},
            actor=case.examiner,
        )

    try:
        report = analyze_media_set(
            args.sources,
            sample_count=args.samples,
            similarity_threshold=args.threshold,
            frame_match_threshold=args.frame_threshold,
        )
        report.write_json(args.out)
    except (OSError, RuntimeError, ValueError, DuplicateAnalysisError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.duplicate-analysis.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        if args.out.exists() and not args.out.is_symlink():
            try:
                args.out.unlink()
            except OSError:
                pass
        print(f"Unable to analyze duplicates: {exc}", file=sys.stderr)
        return 2

    classifications = {}
    for comparison in report.comparisons:
        classifications[comparison.classification] = classifications.get(comparison.classification, 0) + 1
    checkpoint = {
        "report": str(args.out),
        "source_count": len(report.sources),
        "comparison_count": len(report.comparisons),
        "classifications": classifications,
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.duplicate-analysis.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Duplicate analysis complete")
    print()
    print(f"Sources      {len(report.sources)}")
    print(f"Comparisons  {len(report.comparisons)}")
    for classification in ("EXACT", "NEAR_DUPLICATE_CANDIDATE", "DISTINCT", "REVIEW"):
        print(f"{classification:<26} {classifications.get(classification, 0)}")
    print(f"Report       {args.out.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
