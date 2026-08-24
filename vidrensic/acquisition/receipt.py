from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess

from vidrensic.acquisition.ddrescue import AcquisitionPlan
from vidrensic.acquisition.linux import SourceInfo
from vidrensic.acquisition.mapfile import MapSummary, parse_mapfile
from vidrensic.core.hashing import forensic_hashes


PRIVATE_RECEIPT_MODE = 0o600


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

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
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
            "ddrescue_version": self.ddrescue_version,
            "return_codes": list(self.return_codes),
            "forensic_notes": [
                "hashes bind the receipt to derived acquisition/map bytes, not to an independently hashed source disk",
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
                # Receipt paths, device mount information and hashes are case
                # metadata. Do not let a permissive process umask make them
                # group/world-readable when the caller writes outside a Case.
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
    try:
        proc = subprocess.run(
            ["ddrescue", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first = (proc.stdout or proc.stderr).splitlines()
    return first[0].strip() if first else None


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

    map_summary = parse_mapfile(
        plan.mapfile,
        expected_start=plan.offset,
        expected_size=requested_size,
    )
    map_hashes = forensic_hashes(plan.mapfile)
    output_hashes = forensic_hashes(plan.output) if hash_output else None
    output_size = plan.output.stat().st_size

    reasons: list[str] = []
    if not return_codes or any(code != 0 for code in return_codes):
        reasons.append(f"ddrescue return codes are not all zero: {list(return_codes)}")
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
        return_codes=tuple(return_codes),
        map_summary=map_summary,
        output_sha256=output_hashes.sha256 if output_hashes else None,
        output_sha512=output_hashes.sha512 if output_hashes else None,
        map_sha256=map_hashes.sha256,
        map_sha512=map_hashes.sha512,
        output_hash_skipped=not hash_output,
        status=status,
        reasons=tuple(reasons),
    )
