from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
import json
import subprocess


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


def probe_video(path: Path, *, timeout: float = 30.0) -> VideoProbe:
    path = path.expanduser().resolve()
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
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
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed for {path}")
    data = json.loads(proc.stdout)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    format_info = data.get("format") or {}

    duration = None
    raw_duration = format_info.get("duration")
    if raw_duration not in (None, "N/A"):
        try:
            duration = float(raw_duration)
        except ValueError:
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
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
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
    return proc.returncode == 0, proc.stderr.strip()
