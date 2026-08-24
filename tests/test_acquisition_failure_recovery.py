from __future__ import annotations

from pathlib import Path

import pytest

import vidrensic.acquisition.receipt as receipt_module
from vidrensic.acquisition.mapfile import MapBlock, MapSummary
from vidrensic.acquisition.receipt import AcquisitionReceipt
from vidrensic.core.provenance import fingerprint_source, require_same_source


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
    source = root / "source.bin"
    output = root / "output.raw"
    mapfile = root / "output.map"
    source.write_bytes(b"source")
    output.write_bytes(b"data")
    mapfile.write_text("0 4 +\n", encoding="utf-8")
    return AcquisitionReceipt(
        source=source,
        source_size=6,
        source_read_only=None,
        source_mounted_at=(),
        offset=0,
        requested_size=4,
        output=output,
        output_size=4,
        mapfile=mapfile,
        ddrescue_version="synthetic-test",
        return_codes=(0,),
        map_summary=_summary(),
        output_sha256="11" * 32,
        output_sha512=None,
        map_sha256="22" * 32,
        map_sha512=None,
        output_hash_skipped=False,
        output_hash_stable=True,
        map_hash_stable=True,
        status="COMPLETE",
        reasons=(),
    )


def test_resume_source_identity_change_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "evidence.raw"
    source.write_bytes(b"A" * 4096)
    before = fingerprint_source(source, edge_sample_bytes=512)

    source.write_bytes(b"B" * 4096)
    after = fingerprint_source(source, edge_sample_bytes=512)

    with pytest.raises(RuntimeError, match="identity changed"):
        require_same_source(before, after)


def test_receipt_serialization_failure_leaves_no_success_looking_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt(tmp_path)
    destination = tmp_path / "receipt.json"

    def fail_dump(*args, **kwargs):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(receipt_module.json, "dump", fail_dump)
    with pytest.raises(OSError, match="storage failure"):
        receipt.write_json(destination)

    assert destination.exists() is False
    assert destination.with_name(destination.name + ".partial").exists() is False


def test_existing_partial_receipt_blocks_overwrite(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    destination = tmp_path / "receipt.json"
    partial = destination.with_name(destination.name + ".partial")
    partial.write_text("incomplete", encoding="utf-8")

    with pytest.raises(FileExistsError, match="partial"):
        receipt.write_json(destination)
    assert partial.read_text(encoding="utf-8") == "incomplete"
