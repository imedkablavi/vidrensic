from pathlib import Path
import math

import pytest

from vidrensic.core.case import Case
from vidrensic.core.review import ReviewState
import vidrensic.core.review as review_module


SHA256 = "a" * 64


def _case(tmp_path: Path) -> Case:
    return Case.create(tmp_path, "case-review", examiner="examiner")


def _artifact(case: Case, name: str = "clip.mp4") -> Path:
    path = case.root / "derived" / "review" / name
    path.write_bytes(b"video")
    return path


def test_case_review_persists_state_note_bookmark_and_audits(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)

    item = case.review.register_item(
        artifact,
        SHA256,
        kind="review-proxy",
        duration_seconds=12.5,
    )
    assert item.state is ReviewState.REVIEW
    assert item.duration_seconds == 12.5

    case.review.set_state(item.item_id, state=ReviewState.KEEP, expected_sha256=SHA256)
    case.review.set_note(item.item_id, note="Person enters frame", expected_sha256=SHA256)
    bookmark = case.review.add_bookmark(
        item.item_id,
        timestamp_seconds=4.25,
        expected_sha256=SHA256,
        label="entry",
        note="Primary event",
    )

    reopened = Case.load(case.root)
    stored = reopened.review.get_item(item.item_id)
    assert stored.state is ReviewState.KEEP
    assert stored.note == "Person enters frame"
    assert reopened.review.list_bookmarks(item.item_id)[0].bookmark_id == bookmark.bookmark_id

    ok, _ = reopened.audit.verify()
    assert ok


def test_review_rejects_sha_mismatch_and_outside_case(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)
    item = case.review.register_item(artifact, SHA256, duration_seconds=10)

    with pytest.raises(ValueError, match="SHA-256"):
        case.review.set_state(item.item_id, state=ReviewState.KEEP, expected_sha256="b" * 64)

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="inside the case root"):
        case.review.register_item(outside, SHA256)


def test_review_rejects_non_finite_values(tmp_path: Path) -> None:
    case = _case(tmp_path)
    artifact = _artifact(case)

    with pytest.raises(ValueError, match="finite"):
        case.review.register_item(artifact, SHA256, duration_seconds=math.inf)

    item = case.review.register_item(artifact, SHA256, duration_seconds=10)
    with pytest.raises(ValueError, match="finite"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=math.nan, expected_sha256=SHA256)


def test_review_item_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case(tmp_path)
    monkeypatch.setattr(review_module, "MAX_ITEMS", 1)

    case.review.register_item(_artifact(case), SHA256)
    second = _artifact(case, "second.mp4")
    with pytest.raises(ValueError, match="item limit"):
        case.review.register_item(second, "b" * 64)


def test_review_bookmark_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    case = _case(tmp_path)
    monkeypatch.setattr(review_module, "MAX_BOOKMARKS", 1)
    item = case.review.register_item(_artifact(case), SHA256, duration_seconds=30)

    case.review.add_bookmark(item.item_id, timestamp_seconds=1, expected_sha256=SHA256)
    with pytest.raises(ValueError, match="bookmark limit"):
        case.review.add_bookmark(item.item_id, timestamp_seconds=2, expected_sha256=SHA256)
