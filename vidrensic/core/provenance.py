from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
import os
import stat

from vidrensic.acquisition.linux import inspect_source


def _required_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"source fingerprint {field} must be an integer")
    if value < minimum:
        raise ValueError(f"source fingerprint {field} must be >= {minimum}")
    return value


def _optional_int(value: Any, field: str, *, minimum: int = 0) -> int | None:
    if value is None:
        return None
    return _required_int(value, field, minimum=minimum)


def _optional_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source fingerprint {field} must be a non-empty string or null")
    return value.strip()


@dataclass(frozen=True)
class SourceFingerprint:
    path: Path
    size_bytes: int
    is_block_device: bool
    read_only: bool | None
    mounted_at: tuple[str, ...]
    inode: int
    filesystem_device: int
    block_major: int | None
    block_minor: int | None
    mtime_ns: int | None
    edge_sample_bytes: int
    edge_sample_sha256: str | None
    serial: str | None = None
    wwn: str | None = None
    model: str | None = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "is_block_device": self.is_block_device,
            "read_only": self.read_only,
            "mounted_at": list(self.mounted_at),
            "inode": self.inode,
            "filesystem_device": self.filesystem_device,
            "block_major": self.block_major,
            "block_minor": self.block_minor,
            "mtime_ns": self.mtime_ns,
            "edge_sample_bytes": self.edge_sample_bytes,
            "edge_sample_sha256": self.edge_sample_sha256,
            "serial": self.serial,
            "wwn": self.wwn,
            "model": self.model,
            "identity_strength": self.identity_strength,
        }

    @classmethod
    def from_dict(cls, value: Any) -> SourceFingerprint:
        if not isinstance(value, dict):
            raise ValueError("source fingerprint must be an object")
        path_value = value.get("path")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError("source fingerprint path must be a non-empty string")
        mounted = value.get("mounted_at", [])
        if not isinstance(mounted, list) or not all(isinstance(item, str) for item in mounted):
            raise ValueError("source fingerprint mounted_at must be a string list")
        is_block = value.get("is_block_device")
        if not isinstance(is_block, bool):
            raise ValueError("source fingerprint is_block_device must be boolean")
        read_only = value.get("read_only")
        if read_only is not None and not isinstance(read_only, bool):
            raise ValueError("source fingerprint read_only must be boolean or null")

        size_bytes = _required_int(value.get("size_bytes"), "size_bytes", minimum=1)
        inode = _required_int(value.get("inode"), "inode")
        filesystem_device = _required_int(value.get("filesystem_device"), "filesystem_device")
        block_major = _optional_int(value.get("block_major"), "block_major")
        block_minor = _optional_int(value.get("block_minor"), "block_minor")
        mtime_ns = _optional_int(value.get("mtime_ns"), "mtime_ns")
        edge_sample_bytes = _required_int(
            value.get("edge_sample_bytes", 0),
            "edge_sample_bytes",
        )
        if edge_sample_bytes > 16 * 1024 * 1024:
            raise ValueError("source fingerprint edge_sample_bytes exceeds 16 MiB")
        edge_hash = value.get("edge_sample_sha256")
        if edge_hash is not None:
            if not isinstance(edge_hash, str) or len(edge_hash) != 64:
                raise ValueError("source fingerprint edge_sample_sha256 must be 64 hex characters")
            edge_hash = edge_hash.lower()
            if any(character not in "0123456789abcdef" for character in edge_hash):
                raise ValueError("source fingerprint edge_sample_sha256 must be hexadecimal")
        if edge_sample_bytes > 0 and edge_hash is None:
            raise ValueError("source fingerprint edge sample bytes require an edge SHA-256")
        if edge_sample_bytes == 0 and edge_hash is not None:
            raise ValueError("source fingerprint edge SHA-256 requires non-zero sample bytes")
        if is_block and (block_major is None or block_minor is None):
            raise ValueError("block source fingerprint requires major/minor identifiers")
        if is_block and mtime_ns is not None:
            raise ValueError("block source fingerprint must not persist mtime_ns")

        return cls(
            path=Path(path_value).expanduser().resolve(),
            size_bytes=size_bytes,
            is_block_device=is_block,
            read_only=read_only,
            mounted_at=tuple(mounted),
            inode=inode,
            filesystem_device=filesystem_device,
            block_major=block_major,
            block_minor=block_minor,
            mtime_ns=mtime_ns,
            edge_sample_bytes=edge_sample_bytes,
            edge_sample_sha256=edge_hash,
            serial=_optional_string(value.get("serial"), "serial"),
            wwn=_optional_string(value.get("wwn"), "wwn"),
            model=_optional_string(value.get("model"), "model"),
        )

    @property
    def identity_strength(self) -> str:
        if self.is_block_device:
            if self.wwn:
                return "hardware-wwn"
            if self.serial:
                return "hardware-serial"
            return "device-node-fallback"
        if self.edge_sample_sha256:
            return "file-metadata-plus-edge-hash"
        return "file-metadata"

    def same_evidence_identity(self, other: SourceFingerprint) -> bool:
        if self.size_bytes != other.size_bytes or self.is_block_device != other.is_block_device:
            return False

        if self.is_block_device:
            # Prefer stable hardware identity over volatile /dev numbering. If a
            # stable identifier existed in either observation, it must exist and
            # match in both observations; silently falling back would weaken an
            # already-established binding.
            if self.wwn is not None or other.wwn is not None:
                return self.wwn is not None and self.wwn == other.wwn
            if self.serial is not None or other.serial is not None:
                return self.serial is not None and self.serial == other.serial
            return (
                self.block_major == other.block_major
                and self.block_minor == other.block_minor
                and self.inode == other.inode
                and self.filesystem_device == other.filesystem_device
            )

        common = (
            self.inode == other.inode
            and self.filesystem_device == other.filesystem_device
            and self.mtime_ns == other.mtime_ns
        )
        if not common:
            return False
        if self.edge_sample_sha256 is not None or other.edge_sample_sha256 is not None:
            return (
                self.edge_sample_sha256 is not None
                and self.edge_sample_sha256 == other.edge_sample_sha256
            )
        return True


def _edge_digest(path: Path, size: int, sample_bytes: int) -> str:
    fd = os.open(path, os.O_RDONLY)
    digest = sha256()
    try:
        width = min(sample_bytes, size)
        digest.update(b"VIDRENSIC-EDGE-SAMPLE-v1\x00")
        digest.update(size.to_bytes(16, "little", signed=False))
        if width:
            digest.update(os.pread(fd, width, 0))
            if size > width:
                digest.update(os.pread(fd, width, max(0, size - width)))
    finally:
        os.close(fd)
    return digest.hexdigest()


def fingerprint_source(
    path: Path,
    *,
    edge_sample_bytes: int = 0,
) -> SourceFingerprint:
    if edge_sample_bytes < 0 or edge_sample_bytes > 16 * 1024 * 1024:
        raise ValueError("edge_sample_bytes must be between 0 and 16 MiB")

    info = inspect_source(path)
    if not info.exists:
        raise FileNotFoundError(path)
    st = os.stat(info.path, follow_symlinks=False)
    block = stat.S_ISBLK(st.st_mode)
    major = os.major(st.st_rdev) if block else None
    minor = os.minor(st.st_rdev) if block else None
    edge_hash = (
        _edge_digest(info.path, info.size_bytes, edge_sample_bytes)
        if edge_sample_bytes
        else None
    )
    return SourceFingerprint(
        path=info.path,
        size_bytes=info.size_bytes,
        is_block_device=info.is_block_device,
        read_only=info.read_only,
        mounted_at=info.mounted_at,
        inode=st.st_ino,
        filesystem_device=st.st_dev,
        block_major=major,
        block_minor=minor,
        mtime_ns=None if block else st.st_mtime_ns,
        edge_sample_bytes=edge_sample_bytes,
        edge_sample_sha256=edge_hash,
        serial=info.serial,
        wwn=info.wwn,
        model=info.model,
    )


def require_same_source(previous: SourceFingerprint, current: SourceFingerprint) -> None:
    if not previous.same_evidence_identity(current):
        raise RuntimeError("evidence source identity changed; refusing to resume against a different source")
