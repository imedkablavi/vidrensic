from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import subprocess
import tempfile

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import PRIVATE_FILE_MODE, atomic_write_private_json
from vidrensic.media.probe import decode_window, probe_video, run_media_tool_bounded


PROXY_PROFILE = "review-h264-aac"
PROXY_VIDEO_CODEC = "libx264"
PROXY_AUDIO_CODEC = "aac"
PROXY_VIDEO_PRESET = "fast"
PROXY_VIDEO_CRF = 23
PROXY_AUDIO_BITRATE = "128k"
MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 128 * 1024 * 1024 * 1024


class ProxyIntegrityError(RuntimeError):
    """Raised when a controlled review proxy cannot be verified safely."""


@dataclass(frozen=True)
class ProxyReport:
    source: Path
    destination: Path
    source_sha256: str
    source_sha512: str | None
    destination_sha256: str
    destination_sha512: str | None
    source_size_bytes: int
    destination_size_bytes: int
    source_duration_seconds: float | None
    destination_duration_seconds: float | None
    source_codec: str | None
    destination_codec: str | None
    source_width: int | None
    source_height: int | None
    destination_width: int | None
    destination_height: int | None
    source_stream_count: int
    destination_stream_count: int
    decode_smoke_tested: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "proxy": {
                "derived": True,
                "profile": PROXY_PROFILE,
                "transcoded": True,
                "source_mutation_checked": True,
                "decode_smoke_tested": self.decode_smoke_tested,
                "parameters": {
                    "video_codec": PROXY_VIDEO_CODEC,
                    "video_preset": PROXY_VIDEO_PRESET,
                    "video_crf": PROXY_VIDEO_CRF,
                    "audio_codec": PROXY_AUDIO_CODEC,
                    "audio_bitrate": PROXY_AUDIO_BITRATE,
                    "pixel_format": "yuv420p",
                    "faststart": True,
                },
                "limitations": (
                    "A controlled transcode changes the encoded media bytes and may change quality, "
                    "timestamps, metadata, and unsupported streams. It is a review proxy, not a "
                    "replacement for the recovered source and not proof that corruption was repaired."
                ),
            },
            "source": {
                "path": str(self.source),
                "sha256": self.source_sha256,
                "sha512": self.source_sha512,
                "size_bytes": self.source_size_bytes,
                "duration_seconds": self.source_duration_seconds,
                "codec": self.source_codec,
                "width": self.source_width,
                "height": self.source_height,
                "stream_count": self.source_stream_count,
            },
            "destination": {
                "path": str(self.destination),
                "sha256": self.destination_sha256,
                "sha512": self.destination_sha512,
                "size_bytes": self.destination_size_bytes,
                "duration_seconds": self.destination_duration_seconds,
                "codec": self.destination_codec,
                "width": self.destination_width,
                "height": self.destination_height,
                "stream_count": self.destination_stream_count,
            },
        }

    def write_json(self, output: Path) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=False)


def _validate_source(path: Path) -> Path:
    input_path = path.expanduser()
    if input_path.is_symlink():
        raise ValueError(f"media source must not be a symlink: {input_path}")
    resolved = input_path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"media source must be a regular file: {input_path}")
    return resolved


def _validate_destination(source: Path, destination: Path) -> Path:
    input_path = destination.expanduser()
    if input_path.exists() or input_path.is_symlink():
        raise FileExistsError(f"proxy destination already exists: {input_path}")
    parent = input_path.parent.resolve(strict=True)
    resolved = parent / input_path.name
    if resolved == source:
        raise ValueError("proxy destination must differ from source")
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(f"proxy destination already exists: {resolved}")
    if resolved.suffix.lower() != ".mp4":
        raise ValueError("controlled transcode proxy output must use .mp4")
    return resolved


def _remove_regular(path: Path) -> None:
    try:
        if path.is_file() and not path.is_symlink():
            path.unlink()
    except OSError:
        pass


def transcode_proxy(source: Path, destination: Path) -> ProxyReport:
    """Create a verified H.264/AAC MP4 review proxy without modifying source bytes."""

    artifact = _validate_source(source)
    output = _validate_destination(artifact, destination)
    source_before = forensic_hashes_stable(artifact)
    source_probe = probe_video(artifact)
    if source_probe.codec is None or source_probe.duration is None or source_probe.duration <= 0:
        raise ProxyIntegrityError("source does not expose a usable video stream and duration")

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output.name}.",
            suffix=".mp4",
            dir=output.parent,
            delete=False,
        ) as temp:
            temp_name = temp.name
        temp_path = Path(temp_name)
        os.chmod(temp_path, PRIVATE_FILE_MODE)

        args = [
            "-nostdin",
            "-hide_banner",
            "-v",
            "error",
            "-y",
            "-i",
            str(artifact),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            PROXY_VIDEO_CODEC,
            "-preset",
            PROXY_VIDEO_PRESET,
            "-crf",
            str(PROXY_VIDEO_CRF),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            PROXY_AUDIO_CODEC,
            "-b:a",
            PROXY_AUDIO_BITRATE,
            "-movflags",
            "+faststart",
            str(temp_path),
        ]
        try:
            result = run_media_tool_bounded(
                "ffmpeg",
                args,
                timeout=900.0,
                stdout_limit=4096,
                stderr_limit=MAX_DIAGNOSTIC_BYTES,
            )
        except subprocess.TimeoutExpired as exc:
            raise ProxyIntegrityError("controlled transcode proxy timed out after 900 seconds") from exc
        if result.returncode != 0:
            diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
            raise ProxyIntegrityError(diagnostic or f"ffmpeg proxy transcode failed with exit code {result.returncode}")
        if not temp_path.is_file() or temp_path.is_symlink():
            raise ProxyIntegrityError("ffmpeg did not create a regular proxy output")

        output_size = temp_path.stat().st_size
        if output_size <= 0 or output_size > MAX_OUTPUT_BYTES:
            raise ProxyIntegrityError(f"proxy output size {output_size} is outside the safety bound")
        destination_hashes = forensic_hashes_stable(temp_path)
        destination_probe = probe_video(temp_path)
        if destination_probe.codec is None or destination_probe.stream_count <= 0:
            raise ProxyIntegrityError("proxy output could not be probed as a media container")

        decode_duration = min(2.0, destination_probe.duration or 2.0)
        decoded, diagnostic = decode_window(
            temp_path,
            start_seconds=0.0,
            duration_seconds=decode_duration,
            timeout=60.0,
        )
        if not decoded:
            raise ProxyIntegrityError(
                f"proxy decode smoke test failed{': ' + diagnostic if diagnostic else ''}"
            )

        source_after = forensic_hashes_stable(artifact)
        if source_before.sha256 != source_after.sha256 or source_before.sha512 != source_after.sha512:
            raise ProxyIntegrityError("source changed during controlled transcode")

        if output.exists() or output.is_symlink():
            raise FileExistsError(f"proxy destination appeared during transcode: {output}")
        try:
            os.link(temp_path, output)
            temp_path.unlink()
        except OSError as exc:
            raise ProxyIntegrityError(f"unable to atomically publish proxy output: {exc}") from exc
        temp_name = None
        os.chmod(output, PRIVATE_FILE_MODE)

        published_hashes = forensic_hashes_stable(output)
        if (
            published_hashes.sha256 != destination_hashes.sha256
            or published_hashes.sha512 != destination_hashes.sha512
        ):
            _remove_regular(output)
            raise ProxyIntegrityError("published proxy hash does not match verified temporary output")

        return ProxyReport(
            source=artifact,
            destination=output,
            source_sha256=source_after.sha256,
            source_sha512=source_after.sha512,
            destination_sha256=published_hashes.sha256,
            destination_sha512=published_hashes.sha512,
            source_size_bytes=artifact.stat().st_size,
            destination_size_bytes=output.stat().st_size,
            source_duration_seconds=source_probe.duration,
            destination_duration_seconds=destination_probe.duration,
            source_codec=source_probe.codec,
            destination_codec=destination_probe.codec,
            source_width=source_probe.width,
            source_height=source_probe.height,
            destination_width=destination_probe.width,
            destination_height=destination_probe.height,
            source_stream_count=source_probe.stream_count,
            destination_stream_count=destination_probe.stream_count,
            decode_smoke_tested=True,
        )
    except Exception:
        if temp_name:
            _remove_regular(Path(temp_name))
        raise


def transcode_proxy_with_manifest(
    source: Path,
    destination: Path,
    manifest: Path,
) -> ProxyReport:
    """Create a proxy and manifest, removing the proxy if manifest publication fails."""

    manifest_input = manifest.expanduser()
    if manifest_input.exists() or manifest_input.is_symlink():
        raise FileExistsError(f"proxy manifest already exists: {manifest_input}")
    report = transcode_proxy(source, destination)
    try:
        report.write_json(manifest_input)
    except Exception:
        _remove_regular(report.destination)
        raise
    return report
