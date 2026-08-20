from __future__ import annotations

from hashlib import sha256, sha512
from pathlib import Path


def hash_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> dict[str, str]:
    h256 = sha256()
    h512 = sha512()
    with path.open("rb", buffering=0) as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h256.update(chunk)
            h512.update(chunk)
    return {"sha256": h256.hexdigest(), "sha512": h512.hexdigest()}
