from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import os
import subprocess
import tempfile

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import PRIVATE_FILE_MODE, atomic_write_private_json
from vidrensic.media.probe import probe_video, run_media_tool_bounded


MAX_DIAGNOSTIC_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 512 * 1024 * 1024 * 1024


class RepairIntegrityError(RuntimeError):
    """Raised when a derived repair artifact cannot be verified safely."""


@dataclass(frozen=True)
class RemuxReport:
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
    source_stream_count: int
    destination_stream_count: int
    source_codec: str | None
    destination_codec: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "repair": {
                "derived": True,
                "mode": "remux",
                "stream_copy": True,
                "source_mutation_checked": True,
                "compressed_payload_repaired": False,
                "limitations": (
                    "Remuxing rebuilds the container around copied streams; it does not repair "
                    "corrupted compressed video payloads or recover missing frames."
                ),
            },
            "source": {
                "path": str(self.source),
                "sha256": self.source_sha256,
                "sha512": self.source_sha512,
                "size_bytes": self.source_size_bytes,
                "duration_seconds": self.source_duration_seconds,
                "stream_count": self.source_stream_count,
                "codec": self.source_codec,
            },
            "destination": {
                "path": str(self.destination),
                "sha256": self.destination_sha256,
                "sha512": self.destination_sha512,
                "size_bytes": self.destination_size_bytes,
                "duration_seconds": self.destination_duration_seconds,
                "stream_count": self.destination_stream_count,
                "codec": self.destination_codec,
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
        raise FileExistsError(f"repair destination already exists: {input_path}")
    parent = input_path.parent.resolve(strict=True)
    resolved = parent / input_path.name
    if resolved == source:
        raise ValueError("repair destination must differ from source")
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(f"repair destination already exists: {resolved}")
    if resolved.suffix.lower() not in {".mp4", ".mkv", ".mov", ".avi", ".ts", ".m2ts", ".webm"}:
        raise ValueError("remux destination must use a supported container extension")
    return resolved


def _remove_regular(path: Path) -> None:
    try:
        if path.is_file() and not path.is_symlink():
            path.unlink()
    except OSError:
        pass


def remux_video(source: Path, destination: Path) -> RemuxReport:
    """Create a verified stream-copy remux without modifying the source artifact."""

    artifact = _validate_source(source)
    output = _validate_destination(artifact, destination)
    source_before = forensic_hashes_stable(artifact)
    source_probe = probe_video(artifact)
    if source_probe.codec is None:
        raise RepairIntegrityError("source does not expose a usable video stream")

    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output.name}.",
            suffix=output.suffix,
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
            "0",
            "-c",
            "copy",
            str(temp_path),
        ]
        try:
            result = run_media_tool_bounded(
                "ffmpeg",
                args,
                timeout=600.0,
                stdout_limit=4096,
                stderr_limit=MAX_DIAGNOSTIC_BYTES,
            )
        except subprocess.TimeoutExpired as exc:
            raise RepairIntegrityError("remux timed out after 600 seconds") from exc
        if result.returncode != 0:
            diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
            raise RepairIntegrityError(diagnostic or f"ffmpeg remux failed with exit code {result.returncode}")
        if not temp_path.is_file() or temp_path.is_symlink():
            raise RepairIntegrityError("ffmpeg did not create a regular remux output")

        output_size = temp_path.stat().st_size
        if output_size <= 0 or output_size > MAX_OUTPUT_BYTES:
            raise RepairIntegrityError(f"remux output size {output_size} is outside the safety bound")
        destination_hashes = forensic_hashes_stable(temp_path)
        destination_probe = probe_video(temp_path)
        if destination_probe.codec is None or destination_probe.stream_count <= 0:
            raise RepairIntegrityError("remux output could not be probed as a media container")

        source_after = forensic_hashes_stable(artifact)
        if (
            source_before.sha256 != source_after.sha256
            or source_before.sha512 != source_after.sha512
        ):
            raise RepairIntegrityError("source changed during remux")

        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists() or output.is_symlink():
            raise FileExistsError(f"repair destination appeared during remux: {output}")
        try:
            os.link(temp_path, output)
            temp_path.unlink()
        except OSError as exc:
            raise RepairIntegrityError(f"unable to atomically publish remux output: {exc}") from exc
        temp_name = None
        os.chmod(output, PRIVATE_FILE_MODE)

        published_hashes = forensic_hashes_stable(output)
        if (
            published_hashes.sha256 != destination_hashes.sha256
            or published_hashes.sha512 != destination_hashes.sha512
        ):
            _remove_regular(output)
            raise RepairIntegrityError("published remux hash does not match verified temporary output")

        return RemuxReport(
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
            source_stream_count=source_probe.stream_count,
            destination_stream_count=destination_probe.stream_count,
            source_codec=source_probe.codec,
            destination_codec=destination_probe.codec,
        )
    except Exception:
        if temp_name:
            _remove_regular(Path(temp_name))
        raise


def remux_video_with_manifest(
    source: Path,
    destination: Path,
    manifest: Path,
) -> RemuxReport:
    """Remux and publish only when both the derived media and manifest can be committed."""

    if manifest.expanduser().exists() or manifest.expanduser().is_symlink():
        raise FileExistsError(f"repair manifest already exists: {manifest}")
    report = remux_video(source, destination)
    try:
        report.write_json(manifest)
    except Exception:
        _remove_regular(report.destination)
        raise
    return report
