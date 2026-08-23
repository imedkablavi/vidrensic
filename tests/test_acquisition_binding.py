from __future__ import annotations

from pathlib import Path
import stat

import pytest

from vidrensic.acquisition.binding import (
    CONFIRMED_LEGACY,
    CONFIRMED_NEW,
    PENDING_LEGACY,
    confirm_legacy_binding,
    ensure_source_binding,
    load_source_binding,
    source_binding_path,
)
from vidrensic.core.provenance import SourceFingerprint


def _ensure(source: Path, output: Path, mapfile: Path, *, existing: bool = False):
    return ensure_source_binding(
        source=source,
        output=output,
        mapfile=mapfile,
        offset=0,
        requested_size=None,
        existing_acquisition_state=existing,
    )


def test_new_regular_file_acquisition_writes_confirmed_private_binding(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    output = tmp_path / "image.bin"
    mapfile = tmp_path / "image.map"

    binding = _ensure(source, output, mapfile)
    path = source_binding_path(mapfile)
    assert path.is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert binding.state == CONFIRMED_NEW
    assert binding.source.edge_sample_sha256 is not None
    assert binding.source.edge_sample_bytes > 0
    assert binding.source.identity_strength == "file-metadata-plus-edge-hash"
    loaded = load_source_binding(path)
    assert loaded.source.edge_sample_sha256 == binding.source.edge_sample_sha256


def test_bound_regular_file_refuses_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    output = tmp_path / "image.bin"
    mapfile = tmp_path / "image.map"
    _ensure(source, output, mapfile)

    source.write_bytes(b"B" * 200_000)
    with pytest.raises(RuntimeError, match="identity changed"):
        _ensure(source, output, mapfile)


def test_binding_refuses_geometry_or_output_changes(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    output = tmp_path / "image.bin"
    mapfile = tmp_path / "image.map"
    _ensure(source, output, mapfile)

    with pytest.raises(RuntimeError, match="output path changed"):
        ensure_source_binding(
            source=source,
            output=tmp_path / "other.bin",
            mapfile=mapfile,
            offset=0,
            requested_size=None,
            existing_acquisition_state=True,
        )
    with pytest.raises(RuntimeError, match="geometry changed"):
        ensure_source_binding(
            source=source,
            output=output,
            mapfile=mapfile,
            offset=4096,
            requested_size=None,
            existing_acquisition_state=True,
        )


def test_legacy_state_requires_explicit_confirmation_before_resume(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    output = tmp_path / "image.bin"
    output.write_bytes(b"partial")
    mapfile = tmp_path / "image.map"
    mapfile.write_text("legacy map placeholder\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="ddrescue was NOT executed"):
        _ensure(source, output, mapfile, existing=True)

    path = source_binding_path(mapfile)
    pending = load_source_binding(path)
    assert pending.state == PENDING_LEGACY
    assert pending.confirmed_utc is None

    with pytest.raises(RuntimeError, match="pending confirmation"):
        _ensure(source, output, mapfile, existing=True)

    confirmed = confirm_legacy_binding(path)
    assert confirmed.state == CONFIRMED_LEGACY
    assert confirmed.confirmed_utc is not None
    resumed = _ensure(source, output, mapfile, existing=True)
    assert resumed.state == CONFIRMED_LEGACY


def _fingerprint(*, wwn: str | None, serial: str | None, major: int, minor: int) -> SourceFingerprint:
    return SourceFingerprint(
        path=Path(f"/dev/test{minor}"),
        size_bytes=10_000,
        is_block_device=True,
        read_only=True,
        mounted_at=(),
        inode=100 + minor,
        filesystem_device=200 + minor,
        block_major=major,
        block_minor=minor,
        mtime_ns=None,
        edge_sample_bytes=0,
        edge_sample_sha256=None,
        serial=serial,
        wwn=wwn,
        model="RecorderDisk",
    )


def test_block_hardware_identity_survives_device_node_renumbering() -> None:
    before = _fingerprint(wwn="wwn-123", serial="serial-1", major=8, minor=16)
    after = _fingerprint(wwn="wwn-123", serial="serial-1", major=8, minor=32)
    assert before.same_evidence_identity(after)
    assert before.identity_strength == "hardware-wwn"


def test_block_hardware_identity_mismatch_fails_closed() -> None:
    before = _fingerprint(wwn="wwn-123", serial="serial-1", major=8, minor=16)
    after = _fingerprint(wwn="wwn-999", serial="serial-1", major=8, minor=16)
    assert not before.same_evidence_identity(after)
