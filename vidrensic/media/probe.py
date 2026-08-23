from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
import json
import subprocess


MAX_PROBE_JSON_CHARS = 2 * 1024 * 1024
MAX_DIAGNOSTIC_CHARS = 64 * 1024


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


def probe_video(path: Path, *, timeout: float = 30.0) -> VideoProbe:
    if timeout <= 0:
        raise ValueError("ffprobe timeout must be positive")
    path = path.expanduser().resolve()
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(_bounded_text(proc.stderr) or f"ffprobe failed for {path}")
    if len(proc.stdout) > MAX_PROBE_JSON_CHARS:
        raise RuntimeError(
            f"ffprobe JSON exceeded safety limit ({MAX_PROBE_JSON_CHARS} characters)"
        )
    try:
        data = json.loads(proc.stdout)
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
    proc = subprocess.run(
        [
            "ffmpeg",
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode == 0, _bounded_text(proc.stderr)
