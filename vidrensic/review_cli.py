from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.core.review import ReviewState
from vidrensic.media.review_timeline import ReviewTimelineError, build_review_timeline


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected integer") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("integer must be positive")
    return result


def _nonnegative_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected seconds") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("seconds cannot be negative")
    return result


def _sha256(value: str) -> str:
    if len(value) != 64:
        raise argparse.ArgumentTypeError("SHA-256 must be 64 hexadecimal characters")
    try:
        int(value, 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("SHA-256 must be hexadecimal") from exc
    return value.lower()


def _state(value: str) -> ReviewState:
    try:
        return ReviewState(value.upper())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("state must be REVIEW, KEEP or DISCARD") from exc


def _print_item(item) -> None:
    duration = "-" if item.duration_seconds is None else f"{item.duration_seconds:.3f}s"
    print(f"{item.item_id}  {item.state.value:<7}  {item.kind:<16}  {duration:<12}  {item.artifact}")
    if item.note:
        print(f"  note: {item.note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-review",
        description="Manage auditable analyst review state, notes and bookmarks.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list review items")
    list_parser.add_argument("--case", type=Path, required=True)
    list_parser.add_argument("--state", type=_state)
    list_parser.add_argument("--limit", type=_positive_int, default=100)
    list_parser.add_argument("--json", action="store_true")

    timeline_parser = subparsers.add_parser("timeline", help="build a normalized review timeline contract")
    timeline_parser.add_argument("--case", type=Path, required=True)
    timeline_parser.add_argument("--item", required=True)
    timeline_parser.add_argument("--timeline-report", type=Path, required=True)
    timeline_parser.add_argument("--decoder-report", type=Path)
    timeline_parser.add_argument("--out", type=Path, required=True)
    timeline_parser.add_argument("--replace", action="store_true")
    timeline_parser.add_argument("--json", action="store_true")

    state_parser = subparsers.add_parser("set-state", help="set KEEP/REVIEW/DISCARD state")
    state_parser.add_argument("--case", type=Path, required=True)
    state_parser.add_argument("--item", required=True)
    state_parser.add_argument("--sha256", type=_sha256, required=True)
    state_parser.add_argument("--state", type=_state, required=True)

    note_parser = subparsers.add_parser("note", help="set analyst note")
    note_parser.add_argument("--case", type=Path, required=True)
    note_parser.add_argument("--item", required=True)
    note_parser.add_argument("--sha256", type=_sha256, required=True)
    note_parser.add_argument("--text", required=True)

    bookmark_parser = subparsers.add_parser("bookmark", help="add timestamp bookmark")
    bookmark_parser.add_argument("--case", type=Path, required=True)
    bookmark_parser.add_argument("--item", required=True)
    bookmark_parser.add_argument("--sha256", type=_sha256, required=True)
    bookmark_parser.add_argument("--time", type=_nonnegative_float, required=True)
    bookmark_parser.add_argument("--label", default="")
    bookmark_parser.add_argument("--note", default="")

    args = parser.parse_args(argv)
    try:
        case = Case.load(args.case)
        if args.command == "list":
            items = case.review.list_items(state=args.state, limit=args.limit)
            if args.json:
                print(json.dumps([item.to_dict() for item in items], indent=2, sort_keys=True))
            else:
                print("Review items")
                print()
                for item in items:
                    _print_item(item)
            return 0

        if args.command == "timeline":
            contract = build_review_timeline(
                case,
                args.item,
                args.timeline_report,
                decoder_report_path=args.decoder_report,
            )
            output = contract.write_json(args.out, replace=args.replace)
            if args.json:
                print(json.dumps(contract.to_dict(), indent=2, sort_keys=True))
            else:
                print("Review timeline created")
                print()
                print(f"Artifact     {contract.media['artifact']}")
                print(f"State        {contract.item['state']}")
                print(f"Bookmarks    {len(contract.bookmarks):,}")
                print(
                    f"Decoder QC   {('Included' if contract.decoder_errors is not None else 'Not included')}"
                )
                print("Hash binding Yes")
                print(f"Output       {output.expanduser().resolve()}")
            return 0

        if args.command == "set-state":
            item = case.review.set_state(
                args.item,
                state=args.state,
                expected_sha256=args.sha256,
            )
            print(f"State updated: {item.state.value}")
            return 0

        if args.command == "note":
            case.review.set_note(args.item, note=args.text, expected_sha256=args.sha256)
            print("Note updated")
            return 0

        bookmark = case.review.add_bookmark(
            args.item,
            timestamp_seconds=args.time,
            expected_sha256=args.sha256,
            label=args.label,
            note=args.note,
        )
        print(f"Bookmark created: {bookmark.bookmark_id} @ {bookmark.timestamp_seconds:.3f}s")
        return 0
    except (OSError, RuntimeError, ReviewTimelineError, ValueError, KeyError) as exc:
        print(f"Unable to update review state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
