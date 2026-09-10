from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import atomic_write_private_json


MAX_IDENTIFIER_CHARS = 128
MAX_NOTES = 128
MAX_NOTE_CHARS = 4 * 1024
PRIVATE_VALIDATION_FAMILIES = frozenset({
    "wfs",
    "dhav",
    "hikvision",
    "annexb",
    "mpegps",
    "generic",
})


@dataclass(frozen=True)
class PrivateCaseManifest:
    """Metadata for a restricted validation fixture; no evidence is copied."""

    path: Path
    case_id: str
    source: Path
    source_sha256: str
    source_size_bytes: int
    family: str


def _safe_text(value: str, field: str) -> str:
    value = value.strip()
    if not value or len(value) > MAX_IDENTIFIER_CHARS:
        raise ValueError(f"{field} must be 1-{MAX_IDENTIFIER_CHARS} characters")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field} contains invalid control characters")
    return value


def _bounded_notes(notes: Iterable[str]) -> list[str]:
    result: list[str] = []
    for index, note in enumerate(notes):
        if index >= MAX_NOTES:
            raise ValueError(f"notes exceeds {MAX_NOTES} entries")
        if not isinstance(note, str):
            raise ValueError("notes must contain strings only")
        note = note.strip()
        if not note:
            raise ValueError(f"notes[{index}] must be non-empty")
        if len(note) > MAX_NOTE_CHARS:
            raise ValueError(f"notes[{index}] exceeds {MAX_NOTE_CHARS} characters")
        if any(character in note for character in "\x00\r\n"):
            raise ValueError(f"notes[{index}] contains invalid control characters")
        result.append(note)
    return result


def create_private_case_manifest(
    source: Path,
    output: Path,
    *,
    case_id: str,
    family: str,
    manufacturer: str | None = None,
    model: str | None = None,
    firmware: str | None = None,
    notes: Iterable[str] = (),
) -> PrivateCaseManifest:
    """Create owner-only staging metadata for a restricted real-recorder fixture.

    The source evidence is never copied or uploaded. The resulting JSON is an
    internal staging manifest, not a real-recorder corpus admission record and
    not proof of recorder-family compatibility.
    """

    source_input = source.expanduser()
    if source_input.is_symlink():
        raise ValueError("source must be an existing regular non-symlink file")
    source = source_input.resolve(strict=True)
    output = output.expanduser().resolve()
    if not source.is_file():
        raise ValueError("source must be an existing regular non-symlink file")

    case_id = _safe_text(case_id, "case_id")
    family = _safe_text(family, "family")
    if family not in PRIVATE_VALIDATION_FAMILIES:
        allowed = ", ".join(sorted(PRIVATE_VALIDATION_FAMILIES))
        raise ValueError(f"family must be one of: {allowed}")
    if output.exists():
        raise FileExistsError(f"validation manifest already exists: {output}")
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
            device[key] = _safe_text(value, key)

    bounded_notes = _bounded_notes(notes)
    hashes = forensic_hashes_stable(source, include_sha512=False)
    source_size_bytes = source.stat().st_size
    payload: dict[str, Any] = {
        "schema_version": 1,
        "manifest_type": "private-validation-case",
        "case_id": case_id,
        "source": {
            "path": relative_source.as_posix(),
            "size_bytes": source_size_bytes,
            "sha256": hashes.sha256,
        },
        "family": family,
        "provenance": "restricted",
        "redistributable": False,
        "device": device,
        "notes": bounded_notes,
        "private_case_notice": [
            "This manifest records metadata and hashes only; Vidrensic does not upload or copy the source.",
            "Add recovery expectations only after ground truth is independently established.",
            "Do not publish this manifest or source unless redistribution is explicitly authorized.",
        ],
        "claim_boundary": (
            "This staging manifest does not establish recorder-family support, forensic admissibility, "
            "independent validation, or public real-recorder corpus admission."
        ),
    }

    atomic_write_private_json(output, payload, allow_replace=False)
    return PrivateCaseManifest(
        path=output,
        case_id=case_id,
        source=source,
        source_sha256=hashes.sha256,
        source_size_bytes=source_size_bytes,
        family=family,
    )
