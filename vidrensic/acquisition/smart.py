from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
import json
import shutil
import subprocess
import tempfile

from vidrensic.acquisition.linux import require_safe_source
from vidrensic.core.private_io import atomic_write_private_json


MAX_SMARTCTL_STDOUT_BYTES = 4 * 1024 * 1024
MAX_SMARTCTL_STDERR_BYTES = 256 * 1024


@dataclass(frozen=True)
class SmartSnapshot:
    source: Path
    captured: bool
    smartctl_returncode: int | None
    model: str | None
    serial: str | None
    firmware: str | None
    capacity_bytes: int | None
    logical_sector_size: int | None
    physical_sector_size: int | None
    rotation_rate: int | None
    smart_passed: bool | None
    temperature_celsius: int | float | None
    power_on_hours: int | None
    reallocated_sectors: int | None
    pending_sectors: int | None
    offline_uncorrectable: int | None
    reported_uncorrectable: int | None
    raw: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "captured": self.captured,
            "smartctl_returncode": self.smartctl_returncode,
            "model": self.model,
            "serial": self.serial,
            "firmware": self.firmware,
            "capacity_bytes": self.capacity_bytes,
            "logical_sector_size": self.logical_sector_size,
            "physical_sector_size": self.physical_sector_size,
            "rotation_rate": self.rotation_rate,
            "smart_passed": self.smart_passed,
            "temperature_celsius": self.temperature_celsius,
            "power_on_hours": self.power_on_hours,
            "reallocated_sectors": self.reallocated_sectors,
            "pending_sectors": self.pending_sectors,
            "offline_uncorrectable": self.offline_uncorrectable,
            "reported_uncorrectable": self.reported_uncorrectable,
            "raw": self.raw,
            "error": self.error,
        }

    def write_json(self, output: Path) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=True)


def _nested(data: dict[str, Any], *path: str) -> Any:
    value: Any = data
    for part in path:
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _ata_attribute(data: dict[str, Any], attribute_id: int) -> int | None:
    table = _nested(data, "ata_smart_attributes", "table")
    if not isinstance(table, list):
        return None
    for entry in table:
        if not isinstance(entry, dict) or entry.get("id") != attribute_id:
            continue
        raw = entry.get("raw")
        if isinstance(raw, dict):
            value = raw.get("value")
            if isinstance(value, int):
                return value
    return None


def _parse_snapshot(
    source: Path,
    data: dict[str, Any],
    *,
    returncode: int,
    error: str | None,
) -> SmartSnapshot:
    user_capacity = data.get("user_capacity")
    capacity = user_capacity.get("bytes") if isinstance(user_capacity, dict) else None
    sector_size = data.get("logical_block_size")
    physical_sector_size = data.get("physical_block_size")
    smart_status = data.get("smart_status")
    passed = smart_status.get("passed") if isinstance(smart_status, dict) else None
    temperature = data.get("temperature")
    current_temp = temperature.get("current") if isinstance(temperature, dict) else None
    power_on_time = data.get("power_on_time")
    hours = power_on_time.get("hours") if isinstance(power_on_time, dict) else None

    return SmartSnapshot(
        source=source,
        captured=bool(data),
        smartctl_returncode=returncode,
        model=data.get("model_name") or data.get("model_family"),
        serial=data.get("serial_number"),
        firmware=data.get("firmware_version"),
        capacity_bytes=capacity if isinstance(capacity, int) else None,
        logical_sector_size=sector_size if isinstance(sector_size, int) else None,
        physical_sector_size=physical_sector_size if isinstance(physical_sector_size, int) else None,
        rotation_rate=data.get("rotation_rate") if isinstance(data.get("rotation_rate"), int) else None,
        smart_passed=passed if isinstance(passed, bool) else None,
        temperature_celsius=current_temp if isinstance(current_temp, (int, float)) else None,
        power_on_hours=hours if isinstance(hours, int) else _ata_attribute(data, 9),
        reallocated_sectors=_ata_attribute(data, 5),
        pending_sectors=_ata_attribute(data, 197),
        offline_uncorrectable=_ata_attribute(data, 198),
        reported_uncorrectable=_ata_attribute(data, 187),
        raw=data,
        error=error,
    )


def _uncaptured_snapshot(
    source: Path,
    error: str,
    *,
    returncode: int | None = None,
) -> SmartSnapshot:
    return SmartSnapshot(
        source=source,
        captured=False,
        smartctl_returncode=returncode,
        model=None,
        serial=None,
        firmware=None,
        capacity_bytes=None,
        logical_sector_size=None,
        physical_sector_size=None,
        rotation_rate=None,
        smart_passed=None,
        temperature_celsius=None,
        power_on_hours=None,
        reallocated_sectors=None,
        pending_sectors=None,
        offline_uncorrectable=None,
        reported_uncorrectable=None,
        raw={},
        error=error,
    )


def _read_bounded_output(handle: BinaryIO, *, limit: int, label: str) -> bytes:
    handle.flush()
    handle.seek(0)
    data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"smartctl {label} exceeded safety limit of {limit} bytes")
    return data


def capture_smart(source: Path, *, timeout: float = 30.0) -> SmartSnapshot:
    """Capture SMART/device identity using bounded smartctl JSON output.

    smartctl stdout/stderr are directed to temporary files instead of
    ``subprocess.PIPE`` so a broken tool/device cannot make Python buffer an
    unbounded diagnostic stream in memory. The files are then read back through
    explicit limits before JSON decoding.
    """

    if timeout <= 0:
        raise ValueError("timeout must be positive")

    info = require_safe_source(source)
    executable = shutil.which("smartctl")
    if executable is None:
        return _uncaptured_snapshot(info.path, "smartctl is not installed")

    try:
        with tempfile.TemporaryFile(mode="w+b") as stdout_file:
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                try:
                    proc = subprocess.run(
                        [executable, "-j", "-a", str(info.path)],
                        stdout=stdout_file,
                        stderr=stderr_file,
                        timeout=timeout,
                        check=False,
                    )
                except subprocess.TimeoutExpired as exc:
                    return _uncaptured_snapshot(
                        info.path,
                        f"smartctl timed out after {exc.timeout} seconds",
                    )

                try:
                    stdout = _read_bounded_output(
                        stdout_file,
                        limit=MAX_SMARTCTL_STDOUT_BYTES,
                        label="stdout",
                    )
                    stderr_raw = _read_bounded_output(
                        stderr_file,
                        limit=MAX_SMARTCTL_STDERR_BYTES,
                        label="stderr",
                    )
                except ValueError as exc:
                    return _uncaptured_snapshot(
                        info.path,
                        str(exc),
                        returncode=proc.returncode,
                    )
    except OSError as exc:
        return _uncaptured_snapshot(info.path, f"smartctl execution I/O failed: {exc}")

    try:
        stdout_text = stdout.decode("utf-8")
    except UnicodeDecodeError:
        return _uncaptured_snapshot(
            info.path,
            "smartctl stdout is not valid UTF-8 JSON",
            returncode=proc.returncode,
        )
    stderr = stderr_raw.decode("utf-8", errors="replace").strip() or None

    try:
        data = json.loads(stdout_text) if stdout_text.strip() else {}
    except json.JSONDecodeError:
        data = {}
        if stderr is None:
            stderr = "smartctl returned invalid JSON"
    if not isinstance(data, dict):
        data = {}
        if stderr is None:
            stderr = "smartctl JSON root is not an object"
    if not data and stderr is None and proc.returncode != 0:
        stderr = f"smartctl exited with status {proc.returncode}"
    return _parse_snapshot(
        info.path,
        data,
        returncode=proc.returncode,
        error=stderr,
    )
