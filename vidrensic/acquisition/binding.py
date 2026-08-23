from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import argparse
import json
import os

from vidrensic.core.provenance import SourceFingerprint, fingerprint_source, require_same_source


BINDING_SCHEMA_VERSION = 1
REGULAR_FILE_EDGE_SAMPLE_BYTES = 64 * 1024
PRIVATE_FILE_MODE = 0o600
PENDING_LEGACY = "pending-legacy-adoption"
CONFIRMED_NEW = "confirmed-new"
CONFIRMED_LEGACY = "confirmed-legacy-adoption"
CONFIRMED_STATES = frozenset({CONFIRMED_NEW, CONFIRMED_LEGACY})


@dataclass(frozen=True)
class AcquisitionSourceBinding:
    source: SourceFingerprint
    output: Path
    mapfile: Path
    offset: int
    requested_size: int | None
    state: str
    created_utc: str
    confirmed_utc: str | None = None
    schema_version: int = BINDING_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation": "acquisition.source-binding",
            "state": self.state,
            "created_utc": self.created_utc,
            "confirmed_utc": self.confirmed_utc,
            "source": self.source.to_dict(),
            "plan": {
                "output": str(self.output),
                "mapfile": str(self.mapfile),
                "offset": self.offset,
                "requested_size": self.requested_size,
            },
            "forensic_notes": [
                "binding prevents silent resume against a different observed source identity",
                "hardware WWN/serial is preferred for block devices when the operating system exposes it",
                "device-node fallback is weaker across reboot/re-enumeration and is recorded as such",
                "regular-file bindings include a bounded first/last edge-sample hash in addition to inode/mtime metadata",
                "this sidecar is integrity metadata, not a digital signature or trusted timestamp",
            ],
        }

    @classmethod
    def from_dict(cls, value: Any) -> AcquisitionSourceBinding:
        if not isinstance(value, dict) or value.get("schema_version") != BINDING_SCHEMA_VERSION:
            raise ValueError("unsupported acquisition source-binding schema")
        if value.get("operation") != "acquisition.source-binding":
            raise ValueError("unexpected source-binding operation")
        state = value.get("state")
        if state not in {PENDING_LEGACY, CONFIRMED_NEW, CONFIRMED_LEGACY}:
            raise ValueError("invalid acquisition source-binding state")
        plan = value.get("plan")
        if not isinstance(plan, dict):
            raise ValueError("source-binding plan must be an object")
        requested_size = plan.get("requested_size")
        if requested_size is not None:
            requested_size = int(requested_size)
            if requested_size <= 0:
                raise ValueError("source-binding requested_size must be positive")
        offset = int(plan.get("offset", -1))
        if offset < 0:
            raise ValueError("source-binding offset cannot be negative")
        created = value.get("created_utc")
        confirmed = value.get("confirmed_utc")
        if not isinstance(created, str) or not created:
            raise ValueError("source-binding created_utc is required")
        if confirmed is not None and not isinstance(confirmed, str):
            raise ValueError("source-binding confirmed_utc must be a string or null")
        return cls(
            source=SourceFingerprint.from_dict(value.get("source")),
            output=Path(str(plan["output"])).expanduser().resolve(),
            mapfile=Path(str(plan["mapfile"])).expanduser().resolve(),
            offset=offset,
            requested_size=requested_size,
            state=state,
            created_utc=created,
            confirmed_utc=confirmed,
        )


def source_binding_path(mapfile: Path) -> Path:
    resolved = mapfile.expanduser().resolve()
    return resolved.with_name(resolved.name + ".source.json")


def _fingerprint_for_binding(source: Path) -> SourceFingerprint:
    initial = fingerprint_source(source, edge_sample_bytes=0)
    if initial.is_block_device:
        return initial
    return fingerprint_source(source, edge_sample_bytes=REGULAR_FILE_EDGE_SAMPLE_BYTES)


def _write_binding(path: Path, binding: AcquisitionSourceBinding, *, replace_existing: bool) -> Path:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace_existing:
        raise FileExistsError(f"source binding already exists: {path}")
    temp = path.with_name(path.name + ".tmp")
    if temp.exists():
        raise FileExistsError(f"partial source binding already exists: {temp}")
    payload = json.dumps(binding.to_dict(), indent=2, sort_keys=True) + "\n"
    try:
        with temp.open("x", encoding="utf-8") as fh:
            os.chmod(temp, PRIVATE_FILE_MODE)
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        if not replace_existing and path.exists():
            raise FileExistsError(f"source binding appeared concurrently: {path}")
        temp.replace(path)
        os.chmod(path, PRIVATE_FILE_MODE)
    except Exception:
        if temp.exists():
            temp.unlink()
        raise
    return path


def load_source_binding(path: Path) -> AcquisitionSourceBinding:
    path = path.expanduser().resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    return AcquisitionSourceBinding.from_dict(data)


def _require_plan_match(
    binding: AcquisitionSourceBinding,
    *,
    output: Path,
    mapfile: Path,
    offset: int,
    requested_size: int | None,
) -> None:
    if binding.output != output.expanduser().resolve():
        raise RuntimeError("acquisition output path changed from source-binding sidecar")
    if binding.mapfile != mapfile.expanduser().resolve():
        raise RuntimeError("acquisition map path changed from source-binding sidecar")
    if binding.offset != offset or binding.requested_size != requested_size:
        raise RuntimeError("acquisition geometry changed from source-binding sidecar")


def ensure_source_binding(
    *,
    source: Path,
    output: Path,
    mapfile: Path,
    offset: int,
    requested_size: int | None,
    existing_acquisition_state: bool,
) -> AcquisitionSourceBinding:
    """Create or verify the source binding before ddrescue is allowed to run.

    A legacy map/output with no binding is never resumed on first encounter. A
    pending sidecar is written and execution stops until an examiner explicitly
    confirms it with ``python -m vidrensic.acquisition.binding confirm ...``.
    """

    binding_path = source_binding_path(mapfile)
    protected = {
        source.expanduser().resolve(),
        output.expanduser().resolve(),
        mapfile.expanduser().resolve(),
    }
    if binding_path in protected:
        raise ValueError("source-binding path collides with acquisition source/output/map")

    current = _fingerprint_for_binding(source)
    if binding_path.exists():
        binding = load_source_binding(binding_path)
        _require_plan_match(
            binding,
            output=output,
            mapfile=mapfile,
            offset=offset,
            requested_size=requested_size,
        )
        require_same_source(binding.source, current)
        if binding.state not in CONFIRMED_STATES:
            raise RuntimeError(
                "legacy acquisition source binding is pending confirmation; inspect it and run "
                f"python -m vidrensic.acquisition.binding confirm {binding_path}"
            )
        return binding

    now = datetime.now(UTC).isoformat()
    state = PENDING_LEGACY if existing_acquisition_state else CONFIRMED_NEW
    binding = AcquisitionSourceBinding(
        source=current,
        output=output.expanduser().resolve(),
        mapfile=mapfile.expanduser().resolve(),
        offset=offset,
        requested_size=requested_size,
        state=state,
        created_utc=now,
        confirmed_utc=now if state == CONFIRMED_NEW else None,
    )
    _write_binding(binding_path, binding, replace_existing=False)
    if state == PENDING_LEGACY:
        raise RuntimeError(
            "existing acquisition state had no source binding; a pending binding was written and "
            "ddrescue was NOT executed. Verify source/provenance, then run "
            f"python -m vidrensic.acquisition.binding confirm {binding_path}"
        )
    return binding


def confirm_legacy_binding(path: Path, *, source: Path | None = None) -> AcquisitionSourceBinding:
    path = path.expanduser().resolve()
    binding = load_source_binding(path)
    if binding.state in CONFIRMED_STATES:
        return binding
    if binding.state != PENDING_LEGACY:
        raise RuntimeError("source binding is not a confirmable legacy-adoption state")

    candidate = source.expanduser().resolve() if source is not None else binding.source.path
    sample_bytes = binding.source.edge_sample_bytes if not binding.source.is_block_device else 0
    current = fingerprint_source(candidate, edge_sample_bytes=sample_bytes)
    require_same_source(binding.source, current)
    confirmed = replace(
        binding,
        source=current,
        state=CONFIRMED_LEGACY,
        confirmed_utc=datetime.now(UTC).isoformat(),
    )
    _write_binding(path, confirmed, replace_existing=True)
    return confirmed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Confirm a legacy Vidrensic acquisition source binding")
    sub = parser.add_subparsers(dest="command", required=True)
    confirm = sub.add_parser("confirm")
    confirm.add_argument("binding", type=Path)
    confirm.add_argument("--source", type=Path)
    args = parser.parse_args(argv)

    if args.command == "confirm":
        binding = confirm_legacy_binding(args.binding, source=args.source)
        print(json.dumps(binding.to_dict(), indent=2, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
