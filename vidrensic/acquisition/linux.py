from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
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
    serial: str | None = None
    wwn: str | None = None
    model: str | None = None

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
        capture_output=True,
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


def _device_ids(path: Path, major: int, minor: int) -> set[str]:
    """Return source and descendant MAJ:MIN values (partitions/LVs when lsblk reports them)."""

    ids = {f"{major}:{minor}"}
    proc = subprocess.run(
        ["lsblk", "-nr", "-o", "MAJ:MIN", str(path)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            value = line.strip()
            if value and ":" in value:
                ids.add(value)
    return ids


def _mounted_paths(device_ids: set[str]) -> tuple[str, ...]:
    mounts: list[str] = []
    mountinfo = Path("/proc/self/mountinfo")
    if not mountinfo.exists():
        return ()
    for line in mountinfo.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        dev_id = fields[2]
        mount_point = fields[4].replace("\\040", " ")
        if dev_id in device_ids:
            mounts.append(mount_point)
    return tuple(sorted(set(mounts)))


def _clean_identity(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _block_identity(path: Path) -> tuple[str | None, str | None, str | None]:
    """Return best-effort serial/WWN/model hints without changing the device.

    These fields improve resume identity across device-node renumbering, but some
    USB bridges, virtual devices and storage stacks legitimately expose none of
    them. Callers must retain a weaker-identity path for those cases rather than
    inventing identifiers.
    """

    try:
        proc = subprocess.run(
            ["lsblk", "-J", "-d", "-o", "SERIAL,WWN,MODEL", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None, None
    if proc.returncode != 0 or len(proc.stdout) > 1024 * 1024:
        return None, None, None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, None, None
    rows = payload.get("blockdevices") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return None, None, None
    row = rows[0]
    return (
        _clean_identity(row.get("serial")),
        _clean_identity(row.get("wwn")),
        _clean_identity(row.get("model")),
    )


def inspect_source(path: Path) -> SourceInfo:
    path = path.expanduser().resolve()
    if not path.exists():
        return SourceInfo(path, False, False, 0, None, ())

    st = path.stat()
    is_block = stat.S_ISBLK(st.st_mode)
    serial = wwn = model = None
    if is_block:
        major = os.major(st.st_rdev)
        minor = os.minor(st.st_rdev)
        size = _block_size(path)
        ro = _sysfs_ro(major, minor)
        mounts = _mounted_paths(_device_ids(path, major, minor))
        serial, wwn, model = _block_identity(path)
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
        serial=serial,
        wwn=wwn,
        model=model,
    )


def require_safe_source(path: Path, *, allow_write_enabled: bool = False) -> SourceInfo:
    info = inspect_source(path)
    if not info.exists:
        raise FileNotFoundError(path)
    if info.is_block_device:
        if info.mounted_at:
            mounted = ", ".join(info.mounted_at)
            raise PermissionError(
                f"evidence device or descendant is mounted at {mounted}; unmount before acquisition"
            )
        if info.read_only is not True and not allow_write_enabled:
            state = "unknown" if info.read_only is None else "write-enabled"
            raise PermissionError(
                f"evidence block device read-only state is {state}; refusing by default"
            )
    return info
