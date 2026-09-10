from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import stat

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.media.probe import VideoProbe, probe_video
from vidrensic.media.qc import fast_three_point_check, full_decode_check


@dataclass(frozen=True)
class MediaStreamInventory:
    index: int
    codec_type: str | None
    codec: str | None
    width: int | None
    height: int | None
    avg_frame_rate: float | None
    r_frame_rate: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MediaInventoryReport:
    artifact: Path
    size_bytes: int
    sha256: str
    sha512: str | None
    duration_seconds: float | None
    video_codec: str | None
    width: int | None
    height: int | None
    avg_frame_rate: float | None
    r_frame_rate: float | None
    stream_count: int
    streams: tuple[MediaStreamInventory, ...]
    qc: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact": str(self.artifact),
            "size_bytes": self.size_bytes,
            "hashes": {
                "sha256": self.sha256,
                "sha512": self.sha512,
            },
            "media": {
                "duration_seconds": self.duration_seconds,
                "video_codec": self.video_codec,
                "width": self.width,
                "height": self.height,
                "avg_frame_rate": self.avg_frame_rate,
                "r_frame_rate": self.r_frame_rate,
                "stream_count": self.stream_count,
                "streams": [item.to_dict() for item in self.streams],
            },
            "qc": self.qc,
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _stream_inventory(probe: VideoProbe) -> tuple[MediaStreamInventory, ...]:
    raw_streams = probe.raw.get("streams", [])
    if not isinstance(raw_streams, list):
        raise ValueError("ffprobe streams field must be a list")

    streams: list[MediaStreamInventory] = []
    for index, stream in enumerate(raw_streams):
        if not isinstance(stream, dict):
            raise ValueError("ffprobe stream entry must be an object")
        streams.append(
            MediaStreamInventory(
                index=index,
                codec_type=stream.get("codec_type"),
                codec=stream.get("codec_name"),
                width=stream.get("width"),
                height=stream.get("height"),
                avg_frame_rate=_stream_float(stream.get("avg_frame_rate")),
                r_frame_rate=_stream_float(stream.get("r_frame_rate")),
            )
        )
    return tuple(streams)


def _stream_float(value: Any) -> float | None:
    if value in (None, "N/A", "0/0"):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str) or "/" not in value:
        return None
    try:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return None
        return float(numerator) / denominator_value
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _qc_dict(report: Any) -> dict[str, Any]:
    return {
        "mode": report.mode,
        "status": report.decision.status.value,
        "reasons": list(report.decision.reasons),
        "measurements": report.decision.measurements,
        "checkpoints": [asdict(item) for item in report.checkpoints],
        "full_decode_error": report.full_decode_error,
    }


def _validate_artifact(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=True)
    mode = resolved.stat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(f"media artifact must be a regular file: {resolved}")
    return resolved


def inspect_media(
    path: Path,
    *,
    qc_mode: str = "none",
    expected_duration: float | None = None,
    full_decode_timeout: float | None = None,
) -> MediaInventoryReport:
    """Persist a stable, hash-bound inventory for one recovered media artifact."""

    if qc_mode not in {"none", "fast", "full"}:
        raise ValueError("qc_mode must be one of: none, fast, full")
    artifact = _validate_artifact(path)
    hashes = forensic_hashes_stable(artifact)
    probe = probe_video(artifact)
    streams = _stream_inventory(probe)

    qc: dict[str, Any] | None = None
    if qc_mode == "fast":
        qc = _qc_dict(
            fast_three_point_check(
                artifact,
                expected_duration=expected_duration,
            )
        )
    elif qc_mode == "full":
        qc = _qc_dict(
            full_decode_check(
                artifact,
                expected_duration=expected_duration,
                timeout=full_decode_timeout,
            )
        )

    return MediaInventoryReport(
        artifact=artifact,
        size_bytes=artifact.stat().st_size,
        sha256=hashes.sha256,
        sha512=hashes.sha512,
        duration_seconds=probe.duration,
        video_codec=probe.codec,
        width=probe.width,
        height=probe.height,
        avg_frame_rate=probe.avg_frame_rate,
        r_frame_rate=probe.r_frame_rate,
        stream_count=probe.stream_count,
        streams=streams,
        qc=qc,
    )
