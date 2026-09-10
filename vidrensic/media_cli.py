from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic.media.inventory import inspect_media


def _seconds(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected seconds") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("seconds must be positive")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic media",
        description="Inspect and record the forensic inventory of a recovered media artifact.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--qc", choices=("none", "fast", "full"), default="none")
    parser.add_argument("--expected-duration", type=_seconds)
    parser.add_argument("--timeout", type=_seconds)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = inspect_media(
            args.source,
            qc_mode=args.qc,
            expected_duration=args.expected_duration,
            full_decode_timeout=args.timeout,
        )
        output = report.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to inspect media: {exc}", file=sys.stderr)
        return 2

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
