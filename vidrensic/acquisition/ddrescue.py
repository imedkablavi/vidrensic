from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

from vidrensic.acquisition.binding import ensure_source_binding
from vidrensic.acquisition.linux import require_safe_source
from vidrensic.core.audit import AuditLog
from vidrensic.core.hashing import hash_file


FAT32_MAX_FILE_BYTES = 4 * 1024**3 - 1
MAX_DDRESCUE_VERSION_BYTES = 64 * 1024


@dataclass(frozen=True)
class ExecutableIdentity:
    """Observed identity for one resolved native executable.

    The SHA-256/stat tuple binds Vidrensic's execution session to the observed
    bytes at a canonical path. It is provenance evidence, not a vendor
    signature or proof that the binary is trustworthy.
    """

    name: str
    path: Path
    sha256: str
    size_bytes: int
    filesystem_device: int
    inode: int
    mtime_ns: int
    version: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "filesystem_device": self.filesystem_device,
            "inode": self.inode,
            "mtime_ns": self.mtime_ns,
            "version": self.version,
            "claim_limit": (
                "Observed executable bytes/path for this execution session; "
                "not vendor authenticity, package provenance, or a code-signing assertion."
            ),
        }

    def require_unchanged(self) -> None:
        """Fail closed if the executable path no longer identifies the same bytes."""

        try:
            stat_result = self.path.stat()
        except OSError as exc:
            raise RuntimeError(f"{self.name} executable became unavailable: {self.path}") from exc
        if not self.path.is_file():
            raise RuntimeError(f"{self.name} executable is no longer a regular file: {self.path}")
        observed = (
            stat_result.st_size,
            stat_result.st_dev,
            stat_result.st_ino,
            stat_result.st_mtime_ns,
        )
        expected = (
            self.size_bytes,
            self.filesystem_device,
            self.inode,
            self.mtime_ns,
        )
        if observed != expected:
            raise RuntimeError(f"{self.name} executable identity changed during acquisition")
        current_sha256 = hash_file(self.path, ("sha256",))["sha256"]
        if current_sha256 != self.sha256:
            raise RuntimeError(f"{self.name} executable bytes changed during acquisition")


def _bounded_tool_version(executable: Path) -> str | None:
    """Read one bounded version line without buffering arbitrary subprocess output."""

    try:
        with tempfile.TemporaryFile(mode="w+b") as output:
            proc = subprocess.run(
                [str(executable), "--version"],
                stdout=output,
                stderr=output,
                timeout=5,
                check=False,
            )
            output.flush()
            output.seek(0)
            raw = output.read(MAX_DDRESCUE_VERSION_BYTES + 1)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(raw) > MAX_DDRESCUE_VERSION_BYTES:
        return None
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if not lines:
        return None
    value = lines[0].strip()
    if not value:
        return None
    return value if proc.returncode == 0 else f"{value} (version command exit {proc.returncode})"


def resolve_ddrescue_executable() -> ExecutableIdentity:
    """Resolve GNU ddrescue once and capture the exact observed executable identity."""

    discovered = shutil.which("ddrescue")
    if discovered is None:
        raise FileNotFoundError("GNU ddrescue executable was not found in PATH")
    try:
        path = Path(discovered).expanduser().resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"resolved ddrescue executable is unavailable: {discovered}") from exc
    if not path.is_file() or not os.access(path, os.X_OK):
        raise PermissionError(f"resolved ddrescue path is not an executable regular file: {path}")
    stat_result = path.stat()
    return ExecutableIdentity(
        name="ddrescue",
        path=path,
        sha256=hash_file(path, ("sha256",))["sha256"],
        size_bytes=stat_result.st_size,
        filesystem_device=stat_result.st_dev,
        inode=stat_result.st_ino,
        mtime_ns=stat_result.st_mtime_ns,
        version=_bounded_tool_version(path),
    )


def tool_audit_path(mapfile: Path) -> Path:
    """Return the private hash-chained native-tool provenance log for a map file."""

    resolved = mapfile.expanduser().resolve()
    return resolved.with_name(resolved.name + ".tool-audit.jsonl")


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

    def first_pass_command(self, executable: str | Path = "ddrescue") -> list[str]:
        self.validate()
        cmd = [str(executable), "-f", "-n"]
        if self.offset:
            cmd += ["-i", str(self.offset), "-o", "0"]
        if self.size is not None:
            cmd += ["-s", str(self.size)]
        if self.direct:
            cmd.append("-d")
        cmd += [str(self.source), str(self.output), str(self.mapfile)]
        return cmd

    def retry_command(self, executable: str | Path = "ddrescue") -> list[str] | None:
        self.validate()
        if self.retry_passes <= 0:
            return None
        cmd = [str(executable), "-f", "-d", f"-r{self.retry_passes}"]
        if self.offset:
            cmd += ["-i", str(self.offset), "-o", "0"]
        if self.size is not None:
            cmd += ["-s", str(self.size)]
        cmd += [str(self.source), str(self.output), str(self.mapfile)]
        return cmd

    @property
    def required_output_bytes(self) -> int | None:
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
    executable_identity: ExecutableIdentity | None = None,
) -> list[subprocess.CompletedProcess[str]]:
    """Execute ddrescue using one resolved executable identity for every pass.

    New acquisitions write a source-binding sidecar next to the ddrescue map
    before ddrescue starts. A resume verifies that sidecar before reusing the map.
    Legacy map/output state without a sidecar is fail-closed on first encounter.

    The ddrescue binary is resolved once to a canonical absolute path, hashed,
    and checked immediately before and after every pass. A separate owner-only,
    hash-chained tool audit is written beside the map for every execution
    session, including the observed executable path/version/hash and pass return
    codes. The hash chain is tamper-evident relative to a known tail, not a
    digital signature or trusted timestamp.
    """

    plan.validate()
    existing_state = plan.output.exists() or plan.mapfile.exists()
    info = require_safe_source(plan.source, allow_write_enabled=allow_write_enabled_source)
    plan.validate_source_geometry(info.size_bytes)
    check_capacity(plan, source_size=info.size_bytes)
    plan.output.parent.mkdir(parents=True, exist_ok=True)
    plan.mapfile.parent.mkdir(parents=True, exist_ok=True)

    tool = executable_identity or resolve_ddrescue_executable()
    if tool.name != "ddrescue":
        raise ValueError("executable_identity must describe ddrescue")
    tool.require_unchanged()

    ensure_source_binding(
        source=plan.source,
        output=plan.output,
        mapfile=plan.mapfile,
        offset=plan.offset,
        requested_size=plan.size,
        existing_acquisition_state=existing_state,
    )

    audit = AuditLog(tool_audit_path(plan.mapfile))
    session_details = {
        "tool": tool.to_dict(),
        "source": str(plan.source.expanduser().resolve()),
        "output": str(plan.output.expanduser().resolve()),
        "mapfile": str(plan.mapfile.expanduser().resolve()),
        "offset": plan.offset,
        "size": plan.size,
        "retry_passes": plan.retry_passes,
        "direct": plan.direct,
        "claim_limit": (
            "Tool audit records the executable observed by Vidrensic and command results. "
            "It is not a software-vendor signature, trusted timestamp, or proof of chain of custody."
        ),
    }
    audit.append("ddrescue.session.started", session_details)

    commands = [plan.first_pass_command(tool.path)]
    retry = plan.retry_command(tool.path)
    if retry is not None:
        commands.append(retry)

    results: list[subprocess.CompletedProcess[str]] = []
    try:
        for pass_index, cmd in enumerate(commands, start=1):
            tool.require_unchanged()
            result = subprocess.run(cmd, text=True, check=False, timeout=timeout)
            tool.require_unchanged()
            results.append(result)
            audit.append(
                "ddrescue.pass.finished",
                {
                    "pass_index": pass_index,
                    "return_code": result.returncode,
                    "executable_path": str(tool.path),
                    "executable_sha256": tool.sha256,
                },
            )
            if result.returncode != 0:
                break
    except Exception as exc:
        audit.append(
            "ddrescue.session.failed",
            {
                "completed_return_codes": [item.returncode for item in results],
                "error_type": type(exc).__name__,
                "error": str(exc)[:4096],
                "executable_path": str(tool.path),
                "executable_sha256": tool.sha256,
            },
        )
        raise

    audit.append(
        "ddrescue.session.finished",
        {
            "return_codes": [item.returncode for item in results],
            "all_zero": bool(results) and all(item.returncode == 0 for item in results),
            "executable_path": str(tool.path),
            "executable_sha256": tool.sha256,
        },
    )
    return results
