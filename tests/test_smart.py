from __future__ import annotations

from pathlib import Path

from vidrensic.acquisition.smart import _parse_snapshot


def test_parse_smart_snapshot_preserves_health_evidence() -> None:
    data = {
        "model_name": "ST32000646NS",
        "serial_number": "SERIAL-TEST",
        "firmware_version": "G009",
        "user_capacity": {"bytes": 2_000_398_934_016},
        "logical_block_size": 512,
        "physical_block_size": 512,
        "rotation_rate": 7200,
        "smart_status": {"passed": True},
        "temperature": {"current": 37},
        "power_on_time": {"hours": 28649},
        "ata_smart_attributes": {
            "table": [
                {"id": 5, "raw": {"value": 6}},
                {"id": 187, "raw": {"value": 15}},
                {"id": 197, "raw": {"value": 2}},
                {"id": 198, "raw": {"value": 2}},
            ]
        },
    }
    snapshot = _parse_snapshot(Path("/dev/sdb"), data, returncode=0, error=None)
    assert snapshot.captured
    assert snapshot.model == "ST32000646NS"
    assert snapshot.capacity_bytes == 2_000_398_934_016
    assert snapshot.smart_passed is True
    assert snapshot.reallocated_sectors == 6
    assert snapshot.pending_sectors == 2
    assert snapshot.offline_uncorrectable == 2
    assert snapshot.reported_uncorrectable == 15


def test_parse_smart_snapshot_keeps_nonzero_return_code_with_json() -> None:
    snapshot = _parse_snapshot(
        Path("/dev/sdb"),
        {"model_name": "DVR Disk", "smart_status": {"passed": False}},
        returncode=8,
        error="device reports SMART condition",
    )
    assert snapshot.captured
    assert snapshot.smartctl_returncode == 8
    assert snapshot.smart_passed is False
    assert snapshot.error == "device reports SMART condition"
