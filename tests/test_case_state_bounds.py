from __future__ import annotations

from pathlib import Path
import json

import pytest

import vidrensic.core.audit as audit_module
import vidrensic.core.case as case_module
from vidrensic.core.audit import AuditLog, AuditVerificationError
from vidrensic.core.case import Case


def test_case_load_rejects_oversized_metadata_before_json_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = Case.create(tmp_path, "CASE-LIMIT")
    monkeypatch.setattr(case_module, "MAX_CASE_METADATA_BYTES", 32)
    with pytest.raises(ValueError, match="maximum size"):
        Case.load(case.root)


def test_case_load_rejects_tampered_uuid_and_timestamp(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-TAMPER")
    metadata = json.loads(case.metadata_path.read_text(encoding="utf-8"))

    metadata["case_uuid"] = "not-a-uuid"
    case.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid case_uuid"):
        Case.load(case.root)

    metadata["case_uuid"] = case.case_uuid
    metadata["created_utc"] = "2026-08-24T01:00:00"
    case.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError, match="must include a timezone"):
        Case.load(case.root)


def test_case_load_rejects_metadata_symlink(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "CASE-SYMLINK")
    target = tmp_path / "external-case.json"
    target.write_bytes(case.metadata_path.read_bytes())
    case.metadata_path.unlink()
    try:
        case.metadata_path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(ValueError, match="may not be a symlink"):
        Case.load(case.root)


def test_audit_append_rejects_record_over_limit_without_partial_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path)
    monkeypatch.setattr(audit_module, "MAX_AUDIT_LINE_CHARS", 1024)

    with pytest.raises(ValueError, match="audit record exceeds"):
        audit.append("oversized", {"payload": "X" * 2048})

    assert path.read_text(encoding="utf-8") == ""


def test_audit_verify_and_append_fail_closed_on_oversized_existing_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text("X" * 257, encoding="utf-8")
    monkeypatch.setattr(audit_module, "MAX_AUDIT_LINE_CHARS", 256)
    audit = AuditLog(path)

    ok, reason = audit.verify()
    assert ok is False
    assert "exceeds 256 characters" in reason

    with pytest.raises(AuditVerificationError, match="exceeds 256 characters"):
        audit.append("must-not-append", {})
    assert path.read_text(encoding="utf-8") == "X" * 257


def test_audit_verify_rejects_non_object_json_line(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text("[]\n", encoding="utf-8")
    ok, reason = AuditLog(path).verify()
    assert ok is False
    assert "not an object" in reason
