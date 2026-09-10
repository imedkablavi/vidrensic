from __future__ import annotations

from pathlib import Path
import math

import pytest

from vidrensic.core.case import Case
from vidrensic.core.review import ReviewState


SHA = "a" * 64


def _case(tmp_path: Path) -> Case:
    return Case.create(tmp_path, "CASE-REVIEW", examiner="examiner")


def _artifact(case: Case) -> Path:
    artifact = case.root / "derived" / "review" / "clip.mp4"
    artifact.write_bytes(b"derived-media")
    return artifact


def test_review_store_registers_and_updates_item(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)

    item = case.review.register_item(
        artifact,
        SHA,
        kind="review-proxy",
        duration_seconds=12.5,
    )
    assert item.state == ReviewState.REVIEW
    assert item.artifact == artifact.resolve()
    assert item.artifact_sha256 == SHA

    kept = case.review.set_state(item.item_id, state=ReviewState.KEEP, expected_sha256=SHA)
    noted = case.review.set_note(item.item_id, note="Important segment", expected_sha256=SHA)

    assert kept.state == ReviewState.KEEP
    assert noted.note == "Important segment"
    assert case.review.list_items(state=ReviewState.KEEP)[0].item_id == item.item_id


def test_review_store_bookmark_round_trip(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA, duration_seconds=10.0)

    bookmark = case.review.add_bookmark(
        item.item_id,
        timestamp_seconds=3.25,
        expected_sha256=SHA,
        label="door",
        note="Person enters frame",
    )
    bookmarks = case.review.list_bookmarks(item.item_id)

    assert bookmark.item_id == item.item_id
    assert bookmarks[0].timestamp_seconds == pytest.approx(3.25)
    assert bookmarks[0].label == "door"
    assert bookmarks[0].note == "Person enters frame"


def test_review_store_requires_current_artifact_hash(tmp_path: Path) -> None:
    case = _case(tmp_path)
    item = case.review.register_item(_artifact(case), SHA, duration_seconds=5.0)

    with pytest.raises(ValueError, match="SHA-256"):
        case.review.set_state(item.item_id, state=ReviewState.KEEP, expected_sha256="b" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        case.review.set_note(item.item_id, note="stale", expected_sha256="b" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=1.0, expected_sha256="b" * 64)


def test_review_store_rejects_invalid_artifact_locations(tmp_path: Path) -> None:
    case = _case(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="inside the case root"):
        case.review.register_item(outside, SHA)

    target = _artifact(case)
    link = case.root / "derived" / "review" / "link.mp4"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        case.review.register_item(link, SHA)


def test_review_store_rejects_bad_times_and_nonfinite_values(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    with pytest.raises(ValueError):
        case.review.register_item(artifact, SHA, duration_seconds=math.nan)
    with pytest.raises(ValueError):
        case.review.register_item(artifact, SHA, duration_seconds=math.inf)

    item = case.review.register_item(artifact, SHA, duration_seconds=5.0)
    with pytest.raises(ValueError, match="duration"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=6.0, expected_sha256=SHA)
    with pytest.raises(ValueError, match="finite"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=math.nan, expected_sha256=SHA)
    with pytest.raises(ValueError, match="finite"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=math.inf, expected_sha256=SHA)


def test_review_store_writes_audit_events(tmp_path: Path) -> None:
    case = _case(tmp_path)
    item = case.review.register_item(_artifact(case), SHA, duration_seconds=5.0)
    case.review.set_state(item.item_id, state=ReviewState.KEEP, expected_sha256=SHA)
    case.review.set_note(item.item_id, note="check", expected_sha256=SHA)
    case.review.add_bookmark(item.item_id, timestamp_seconds=1.0, expected_sha256=SHA)

    valid, tail = case.audit.verify()
    text = (case.root / "logs" / "audit.jsonl").read_text(encoding="utf-8")

    assert valid is True
    assert len(tail) == 64
    assert "review.item.registered" in text
    assert "review.item.state_changed" in text
    assert "review.item.note_changed" in text
    assert "review.bookmark.created" in text
