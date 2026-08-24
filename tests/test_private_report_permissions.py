from __future__ import annotations

from pathlib import Path
import json
import os
import stat

import pytest

from vidrensic.acquisition.mapfile import MapBlock, MapSummary
from vidrensic.acquisition.receipt import AcquisitionReceipt
from vidrensic.acquisition.smart import SmartSnapshot
from vidrensic.core.models import EvidenceStatus, QCDecision
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.media.probe import VideoProbe
from vidrensic.media.qc import MediaQCReport
from vidrensic.plugins.wfs.layout import WFSLayoutProfile
from vidrensic.profiler.hitmap import HitMapReport
from vidrensic.profiler.source import SourceProfile
from vidrensic.profiler.triage import TriageReport


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _summary() -> MapSummary:
    return MapSummary(
        blocks=(MapBlock(0, 4, "+"),),
        status_bytes={
            "non_tried": 0,
            "non_trimmed": 0,
            "non_scraped": 0,
            "bad_sector": 0,
            "finished": 4,
        },
        segment_count=1,
        mapped_bytes=4,
        first_position=0,
        last_position=4,
        overlap_bytes=0,
        gap_bytes=0,
        expected_start=0,
        expected_size=4,
        expected_covered_bytes=4,
        expected_finished_bytes=4,
    )


def _receipt(root: Path) -> AcquisitionReceipt:
    return AcquisitionReceipt(
        source=root / "source.raw",
        source_size=4,
        source_read_only=True,
        source_mounted_at=(),
        offset=0,
        requested_size=4,
        output=root / "image.raw",
        output_size=4,
        mapfile=root / "image.map",
        ddrescue_version="synthetic",
        return_codes=(0,),
        map_summary=_summary(),
        output_sha256="11" * 32,
        output_sha512=None,
        map_sha256="22" * 32,
        map_sha512=None,
        output_hash_skipped=False,
        status="COMPLETE",
        reasons=(),
    )


def _assert_private_write(report, path: Path) -> None:
    old_umask = os.umask(0)
    try:
        output = report.write_json(path)
    finally:
        os.umask(old_umask)
    assert _mode(output) == 0o600
    assert output.is_file()


def test_atomic_private_json_ignores_permissive_umask(tmp_path: Path) -> None:
    old_umask = os.umask(0)
    try:
        output = atomic_write_private_json(tmp_path / "report.json", {"serial": "sensitive"})
    finally:
        os.umask(old_umask)

    assert _mode(output) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["serial"] == "sensitive"
    assert not output.with_name(output.name + ".partial").exists()


def test_source_profile_json_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    report = SourceProfile(
        source=Path("/dev/synthetic"),
        size_bytes=4096,
        is_block_device=True,
        read_only=True,
        mounted_at=(),
        sampling_only=True,
        sample_size=512,
        samples=(),
        aggregate_signatures={},
        notes=("synthetic",),
    )
    _assert_private_write(report, tmp_path / "source-profile.json")


def test_acquisition_receipt_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    _assert_private_write(_receipt(tmp_path), tmp_path / "receipt.json")


def test_smart_snapshot_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    report = SmartSnapshot(
        source=Path("/dev/synthetic"),
        captured=True,
        smartctl_returncode=0,
        model="Synthetic DVR Disk",
        serial="SERIAL-PRIVATE",
        firmware="TEST",
        capacity_bytes=4096,
        logical_sector_size=512,
        physical_sector_size=4096,
        rotation_rate=None,
        smart_passed=True,
        temperature_celsius=30,
        power_on_hours=1,
        reallocated_sectors=0,
        pending_sectors=0,
        offline_uncorrectable=0,
        reported_uncorrectable=0,
        raw={"serial_number": "SERIAL-PRIVATE"},
        error=None,
    )
    path = tmp_path / "smart.json"
    _assert_private_write(report, path)
    assert json.loads(path.read_text(encoding="utf-8"))["serial"] == "SERIAL-PRIVATE"


def test_triage_and_hitmap_reports_are_owner_only_under_umask_zero(tmp_path: Path) -> None:
    triage = TriageReport(
        source=Path("/evidence/private.raw"),
        source_info={"path": "/evidence/private.raw"},
        storage={},
        sample_profile={},
        hitmap={},
        format_detection={},
        recommended_actions=(),
        notes=("synthetic",),
    )
    hitmap = HitMapReport(
        source=Path("/evidence/private.raw"),
        source_size=4096,
        range_start=0,
        range_stop=4096,
        scanned_bytes=4096,
        chunk_size=4096,
        max_offsets_per_signature=16,
        signatures=(),
        notes=("synthetic",),
    )
    _assert_private_write(triage, tmp_path / "triage.json")
    _assert_private_write(hitmap, tmp_path / "hitmap.json")


def test_wfs_layout_report_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    report = WFSLayoutProfile(
        source=Path("/evidence/private.raw"),
        range_start=0,
        range_size=4096,
        fragment_size=2 * 1024 * 1024,
        sector_size=512,
        hypotheses=(),
        notes=("synthetic",),
    )
    _assert_private_write(report, tmp_path / "wfs-layout.json")


def test_media_qc_report_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    media = tmp_path / "private-recovered.mp4"
    probe = VideoProbe(
        path=media,
        duration=10.0,
        codec="h264",
        width=1920,
        height=1080,
        avg_frame_rate=25.0,
        r_frame_rate=25.0,
        stream_count=1,
        raw={},
    )
    report = MediaQCReport(
        path=media,
        mode="full-decode",
        decision=QCDecision(EvidenceStatus.REVIEW, ("synthetic",), {"duration": 10.0}),
        probe=probe,
        full_decode_error="private diagnostic context",
    )
    path = tmp_path / "qc.json"
    _assert_private_write(report, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["path"] == str(media)
    assert data["full_decode_error"] == "private diagnostic context"


def test_private_json_no_replace_mode_preserves_existing_final(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        atomic_write_private_json(output, {"new": True}, allow_replace=False)

    assert output.read_text(encoding="utf-8") == "existing"
