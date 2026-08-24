from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os


PRIVATE_FILE_MODE = 0o600
PRIVATE_DIR_MODE = 0o700


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_private_json(
    output: Path,
    payload: Any,
    *,
    allow_replace: bool = True,
) -> Path:
    """Atomically write JSON with owner-only permissions.

    This helper is intended for local forensic reports containing source paths,
    device identifiers, offsets, hashes, or examiner-generated diagnostics. It
    deliberately does not provide encryption at rest or secure deletion.
    """

    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".partial")

    if not allow_replace and output.exists():
        raise FileExistsError(f"output already exists: {output}")
    if temp.exists():
        raise FileExistsError(f"partial output already exists: {temp}")

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(temp, flags, PRIVATE_FILE_MODE)
    try:
        os.fchmod(fd, PRIVATE_FILE_MODE)
        with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.close(fd)
        fd = -1

        if allow_replace:
            os.replace(temp, output)
        else:
            # Hard-linking publishes the fully-written inode only when the final
            # destination does not already exist. This preserves fail-closed
            # no-overwrite semantics without a check-then-replace race.
            os.link(temp, output)
            os.unlink(temp)
        os.chmod(output, PRIVATE_FILE_MODE)
        _fsync_directory(output.parent)
        return output
    except Exception:
        if fd >= 0:
            os.close(fd)
        try:
            temp.unlink()
        except FileNotFoundError:
            pass
        raise
