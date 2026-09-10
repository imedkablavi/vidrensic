from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.core.models import EvidenceStatus
from vidrensic.media.forensic_scan_engine import (
    _analyze_inventory,
    _build_evidence_intervals,
    _confidence_assessment,
    _derive_status,
    run_forensic_scan,
)
from vidrensic.media.inventory import MediaInventoryReport, MediaStreamInventory


_HASHES = SimpleNamespace(sha256="a" * 64, sha512="b" * 128)


def _inventory(*, avg: float = 25.0, real: float = 25.0, qc_status: str = "PASS") -> MediaInventoryReport:
    return MediaInventoryReport(
        artifact=Path("candidate.mp4"),
        size_bytes=1234,
        sha256="a" * 64,
        sha512="b" * 128,
        duration_seconds=12.0,
        video_codec="h264",
        width=1920,
        height=1080,
        avg_frame_rate=avg,
        r_frame_rate=real,
        stream_count=1,
        streams=(
            MediaStreamInventory(
                index=0,
                codec_type="video",
                codec="h264",
                width=1920,
                height=1080,
                avg_frame_rate=avg,
                r_frame_rate=real,
            ),
        ),
        qc={"mode": "full-decode", "status": qc_status, "reasons": [], "measurements": {}},
    )


def test_inventory_flags_material_frame_rate_disagreement() -> None:
    findings = []
    _analyze_inventory(_inventory(avg=25.0, real=30.0), findings)
    assert any(item.code == "FRAME_RATE_DISAGREEMENT" for item in findings)


def test_deep_clean_evidence_can_pass() -> None:
    findings = []
    timeline = {
        "truncated": False,
        "pts_non_monotonic": 0,
        "dts_non_monotonic": 0,
        "duplicate_pts": 0,
        "large_gaps": 0,
    }
    assert _derive_status(
        findings,
        profile="deep",
        qc={"status": "PASS"},
        timeline=timeline,
        decoder_regions=None,
        hash_stable=True,
    ) is EvidenceStatus.PASS


def test_deep_requires_expected_duration_at_entrypoint(tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"video")
    with pytest.raises(ValueError, match="requires expected_duration"):
        run_forensic_scan(artifact, profile="deep")


def test_deep_never_passes_without_complete_timeline() -> None:
    findings = []
    assert _derive_status(
        findings,
        profile="deep",
        qc={"status": "PASS"},
        timeline={"truncated": True},
        decoder_regions=None,
        hash_stable=True,
    ) is EvidenceStatus.REVIEW


def test_scan_fails_when_artifact_changes(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"video")
    inventory = _inventory(qc_status="PASS")

    monkeypatch.setattr(
        "vidrensic.media.forensic_scan_engine.inspect_media",
        lambda *args, **kwargs: inventory,
    )

    mutated = SimpleNamespace(sha256="c" * 64, sha512="d" * 128)
    calls = iter((_HASHES, mutated))
    monkeypatch.setattr(
        "vidrensic.media.forensic_scan_engine.forensic_hashes_stable",
        lambda path: next(calls),
    )

    report = run_forensic_scan(artifact, profile="quick")
    assert report.status is EvidenceStatus.FAIL
    assert any(item.code == "ARTIFACT_CHANGED_DURING_SCAN" for item in report.findings)


def test_standard_scan_records_timeline_anomaly(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"video")
    inventory = _inventory(qc_status="REVIEW")
    timeline = SimpleNamespace(
        truncated=False,
        pts_non_monotonic=2,
        dts_non_monotonic=0,
        duplicate_pts=0,
        large_gaps=1,
        duration_delta_seconds=0.2,
        anomalies=(
            SimpleNamespace(frame=12, kind="pts-backwards", previous=10.0, current=9.5, delta=-0.5),
            SimpleNamespace(frame=14, kind="large-gap", previous=None, current=None, delta=3.0),
        ),
        to_dict=lambda: {
            "timeline": {
                "truncated": False,
                "pts_non_monotonic": 2,
                "dts_non_monotonic": 0,
                "duplicate_pts": 0,
                "large_gaps": 1,
            }
        },
    )
    monkeypatch.setattr(
        "vidrensic.media.forensic_scan_engine.forensic_hashes_stable",
        lambda path: _HASHES,
    )
    monkeypatch.setattr(
        "vidrensic.media.forensic_scan_engine.inspect_media",
        lambda *args, **kwargs: inventory,
    )
    monkeypatch.setattr(
        "vidrensic.media.forensic_scan_engine.analyze_media_timeline",
        lambda *args, **kwargs: timeline,
    )

    report = run_forensic_scan(artifact, profile="standard")
    assert report.status is EvidenceStatus.REVIEW
    codes = {item.code for item in report.findings}
    assert "MEDIA_QC_INCOMPLETE" in codes
    assert "PTS_NON_MONOTONIC" in codes
    assert "LARGE_TIMESTAMP_GAPS" in codes
    assert report.timeline["pts_non_monotonic"] == 2
    assert len(report.evidence_intervals) == 2
    assert report.evidence_intervals[0].start_seconds == 9.5
    assert report.evidence_intervals[0].end_seconds == 10.0
    assert report.evidence_intervals[0].confidence == "High"


def test_decoder_regions_become_intervals() -> None:
    timeline = None
    decoder = SimpleNamespace(
        regions=(
            SimpleNamespace(start_seconds=20.0, end_seconds=24.0),
        ),
    )
    intervals = _build_evidence_intervals(timeline, decoder)
    assert len(intervals) == 1
    assert intervals[0].source == "decoder"
    assert intervals[0].code == "DECODER_ERROR_REGION"
    assert intervals[0].start_seconds == 20.0
    assert intervals[0].end_seconds == 24.0
    assert intervals[0].confidence == "Moderate"


def test_deep_clean_evidence_has_high_confidence() -> None:
    level, basis = _confidence_assessment(
        profile="deep",
        qc={"status": "PASS"},
        timeline={"truncated": False},
        findings=[],
        hash_stable=True,
    )
    assert level == "High"
    assert "artifact identity remained stable" in basis
    assert "no review/fail findings remain" in basis


def test_incomplete_evidence_has_lower_confidence() -> None:
    level, basis = _confidence_assessment(
        profile="standard",
        qc={"status": "REVIEW"},
        timeline={"truncated": True},
        findings=[],
        hash_stable=True,
    )
    assert level == "Low"
    assert "timeline evidence is missing or bounded/incomplete" in basis
