from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

from vidrensic.acquisition.linux import require_safe_source


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
        return self.size


def check_capacity(plan: AcquisitionPlan, *, reserve_bytes: int = 2 * 1024**3) -> None:
    plan.validate()
    required = plan.required_output_bytes
    if required is None:
        return
    parent = plan.output.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(parent).free
    if free < required + reserve_bytes:
        raise OSError(
            f"insufficient free space: need at least {required + reserve_bytes} bytes, have {free}"
        )


def execute_plan(
    plan: AcquisitionPlan,
    *,
    allow_write_enabled_source: bool = False,
    timeout: float | None = None,
) -> list[subprocess.CompletedProcess[str]]:
    """Execute ddrescue without shell interpolation.

    Existing map files are intentionally reused so interrupted acquisitions can
    resume. The evidence source is safety-checked immediately before execution.
    """

    plan.validate()
    require_safe_source(plan.source, allow_write_enabled=allow_write_enabled_source)
    check_capacity(plan)
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    plan.mapfile.parent.mkdir(parents=True, exist_ok=True)

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
