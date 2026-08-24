from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import os

from vidrensic.acquisition.binding import (
    CONFIRMED_STATES,
    MAX_SOURCE_BINDING_BYTES,
    load_source_binding,
    source_binding_path,
)
from vidrensic.acquisition.ddrescue import (
    AcquisitionPlan,
    resolve_ddrescue_executable,
    tool_audit_path,
)
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.mapfile import MapSummary, parse_mapfile
from vidrensic.core.audit import AuditLog, MAX_AUDIT_LINE_CHARS
from vidrensic.core.hashing import forensic_hashes
from vidrensic.core.provenance import fingerprint_source, require_same_source


PRIVATE_RECEIPT_MODE = 0o600
MAX_TOOL_AUDIT_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class AcquisitionReceipt:
    source: Path
    source_size: int
    source_read_only: bool | None
    source_mounted_at: tuple[str, ...]
    offset: int
    requested_size: int
    output: Path
    output_size: int
    mapfile: Path
    ddrescue_version: str | None
    return_codes: tuple[int, ...]
    map_summary: MapSummary
    output_sha256: str | None
    output_sha512: str | None
    map_sha256: str
    map_sha512: str | None
    output_hash_skipped: bool
    status: str
    reasons: tuple[str, ...]
    source_binding_path: Path | None = None
    source_binding_sha256: str | None = None
    source_binding_state: str | None = None
    source_binding_identity_strength: str | None = None
    tool_audit_path: Path | None = None
    tool_audit_sha256: str | None = None
    tool_audit_tail_hash: str | None = None
    tool_audit_valid: bool | None = None
    tool_audit_last_event: str | None = None
    tool_audit_return_codes: tuple[int, ...] | None = None

    def to_dict(self) -> dict:
        return {
            "schema_version": 2,
            "operation": "acquisition.ddrescue",
            "status": self.status,
            "reasons": list(self.reasons),
            "source": {
                "path": str(self.source),
                "size_bytes": self.source_size,
                "read_only": self.source_read_only,
                "mounted_at": list(self.source_mounted_at),
            },
            "range": {
                "input_offset": self.offset,
                "requested_size": self.requested_size,
                "output_offset": 0,
            },
            "output": {
                "path": str(self.output),
                "size_bytes": self.output_size,
                "sha256": self.output_sha256,
                "sha512": self.output_sha512,
                "hash_skipped": self.output_hash_skipped,
            },
            "mapfile": {
                "path": str(self.mapfile),
                "sha256": self.map_sha256,
                "sha512": self.map_sha512,
                "summary": self.map_summary.to_dict(),
            },
            "provenance": {
                "source_binding": {
                    "path": None if self.source_binding_path is None else str(self.source_binding_path),
                    "sha256": self.source_binding_sha256,
                    "state": self.source_binding_state,
                    "identity_strength": self.source_binding_identity_strength,
                },
                "tool_audit": {
                    "path": None if self.tool_audit_path is None else str(self.tool_audit_path),
                    "sha256": self.tool_audit_sha256,
                    "tail_hash": self.tool_audit_tail_hash,
                    "valid": self.tool_audit_valid,
                    "last_event": self.tool_audit_last_event,
                    "recorded_return_codes": (
                        None
                        if self.tool_audit_return_codes is None
                        else list(self.tool_audit_return_codes)
                    ),
                },
            },
            "ddrescue_version": self.ddrescue_version,
            "return_codes": list(self.return_codes),
            "forensic_notes": [
                "hashes bind the receipt to exact acquisition/map/provenance-sidecar bytes, not to an independently full-hashed source disk",
                "source identity is rechecked against the persisted source binding before COMPLETE is possible",
                "the final ddrescue tool-audit record must be a successful session whose return codes match this receipt",
                "a newer started/pass event without a terminal session event forces REVIEW",
                "tool-audit/source-binding hashes are integrity evidence, not digital signatures or trusted timestamps",
                "ddrescue_version is observed in the verification environment and is not substituted for the execution-session tool audit",
                "a skipped output hash leaves verification incomplete and forces REVIEW status",
                "map completion is evaluated against the requested source range",
            ],
        }

    def write_json(self, path: Path) -> Path:
        path = path.expanduser().resolve()
        if path.exists():
            raise FileExistsError(f"acquisition receipt already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        if partial.exists():
            raise FileExistsError(f"partial acquisition receipt already exists: {partial}")
        try:
            with partial.open("x", encoding="utf-8") as fh:
                os.fchmod(fh.fileno(), PRIVATE_RECEIPT_MODE)
                json.dump(self.to_dict(), fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            partial.replace(path)
            os.chmod(path, PRIVATE_RECEIPT_MODE)
        except Exception:
            if partial.exists():
                partial.unlink()
            raise
        return path


def ddrescue_version() -> str | None:
    """Observe ddrescue version in the current verification environment."""

    try:
        return resolve_ddrescue_executable().version
    except (OSError, ValueError):
        return None


def _bounded_sha256(path: Path, *, max_bytes: int, label: str) -> str:
    digest = sha256()
    read_bytes = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(min(1024 * 1024, max_bytes + 1 - read_bytes))
            if not chunk:
                break
            read_bytes += len(chunk)
            if read_bytes > max_bytes:
                raise ValueError(f"{label} exceeds maximum size of {max_bytes} bytes")
            digest.update(chunk)
    return digest.hexdigest()


def _binding_provenance(
    plan: AcquisitionPlan,
    source_info: SourceInfo,
) -> tuple[dict[str, object], list[str]]:
    path = source_binding_path(plan.mapfile)
    result: dict[str, object] = {
        "path": path,
        "sha256": None,
        "state": None,
        "identity_strength": None,
    }
    reasons: list[str] = []
    if not path.exists():
        reasons.append("acquisition source-binding sidecar is missing")
        return result, reasons
    if path.is_symlink():
        reasons.append("acquisition source-binding sidecar may not be a symlink")
        return result, reasons

    try:
        before_hash = _bounded_sha256(
            path,
            max_bytes=MAX_SOURCE_BINDING_BYTES,
            label="acquisition source-binding sidecar",
        )
        binding = load_source_binding(path)
    except (OSError, ValueError) as exc:
        reasons.append(f"acquisition source-binding sidecar is invalid: {type(exc).__name__}: {exc}")
        return result, reasons

    result["state"] = binding.state
    result["identity_strength"] = binding.source.identity_strength

    if binding.state not in CONFIRMED_STATES:
        reasons.append(f"acquisition source binding is not confirmed: {binding.state}")
    if binding.output != plan.output.expanduser().resolve():
        reasons.append("source-binding output path does not match the receipt plan")
    if binding.mapfile != plan.mapfile.expanduser().resolve():
        reasons.append("source-binding map path does not match the receipt plan")
    if binding.offset != plan.offset or binding.requested_size != plan.size:
        reasons.append("source-binding acquisition geometry does not match the receipt plan")

    try:
        sample_bytes = binding.source.edge_sample_bytes if not binding.source.is_block_device else 0
        current = fingerprint_source(source_info.path, edge_sample_bytes=sample_bytes)
        require_same_source(binding.source, current)
    except (OSError, RuntimeError, ValueError) as exc:
        reasons.append(f"current source does not match source-binding identity: {exc}")

    try:
        after_hash = _bounded_sha256(
            path,
            max_bytes=MAX_SOURCE_BINDING_BYTES,
            label="acquisition source-binding sidecar",
        )
    except (OSError, ValueError) as exc:
        reasons.append(f"acquisition source-binding sidecar became unreadable: {type(exc).__name__}: {exc}")
        return result, reasons
    result["sha256"] = after_hash
    if before_hash != after_hash:
        reasons.append("source-binding sidecar changed during receipt verification")
    return result, reasons


def _last_tool_record(path: Path) -> dict | None:
    last: dict | None = None
    with path.open("r", encoding="utf-8") as handle:
        while True:
            line = handle.readline(MAX_AUDIT_LINE_CHARS + 1)
            if not line:
                break
            if len(line) > MAX_AUDIT_LINE_CHARS:
                raise ValueError("tool-audit line exceeds configured safety limit")
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError("tool-audit record is not an object")
            last = record
    return last


def _tool_audit_provenance(
    plan: AcquisitionPlan,
    return_codes: tuple[int, ...],
) -> tuple[dict[str, object], list[str]]:
    path = tool_audit_path(plan.mapfile)
    result: dict[str, object] = {
        "path": path,
        "sha256": None,
        "tail_hash": None,
        "valid": None,
        "last_event": None,
        "return_codes": None,
    }
    reasons: list[str] = []
    if not path.exists():
        reasons.append("ddrescue tool-audit sidecar is missing")
        return result, reasons
    if path.is_symlink():
        reasons.append("ddrescue tool-audit sidecar may not be a symlink")
        return result, reasons

    try:
        before_hash = _bounded_sha256(
            path,
            max_bytes=MAX_TOOL_AUDIT_BYTES,
            label="ddrescue tool-audit sidecar",
        )
    except (OSError, ValueError) as exc:
        result["valid"] = False
        reasons.append(f"ddrescue tool-audit sidecar is invalid: {type(exc).__name__}: {exc}")
        return result, reasons

    audit = AuditLog(path)
    ok, tail_or_reason = audit.verify()
    if not ok:
        result["valid"] = False
        reasons.append(f"ddrescue tool-audit hash chain is invalid: {tail_or_reason}")
        return result, reasons

    try:
        last_record = _last_tool_record(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result["valid"] = False
        reasons.append(f"ddrescue tool-audit final record is unreadable: {type(exc).__name__}: {exc}")
        return result, reasons

    try:
        after_hash = _bounded_sha256(
            path,
            max_bytes=MAX_TOOL_AUDIT_BYTES,
            label="ddrescue tool-audit sidecar",
        )
    except (OSError, ValueError) as exc:
        result["valid"] = False
        reasons.append(f"ddrescue tool-audit sidecar became unreadable: {type(exc).__name__}: {exc}")
        return result, reasons
    ok_after, after_reason = audit.verify(expected_tail_hash=tail_or_reason)
    if before_hash != after_hash or not ok_after:
        result["valid"] = False
        result["sha256"] = after_hash
        reasons.append(
            "ddrescue tool-audit changed during receipt verification"
            if before_hash != after_hash
            else f"ddrescue tool-audit changed during receipt verification: {after_reason}"
        )
        return result, reasons

    result["sha256"] = after_hash
    result["tail_hash"] = tail_or_reason
    result["valid"] = True
    if last_record is None:
        reasons.append("ddrescue tool-audit has no execution-session records")
        return result, reasons

    event = last_record.get("event")
    result["last_event"] = event
    if event != "ddrescue.session.finished":
        reasons.append(f"latest ddrescue tool-audit event is not a completed session: {event}")
        return result, reasons

    details = last_record.get("details")
    if not isinstance(details, dict):
        reasons.append("ddrescue tool-audit finished event has invalid details")
        return result, reasons
    recorded = details.get("return_codes")
    if isinstance(recorded, list) and all(type(code) is int for code in recorded):
        recorded_codes = tuple(recorded)
        result["return_codes"] = recorded_codes
    else:
        recorded_codes = None

    if recorded_codes is None:
        reasons.append("ddrescue tool-audit finished event has invalid return_codes")
        return result, reasons
    if details.get("all_zero") is not True:
        reasons.append("ddrescue tool-audit finished event does not confirm all-zero return codes")
    if recorded_codes != return_codes:
        reasons.append(
            "receipt return codes do not match the latest ddrescue tool-audit session: "
            f"receipt={list(return_codes)} audit={list(recorded_codes)}"
        )
    return result, reasons


def build_acquisition_receipt(
    plan: AcquisitionPlan,
    source_info: SourceInfo,
    return_codes: list[int] | tuple[int, ...],
    *,
    hash_output: bool = True,
) -> AcquisitionReceipt:
    requested_size = plan.validate_source_geometry(source_info.size_bytes)
    if not plan.output.is_file():
        raise FileNotFoundError(f"acquisition output does not exist: {plan.output}")
    if not plan.mapfile.is_file():
        raise FileNotFoundError(f"ddrescue mapfile does not exist: {plan.mapfile}")

    normalized_return_codes = tuple(return_codes)
    map_summary = parse_mapfile(
        plan.mapfile,
        expected_start=plan.offset,
        expected_size=requested_size,
    )
    map_hashes = forensic_hashes(plan.mapfile)
    output_hashes = forensic_hashes(plan.output) if hash_output else None
    output_size = plan.output.stat().st_size

    binding, binding_reasons = _binding_provenance(plan, source_info)
    tool_audit, tool_reasons = _tool_audit_provenance(plan, normalized_return_codes)

    reasons: list[str] = [*binding_reasons, *tool_reasons]
    if not normalized_return_codes or any(code != 0 for code in normalized_return_codes):
        reasons.append(f"ddrescue return codes are not all zero: {list(normalized_return_codes)}")
    if map_summary.complete_for_expected_range is not True:
        reasons.append("ddrescue map does not show the full requested range as finished")
    if output_size < requested_size:
        reasons.append(
            f"output logical size {output_size} is smaller than requested acquisition size {requested_size}"
        )
    if not hash_output:
        reasons.append("output cryptographic hashing was explicitly skipped")

    status = "COMPLETE" if not reasons else "REVIEW"
    return AcquisitionReceipt(
        source=source_info.path,
        source_size=source_info.size_bytes,
        source_read_only=source_info.read_only,
        source_mounted_at=source_info.mounted_at,
        offset=plan.offset,
        requested_size=requested_size,
        output=plan.output.expanduser().resolve(),
        output_size=output_size,
        mapfile=plan.mapfile.expanduser().resolve(),
        ddrescue_version=ddrescue_version(),
        return_codes=normalized_return_codes,
        map_summary=map_summary,
        output_sha256=output_hashes.sha256 if output_hashes else None,
        output_sha512=output_hashes.sha512 if output_hashes else None,
        map_sha256=map_hashes.sha256,
        map_sha512=map_hashes.sha512,
        output_hash_skipped=not hash_output,
        status=status,
        reasons=tuple(reasons),
        source_binding_path=binding["path"] if isinstance(binding["path"], Path) else None,
        source_binding_sha256=(
            binding["sha256"] if isinstance(binding["sha256"], str) else None
        ),
        source_binding_state=binding["state"] if isinstance(binding["state"], str) else None,
        source_binding_identity_strength=(
            binding["identity_strength"]
            if isinstance(binding["identity_strength"], str)
            else None
        ),
        tool_audit_path=(tool_audit["path"] if isinstance(tool_audit["path"], Path) else None),
        tool_audit_sha256=(
            tool_audit["sha256"] if isinstance(tool_audit["sha256"], str) else None
        ),
        tool_audit_tail_hash=(
            tool_audit["tail_hash"] if isinstance(tool_audit["tail_hash"], str) else None
        ),
        tool_audit_valid=(
            tool_audit["valid"] if isinstance(tool_audit["valid"], bool) else None
        ),
        tool_audit_last_event=(
            tool_audit["last_event"] if isinstance(tool_audit["last_event"], str) else None
        ),
        tool_audit_return_codes=(
            tool_audit["return_codes"]
            if isinstance(tool_audit["return_codes"], tuple)
            else None
        ),
    )
