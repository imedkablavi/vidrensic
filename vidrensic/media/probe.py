from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, BinaryIO
import json
import os
import shutil
import subprocess
import tempfile


MAX_PROBE_JSON_BYTES = 2 * 1024 * 1024
# Compatibility alias for callers/tests that treated the former text limit as a public constant.
MAX_PROBE_JSON_CHARS = MAX_PROBE_JSON_BYTES
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_DIAGNOSTIC_CHARS = MAX_DIAGNOSTIC_BYTES
MAX_MEDIA_STDOUT_BYTES = 4 * 1024


@dataclass(frozen=True)
class MediaToolResult:
    executable: Path
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool


@dataclass(frozen=True)
class VideoProbe:
    path: Path
    duration: float | None
    codec: str | None
    width: int | None
    height: int | None
    avg_frame_rate: float | None
    r_frame_rate: float | None
    stream_count: int
    raw: dict[str, Any]


def _rate(value: str | None) -> float | None:
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return None


def _bounded_text(value: str, *, limit: int = MAX_DIAGNOSTIC_CHARS) -> str:
    if limit <= 0:
        raise ValueError("diagnostic limit must be positive")
    if len(value) <= limit:
        return value.strip()
    return value[:limit].rstrip() + "\n[diagnostic output truncated]"


def _resolve_media_tool(name: str) -> Path:
    discovered = shutil.which(name)
    if discovered is None:
        raise FileNotFoundError(f"required media tool was not found in PATH: {name}")
    try:
        resolved = Path(discovered).expanduser().resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"resolved media tool is unavailable: {discovered}") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise PermissionError(f"resolved media tool is not an executable regular file: {resolved}")
    return resolved


def _read_bounded_output(
    handle: BinaryIO,
    *,
    limit: int,
) -> tuple[bytes, bool]:
    if limit < 0:
        raise ValueError("output limit cannot be negative")
    handle.flush()
    handle.seek(0)
    data = handle.read(limit + 1)
    if len(data) > limit:
        return data[:limit], True
    return data, False


def run_media_tool_bounded(
    name: str,
    args: list[str],
    *,
    timeout: float,
    stdout_limit: int,
    stderr_limit: int = MAX_DIAGNOSTIC_BYTES,
) -> MediaToolResult:
    """Run one media utility without PIPE-backed unbounded Python buffering.

    The executable is resolved to an absolute regular executable path immediately
    before the invocation. stdout/stderr are directed to temporary files and only
    bounded prefixes are read back into Python memory. This bounds process-output
    memory use; it is not executable authenticity, sandboxing, or a guarantee that
    a hostile native process cannot consume temporary-storage capacity while it runs.
    """

    if timeout <= 0:
        raise ValueError("media tool timeout must be positive")
    if stdout_limit < 0 or stderr_limit < 0:
        raise ValueError("media tool output limits cannot be negative")

    executable = _resolve_media_tool(name)
    with tempfile.TemporaryFile(mode="w+b") as stdout_file:
        with tempfile.TemporaryFile(mode="w+b") as stderr_file:
            proc = subprocess.run(
                [str(executable), *args],
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                timeout=timeout,
                check=False,
            )
            stdout, stdout_truncated = _read_bounded_output(
                stdout_file,
                limit=stdout_limit,
            )
            stderr, stderr_truncated = _read_bounded_output(
                stderr_file,
                limit=stderr_limit,
            )

    return MediaToolResult(
        executable=executable,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _diagnostic_text(raw: bytes, *, truncated: bool) -> str:
    value = raw.decode("utf-8", errors="replace").strip()
    if truncated:
        suffix = "[diagnostic output truncated]"
        return f"{value}\n{suffix}" if value else suffix
    return value


def probe_video(path: Path, *, timeout: float = 30.0) -> VideoProbe:
    if timeout <= 0:
        raise ValueError("ffprobe timeout must be positive")
    path = path.expanduser().resolve()
    result = run_media_tool_bounded(
        "ffprobe",
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        timeout=timeout,
        stdout_limit=MAX_PROBE_JSON_BYTES,
        stderr_limit=MAX_DIAGNOSTIC_BYTES,
    )
    if result.returncode != 0:
        error = _diagnostic_text(result.stderr, truncated=result.stderr_truncated)
        raise RuntimeError(error or f"ffprobe failed for {path}")
    if result.stdout_truncated:
        raise RuntimeError(
            f"ffprobe JSON exceeded safety limit ({MAX_PROBE_JSON_BYTES} bytes)"
        )
    try:
        stdout = result.stdout.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("ffprobe JSON is not valid UTF-8") from exc
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe returned invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("ffprobe JSON root must be an object")

    streams = data.get("streams") or []
    if not isinstance(streams, list):
        raise RuntimeError("ffprobe streams field must be a list")
    video = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    format_info = data.get("format") or {}
    if not isinstance(format_info, dict):
        format_info = {}

    duration = None
    raw_duration = format_info.get("duration")
    if raw_duration not in (None, "N/A"):
        try:
            duration = float(raw_duration)
        except (TypeError, ValueError):
            duration = None

    return VideoProbe(
        path=path,
        duration=duration,
        codec=video.get("codec_name") if video else None,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        avg_frame_rate=_rate(video.get("avg_frame_rate") if video else None),
        r_frame_rate=_rate(video.get("r_frame_rate") if video else None),
        stream_count=len(streams),
        raw=data,
    )


def decode_window(
    path: Path,
    *,
    start_seconds: float,
    duration_seconds: float = 2.0,
    timeout: float = 20.0,
) -> tuple[bool, str]:
    if start_seconds < 0 or duration_seconds <= 0:
        raise ValueError("invalid decode window")
    if timeout <= 0:
        raise ValueError("decode timeout must be positive")
    result = run_media_tool_bounded(
        "ffmpeg",
        [
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-xerror",
            "-ss",
            f"{start_seconds:.3f}",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-t",
            f"{duration_seconds:.3f}",
            "-f",
            "null",
            "-",
        ],
        timeout=timeout,
        stdout_limit=MAX_MEDIA_STDOUT_BYTES,
        stderr_limit=MAX_DIAGNOSTIC_BYTES,
    )
    error = _diagnostic_text(result.stderr, truncated=result.stderr_truncated)
    if result.stdout_truncated:
        extra = f"ffmpeg stdout exceeded safety limit ({MAX_MEDIA_STDOUT_BYTES} bytes)"
        error = f"{error}\n{extra}" if error else extra
    return result.returncode == 0 and not result.stdout_truncated, error
