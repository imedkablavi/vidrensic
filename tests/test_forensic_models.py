from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from vidrensic.acquisition.mapfile import parse_mapfile
from vidrensic.core.doctor import run_doctor
from vidrensic.core.provenance import fingerprint_source, require_same_source
from vidrensic.core.timebase import ClockAnchor, NativeTimestampEvidence, fit_clock_model


def test_source_fingerprint_detects_regular_file_replacement(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"A" * 4096)
    first = fingerprint_source(source, edge_sample_bytes=512)
    second = fingerprint_source(source, edge_sample_bytes=512)
    require_same_source(first, second)

    source.write_bytes(b"B" * 4096)
    changed = fingerprint_source(source, edge_sample_bytes=512)
    with pytest.raises(RuntimeError):
        require_same_source(first, changed)


def test_native_timestamp_keeps_timezone_unknown_without_evidence() -> None:
    item = NativeTimestampEvidence(
        decoded_local=datetime(2026, 8, 9, 9, 0, 0),
        raw_value="0x12345678",
        source_kind="WFS packed timestamp",
    )
    data = item.to_dict()
    assert data["timezone_name"] is None
    assert data["classification"] == "NATIVE"


def test_clock_model_recovers_offset_and_drift_from_anchors() -> None:
    base_local = datetime(2026, 8, 9, 9, 0, 0)
    base_utc = datetime(2026, 8, 9, 7, 0, 10, tzinfo=UTC)
    # Recorder runs 100 ppm slow relative to reference: one recorder hour
    # corresponds to 3600.36 reference seconds.
    slope = 1.0001
    anchors = []
    for hours in (0, 1, 4, 8):
        local = base_local + timedelta(hours=hours)
        reference = base_utc + timedelta(seconds=hours * 3600 * slope)
        anchors.append(ClockAnchor(local, reference, f"anchor-{hours}"))

    model = fit_clock_model(anchors, residual_review_threshold_seconds=0.01)
    assert model.status == "PASS"
    assert model.drift_ppm == pytest.approx(100.0, abs=0.1)
    corrected = model.correct(base_local + timedelta(hours=2))
    expected = base_utc + timedelta(seconds=2 * 3600 * slope)
    assert abs((corrected - expected).total_seconds()) < 0.001


def test_single_clock_anchor_is_review_not_fake_drift_measurement() -> None:
    model = fit_clock_model(
        [
            ClockAnchor(
                datetime(2026, 8, 9, 9, 0, 0),
                datetime(2026, 8, 9, 7, 0, 5, tzinfo=UTC),
                "phone-video-visible-clock",
            )
        ]
    )
    assert model.status == "REVIEW"
    assert model.drift_ppm == 0.0


def test_ddrescue_map_parser_tracks_expected_completion(tmp_path: Path) -> None:
    mapfile = tmp_path / "image.map"
    mapfile.write_text(
        """# Mapfile. Created by GNU ddrescue
# current_pos current_status current_pass
0x00002000 ? 1
# pos size status
0x00001000 0x00001000 +
0x00002000 0x00000800 +
0x00002800 0x00000800 -
""",
        encoding="utf-8",
    )
    summary = parse_mapfile(mapfile, expected_start=0x1000, expected_size=0x2000)
    assert summary.status_bytes["finished"] == 0x1800
    assert summary.status_bytes["bad_sector"] == 0x800
    assert summary.expected_covered_bytes == 0x2000
    assert summary.expected_finished_bytes == 0x1800
    assert summary.complete_for_expected_range is False


def test_doctor_report_is_serializable_and_explicit_about_capabilities() -> None:
    report = run_doctor()
    data = report.to_dict()
    assert data["product"] == "Vidrensic"
    assert "tools" in data
    assert "source-safety" in data["capabilities"]
    assert all("available" in item for item in data["tools"])
