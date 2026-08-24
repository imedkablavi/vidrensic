from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile


MAX_BLOCKDEV_STDOUT_BYTES = 64 * 1024
MAX_BLOCKDEV_STDERR_BYTES = 64 * 1024
MAX_LSBLK_IDS_STDOUT_BYTES = 2 * 1024 * 1024
MAX_LSBLK_IDENTITY_STDOUT_BYTES = 1024 * 1024
MAX_LSBLK_STDERR_BYTES = 256 * 1024
MAX_MOUNTINFO_BYTES = 32 * 1024 * 1024
MAX_MOUNTINFO_LINE_BYTES = 256 * 1024
_DEVICE_ID_RE = re.compile(r"^[0-9]+:[0-9]+$")


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


def _resolve_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"required Linux source-probe tool was not found: {name}")
    return str(Path(executable).resolve())


def _read_bounded(handle: BinaryIO, *, limit: int, label: str) -> bytes:
    handle.flush()
    handle.seek(0)
    data = handle.read(limit + 1)
    if len(data) > limit:
        raise OSError(f"{label} exceeded safety limit of {limit} bytes")
    return data


def _run_bounded_tool(
    name: str,
    args: list[str],
    *,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int,
) -> tuple[int, bytes, bytes]:
    """Run one probe tool without PIPE-backed unbounded output buffering."""

    executable = _resolve_tool(name)
    try:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file:
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                try:
                    proc = subprocess.run(
                        [executable, *args],
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        timeout=timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise OSError(f"{name} timed out after {exc.timeout} seconds") from exc
                stdout = _read_bounded(
                    stdout_file,
                    limit=stdout_limit,
                    label=f"{name} stdout",
                )
                stderr = _read_bounded(
                    stderr_file,
                    limit=stderr_limit,
                    label=f"{name} stderr",
                )
    except OSError:
        raise
    return proc.returncode, stdout, stderr


def _bounded_error(stderr: bytes, fallback: str) -> str:
    value = stderr.decode("utf-8", errors="replace").strip()
    return value or fallback


def _block_size(path: Path) -> int:
    returncode, stdout, stderr = _run_bounded_tool(
        "blockdev",
        ["--getsize64", str(path)],
        timeout=15,
        stdout_limit=MAX_BLOCKDEV_STDOUT_BYTES,
        stderr_limit=MAX_BLOCKDEV_STDERR_BYTES,
    )
    if returncode != 0:
        raise OSError(_bounded_error(stderr, f"unable to determine size of {path}"))
    try:
        value = int(stdout.decode("ascii").strip())
    except (UnicodeDecodeError, ValueError) as exc:
        raise OSError("blockdev returned an invalid size") from exc
    if value <= 0:
        raise OSError("blockdev returned a non-positive source size")
    return value


def _sysfs_ro(major: int, minor: int) -> bool | None:
    link = Path("/sys/dev/block") / f"{major}:{minor}"
    if not link.exists():
        return None
    try:
        resolved = link.resolve()
        with (resolved / "ro").open("rb") as handle:
            raw = handle.read(17)
    except OSError:
        return None
    if len(raw) > 16:
        return None
    value = raw.decode("ascii", errors="ignore").strip()
    if value == "1":
        return True
    if value == "0":
        return False
    return None


def _device_ids(path: Path, major: int, minor: int) -> set[str]:
    """Return source and descendant MAJ:MIN values, failing closed on probe errors.

    Descendant enumeration is part of the mounted-device safety decision. A
    failed/truncated/malformed `lsblk` result must therefore not be interpreted as
    "no descendants".
    """

    returncode, stdout, stderr = _run_bounded_tool(
        "lsblk",
        ["-nr", "-o", "MAJ:MIN", str(path)],
        timeout=15,
        stdout_limit=MAX_LSBLK_IDS_STDOUT_BYTES,
        stderr_limit=MAX_LSBLK_STDERR_BYTES,
    )
    if returncode != 0:
        raise OSError(_bounded_error(stderr, "lsblk descendant enumeration failed"))
    try:
        text = stdout.decode("ascii")
    except UnicodeDecodeError as exc:
        raise OSError("lsblk descendant enumeration was not ASCII") from exc

    ids = {f"{major}:{minor}"}
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        if _DEVICE_ID_RE.fullmatch(value) is None:
            raise OSError(f"lsblk returned malformed MAJ:MIN value: {value!r}")
        ids.add(value)
    return ids


def _mounted_paths(
    device_ids: set[str],
    *,
    mountinfo: Path = Path("/proc/self/mountinfo"),
) -> tuple[str, ...]:
    """Stream mountinfo with explicit byte/line bounds.

    Failure to inspect mountinfo for a block-device source is not equivalent to
    an unmounted source, so malformed or unavailable state raises instead of
    returning an empty mount list.
    """

    if not mountinfo.exists():
        raise OSError(f"mount information is unavailable: {mountinfo}")
    mounts: list[str] = []
    total = 0
    line_no = 0
    with mountinfo.open("rb") as handle:
        while True:
            raw = handle.readline(MAX_MOUNTINFO_LINE_BYTES + 1)
            if not raw:
                break
            line_no += 1
            total += len(raw)
            if total > MAX_MOUNTINFO_BYTES:
                raise OSError(
                    f"mountinfo exceeded safety limit of {MAX_MOUNTINFO_BYTES} bytes"
                )
            if len(raw) > MAX_MOUNTINFO_LINE_BYTES:
                raise OSError(
                    f"mountinfo line {line_no} exceeded safety limit of "
                    f"{MAX_MOUNTINFO_LINE_BYTES} bytes"
                )
            line = raw.decode("utf-8", errors="replace")
            fields = line.split()
            if len(fields) < 5:
                raise OSError(f"mountinfo line {line_no} is malformed")
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
    """Return bounded, best-effort serial/WWN/model hints without changing the device.

    Identity hints improve resume binding but are not required to make the mount
    safety decision. Probe failure therefore degrades to the documented weaker
    device-node fallback instead of inventing identifiers.
    """

    try:
        returncode, stdout, _stderr = _run_bounded_tool(
            "lsblk",
            ["-J", "-d", "-o", "SERIAL,WWN,MODEL", str(path)],
            timeout=15,
            stdout_limit=MAX_LSBLK_IDENTITY_STDOUT_BYTES,
            stderr_limit=MAX_LSBLK_STDERR_BYTES,
        )
    except OSError:
        return None, None, None
    if returncode != 0:
        return None, None, None
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
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
