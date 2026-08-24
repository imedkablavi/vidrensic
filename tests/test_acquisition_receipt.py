from __future__ import annotations

from pathlib import Path

from vidrensic.acquisition.binding import ensure_source_binding
from vidrensic.acquisition.ddrescue import AcquisitionPlan, tool_audit_path
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.receipt import build_acquisition_receipt
from vidrensic.core.audit import AuditLog


def _source_info(source: Path) -> SourceInfo:
    return SourceInfo(
        path=source.resolve(),
        exists=True,
        is_block_device=False,
        size_bytes=16,
        read_only=None,
        mounted_at=(),
    )


def _complete_map(path: Path) -> None:
    path.write_text(
        "# Mapfile. Created by GNU ddrescue\n"
        "# current_pos  current_status  current_pass\n"
        "0x00000010     +               1\n"
        "#      pos        size  status\n"
        "0x00000000  0x00000010  +\n",
        encoding="utf-8",
    )


def _provenance(plan: AcquisitionPlan, return_codes: tuple[int, ...]) -> None:
    ensure_source_binding(
        source=plan.source,
        output=plan.output,
        mapfile=plan.mapfile,
        offset=plan.offset,
        requested_size=plan.size,
        existing_acquisition_state=False,
    )
    audit = AuditLog(tool_audit_path(plan.mapfile))
    audit.append(
        "ddrescue.session.started",
        {
            "tool": {
                "path": "/usr/bin/ddrescue-synthetic",
                "sha256": "ab" * 32,
                "version": "synthetic",
            }
        },
    )
    audit.append(
        "ddrescue.session.finished",
        {
            "return_codes": list(return_codes),
            "all_zero": bool(return_codes) and all(code == 0 for code in return_codes),
            "executable_path": "/usr/bin/ddrescue-synthetic",
            "executable_sha256": "ab" * 32,
        },
    )


def test_complete_receipt_requires_map_range_and_hashes(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"abcdefghijklmnop")
    output = tmp_path / "output.raw"
    output.write_bytes(b"abcdefghijklmnop")
    mapfile = tmp_path / "output.map"
    _complete_map(mapfile)
    plan = AcquisitionPlan(source, output, mapfile, size=16)
    _provenance(plan, (0,))

    receipt = build_acquisition_receipt(plan, _source_info(source), [0])
    assert receipt.status == "COMPLETE"
    assert receipt.output_sha256 is not None
    assert receipt.map_sha256 is not None
    assert receipt.map_summary.complete_for_expected_range is True
    assert receipt.source_binding_sha256 is not None
    assert receipt.source_binding_state == "confirmed-new"
    assert receipt.tool_audit_valid is True
    assert receipt.tool_audit_sha256 is not None
    assert receipt.tool_audit_return_codes == (0,)
    data = receipt.to_dict()
    assert data["schema_version"] == 2
    assert data["provenance"]["tool_audit"]["valid"] is True


def test_receipt_review_when_map_has_unresolved_ranges(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"abcdefghijklmnop")
    output = tmp_path / "output.raw"
    output.write_bytes(b"abcdefghijklmnop")
    mapfile = tmp_path / "output.map"
    mapfile.write_text(
        "0x00000000 0x00000008 +\n0x00000008 0x00000008 ?\n",
        encoding="utf-8",
    )
    plan = AcquisitionPlan(source, output, mapfile, size=16)
    _provenance(plan, (0,))
    receipt = build_acquisition_receipt(plan, _source_info(source), [0])
    assert receipt.status == "REVIEW"
    assert any("map" in reason.lower() for reason in receipt.reasons)


def test_receipt_review_when_output_hash_is_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"abcdefghijklmnop")
    output = tmp_path / "output.raw"
    output.write_bytes(b"abcdefghijklmnop")
    mapfile = tmp_path / "output.map"
    _complete_map(mapfile)
    plan = AcquisitionPlan(source, output, mapfile, size=16)
    _provenance(plan, (0,))
    receipt = build_acquisition_receipt(
        plan,
        _source_info(source),
        [0],
        hash_output=False,
    )
    assert receipt.status == "REVIEW"
    assert receipt.output_sha256 is None
    assert receipt.output_hash_skipped is True


def test_receipt_rejects_truncated_output(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"abcdefghijklmnop")
    output = tmp_path / "output.raw"
    output.write_bytes(b"short")
    mapfile = tmp_path / "output.map"
    _complete_map(mapfile)
    plan = AcquisitionPlan(source, output, mapfile, size=16)
    _provenance(plan, (0,))
    receipt = build_acquisition_receipt(plan, _source_info(source), [0])
    assert receipt.status == "REVIEW"
    assert any("smaller" in reason for reason in receipt.reasons)
