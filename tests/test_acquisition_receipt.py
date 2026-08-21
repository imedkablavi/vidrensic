from __future__ import annotations

from pathlib import Path

from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.receipt import build_acquisition_receipt


def _info(source: Path, size: int) -> SourceInfo:
    return SourceInfo(
        path=source.resolve(),
        exists=True,
        is_block_device=False,
        size_bytes=size,
        read_only=None,
        mounted_at=(),
    )


def test_complete_acquisition_receipt(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"S" * 8192)
    output = tmp_path / "image.raw"
    output.write_bytes(b"A" * 4096)
    mapfile = tmp_path / "image.map"
    mapfile.write_text("0x00001000 0x00001000 +\n", encoding="utf-8")
    plan = AcquisitionPlan(source, output, mapfile, offset=4096, size=4096)
    monkeypatch.setattr("vidrensic.acquisition.receipt.ddrescue_version", lambda: "GNU ddrescue TEST")

    receipt = build_acquisition_receipt(plan, _info(source, 8192), [0])
    assert receipt.status == "COMPLETE"
    assert receipt.map_summary.complete_for_expected_range is True
    assert receipt.output_sha256 is not None
    assert receipt.map_sha256
    assert receipt.ddrescue_version == "GNU ddrescue TEST"


def test_bad_sector_map_forces_review(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"S" * 8192)
    output = tmp_path / "image.raw"
    output.write_bytes(b"A" * 4096)
    mapfile = tmp_path / "image.map"
    mapfile.write_text(
        "0x00001000 0x00000800 +\n0x00001800 0x00000800 -\n",
        encoding="utf-8",
    )
    plan = AcquisitionPlan(source, output, mapfile, offset=4096, size=4096)
    monkeypatch.setattr("vidrensic.acquisition.receipt.ddrescue_version", lambda: None)

    receipt = build_acquisition_receipt(plan, _info(source, 8192), [0])
    assert receipt.status == "REVIEW"
    assert receipt.map_summary.status_bytes["bad_sector"] == 2048
    assert any("full requested range" in reason for reason in receipt.reasons)


def test_skipping_output_hash_is_explicit_review(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"S" * 4096)
    output = tmp_path / "image.raw"
    output.write_bytes(b"A" * 4096)
    mapfile = tmp_path / "image.map"
    mapfile.write_text("0x00000000 0x00001000 +\n", encoding="utf-8")
    plan = AcquisitionPlan(source, output, mapfile, size=4096)
    monkeypatch.setattr("vidrensic.acquisition.receipt.ddrescue_version", lambda: "test")

    receipt = build_acquisition_receipt(plan, _info(source, 4096), [0], hash_output=False)
    assert receipt.status == "REVIEW"
    assert receipt.output_hash_skipped
    assert receipt.output_sha256 is None
