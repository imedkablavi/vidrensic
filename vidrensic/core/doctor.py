from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
import os
import platform
import shutil
import subprocess
import sys
import tempfile

from cryptography import __version__ as cryptography_version

from vidrensic import __product__, __version__


MAX_TOOL_VERSION_STDOUT_BYTES = 64 * 1024
MAX_TOOL_VERSION_STDERR_BYTES = 64 * 1024


@dataclass(frozen=True)
class ToolCheck:
    name: str
    available: bool
    path: str | None
    version: str | None
    capability: str
    mandatory_for_core: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "path": self.path,
            "version": self.version,
            "capability": self.capability,
            "mandatory_for_core": self.mandatory_for_core,
            "error": self.error,
        }


@dataclass(frozen=True)
class DoctorReport:
    product: str
    version: str
    python: str
    platform: str
    linux: bool
    cryptography: str
    tools: tuple[ToolCheck, ...]

    @property
    def core_ready(self) -> bool:
        return self.linux and all(check.available for check in self.tools if check.mandatory_for_core)

    def capability_ready(self, capability: str) -> bool:
        checks = [check for check in self.tools if check.capability == capability]
        return bool(checks) and all(check.available for check in checks)

    def to_dict(self) -> dict:
        return {
            "schema_version": 1,
            "product": self.product,
            "version": self.version,
            "python": self.python,
            "platform": self.platform,
            "linux": self.linux,
            "cryptography": self.cryptography,
            "core_ready": self.core_ready,
            "capabilities": {
                name: self.capability_ready(name)
                for name in sorted({check.capability for check in self.tools})
            },
            "tools": [check.to_dict() for check in self.tools],
        }


TOOL_SPECS = (
    ("findmnt", ("--version",), "source-safety", True),
    ("lsblk", ("--version",), "source-safety", True),
    ("blockdev", ("--version",), "source-safety", True),
    ("ddrescue", ("--version",), "acquisition", False),
    ("smartctl", ("--version",), "smart", False),
    ("ffprobe", ("-version",), "media-qc", False),
    ("ffmpeg", ("-version",), "media-qc", False),
)


def _read_bounded_version_output(
    handle: BinaryIO,
    *,
    limit: int,
) -> tuple[bytes, bool]:
    if limit <= 0:
        raise ValueError("version output limit must be positive")
    handle.flush()
    handle.seek(0)
    data = handle.read(limit + 1)
    if len(data) > limit:
        return data[:limit], True
    return data, False


def _resolve_doctor_tool(path: str) -> Path:
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"resolved tool path is unavailable: {path}") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise PermissionError(f"resolved tool path is not an executable regular file: {resolved}")
    return resolved


def _first_version_line(name: str, path: str, args: tuple[str, ...]) -> ToolCheck:
    capability = next(spec[2] for spec in TOOL_SPECS if spec[0] == name)
    mandatory = next(spec[3] for spec in TOOL_SPECS if spec[0] == name)
    try:
        resolved = _resolve_doctor_tool(path)
        with tempfile.TemporaryFile(mode="w+b") as stdout_file:
            with tempfile.TemporaryFile(mode="w+b") as stderr_file:
                proc = subprocess.run(
                    [str(resolved), *args],
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    timeout=5,
                    check=False,
                )
                stdout, stdout_truncated = _read_bounded_version_output(
                    stdout_file,
                    limit=MAX_TOOL_VERSION_STDOUT_BYTES,
                )
                stderr, stderr_truncated = _read_bounded_version_output(
                    stderr_file,
                    limit=MAX_TOOL_VERSION_STDERR_BYTES,
                )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ToolCheck(name, False, path, None, capability, mandatory, type(exc).__name__)

    display_path = str(resolved)
    if stdout_truncated or stderr_truncated:
        return ToolCheck(
            name,
            False,
            display_path,
            None,
            capability,
            mandatory,
            "version command output exceeded safety limit",
        )

    selected = stdout if stdout.strip() else stderr
    text = selected.decode("utf-8", errors="replace")
    lines = text.splitlines()
    first = lines[0].strip() if lines else None
    if proc.returncode != 0:
        return ToolCheck(
            name,
            False,
            display_path,
            first,
            capability,
            mandatory,
            f"version command returned {proc.returncode}",
        )
    return ToolCheck(name, True, display_path, first, capability, mandatory)


def run_doctor() -> DoctorReport:
    checks: list[ToolCheck] = []
    for name, args, capability, mandatory in TOOL_SPECS:
        path = shutil.which(name)
        if path is None:
            checks.append(ToolCheck(name, False, None, None, capability, mandatory, "not found in PATH"))
            continue
        checks.append(_first_version_line(name, path, args))

    return DoctorReport(
        product=__product__,
        version=__version__,
        python=sys.version.split()[0],
        platform=platform.platform(),
        linux=sys.platform.startswith("linux"),
        cryptography=cryptography_version,
        tools=tuple(checks),
    )
