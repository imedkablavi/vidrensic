from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator
from statistics import median
import os
import shutil
import subprocess
import tempfile

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.media.probe import probe_video


DEFAULT_TIMELINE_TIMEOUT = 1800.0
MAX_FRAME_RECORDS = 2_000_000
MAX_ANOMALIES = 10_000
MAX_KEYFRAMES = 500_000
MAX_FFPROBE_LINE_BYTES = 64 * 1024
MAX_FFPROBE_STDOUT_BYTES = 512 * 1024 * 1024
MAX_FFPROBE_DIAGNOSTIC_BYTES = 64 * 1024


class TimelineAnalysisError(RuntimeError):
    """Raised when a media timeline cannot be qualified safely."""


@dataclass(frozen=True)
class TimelineAnomaly:
    frame: int
    kind: str
    previous: float | None
    current: float | None
    delta: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaTimelineReport:
    artifact: Path
    size_bytes: int
    sha256: str
    sha512: str | None
    duration_seconds: float | None
    frame_count: int
    keyframe_count: int
    keyframes: tuple[float, ...]
    inferred_frame_rate: float | None
    frame_rate_confidence: str
    pts_non_monotonic: int
    dts_non_monotonic: int
    duplicate_pts: int
    large_gaps: int
    anomalies: tuple[TimelineAnomaly, ...]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact": str(self.artifact),
            "size_bytes": self.size_bytes,
            "hashes": {
                "sha256": self.sha256,
                "sha512": self.sha512,
            },
            "timeline": {
                "duration_seconds": self.duration_seconds,
                "frame_count": self.frame_count,
                "keyframe_count": self.keyframe_count,
                "keyframes_seconds": list(self.keyframes),
                "inferred_frame_rate": self.inferred_frame_rate,
                "frame_rate_confidence": self.frame_rate_confidence,
                "pts_non_monotonic": self.pts_non_monotonic,
                "dts_non_monotonic": self.dts_non_monotonic,
                "duplicate_pts": self.duplicate_pts,
                "large_gaps": self.large_gaps,
                "truncated": self.truncated,
                "anomalies": [item.to_dict() for item in self.anomalies],
            },
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _resolve_ffprobe() -> Path:
    discovered = shutil.which("ffprobe")
    if discovered is None:
        raise FileNotFoundError("required media tool was not found in PATH: ffprobe")
    resolved = Path(discovered).expanduser().resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise PermissionError(f"ffprobe is not an executable regular file: {resolved}")
    return resolved


def _run_frame_probe(
    path: Path,
    *,
    timeout: float,
) -> Iterator[tuple[float | None, float | None, bool, float | None]]:
    if timeout <= 0:
        raise ValueError("timeline timeout must be positive")
    executable = _resolve_ffprobe()
    command = [
        str(executable),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_entries",
        "frame=best_effort_timestamp_time,pkt_dts_time,pict_type,pkt_duration_time,key_frame",
        "-of",
        "csv=p=0:nk=1",
        str(path),
    ]

    with tempfile.TemporaryFile(mode="w+b") as stderr_file:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
        )
        stdout_bytes = 0
        try:
            assert process.stdout is not None
            while True:
                line = process.stdout.readline(MAX_FFPROBE_LINE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_FFPROBE_LINE_BYTES:
                    process.kill()
                    process.wait()
                    raise TimelineAnalysisError("ffprobe frame record exceeded the safety limit")
                stdout_bytes += len(line)
                if stdout_bytes > MAX_FFPROBE_STDOUT_BYTES:
                    process.kill()
                    process.wait()
                    raise TimelineAnalysisError("ffprobe frame output exceeded the safety limit")
                parsed = _parse_frame_line(line)
                if parsed is not None:
                    yield parsed

            try:
                return_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait()
                raise TimelineAnalysisError(f"timeline analysis timed out after {timeout} seconds") from exc
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            try:
                process.stdout.close() if process.stdout is not None else None
            except OSError:
                pass

        stderr_file.flush()
        stderr_file.seek(0)
        diagnostic = stderr_file.read(MAX_FFPROBE_DIAGNOSTIC_BYTES + 1)
        if len(diagnostic) > MAX_FFPROBE_DIAGNOSTIC_BYTES:
            diagnostic = diagnostic[:MAX_FFPROBE_DIAGNOSTIC_BYTES] + b"\n[diagnostic output truncated]"
        if return_code != 0:
            text = diagnostic.decode("utf-8", errors="replace").strip()
            raise TimelineAnalysisError(text or f"ffprobe failed with exit code {return_code}")


def _parse_float(value: str) -> float | None:
    if value in {"", "N/A", "nan", "NaN"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_frame_line(line: bytes) -> tuple[float | None, float | None, bool, float | None] | None:
    text = line.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    fields = [item.strip() for item in text.split(",")]
    if len(fields) < 5:
        return None
    pts = _parse_float(fields[0])
    dts = _parse_float(fields[1])
    duration = _parse_float(fields[3])
    keyframe = fields[4] == "1"
    return pts, dts, keyframe, duration


def _frame_rate_confidence(intervals: list[float], *, truncated: bool, anomalies: int) -> str:
    if len(intervals) < 20:
        return "Low"
    center = median(intervals)
    if center <= 0:
        return "Low"
    deviation = median(abs(item - center) for item in intervals) / center
    if not truncated and anomalies == 0 and deviation < 0.02:
        return "High"
    if deviation < 0.10:
        return "Moderate"
    return "Low"


def analyze_media_timeline(
    path: Path,
    *,
    timeout: float = DEFAULT_TIMELINE_TIMEOUT,
) -> MediaTimelineReport:
    """Build a bounded keyframe/timing inventory from the first video stream."""

    artifact = path.expanduser().resolve(strict=True)
    if not artifact.is_file() or artifact.is_symlink():
        raise ValueError("media artifact must be a regular non-symlink file")

    before_hashes = forensic_hashes_stable(artifact)
    probe = probe_video(artifact)

    frame_count = 0
    keyframe_count = 0
    keyframes: list[float] = []
    intervals: list[float] = []
    anomalies: list[TimelineAnomaly] = []
    pts_non_monotonic = 0
    dts_non_monotonic = 0
    duplicate_pts = 0
    large_gaps = 0
    previous_pts: float | None = None
    previous_dts: float | None = None
    truncated = False

    for pts, dts, keyframe, _duration in _run_frame_probe(artifact, timeout=timeout):
        frame_count += 1
        if frame_count > MAX_FRAME_RECORDS:
            truncated = True
            break

        if keyframe:
            keyframe_count += 1
            if pts is not None and len(keyframes) < MAX_KEYFRAMES:
                keyframes.append(pts)
            elif pts is not None:
                truncated = True

        if pts is not None and previous_pts is not None:
            delta = pts - previous_pts
            if delta < -1e-6:
                pts_non_monotonic += 1
                if len(anomalies) < MAX_ANOMALIES:
                    anomalies.append(
                        TimelineAnomaly(frame_count, "pts-backwards", previous_pts, pts, delta)
                    )
            elif abs(delta) <= 1e-9:
                duplicate_pts += 1
                if len(anomalies) < MAX_ANOMALIES:
                    anomalies.append(
                        TimelineAnomaly(frame_count, "duplicate-pts", previous_pts, pts, delta)
                    )
            elif len(intervals) < MAX_FRAME_RECORDS:
                intervals.append(delta)
        previous_pts = pts if pts is not None else previous_pts

        if dts is not None and previous_dts is not None and dts < previous_dts - 1e-6:
            dts_non_monotonic += 1
            if len(anomalies) < MAX_ANOMALIES:
                anomalies.append(
                    TimelineAnomaly(frame_count, "dts-backwards", previous_dts, dts, dts - previous_dts)
                )
        previous_dts = dts if dts is not None else previous_dts

        if frame_count == MAX_FRAME_RECORDS:
            truncated = True
            break

    if intervals:
        center = median(intervals)
        threshold = max(center * 3.0, 1.0)
        gap_positions = [item for item in intervals if item > threshold]
        large_gaps = len(gap_positions)
        if gap_positions and len(anomalies) < MAX_ANOMALIES:
            # Keep the compact anomaly map bounded; detailed intervals are in measurements above.
            for gap in gap_positions[: MAX_ANOMALIES - len(anomalies)]:
                anomalies.append(TimelineAnomaly(0, "large-gap", None, None, gap))
        inferred_rate = 1.0 / center if center > 0 else None
    else:
        inferred_rate = None

    after_hashes = forensic_hashes_stable(artifact)
    if before_hashes.sha256 != after_hashes.sha256 or before_hashes.sha512 != after_hashes.sha512:
        raise TimelineAnalysisError("media artifact changed during timeline analysis")

    total_anomalies = pts_non_monotonic + dts_non_monotonic + duplicate_pts + large_gaps
    return MediaTimelineReport(
        artifact=artifact,
        size_bytes=artifact.stat().st_size,
        sha256=after_hashes.sha256,
        sha512=after_hashes.sha512,
        duration_seconds=probe.duration,
        frame_count=frame_count,
        keyframe_count=keyframe_count,
        keyframes=tuple(keyframes),
        inferred_frame_rate=inferred_rate,
        frame_rate_confidence=_frame_rate_confidence(
            intervals,
            truncated=truncated,
            anomalies=total_anomalies,
        ),
        pts_non_monotonic=pts_non_monotonic,
        dts_non_monotonic=dts_non_monotonic,
        duplicate_pts=duplicate_pts,
        large_gaps=large_gaps,
        anomalies=tuple(anomalies),
        truncated=truncated,
    )
