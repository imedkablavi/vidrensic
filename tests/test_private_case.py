from __future__ import annotations

from pathlib import Path
import json
import stat

import pytest

from vidrensic.validation.private_case import (
    MAX_NOTES,
    MAX_NOTE_CHARS,
    create_private_case_manifest,
)


def test_private_case_manifest_is_owner_only_and_hashes_source_stably(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "recorder-image.raw"
    source.parent.mkdir()
    source.write_bytes(b"fixture-bytes")
    output = tmp_path / "private-case.json"

    manifest = create_private_case_manifest(
        source,
        output,
        case_id="lab-wfs-001",
        family="wfs",
        manufacturer="Example",
        model="Recorder-1",
        firmware="1.0",
        notes=("restricted lab fixture", "ground truth pending independent review"),
    )

    assert manifest.path == output.resolve()
    assert manifest.source == source.resolve()
    assert manifest.source_sha256
    assert manifest.source_size_bytes == len(b"fixture-bytes")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["manifest_type"] == "private-validation-case"
    assert data["case_id"] == "lab-wfs-001"
    assert data["source"]["path"] == "evidence/recorder-image.raw"
    assert data["source"]["sha256"] == manifest.source_sha256
    assert data["provenance"] == "restricted"
    assert data["redistributable"] is False
    assert data["device"] == {
        "manufacturer": "Example",
        "model": "Recorder-1",
        "firmware": "1.0",
    }
    assert source.read_bytes() == b"fixture-bytes"


def test_private_case_rejects_symlink_source(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    target = tmp_path / "target.raw"
    target.write_bytes(b"fixture")
    try:
        source.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="regular non-symlink"):
        create_private_case_manifest(
            source,
            tmp_path / "manifest.json",
            case_id="case-1",
            family="generic",
        )


def test_private_case_requires_output_in_source_directory_or_parent(tmp_path: Path) -> None:
    source = tmp_path / "evidence" / "source.raw"
    source.parent.mkdir()
    source.write_bytes(b"fixture")

    with pytest.raises(ValueError, match="source directory or one of its parent"):
        create_private_case_manifest(
            source,
            tmp_path / "outside" / "manifest.json",
            case_id="case-1",
            family="generic",
        )


def test_private_case_rejects_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"fixture")
    output = tmp_path / "manifest.json"
    output.write_text("existing", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        create_private_case_manifest(
            source,
            output,
            case_id="case-1",
            family="generic",
        )


def test_private_case_bounds_notes_and_identifiers(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"fixture")

    with pytest.raises(ValueError, match="notes exceeds"):
        create_private_case_manifest(
            source,
            tmp_path / "too-many.json",
            case_id="case-1",
            family="generic",
            notes=["ok"] * (MAX_NOTES + 1),
        )

    with pytest.raises(ValueError, match=r"notes\[0\] exceeds"):
        create_private_case_manifest(
            source,
            tmp_path / "too-long.json",
            case_id="case-1",
            family="generic",
            notes=["x" * (MAX_NOTE_CHARS + 1)],
        )

    with pytest.raises(ValueError, match="case_id contains invalid control"):
        create_private_case_manifest(
            source,
            tmp_path / "bad-id.json",
            case_id="bad\nid",
            family="generic",
        )


def test_private_case_rejects_invalid_note_types(tmp_path: Path) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"fixture")

    with pytest.raises(ValueError, match="notes must contain strings only"):
        create_private_case_manifest(
            source,
            tmp_path / "bad-note.json",
            case_id="case-1",
            family="generic",
            notes=["ok", 123],  # type: ignore[list-item]
        )
