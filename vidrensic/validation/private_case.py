from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import os

from vidrensic.core.hashing import hash_file


@dataclass(frozen=True)
class PrivateCaseManifest:
    path: Path
    case_id: str
    source: Path
    source_sha256: str
    family: str


def _safe_identifier(value: str, field: str) -> str:
    value = value.strip()
    if not value or len(value) > 128:
        raise ValueError(f"{field} must be 1-128 characters")
    if any(ch in value for ch in "\x00\r\n"):
        raise ValueError(f"{field} contains invalid control characters")
    return value


def create_private_case_manifest(
    source: Path,
    output: Path,
    *,
    case_id: str,
    family: str,
    manufacturer: str | None = None,
    model: str | None = None,
    firmware: str | None = None,
    notes: tuple[str, ...] = (),
) -> PrivateCaseManifest:
    """Create a restricted validation manifest beside/above an existing source.

    No evidence is copied or uploaded. The output manifest must live in a parent
    directory of the source so that the corpus keeps a portable relative path.
    """

    source = source.expanduser().resolve()
    output = output.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be an existing regular non-symlink file")
    case_id = _safe_identifier(case_id, "case_id")
    family = _safe_identifier(family, "family")
    if output.exists():
        raise FileExistsError(f"validation manifest already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        relative_source = source.relative_to(output.parent)
    except ValueError as exc:
        raise ValueError(
            "output manifest must be in the source directory or one of its parent directories"
        ) from exc

    device: dict[str, str] = {}
    for key, value in (
        ("manufacturer", manufacturer),
        ("model", model),
        ("firmware", firmware),
    ):
        if value is not None:
            device[key] = _safe_identifier(value, key)

    digest = hash_file(source, ("sha256",))["sha256"]
    payload: dict[str, Any] = {
        "schema_version": 1,
        "corpus_id": f"restricted-{case_id}",
        "description": "Private/restricted real-recorder validation case. Do not publish without authorization.",
        "cases": [
            {
                "case_id": case_id,
                "source": relative_source.as_posix(),
                "family": family,
                "provenance": "restricted",
                "redistributable": False,
                "source_sha256": digest,
                "expectations": [
                    {
                        "kind": "source_hash",
                        "expected": {"sha256": digest},
                    }
                ],
                "notes": list(notes),
                "device": device,
            }
        ],
        "private_case_notice": [
            "This manifest records metadata and hashes only; Vidrensic does not upload the source.",
            "Add format/recovery expectations only after ground truth is independently established.",
            "Keep restricted manifests and evidence outside the public repository unless redistribution is authorized.",
        ],
    }

    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"partial validation manifest already exists: {partial}")
    try:
        with partial.open("x", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        partial.replace(output)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise

    return PrivateCaseManifest(
        path=output,
        case_id=case_id,
        source=source,
        source_sha256=digest,
        family=family,
    )
