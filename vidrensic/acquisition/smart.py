from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import shutil
import subprocess

from vidrensic.acquisition.linux import require_safe_source


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
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


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


def capture_smart(source: Path, *, timeout: float = 30.0) -> SmartSnapshot:
    """Capture SMART/device identity using smartctl JSON without modifying the source."""

    info = require_safe_source(source)
    executable = shutil.which("smartctl")
    if executable is None:
        return SmartSnapshot(
            source=info.path,
            captured=False,
            smartctl_returncode=None,
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
            error="smartctl is not installed",
        )

    try:
        proc = subprocess.run(
            [executable, "-j", "-a", str(info.path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SmartSnapshot(
            source=info.path,
            captured=False,
            smartctl_returncode=None,
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
            error=f"smartctl timed out after {exc.timeout} seconds",
        )

    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        data = {}
    stderr = proc.stderr.strip() or None
    if not data and stderr is None and proc.returncode != 0:
        stderr = f"smartctl exited with status {proc.returncode}"
    return _parse_snapshot(
        info.path,
        data,
        returncode=proc.returncode,
        error=stderr,
    )
