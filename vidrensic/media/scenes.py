from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import math
import os
import subprocess

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import PRIVATE_FILE_MODE, atomic_write_private_json
from vidrensic.media.probe import run_media_tool_bounded, probe_video


DEFAULT_SAMPLE_COUNT = 24
DEFAULT_THUMBNAIL_WIDTH = 320
DEFAULT_TIMEOUT = 180.0
MAX_SAMPLE_COUNT = 256
MAX_THUMBNAIL_WIDTH = 640
MAX_TIMEOUT = 1800.0
MAX_OUTPUT_BYTES = 128 * 1024 * 1024


class SceneSamplingError(RuntimeError):
    """Raised when derived visual scene sampling cannot be completed safely."""


@dataclass(frozen=True)
class SceneSamplingReport:
    artifact: Path
    source_size_bytes: int
    source_sha256: str
    source_sha512: str | None
    duration_seconds: float
    requested_sample_count: int
    thumbnail_width: int
    columns: int
    rows: int
    approximate_interval_seconds: float
    output: Path
    output_size_bytes: int
    output_sha256: str
    output_sha512: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact": str(self.artifact),
            "source": {
                "size_bytes": self.source_size_bytes,
                "sha256": self.source_sha256,
                "sha512": self.source_sha512,
            },
            "scene_sampling": {
                "derived": True,
                "requested_sample_count": self.requested_sample_count,
                "thumbnail_width": self.thumbnail_width,
                "columns": self.columns,
                "rows": self.rows,
                "approximate_interval_seconds": self.approximate_interval_seconds,
                "duration_seconds": self.duration_seconds,
                "timestamp_mapping": "evenly spaced request; contact-sheet cells are visual triage aids, not exact frame indices",
            },
            "output": {
                "path": str(self.output),
                "size_bytes": self.output_size_bytes,
                "sha256": self.output_sha256,
                "sha512": self.output_sha512,
            },
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _validate_source(path: Path) -> Path:
    input_path = path.expanduser()
    if input_path.is_symlink():
        raise ValueError("media artifact must be a regular non-symlink file")
    resolved = input_path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError("media artifact must be a regular non-symlink file")
    return resolved


def _validate_output(path: Path) -> Path:
    input_path = path.expanduser()
    if input_path.exists() or input_path.is_symlink():
        raise FileExistsError(f"contact-sheet output already exists: {input_path}")
    parent = input_path.parent.resolve(strict=True)
    resolved = parent / input_path.name
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(f"contact-sheet output already exists: {resolved}")
    return resolved


def _grid(sample_count: int) -> tuple[int, int]:
    columns = min(6, max(1, math.ceil(math.sqrt(sample_count))))
    rows = math.ceil(sample_count / columns)
    return columns, rows


def _hash_file(path: Path) -> tuple[str, str | None, int]:
    hashes = forensic_hashes_stable(path)
    return hashes.sha256, hashes.sha512, path.stat().st_size


def create_contact_sheet(
    path: Path,
    output: Path,
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    thumbnail_width: int = DEFAULT_THUMBNAIL_WIDTH,
    timeout: float = DEFAULT_TIMEOUT,
) -> SceneSamplingReport:
    """Create a bounded derived contact sheet for visual triage.

    The sheet is intentionally not an evidence substitute. Sampling is approximately
    even over the nominal duration, and the exact source frame/time for a cell is not
    asserted by this report.
    """

    if not 1 <= sample_count <= MAX_SAMPLE_COUNT:
        raise ValueError(f"sample_count must be between 1 and {MAX_SAMPLE_COUNT}")
    if not 64 <= thumbnail_width <= MAX_THUMBNAIL_WIDTH:
        raise ValueError(f"thumbnail_width must be between 64 and {MAX_THUMBNAIL_WIDTH}")
    if not 0 < timeout <= MAX_TIMEOUT:
        raise ValueError(f"timeout must be between 0 and {MAX_TIMEOUT}")

    artifact = _validate_source(path)
    destination = _validate_output(output)
    before = forensic_hashes_stable(artifact)
    probe = probe_video(artifact)
    if probe.codec is None or probe.duration is None or probe.duration <= 0:
        raise SceneSamplingError("source does not expose a usable video duration")

    columns, rows = _grid(sample_count)
    interval = probe.duration / sample_count
    fps = sample_count / probe.duration
    suffix = destination.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        muxer = "mjpeg"
    elif suffix == ".png":
        muxer = "image2"
    else:
        raise ValueError("contact-sheet output must use .png, .jpg, or .jpeg")

    vf = (
        f"fps={fps:.12f},"
        f"scale={thumbnail_width}:-2:force_original_aspect_ratio=decrease,"
        f"pad={thumbnail_width}:ih:(ow-iw)/2:0,"
        f"tile={columns}x{rows}:padding=4:margin=4"
    )
    args = [
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-n",
        "-i",
        str(artifact),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        vf,
        "-frames:v",
        "1",
    ]
    if muxer == "mjpeg":
        args.extend(["-q:v", "3"])
    else:
        args.extend(["-compression_level", "6"])
    args.extend(["-f", muxer, str(destination)])

    try:
        result = run_media_tool_bounded(
            "ffmpeg",
            args,
            timeout=timeout,
            stdout_limit=4096,
            stderr_limit=64 * 1024,
        )
    except subprocess.TimeoutExpired as exc:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise SceneSamplingError(f"contact-sheet generation timed out after {timeout} seconds") from exc

    if result.returncode != 0:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        raise SceneSamplingError(diagnostic or f"ffmpeg failed with exit code {result.returncode}")
    if not destination.is_file() or destination.is_symlink():
        raise SceneSamplingError("ffmpeg did not create a regular contact-sheet file")

    output_size = destination.stat().st_size
    if output_size <= 0 or output_size > MAX_OUTPUT_BYTES:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise SceneSamplingError(
            f"contact-sheet output size {output_size} is outside the safety bound"
        )
    os.chmod(destination, PRIVATE_FILE_MODE)

    after = forensic_hashes_stable(artifact)
    if before.sha256 != after.sha256 or before.sha512 != after.sha512:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise SceneSamplingError("media artifact changed during contact-sheet generation")

    output_sha256, output_sha512, output_size = _hash_file(destination)
    return SceneSamplingReport(
        artifact=artifact,
        source_size_bytes=artifact.stat().st_size,
        source_sha256=after.sha256,
        source_sha512=after.sha512,
        duration_seconds=probe.duration,
        requested_sample_count=sample_count,
        thumbnail_width=thumbnail_width,
        columns=columns,
        rows=rows,
        approximate_interval_seconds=interval,
        output=destination,
        output_size_bytes=output_size,
        output_sha256=output_sha256,
        output_sha512=output_sha512,
    )
