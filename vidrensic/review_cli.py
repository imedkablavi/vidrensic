from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from vidrensic.core.case import Case
from vidrensic.core.candidate_metadata import CandidateMetadataError
from vidrensic.core.delete_plan import DeletionPlanError, create_deletion_plan, execute_deletion_plan
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


def _unit_float(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected number") from exc
    if not 0.0 <= result <= 1.0:
        raise argparse.ArgumentTypeError("value must be between 0 and 1")
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


def _case_owned_path(case: Case, path: Path) -> Path:
    candidate = path.expanduser()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(case.root)
    except ValueError as exc:
        raise ValueError("output path must be inside the case root") from exc
    return resolved


def _print_item(item) -> None:
    duration = "-" if item.duration_seconds is None else f"{item.duration_seconds:.3f}s"
    print(f"{item.item_id}  {item.state.value:<7}  {item.kind:<16}  {duration:<12}  {item.artifact}")
    if item.note:
        print(f"  note: {item.note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-review",
        description=(
            "Manage auditable analyst review state, candidate metadata provenance, "
            "bookmarks and safe derived deletion plans."
        ),
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

    metadata_set_parser = subparsers.add_parser(
        "metadata-set",
        help="set one provenance-backed candidate metadata claim",
    )
    metadata_set_parser.add_argument("--case", type=Path, required=True)
    metadata_set_parser.add_argument("--item", required=True)
    metadata_set_parser.add_argument("--sha256", type=_sha256, required=True)
    metadata_set_parser.add_argument(
        "--field",
        choices=(
            "recording_start_utc",
            "recording_end_utc",
            "camera_slot",
            "source_label",
            "format_family",
        ),
        required=True,
    )
    metadata_set_parser.add_argument("--value", required=True)
    metadata_set_parser.add_argument(
        "--source-kind",
        choices=(
            "native-metadata",
            "timeline-report",
            "reconstruction-manifest",
            "operator-observation",
        ),
        required=True,
    )
    metadata_set_parser.add_argument("--source-path", type=Path)
    metadata_set_parser.add_argument("--source-sha256", type=_sha256)
    metadata_set_parser.add_argument("--evidence-pointer")
    metadata_set_parser.add_argument("--confidence", type=_unit_float, default=1.0)
    metadata_set_parser.add_argument("--json", action="store_true")

    metadata_get_parser = subparsers.add_parser(
        "metadata-get",
        help="show candidate metadata claims and provenance",
    )
    metadata_get_parser.add_argument("--case", type=Path, required=True)
    metadata_get_parser.add_argument("--item", required=True)
    metadata_get_parser.add_argument("--sha256", type=_sha256, required=True)
    metadata_get_parser.add_argument("--json", action="store_true")

    deletion_plan_parser = subparsers.add_parser(
        "deletion-plan",
        help="create a hash-bound, non-destructive plan for derived/work files",
    )
    deletion_plan_parser.add_argument("--case", type=Path, required=True)
    deletion_plan_parser.add_argument("--path", type=Path, action="append", required=True)
    deletion_plan_parser.add_argument("--reason", required=True)
    deletion_plan_parser.add_argument("--out", type=Path, required=True)
    deletion_plan_parser.add_argument("--replace", action="store_true")
    deletion_plan_parser.add_argument("--json", action="store_true")

    deletion_execute_parser = subparsers.add_parser(
        "execute-deletion",
        help="explicitly execute a previously created deletion plan",
    )
    deletion_execute_parser.add_argument("--case", type=Path, required=True)
    deletion_execute_parser.add_argument("--plan", type=Path, required=True)
    deletion_execute_parser.add_argument("--tombstones", type=Path)
    deletion_execute_parser.add_argument(
        "--execute",
        action="store_true",
        help="required confirmation for deletion",
    )
    deletion_execute_parser.add_argument("--json", action="store_true")

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

        if args.command == "metadata-set":
            item = case.review.get_item(args.item)
            if item.artifact_sha256 != args.sha256:
                raise CandidateMetadataError("metadata artifact SHA-256 does not match the review item")
            claim = case.candidate_metadata.set_claim(
                args.item,
                args.sha256,
                field=args.field,
                value=args.value,
                source_kind=args.source_kind,
                source_path=args.source_path,
                source_sha256=args.source_sha256,
                evidence_pointer=args.evidence_pointer,
                confidence=args.confidence,
            )
            if args.json:
                print(json.dumps(claim.to_dict(), indent=2, sort_keys=True))
            else:
                print(f"Metadata claim recorded: {claim.field}={claim.value}")
                print(f"Source kind  {claim.source_kind}")
                print(f"Confidence   {claim.confidence:.3f}")
                print(f"Source SHA   {claim.source_sha256 or 'operator observation'}")
            return 0

        if args.command == "metadata-get":
            item = case.review.get_item(args.item)
            if item.artifact_sha256 != args.sha256:
                raise CandidateMetadataError("metadata artifact SHA-256 does not match the review item")
            metadata = case.candidate_metadata.get(args.item, args.sha256)
            if args.json:
                print(json.dumps(metadata.to_dict(), indent=2, sort_keys=True))
            else:
                print("Candidate metadata")
                print()
                for claim in metadata.claims:
                    print(
                        f"{claim.field} = {claim.value}  ({claim.source_kind}; "
                        f"confidence={claim.confidence:.3f})"
                    )
            return 0

        if args.command == "deletion-plan":
            output = _case_owned_path(case, args.out)
            plan = create_deletion_plan(
                case.root,
                args.path,
                actor=case.examiner,
                reason=args.reason,
            )
            output = plan.write_json(output, replace=args.replace)
            case.audit.append(
                "review.deletion-plan.created",
                {
                    "plan_id": plan.plan_id,
                    "targets": [
                        {"relative_path": target.relative_path, "sha256": target.sha256}
                        for target in plan.targets
                    ],
                    "reason": args.reason,
                },
                actor=case.examiner,
            )
            if args.json:
                print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
            else:
                print("Deletion plan created (no files deleted)")
                print()
                print(f"Plan ID      {plan.plan_id}")
                print(f"Targets      {len(plan.targets):,}")
                for target in plan.targets:
                    print(
                        f"  {target.relative_path}  {target.size_bytes:,} bytes  {target.sha256}"
                    )
                print(f"Output       {output}")
            return 0

        if args.command == "execute-deletion":
            if not args.execute:
                print("Refusing to delete files: pass --execute explicitly.", file=sys.stderr)
                return 2
            plan_path = _case_owned_path(case, args.plan)
            tombstone_path = None if args.tombstones is None else _case_owned_path(case, args.tombstones)
            results = execute_deletion_plan(
                case.root,
                plan_path,
                tombstone_path=tombstone_path,
                actor=case.examiner,
            )
            case.audit.append(
                "review.deletion-plan.executed",
                {
                    "plan": str(plan_path.relative_to(case.root)),
                    "tombstones": str(
                        (tombstone_path or (case.root / "state" / "deletion_tombstones.jsonl"))
                        .relative_to(case.root)
                    ),
                    "deleted_targets": [item["relative_path"] for item in results],
                },
                actor=case.examiner,
            )
            if args.json:
                print(json.dumps(results, indent=2, sort_keys=True))
            else:
                print(f"Deleted {len(results):,} derived/work files")
                for result in results:
                    print(f"  {result['relative_path']}  {result['expected_sha256']}")
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
    except (
        OSError,
        RuntimeError,
        CandidateMetadataError,
        DeletionPlanError,
        ReviewTimelineError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"Unable to update review state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
