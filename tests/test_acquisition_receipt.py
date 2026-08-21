from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

import pytest

import vidrensic.acquisition.receipt as receipt_mod
from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.receipt import build_acquisition_receipt, ddrescue_version


def _info(source: Path, size: int) -> SourceInfo:
    return SourceInfo(
        path=source.resolve(),
        exists=True,
        is_block_device=False,
        size_bytes=size,
        read_only=None,
        mounted_at=(),
    )


def _files(tmp_path: Path, *, output_size: int = 1024, map_status: str = "+"):
    source = tmp_path / "source.raw"
    source.write_bytes(b"S" * 1024)
    output = tmp_path / "output.raw"
    output.write_bytes(b"O" * output_size)
    mapfile = tmp_path / "output.map"
    mapfile.write_text(f"0x0 0x400 {map_status}\n", encoding="utf-8")
    plan = AcquisitionPlan(source=source, output=output, mapfile=mapfile, offset=0, size=1024)
    return source, output, mapfile, plan


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


def test_receipt_to_dict_and_atomic_json_write(tmp_path: Path, monkeypatch) -> None:
    source, _, _, plan = _files(tmp_path)
    monkeypatch.setattr(receipt_mod, "ddrescue_version", lambda: "GNU ddrescue 1.test")
    receipt = build_acquisition_receipt(plan, _info(source, 1024), [0])
    payload = receipt.to_dict()
    assert payload["operation"] == "acquisition.ddrescue"
    assert payload["output"]["sha512"] == receipt.output_sha512
    assert payload["mapfile"]["summary"]["complete_for_expected_range"] is True

    report = tmp_path / "receipt.json"
    assert receipt.write_json(report) == report.resolve()
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "COMPLETE"
    with pytest.raises(FileExistsError, match="already exists"):
        receipt.write_json(report)


def test_receipt_review_reasons_cover_return_map_size_and_hash_skip(tmp_path: Path, monkeypatch) -> None:
    source, _, _, plan = _files(tmp_path, output_size=512, map_status="-")
    monkeypatch.setattr(receipt_mod, "ddrescue_version", lambda: None)
    receipt = build_acquisition_receipt(plan, _info(source, 1024), [1], hash_output=False)
    assert receipt.status == "REVIEW"
    joined = " | ".join(receipt.reasons)
    assert "return codes" in joined
    assert "full requested range" in joined
    assert "smaller" in joined
    assert "hashing was explicitly skipped" in joined


def test_empty_return_codes_are_review(tmp_path: Path, monkeypatch) -> None:
    source, _, _, plan = _files(tmp_path)
    monkeypatch.setattr(receipt_mod, "ddrescue_version", lambda: "test")
    receipt = build_acquisition_receipt(plan, _info(source, 1024), [])
    assert receipt.status == "REVIEW"
    assert any("return codes" in reason for reason in receipt.reasons)


def test_receipt_requires_output_and_map(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"S" * 10)
    plan = AcquisitionPlan(source, tmp_path / "missing.raw", tmp_path / "missing.map", size=10)
    with pytest.raises(FileNotFoundError, match="output"):
        build_acquisition_receipt(plan, _info(source, 10), [0])
    plan.output.write_bytes(b"O" * 10)
    with pytest.raises(FileNotFoundError, match="mapfile"):
        build_acquisition_receipt(plan, _info(source, 10), [0])


def test_ddrescue_version_success_error_timeout_and_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        receipt_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="GNU ddrescue 1.28\nmore\n", stderr=""),
    )
    assert ddrescue_version() == "GNU ddrescue 1.28"

    monkeypatch.setattr(
        receipt_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="", stderr="fallback version\n"),
    )
    assert ddrescue_version() == "fallback version"

    def os_error(*args, **kwargs):
        raise OSError("missing")

    monkeypatch.setattr(receipt_mod.subprocess, "run", os_error)
    assert ddrescue_version() is None

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5)

    monkeypatch.setattr(receipt_mod.subprocess, "run", timed_out)
    assert ddrescue_version() is None


def test_receipt_partial_path_collision_is_rejected(tmp_path: Path, monkeypatch) -> None:
    source, _, _, plan = _files(tmp_path)
    monkeypatch.setattr(receipt_mod, "ddrescue_version", lambda: "test")
    receipt = build_acquisition_receipt(plan, _info(source, 1024), [0])
    report = tmp_path / "receipt.json"
    partial = tmp_path / "receipt.json.partial"
    partial.write_text("old", encoding="utf-8")
    with pytest.raises(FileExistsError, match="partial"):
        receipt.write_json(report)
