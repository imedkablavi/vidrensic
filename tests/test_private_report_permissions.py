from __future__ import annotations

from pathlib import Path
import json
import os
import stat

import pytest

from vidrensic.acquisition.mapfile import MapBlock, MapSummary
from vidrensic.acquisition.receipt import AcquisitionReceipt
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.profiler.source import SourceProfile


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

    old_umask = os.umask(0)
    try:
        output = report.write_json(tmp_path / "source-profile.json")
    finally:
        os.umask(old_umask)

    assert _mode(output) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["source"] == "/dev/synthetic"


def test_acquisition_receipt_is_owner_only_under_umask_zero(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    output = tmp_path / "receipt.json"

    old_umask = os.umask(0)
    try:
        receipt.write_json(output)
    finally:
        os.umask(old_umask)

    assert _mode(output) == 0o600
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "COMPLETE"


def test_private_json_no_replace_mode_preserves_existing_final(tmp_path: Path) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError):
        atomic_write_private_json(output, {"new": True}, allow_replace=False)

    assert output.read_text(encoding="utf-8") == "existing"
