from __future__ import annotations

from collections.abc import Callable, Iterable
from hashlib import new as new_hash
from pathlib import Path

from vidrensic.core.models import HashSet


ProgressCallback = Callable[[int, int], None]


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
