from pathlib import Path

from vidrensic.core.candidate_metadata import CandidateMetadata, MetadataClaim
from vidrensic.core.candidate_metadata_projection import project_candidate_metadata


def _claim(*, field: str, value: str, evidence: bool, source: str) -> MetadataClaim:
    return MetadataClaim(
        claim_id=source,
        item_id="item-1",
        artifact_sha256="a" * 64,
        field=field,
        value=value,
        source_kind="native-metadata" if evidence else "operator-observation",
        source_path=Path(f"/case/reports/{source}.json") if evidence else None,
        source_sha256="b" * 64 if evidence else None,
        evidence_pointer=f"/{field}",
        confidence=0.9,
        created_utc="2026-09-10T10:00:00+00:00",
    )


def test_projection_marks_conflicting_field_ambiguous() -> None:
    metadata = CandidateMetadata(
        item_id="item-1",
        artifact_sha256="a" * 64,
        claims=(
            _claim(field="camera_slot", value="01", evidence=True, source="a"),
            _claim(field="camera_slot", value="02", evidence=True, source="b"),
            _claim(field="recording_start_utc", value="2026-09-10T10:00:00Z", evidence=True, source="c"),
        ),
    )

    projected = project_candidate_metadata(metadata)

    assert projected["fields"]["camera_slot"]["ambiguous"] is True
    assert projected["fields"]["camera_slot"]["value"] is None
    assert projected["fields"]["camera_slot"]["evidence_backed"] is False
    assert projected["fields"]["recording_start_utc"]["evidence_backed"] is True
    assert projected["recording_start_utc"] == "2026-09-10T10:00:00Z"


def test_projection_accepts_matching_evidence_claims() -> None:
    metadata = CandidateMetadata(
        item_id="item-1",
        artifact_sha256="a" * 64,
        claims=(
            _claim(field="camera_slot", value="04", evidence=True, source="a"),
            _claim(field="camera_slot", value="04", evidence=True, source="b"),
        ),
    )

    projected = project_candidate_metadata(metadata)

    assert projected["fields"]["camera_slot"]["ambiguous"] is False
    assert projected["fields"]["camera_slot"]["value"] == "04"
    assert projected["fields"]["camera_slot"]["evidence_backed"] is True
