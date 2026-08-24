from __future__ import annotations

from pathlib import Path

import pytest

import vidrensic.acquisition.receipt as receipt_module
from vidrensic.acquisition.binding import ensure_source_binding
from vidrensic.acquisition.ddrescue import AcquisitionPlan, tool_audit_path
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.receipt import build_acquisition_receipt
from vidrensic.core.audit import AuditLog
from vidrensic.core.hashing import FileChangedDuringHashError


def _plan(tmp_path: Path) -> AcquisitionPlan:
    source = tmp_path / "source.raw"
    output = tmp_path / "output.raw"
    mapfile = tmp_path / "output.map"
    source.write_bytes(b"abcdefghijklmnop")
    output.write_bytes(b"abcdefghijklmnop")
    mapfile.write_text("0x00000000 0x00000010 +\n", encoding="utf-8")
    plan = AcquisitionPlan(source, output, mapfile, size=16)
    ensure_source_binding(
        source=source,
        output=output,
        mapfile=mapfile,
        offset=0,
        requested_size=16,
        existing_acquisition_state=False,
    )
    audit = AuditLog(tool_audit_path(mapfile))
    audit.append("ddrescue.session.started", {"tool": {"sha256": "ab" * 32}})
    audit.append("ddrescue.session.finished", {"return_codes": [0], "all_zero": True})
    return plan


def _source_info(source: Path) -> SourceInfo:
    return SourceInfo(
        path=source.resolve(),
        exists=True,
        is_block_device=False,
        size_bytes=16,
        read_only=None,
        mounted_at=(),
    )


def test_unstable_map_hash_is_omitted_and_forces_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path)
    original = receipt_module._stable_artifact_hash

    def unstable(path: Path):
        if path.expanduser().resolve() == plan.mapfile.resolve():
            raise FileChangedDuringHashError("synthetic map mutation")
        return original(path)

    monkeypatch.setattr(receipt_module, "_stable_artifact_hash", unstable)
    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])

    assert receipt.status == "REVIEW"
    assert receipt.map_hash_stable is False
    assert receipt.map_sha256 is None
    assert receipt.map_sha512 is None
    assert receipt.output_hash_stable is True
    assert any("map hash is not stable" in reason for reason in receipt.reasons)


def test_unstable_output_hash_is_omitted_and_forces_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(tmp_path)
    original = receipt_module._stable_artifact_hash

    def unstable(path: Path):
        if path.expanduser().resolve() == plan.output.resolve():
            raise FileChangedDuringHashError("synthetic output mutation")
        return original(path)

    monkeypatch.setattr(receipt_module, "_stable_artifact_hash", unstable)
    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])

    assert receipt.status == "REVIEW"
    assert receipt.output_hash_stable is False
    assert receipt.output_sha256 is None
    assert receipt.output_sha512 is None
    assert receipt.map_hash_stable is True
    assert any("output hash is not stable" in reason for reason in receipt.reasons)
