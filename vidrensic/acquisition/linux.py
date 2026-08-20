from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import stat
import subprocess


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    exists: bool
    is_block_device: bool
    size_bytes: int
    read_only: bool | None
    mounted_at: tuple[str, ...]
    major: int | None = None
    minor: int | None = None

    @property
    def safe_for_forensic_read(self) -> bool:
        if not self.exists:
            return False
        if not self.is_block_device:
            return True
        return self.read_only is True and not self.mounted_at


def _block_size(path: Path) -> int:
    proc = subprocess.run(
        ["blockdev", "--getsize64", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise OSError(proc.stderr.strip() or f"unable to determine size of {path}")
    return int(proc.stdout.strip())


def _sysfs_ro(major: int, minor: int) -> bool | None:
    link = Path("/sys/dev/block") / f"{major}:{minor}"
    if not link.exists():
        return None
    try:
        resolved = link.resolve()
        value = (resolved / "ro").read_text(encoding="ascii").strip()
    except OSError:
        return None
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _mounted_paths(path: Path, major: int | None, minor: int | None) -> tuple[str, ...]:
    mounts: list[str] = []
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return ()
    wanted = f"{major}:{minor}" if major is not None and minor is not None else None
    for line in mountinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        dev_id = fields[2]
        mount_point = fields[4].replace("\\040", " ")
        if wanted is not None and dev_id == wanted:
            mounts.append(mount_point)
    return tuple(sorted(set(mounts)))


def inspect_source(path: Path) -> SourceInfo:
    path = path.expanduser().resolve()
    if not path.exists():
        return SourceInfo(path, False, False, 0, None, ())

    st = path.stat()
    is_block = stat.S_ISBLK(st.st_mode)
    if is_block:
        major = os.major(st.st_rdev)
        minor = os.minor(st.st_rdev)
        size = _block_size(path)
        ro = _sysfs_ro(major, minor)
        mounts = _mounted_paths(path, major, minor)
    else:
        major = minor = None
        size = st.st_size
        ro = None
        mounts = ()

    return SourceInfo(
        path=path,
        exists=True,
        is_block_device=is_block,
        size_bytes=size,
        read_only=ro,
        mounted_at=mounts,
        major=major,
        minor=minor,
    )


def require_safe_source(path: Path, *, allow_write_enabled: bool = False) -> SourceInfo:
    info = inspect_source(path)
    if not info.exists:
        raise FileNotFoundError(path)
    if info.is_block_device:
        if info.mounted_at:
            raise PermissionError(
                f"evidence device is mounted at {', '.join(info.mounted_at)}; unmount before acquisition"
            )
        if info.read_only is not True and not allow_write_enabled:
            state = "unknown" if info.read_only is None else "write-enabled"
            raise PermissionError(
                f"evidence block device read-only state is {state}; refusing by default"
            )
    return info
