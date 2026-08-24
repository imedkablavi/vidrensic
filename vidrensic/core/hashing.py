from __future__ import annotations

from collections.abc import Callable, Iterable
from hashlib import new as new_hash
from pathlib import Path
import os
import stat

from vidrensic.core.models import HashSet


ProgressCallback = Callable[[int, int], None]


class FileChangedDuringHashError(RuntimeError):
    """Raised when a forensic artifact cannot be shown stable for one hash pass."""


def hash_file(
    path: Path,
    algorithms: Iterable[str] = ("sha256", "sha512"),
    *,
    block_size: int = 8 * 1024 * 1024,
    progress: ProgressCallback | None = None,
) -> dict[str, str]:
    if block_size <= 0:
        raise ValueError("block_size must be positive")
    algs = tuple(dict.fromkeys(algorithms))
    if not algs:
        raise ValueError("at least one hash algorithm is required")

    digests = {name: new_hash(name) for name in algs}
    total = path.stat().st_size
    done = 0
    with path.open("rb", buffering=0) as fh:
        while True:
            chunk = fh.read(block_size)
            if not chunk:
                break
            for digest in digests.values():
                digest.update(chunk)
            done += len(chunk)
            if progress is not None:
                progress(done, total)
    return {name: digest.hexdigest() for name, digest in digests.items()}


def forensic_hashes(path: Path, *, include_sha512: bool = True) -> HashSet:
    algorithms = ("sha256", "sha512") if include_sha512 else ("sha256",)
    result = hash_file(path, algorithms)
    return HashSet(sha256=result["sha256"], sha512=result.get("sha512"))


def _stable_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def hash_file_stable(
    path: Path,
    algorithms: Iterable[str] = ("sha256", "sha512"),
    *,
    block_size: int = 8 * 1024 * 1024,
    progress: ProgressCallback | None = None,
) -> dict[str, str]:
    """Hash one regular file and fail if its identity changes during the pass.

    The file is opened once and hashed through that descriptor. POSIX
    ``O_NOFOLLOW`` is used when available so the acquisition artifact cannot be
    silently redirected through a symlink at open time. File descriptor metadata
    is compared before/after the read, the byte count must match the final size,
    and the pathname must still resolve to the same device/inode after hashing.

    This is a local consistency check against ordinary concurrent mutation or
    replacement. It is not filesystem snapshotting and does not defend against a
    privileged adversary capable of racing every verification operation.
    """

    if block_size <= 0:
        raise ValueError("block_size must be positive")
    algs = tuple(dict.fromkeys(algorithms))
    if not algs:
        raise ValueError("at least one hash algorithm is required")

    resolved = path.expanduser().absolute()
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(resolved, flags)
    except OSError as exc:
        raise FileChangedDuringHashError(
            f"unable to open stable regular file for hashing: {resolved}: {exc}"
        ) from exc

    digests = {name: new_hash(name) for name in algs}
    done = 0
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise FileChangedDuringHashError(
                f"forensic hash target is not a regular file: {resolved}"
            )
        total = before.st_size
        with os.fdopen(fd, "rb", buffering=0, closefd=False) as handle:
            while True:
                chunk = handle.read(block_size)
                if not chunk:
                    break
                for digest in digests.values():
                    digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)

        after = os.fstat(fd)
        if _stable_identity(before) != _stable_identity(after):
            raise FileChangedDuringHashError(
                f"forensic hash target changed during hashing: {resolved}"
            )
        if done != after.st_size:
            raise FileChangedDuringHashError(
                f"forensic hash byte count changed during hashing: read={done} size={after.st_size}"
            )
        try:
            pathname_after = os.stat(resolved, follow_symlinks=False)
        except OSError as exc:
            raise FileChangedDuringHashError(
                f"forensic hash pathname became unavailable after hashing: {resolved}"
            ) from exc
        if stat.S_ISLNK(pathname_after.st_mode):
            raise FileChangedDuringHashError(
                f"forensic hash pathname became a symlink during hashing: {resolved}"
            )
        if not stat.S_ISREG(pathname_after.st_mode):
            raise FileChangedDuringHashError(
                f"forensic hash pathname is no longer a regular file: {resolved}"
            )
        if (pathname_after.st_dev, pathname_after.st_ino) != (after.st_dev, after.st_ino):
            raise FileChangedDuringHashError(
                f"forensic hash pathname was replaced during hashing: {resolved}"
            )
    finally:
        os.close(fd)

    return {name: digest.hexdigest() for name, digest in digests.items()}


def forensic_hashes_stable(path: Path, *, include_sha512: bool = True) -> HashSet:
    algorithms = ("sha256", "sha512") if include_sha512 else ("sha256",)
    result = hash_file_stable(path, algorithms)
    return HashSet(sha256=result["sha256"], sha512=result.get("sha512"))
