from __future__ import annotations

from pathlib import Path
import json
import os
import stat

import pytest

from vidrensic.export import export_evidence


def test_export_creates_verified_byte_for_byte_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "exports" / "evidence.bin"
    manifest = tmp_path / "exports" / "evidence.json"
    source.write_bytes(bytes(range(256)) * 8)

    result = export_evidence(source, destination, manifest)

    assert destination.read_bytes() == source.read_bytes()
    assert result["copy"]["byte_for_byte"] is True
    assert result["copy"]["verified"] is True
    assert result["source"]["sha256"] == result["destination"]["sha256"]
    assert result["source"]["sha512"] == result["destination"]["sha512"]
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o600
    assert json.loads(manifest.read_text(encoding="utf-8"))["schema_version"] == 1


def test_export_refuses_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "evidence.bin"
    manifest = tmp_path / "evidence.json"
    source.write_bytes(b"source")
    destination.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        export_evidence(source, destination, manifest)

    assert destination.read_bytes() == b"keep"


def test_export_rejects_source_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    target = tmp_path / "target.bin"
    destination = tmp_path / "evidence.bin"
    manifest = tmp_path / "evidence.json"
    target.write_bytes(b"source")
    source.symlink_to(target)

    with pytest.raises(ValueError, match="regular non-symlink"):
        export_evidence(source, destination, manifest)


def test_export_rejects_same_source_and_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    manifest = tmp_path / "evidence.json"
    source.write_bytes(b"source")

    with pytest.raises(ValueError, match="different files"):
        export_evidence(source, source, manifest)
