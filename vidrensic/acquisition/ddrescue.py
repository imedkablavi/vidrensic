from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from vidrensic.acquisition.linux import require_safe_source


FAT32_MAX_FILE_BYTES = 4 * 1024**3 - 1


@dataclass(frozen=True)
class AcquisitionPlan:
    source: Path
    output: Path
    mapfile: Path
    offset: int = 0
    size: int | None = None
    retry_passes: int = 0
    direct: bool = False

    def validate(self) -> None:
        if self.offset < 0:
            raise ValueError("offset cannot be negative")
        if self.size is not None and self.size <= 0:
            raise ValueError("size must be positive")
        if self.retry_passes < 0 or self.retry_passes > 5:
            raise ValueError("retry_passes must be between 0 and 5")
        if self.output.resolve() == self.source.resolve():
            raise ValueError("output cannot be the evidence source")
        if self.mapfile.resolve() == self.source.resolve():
            raise ValueError("mapfile cannot be the evidence source")
        if self.output.resolve() == self.mapfile.resolve():
            raise ValueError("output and mapfile must be different paths")

    def validate_source_geometry(self, source_size: int) -> int:
        """Return the expected logical output size after validating source bounds."""

        self.validate()
        if source_size <= 0:
            raise ValueError("source size must be positive")
        if self.offset >= source_size:
            raise ValueError("acquisition offset is at or beyond the source end")
        available = source_size - self.offset
        if self.size is not None:
            if self.size > available:
                raise ValueError(
                    f"requested acquisition size {self.size} exceeds {available} available source bytes"
                )
            return self.size
        return available

    def first_pass_command(self) -> list[str]:
        self.validate()
        cmd = ["ddrescue", "-f", "-n"]
        if self.offset:
            cmd += ["-i", str(self.offset), "-o", "0"]
        if self.size is not None:
            cmd += ["-s", str(self.size)]
        if self.direct:
            cmd.append("-d")
        cmd += [str(self.source), str(self.output), str(self.mapfile)]
        return cmd

    def retry_command(self) -> list[str] | None:
        self.validate()
        if self.retry_passes <= 0:
            return None
        cmd = ["ddrescue", "-f", "-d", f"-r{self.retry_passes}"]
        if self.offset:
            cmd += ["-i", str(self.offset), "-o", "0"]
        if self.size is not None:
            cmd += ["-s", str(self.size)]
        cmd += [str(self.source), str(self.output), str(self.mapfile)]
        return cmd

    @property
    def required_output_bytes(self) -> int | None:
        # Without source geometry, an unbounded acquisition cannot know its final
        # output size. Execution always resolves this with validate_source_geometry().
        return self.size

    @property
    def existing_output_bytes(self) -> int:
        try:
            return self.output.stat().st_size
        except FileNotFoundError:
            return 0

    @property
    def additional_required_bytes(self) -> int | None:
        required = self.required_output_bytes
        if required is None:
            return None
        return max(0, required - self.existing_output_bytes)


def _filesystem_type(path: Path) -> str | None:
    proc = subprocess.run(
        ["findmnt", "-n", "-o", "FSTYPE", "-T", str(path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip().lower()
    return value or None


def check_capacity(
    plan: AcquisitionPlan,
    *,
    source_size: int | None = None,
    reserve_bytes: int = 2 * 1024**3,
) -> None:
    """Preflight free space and common destination file-size limits.

    When source geometry is available, full/unbounded acquisitions are checked
    just as strictly as selective acquisitions. Existing partial output bytes are
    deducted so resumable ddrescue jobs do not require the full size twice.
    """

    plan.validate()
    if reserve_bytes < 0:
        raise ValueError("reserve_bytes cannot be negative")

    if source_size is None:
        required_total = plan.required_output_bytes
        if required_total is None:
            raise ValueError("source_size is required to preflight an unbounded acquisition")
    else:
        required_total = plan.validate_source_geometry(source_size)

    additional = max(0, required_total - plan.existing_output_bytes)
    parent = plan.output.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)

    fstype = _filesystem_type(parent)
    if fstype in {"vfat", "msdos", "fat", "fat32"} and required_total > FAT32_MAX_FILE_BYTES:
        raise OSError(
            f"destination filesystem {fstype} cannot safely hold a {required_total}-byte single image; "
            "use ext4/XFS/exFAT/another large-file filesystem or a segmented forensic format"
        )

    free = shutil.disk_usage(parent).free
    if free < additional + reserve_bytes:
        raise OSError(
            f"insufficient free space: need about {additional + reserve_bytes} additional bytes, "
            f"have {free}"
        )


def execute_plan(
    plan: AcquisitionPlan,
    *,
    allow_write_enabled_source: bool = False,
    timeout: float | None = None,
) -> list[subprocess.CompletedProcess[str]]:
    """Execute ddrescue without shell interpolation.

    Existing map files are intentionally reused so interrupted acquisitions can
    resume. Capacity preflight accounts for bytes already present in a partial
    output. The evidence source is safety-checked immediately before execution.
    """

    plan.validate()
    info = require_safe_source(plan.source, allow_write_enabled=allow_write_enabled_source)
    plan.validate_source_geometry(info.size_bytes)
    check_capacity(plan, source_size=info.size_bytes)
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    plan.mapfile.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("ddrescue") is None:
        raise FileNotFoundError("GNU ddrescue executable was not found in PATH")

    commands = [plan.first_pass_command()]
    retry = plan.retry_command()
    if retry is not None:
        commands.append(retry)

    results: list[subprocess.CompletedProcess[str]] = []
    for cmd in commands:
        result = subprocess.run(cmd, text=True, check=False, timeout=timeout)
        results.append(result)
        if result.returncode != 0:
            break
    return results
