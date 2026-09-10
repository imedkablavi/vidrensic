from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic.core.case import Case
from vidrensic.media.decoder_regions import analyze_decoder_error_regions
from vidrensic.media.inventory import inspect_media
from vidrensic.media.timeline import analyze_media_timeline


def _seconds(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected seconds") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("seconds must be positive")
    return result


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("integer must be positive")
    return result


def _duration(value: float | None) -> str:
    if value is None:
        return "Unknown"
    total = max(0, round(value))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _fps(value: float | None) -> str:
    return "Unknown" if value is None else f"{value:.3g} fps"


def _timeline_exit_code(report) -> int:
    if report.truncated:
        return 3
    if report.pts_non_monotonic or report.dts_non_monotonic or report.duplicate_pts or report.large_gaps:
        return 3
    if report.duration_confidence == "Low":
        return 3
    return 0


def _decoder_regions_exit_code(report) -> int:
    if report.failed_window_count or not report.sampling_complete:
        return 3
    return 0


def _run_decoder_regions(args, case: Case | None) -> int:
    details = {
        "source": str(args.source),
        "output": str(args.out),
        "window_seconds": args.window_seconds,
        "max_windows": args.max_windows,
        "timeout": args.timeout,
    }
    job = None
    if case:
        job = case.jobs.create("media.decoder-errors", details)
        case.jobs.start(job.job_id)
        case.audit.append(
            "media.decoder-errors.started",
            {**details, "job_id": job.job_id},
            actor=case.examiner,
        )

    try:
        report = analyze_decoder_error_regions(
            args.source,
            window_seconds=args.window_seconds,
            max_windows=args.max_windows,
            timeout_per_window=args.timeout if args.timeout is not None else 20.0,
        )
        output = report.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.decoder-errors.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to analyze decoder errors: {exc}", file=sys.stderr)
        return 2

    checkpoint = {
        "report": str(output),
        "sha256": report.sha256,
        "sha512": report.sha512,
        "window_count": report.window_count,
        "failed_window_count": report.failed_window_count,
        "coverage_fraction": report.coverage_fraction,
        "sampling_complete": report.sampling_complete,
        "region_count": len(report.regions),
    }
    if case and job:
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.decoder-errors.finished",
            {**details, "job_id": job.job_id, **checkpoint},
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return _decoder_regions_exit_code(report)

    print("Decoder error analysis complete")
    print()
    print(f"Artifact     {report.artifact.name}")
    print(f"Duration     {_duration(report.duration_seconds)}")
    print(f"Windows      {report.window_count:,}")
    print(f"Failed       {report.failed_window_count:,}")
    print(f"Coverage     {report.coverage_fraction:.1%}")
    print(f"Regions      {len(report.regions):,}")
    print(f"Assessment   {('Review required' if report.failed_window_count or not report.sampling_complete else 'No sampled errors')}")
    if report.regions:
        print()
        print("Suspect regions")
        for region in report.regions[:20]:
            print(
                f"  {_duration(region.start_seconds)} – {_duration(region.end_seconds)}"
                f"  ({region.failed_windows} failed windows)"
            )
        if len(report.regions) > 20:
            print(f"  … and {len(report.regions) - 20} more")
    print(f"Report       {output.expanduser().resolve()}")
    return _decoder_regions_exit_code(report)


def _run_timeline(args, case: Case | None) -> int:
    details = {
        "source": str(args.source),
        "output": str(args.out),
        "timeout": args.timeout,
    }
    job = None
    if case:
        job = case.jobs.create("media.timeline", details)
        case.jobs.start(job.job_id)
        case.audit.append("media.timeline.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = analyze_media_timeline(
            args.source,
            timeout=args.timeout if args.timeout is not None else 1800.0,
        )
        output = report.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.timeline.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to analyze timeline: {exc}", file=sys.stderr)
        return 2

    if case and job:
        checkpoint = {
            "report": str(output),
            "sha256": report.sha256,
            "sha512": report.sha512,
            "frame_count": report.frame_count,
            "keyframe_count": report.keyframe_count,
            "pts_non_monotonic": report.pts_non_monotonic,
            "dts_non_monotonic": report.dts_non_monotonic,
            "duplicate_pts": report.duplicate_pts,
            "large_gaps": report.large_gaps,
            "truncated": report.truncated,
            "duration_seconds": report.duration_seconds,
            "observed_duration_seconds": report.observed_duration_seconds,
            "duration_delta_seconds": report.duration_delta_seconds,
            "duration_confidence": report.duration_confidence,
        }
        case.jobs.checkpoint(job.job_id, checkpoint)
        case.jobs.complete(job.job_id)
        case.audit.append("media.timeline.finished", {**details, "job_id": job.job_id, **checkpoint}, actor=case.examiner)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return _timeline_exit_code(report)

    print("Timeline analysis complete")
    print()
    print(f"Artifact     {report.artifact.name}")
    print(f"Duration     {_duration(report.duration_seconds)} nominal")
    print(f"Observed     {_duration(report.observed_duration_seconds)} from frame timestamps")
    print(f"Duration QC  {report.duration_confidence}")
    print(f"Frames       {report.frame_count:,}")
    print(f"Keyframes    {report.keyframe_count:,}")
    print(f"Frame rate   {_fps(report.inferred_frame_rate)}")
    print(f"Timing       {('Stable' if not (report.pts_non_monotonic or report.dts_non_monotonic or report.duplicate_pts or report.large_gaps) else 'Review required')}")
    if report.truncated:
        print("Coverage     Analysis limit reached")
    else:
        print("Coverage     Complete")
    print(f"Report       {output.expanduser().resolve()}")
    return _timeline_exit_code(report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic media",
        description="Inspect and record the forensic inventory of a recovered media artifact.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qc", choices=("none", "fast", "full"), default="none")
    parser.add_argument("--timeline", action="store_true", help="analyze frame timing and keyframes")
    parser.add_argument("--decoder-errors", action="store_true", help="map sampled decoder-error regions")
    parser.add_argument("--window-seconds", type=_seconds, default=4.0, help="decoder-error window size")
    parser.add_argument("--max-windows", type=_positive_int, default=512, help="maximum decoder-error windows")
    parser.add_argument("--expected-duration", type=_seconds)
    parser.add_argument("--timeout", type=_seconds)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--case", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.timeline and args.qc != "none":
        parser.error("--timeline cannot be combined with --qc")
    if args.decoder_errors and args.qc != "none":
        parser.error("--decoder-errors cannot be combined with --qc")
    if args.timeline and args.decoder_errors:
        parser.error("--timeline and --decoder-errors are separate analysis modes")
    if args.decoder_errors and args.expected_duration is not None:
        parser.error("--expected-duration is only valid with --qc")

    case = Case.load(args.case) if args.case else None
    if args.decoder_errors:
        return _run_decoder_regions(args, case)
    if args.timeline:
        return _run_timeline(args, case)

    details = {
        "source": str(args.source),
        "output": str(args.out),
        "qc": args.qc,
        "expected_duration": args.expected_duration,
        "timeout": args.timeout,
    }
    job = None
    if case:
        job = case.jobs.create("media.inventory", details)
        case.jobs.start(job.job_id)
        case.audit.append("media.inventory.started", {**details, "job_id": job.job_id}, actor=case.examiner)

    try:
        report = inspect_media(
            args.source,
            qc_mode=args.qc,
            expected_duration=args.expected_duration,
            full_decode_timeout=args.timeout,
        )
        output = report.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        if case and job:
            case.jobs.fail(job.job_id, f"{type(exc).__name__}: {exc}")
            case.audit.append(
                "media.inventory.failed",
                {**details, "job_id": job.job_id, "error": f"{type(exc).__name__}: {exc}"},
                actor=case.examiner,
            )
        print(f"Unable to inspect media: {exc}", file=sys.stderr)
        return 2

    if case and job:
        case.jobs.checkpoint(
            job.job_id,
            {
                "report": str(output),
                "sha256": report.sha256,
                "sha512": report.sha512,
                "size_bytes": report.size_bytes,
                "qc_status": None if report.qc is None else report.qc["status"],
            },
        )
        case.jobs.complete(job.job_id)
        case.audit.append(
            "media.inventory.finished",
            {
                **details,
                "job_id": job.job_id,
                "report": str(output),
                "sha256": report.sha256,
                "sha512": report.sha512,
                "size_bytes": report.size_bytes,
                "qc_status": None if report.qc is None else report.qc["status"],
            },
            actor=case.examiner,
        )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return _exit_code(report)

    print("Media inspection complete")
    print()
    print(f"Artifact     {report.artifact.name}")
    print(f"Duration     {_duration(report.duration_seconds)}")
    print(f"Video        {report.video_codec or 'No video stream'}")
    if report.width is not None and report.height is not None:
        print(f"Resolution   {report.width} × {report.height}")
    print(f"Frame rate   {_fps(report.avg_frame_rate)}")
    print(f"Streams      {report.stream_count}")
    print("Integrity    Stable during inspection")

    if report.qc is None:
        print("Assessment   Inventory recorded")
    else:
        status = report.qc["status"]
        user_status = {
            "PASS": "Ready",
            "REVIEW": "Review required",
            "FAIL": "Check media",
            "UNKNOWN": "Review required",
        }.get(status, "Review required")
        print(f"Assessment   {user_status}")

    print(f"Report       {output.expanduser().resolve()}")
    return _exit_code(report)


def _exit_code(report) -> int:
    if report.video_codec is None:
        return 3
    if report.qc is not None and report.qc["status"] == "FAIL":
        return 3
    if report.qc is not None and report.qc["status"] in {"REVIEW", "UNKNOWN"}:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
