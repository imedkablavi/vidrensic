from pathlib import Path

import pytest

from vidrensic.core.candidate_metadata import CandidateMetadataError
from vidrensic.core.case import Case
from vidrensic.core.hashing import forensic_hashes_stable


def _case(tmp_path: Path) -> tuple[Case, str]:
    case = Case.create(tmp_path, "CASE-META", examiner="examiner")
    artifact = case.root / "derived" / "review" / "candidate.mp4"
    artifact.write_bytes(b"candidate")
    item = case.review.register_item(
        artifact,
        forensic_hashes_stable(artifact).sha256,
        kind="media",
        duration_seconds=12.0,
    )
    return case, item.item_id


def test_evidence_backed_recording_time_requires_source(tmp_path: Path) -> None:
    case, item_id = _case(tmp_path)
    item = case.review.get_item(item_id)

    with pytest.raises(CandidateMetadataError, match="requires source_path"):
        case.candidate_metadata.set_claim(
            item_id,
            item.artifact_sha256,
            field="recording_start_utc",
            value="2026-09-10T10:00:00Z",
            source_kind="native-metadata",
        )


def test_metadata_source_hash_is_verified(tmp_path: Path) -> None:
    case, item_id = _case(tmp_path)
    item = case.review.get_item(item_id)
    source = case.root / "reports" / "native.json"
    source.write_text('{"recording_start_utc":"2026-09-10T10:00:00Z"}\n', encoding="utf-8")
    wrong_sha = "0" * 64

    with pytest.raises(CandidateMetadataError, match="does not match the file"):
        case.candidate_metadata.set_claim(
            item_id,
            item.artifact_sha256,
            field="recording_start_utc",
            value="2026-09-10T10:00:00Z",
            source_kind="native-metadata",
            source_path=source,
            source_sha256=wrong_sha,
        )


def test_metadata_round_trips_with_provenance(tmp_path: Path) -> None:
    case, item_id = _case(tmp_path)
    item = case.review.get_item(item_id)
    source = case.root / "reports" / "native.json"
    source.write_text('{"camera_slot":"04"}\n', encoding="utf-8")
    source_sha = forensic_hashes_stable(source).sha256

    claim = case.candidate_metadata.set_claim(
        item_id,
        item.artifact_sha256,
        field="camera_slot",
        value="04",
        source_kind="native-metadata",
        source_path=source,
        source_sha256=source_sha,
        evidence_pointer="/camera_slot",
        confidence=0.92,
    )

    metadata = case.candidate_metadata.get(item_id, item.artifact_sha256)
    assert metadata.values()["camera_slot"] == "04"
    assert metadata.to_dict()["evidence_backed"] is True
    assert metadata.claims[0].claim_id == claim.claim_id
    assert metadata.claims[0].source_sha256 == source_sha
    assert metadata.claims[0].evidence_pointer == "/camera_slot"


def test_operator_observation_is_not_evidence_backed(tmp_path: Path) -> None:
    case, item_id = _case(tmp_path)
    item = case.review.get_item(item_id)

    case.candidate_metadata.set_claim(
        item_id,
        item.artifact_sha256,
        field="camera_slot",
        value="04",
        source_kind="operator-observation",
        confidence=0.5,
    )

    metadata = case.candidate_metadata.get(item_id, item.artifact_sha256)
    assert metadata.to_dict()["evidence_backed"] is False
