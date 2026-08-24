from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os

import pytest

from vidrensic.core.hashing import FileChangedDuringHashError, hash_file_stable


def test_stable_hash_matches_sha256_for_unchanged_regular_file(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    payload = b"0123456789abcdef"
    path.write_bytes(payload)

    result = hash_file_stable(path, ("sha256",), block_size=4)

    assert result == {"sha256": sha256(payload).hexdigest()}


def test_stable_hash_rejects_in_place_mutation_during_read(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"A" * 64)
    changed = False

    def mutate(done: int, total: int) -> None:
        nonlocal changed
        assert total == 64
        if not changed and done >= 8:
            changed = True
            with path.open("r+b", buffering=0) as handle:
                handle.seek(32)
                handle.write(b"B" * 8)
                handle.flush()
                os.fsync(handle.fileno())

    with pytest.raises(FileChangedDuringHashError, match="changed during hashing"):
        hash_file_stable(path, ("sha256",), block_size=8, progress=mutate)
    assert changed is True


def test_stable_hash_rejects_path_replacement_while_old_fd_is_open(tmp_path: Path) -> None:
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"A" * 64)
    replacement = tmp_path / "replacement.bin"
    replacement.write_bytes(b"B" * 64)
    replaced = False

    def replace_path(done: int, total: int) -> None:
        nonlocal replaced
        assert total == 64
        if not replaced and done >= 8:
            replaced = True
            os.replace(replacement, path)

    with pytest.raises(FileChangedDuringHashError, match="pathname was replaced"):
        hash_file_stable(path, ("sha256",), block_size=8, progress=replace_path)
    assert replaced is True
    assert path.read_bytes() == b"B" * 64


def test_stable_hash_rejects_symlink_target(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"evidence")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target.name)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    with pytest.raises(FileChangedDuringHashError, match="unable to open stable regular file"):
        hash_file_stable(link, ("sha256",))
