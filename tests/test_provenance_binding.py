from __future__ import annotations

from pathlib import Path

import pytest

from vidrensic.core.provenance import (
    SourceFingerprint,
    fingerprint_source,
    require_same_source,
)


def _block(
    *,
    size: int = 10_000,
    major: int = 8,
    minor: int = 16,
    inode: int = 100,
    filesystem_device: int = 200,
    serial: str | None = None,
    wwn: str | None = None,
) -> SourceFingerprint:
    return SourceFingerprint(
        path=Path(f"/dev/test{minor}"),
        size_bytes=size,
        is_block_device=True,
        read_only=True,
        mounted_at=(),
        inode=inode,
        filesystem_device=filesystem_device,
        block_major=major,
        block_minor=minor,
        mtime_ns=None,
        edge_sample_bytes=0,
        edge_sample_sha256=None,
        serial=serial,
        wwn=wwn,
        model="SyntheticDisk",
    )


def _regular(
    *,
    inode: int = 10,
    filesystem_device: int = 20,
    mtime_ns: int = 30,
    edge: str | None = None,
) -> SourceFingerprint:
    return SourceFingerprint(
        path=Path("/tmp/evidence.bin"),
        size_bytes=4096,
        is_block_device=False,
        read_only=None,
        mounted_at=(),
        inode=inode,
        filesystem_device=filesystem_device,
        block_major=None,
        block_minor=None,
        mtime_ns=mtime_ns,
        edge_sample_bytes=512 if edge is not None else 0,
        edge_sample_sha256=edge,
    )


def test_source_fingerprint_round_trip_and_identity_strengths() -> None:
    original = _block(serial="SER-1", wwn="WWN-1")
    loaded = SourceFingerprint.from_dict(original.to_dict())
    assert loaded == original
    assert loaded.identity_strength == "hardware-wwn"
    assert _block(serial="SER-1").identity_strength == "hardware-serial"
    assert _block().identity_strength == "device-node-fallback"
    assert _regular(edge="aa" * 32).identity_strength == "file-metadata-plus-edge-hash"
    assert _regular().identity_strength == "file-metadata"


def test_source_fingerprint_from_dict_rejects_invalid_shapes() -> None:
    with pytest.raises(ValueError, match="object"):
        SourceFingerprint.from_dict([])

    payload = _regular().to_dict()
    payload["mounted_at"] = "not-a-list"
    with pytest.raises(ValueError, match="mounted_at"):
        SourceFingerprint.from_dict(payload)


def test_block_identity_prefers_stable_ids_and_fails_closed_on_missing_or_changed_ids() -> None:
    assert _block(wwn="WWN-1", serial="SER-1", minor=16).same_evidence_identity(
        _block(wwn="WWN-1", serial="SER-2", minor=32)
    )
    assert not _block(wwn="WWN-1").same_evidence_identity(_block(wwn=None))
    assert not _block(wwn="WWN-1").same_evidence_identity(_block(wwn="WWN-2"))

    assert _block(serial="SER-1", minor=16).same_evidence_identity(
        _block(serial="SER-1", minor=32)
    )
    assert not _block(serial="SER-1").same_evidence_identity(_block(serial=None))
    assert not _block(serial="SER-1").same_evidence_identity(_block(serial="SER-2"))


def test_block_device_node_fallback_requires_same_observed_node_identity() -> None:
    before = _block()
    assert before.same_evidence_identity(_block())
    assert not before.same_evidence_identity(_block(minor=17))
    assert not before.same_evidence_identity(_block(inode=999))
    assert not before.same_evidence_identity(_block(filesystem_device=999))


def test_identity_rejects_geometry_or_source_type_changes() -> None:
    assert not _block(size=10_000).same_evidence_identity(_block(size=20_000))
    assert not _block().same_evidence_identity(_regular())


def test_regular_file_identity_requires_metadata_and_symmetric_edge_hash() -> None:
    digest = "ab" * 32
    before = _regular(edge=digest)
    assert before.same_evidence_identity(_regular(edge=digest))
    assert not before.same_evidence_identity(_regular(edge="cd" * 32))
    assert not before.same_evidence_identity(_regular(edge=None))
    assert not _regular(edge=None).same_evidence_identity(before)
    assert not before.same_evidence_identity(_regular(edge=digest, inode=11))
    assert not before.same_evidence_identity(_regular(edge=digest, filesystem_device=21))
    assert not before.same_evidence_identity(_regular(edge=digest, mtime_ns=31))
    assert _regular(edge=None).same_evidence_identity(_regular(edge=None))


def test_fingerprint_source_validates_sampling_bounds_and_missing_source(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 4096)

    with pytest.raises(ValueError, match="between 0 and 16 MiB"):
        fingerprint_source(source, edge_sample_bytes=-1)
    with pytest.raises(ValueError, match="between 0 and 16 MiB"):
        fingerprint_source(source, edge_sample_bytes=16 * 1024 * 1024 + 1)
    with pytest.raises(FileNotFoundError):
        fingerprint_source(tmp_path / "missing.bin")


def test_regular_file_fingerprint_edge_digest_is_stable_and_detects_change(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes((b"A" * 4096) + (b"B" * 4096))
    first = fingerprint_source(source, edge_sample_bytes=1024)
    second = fingerprint_source(source, edge_sample_bytes=1024)
    assert first.edge_sample_sha256 == second.edge_sample_sha256
    require_same_source(first, second)

    source.write_bytes((b"C" * 4096) + (b"D" * 4096))
    changed = fingerprint_source(source, edge_sample_bytes=1024)
    with pytest.raises(RuntimeError, match="identity changed"):
        require_same_source(first, changed)
