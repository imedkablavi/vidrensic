from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    is_block_device: bool
    read_only: bool | None
    size_bytes: int | None


def inspect_source(path: Path) -> SourceInfo:
    st = path.stat()
    is_block = os.path.exists(path) and (st.st_mode & 0o170000) == 0o060000
    ro = None
    size = st.st_size if not is_block else None
    if is_block:
        name = path.name
        sys_ro = Path("/sys/class/block") / name / "ro"
        if sys_ro.exists():
            ro = sys_ro.read_text(encoding="ascii").strip() == "1"
        sys_size = Path("/sys/class/block") / name / "size"
        if sys_size.exists():
            sectors = int(sys_size.read_text(encoding="ascii").strip())
            size = sectors * 512
    return SourceInfo(path=path, is_block_device=is_block, read_only=ro, size_bytes=size)


def require_read_only_device(info: SourceInfo) -> None:
    if not info.is_block_device:
        return
    if info.read_only is not True:
        raise RuntimeError(f"Refusing acquisition: {info.path} is not confirmed read-only")
