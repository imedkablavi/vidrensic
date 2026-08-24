from __future__ import annotations

from pathlib import Path

import pytest

from vidrensic.acquisition.binding import (
    MAX_SOURCE_BINDING_BYTES,
    ensure_source_binding,
    source_binding_path,
)
from vidrensic.acquisition.ddrescue import AcquisitionPlan, tool_audit_path
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.receipt import build_acquisition_receipt
from vidrensic.core.audit import AuditLog


def _source_info(source: Path) -> SourceInfo:
    return SourceInfo(
        path=source.resolve(),
        size_bytes=16,
        is_block_device=False,
        read_only=None,
        mounted_at=(),
        filesystem_device=None,
        inode=None,
        block_major=None,
        block_minor=None,
        serial=None,
        wwn=None,
        model=None,
    )


def _plan(tmp_path: Path) -> AcquisitionPlan:
    source = tmp_path / "source.raw"
    output = tmp_path / "output.raw"
    mapfile = tmp_path / "output.map"
    source.write_bytes(b"abcdefghijklmnop")
    output.write_bytes(b"abcdefghijklmnop")
    mapfile.write_text("0x00000000 0x00000010 +\n", encoding="utf-8")
    return AcquisitionPlan(source, output, mapfile, size=16)


def _bind(plan: AcquisitionPlan) -> None:
    ensure_source_binding(
        source=plan.source,
        output=plan.output,
        mapfile=plan.mapfile,
        offset=plan.offset,
        requested_size=plan.size,
        existing_acquisition_state=False,
    )


def _audit(plan: AcquisitionPlan, return_codes: tuple[int, ...] = (0,)) -> None:
    audit = AuditLog(tool_audit_path(plan.mapfile))
    audit.append("ddrescue.session.started", {"tool": {"sha256": "ab" * 32}})
    audit.append(
        "ddrescue.session.finished",
        {"return_codes": list(return_codes), "all_zero": all(code == 0 for code in return_codes)},
    )


def test_missing_provenance_sidecars_keep_receipt_in_review(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert any("source-binding sidecar is missing" in reason for reason in receipt.reasons)
    assert any("tool-audit sidecar is missing" in reason for reason in receipt.reasons)


def test_tool_audit_return_codes_must_match_receipt(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _bind(plan)
    _audit(plan, (0,))
    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0, 0])
    assert receipt.status == "REVIEW"
    assert any("return codes do not match" in reason for reason in receipt.reasons)
    assert receipt.tool_audit_return_codes == (0,)


def test_latest_failed_tool_session_keeps_receipt_in_review(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _bind(plan)
    _audit(plan, (0,))
    AuditLog(tool_audit_path(plan.mapfile)).append(
        "ddrescue.session.failed",
        {"completed_return_codes": [], "error_type": "TimeoutExpired", "error": "synthetic"},
    )
    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert receipt.tool_audit_last_event == "ddrescue.session.failed"
    assert any("latest terminal ddrescue session is not successful" in reason for reason in receipt.reasons)


def test_tampered_tool_audit_is_rejected(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _bind(plan)
    _audit(plan)
    audit_path = tool_audit_path(plan.mapfile)
    text = audit_path.read_text(encoding="utf-8")
    audit_path.write_text(text.replace("ddrescue.session.started", "ddrescue.session.STARTED", 1), encoding="utf-8")

    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert receipt.tool_audit_valid is False
    assert any("hash chain is invalid" in reason for reason in receipt.reasons)


def test_source_change_after_binding_is_detected(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _bind(plan)
    _audit(plan)
    plan.source.write_bytes(b"ponmlkjihgfedcba")

    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert any("does not match source-binding identity" in reason for reason in receipt.reasons)


def test_oversized_source_binding_is_rejected_without_unbounded_json_load(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _bind(plan)
    _audit(plan)
    binding_path = source_binding_path(plan.mapfile)
    binding_path.write_text("{" + (" " * (MAX_SOURCE_BINDING_BYTES + 1)) + "}", encoding="utf-8")

    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert any("source-binding sidecar is invalid" in reason for reason in receipt.reasons)
    assert any("maximum size" in reason for reason in receipt.reasons)


def test_symlinked_source_binding_is_rejected(tmp_path: Path) -> None:
    plan = _plan(tmp_path)
    _audit(plan)
    real = tmp_path / "real-binding.json"
    real.write_text("{}", encoding="utf-8")
    binding_path = source_binding_path(plan.mapfile)
    try:
        binding_path.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    receipt = build_acquisition_receipt(plan, _source_info(plan.source), [0])
    assert receipt.status == "REVIEW"
    assert any("may not be a symlink" in reason for reason in receipt.reasons)
