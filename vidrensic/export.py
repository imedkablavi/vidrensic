from __future__ import annotations

from hashlib import sha256, sha512
from pathlib import Path
from typing import Any
import os
import stat

from vidrensic.core.private_io import PRIVATE_FILE_MODE, atomic_write_private_json


EXPORT_CHUNK_BYTES = 8 * 1024 * 1024


class ExportIntegrityError(RuntimeError):
    """Raised when an evidence export cannot be shown byte-for-byte stable."""


def _open_regular_source(path: Path) -> int:
    resolved = path.expanduser().resolve(strict=True)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(resolved, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"source must be a regular file: {resolved}")
    except Exception:
        os.close(fd)
        raise
    return fd


def _copy_and_hash(source: Path, destination: Path) -> tuple[dict[str, str], int]:
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().resolve()
    if source == destination:
        raise ValueError("source and destination must be different files")
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_fd = _open_regular_source(source)
    output_fd: int | None = None
    sha256_digest = sha256()
    sha512_digest = sha512()
    total = 0
    try:
        before = os.fstat(source_fd)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        output_fd = os.open(destination, flags, PRIVATE_FILE_MODE)
        with os.fdopen(source_fd, "rb", buffering=0, closefd=False) as source_handle:
            with os.fdopen(output_fd, "wb", buffering=0, closefd=False) as output_handle:
                while True:
                    chunk = source_handle.read(EXPORT_CHUNK_BYTES)
                    if not chunk:
                        break
                    output_handle.write(chunk)
                    sha256_digest.update(chunk)
                    sha512_digest.update(chunk)
                    total += len(chunk)
                output_handle.flush()
                os.fsync(output_handle.fileno())

        after = os.fstat(source_fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ExportIntegrityError("source changed during export")
        if total != after.st_size:
            raise ExportIntegrityError(
                f"source size changed during export: copied={total} size={after.st_size}"
            )
    except Exception:
        if output_fd is not None:
            try:
                os.close(output_fd)
            except OSError:
                pass
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        try:
            os.close(source_fd)
        except OSError:
            pass
        if output_fd is not None:
            try:
                os.close(output_fd)
            except OSError:
                pass

    os.chmod(destination, PRIVATE_FILE_MODE)
    expected = {
        "sha256": sha256_digest.hexdigest(),
        "sha512": sha512_digest.hexdigest(),
    }
    return expected, total


def _hash_output(path: Path) -> dict[str, str]:
    digests = {"sha256": sha256(), "sha512": sha512()}
    with path.open("rb", buffering=0) as handle:
        while True:
            chunk = handle.read(EXPORT_CHUNK_BYTES)
            if not chunk:
                break
            for digest in digests.values():
                digest.update(chunk)
    return {name: digest.hexdigest() for name, digest in digests.items()}


def export_evidence(
    source: Path,
    destination: Path,
    manifest: Path,
    *,
    profile: str = "master",
    replace: bool = False,
) -> dict[str, Any]:
    """Create and verify an exact byte-for-byte evidence copy plus manifest."""

    if profile not in {"master", "review"}:
        raise ValueError("profile must be one of: master, review")
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError("source must be a regular non-symlink file")
    if destination.exists():
        if not replace:
            raise FileExistsError(f"destination already exists: {destination}")
        raise ValueError("replace is not supported for evidence exports; choose a new destination")

    copied_hashes, copied_bytes = _copy_and_hash(source, destination)
    output_hashes = _hash_output(destination)
    if copied_hashes != output_hashes:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise ExportIntegrityError("export verification failed; destination hash does not match source bytes")

    output_stat = destination.stat()
    if output_stat.st_size != copied_bytes:
        raise ExportIntegrityError("export verification failed; destination size differs from source")

    payload: dict[str, Any] = {
        "schema_version": 1,
        "export_profile": profile,
        "copy": {
            "byte_for_byte": True,
            "verified": True,
            "chunk_size_bytes": EXPORT_CHUNK_BYTES,
        },
        "source": {
            "path": str(source),
            "size_bytes": copied_bytes,
            "sha256": copied_hashes["sha256"],
            "sha512": copied_hashes["sha512"],
        },
        "destination": {
            "path": str(destination),
            "size_bytes": output_stat.st_size,
            "sha256": output_hashes["sha256"],
            "sha512": output_hashes["sha512"],
        },
    }
    atomic_write_private_json(manifest, payload, allow_replace=False)
    return payload
