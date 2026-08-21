from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import stat

from vidrensic.acquisition.linux import inspect_source


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
        }

    def same_evidence_identity(self, other: SourceFingerprint) -> bool:
        common = (
            self.size_bytes == other.size_bytes
            and self.is_block_device == other.is_block_device
            and self.inode == other.inode
            and self.filesystem_device == other.filesystem_device
            and self.block_major == other.block_major
            and self.block_minor == other.block_minor
        )
        if not common:
            return False
        if not self.is_block_device and self.mtime_ns != other.mtime_ns:
            return False
        if self.edge_sample_sha256 is not None or other.edge_sample_sha256 is not None:
            return self.edge_sample_sha256 == other.edge_sample_sha256
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
    )


def require_same_source(previous: SourceFingerprint, current: SourceFingerprint) -> None:
    if not previous.same_evidence_identity(current):
        raise RuntimeError("evidence source identity changed; refusing to resume against a different source")
