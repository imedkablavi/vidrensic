from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import subprocess

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.media.probe import decode_window, probe_video


DEFAULT_WINDOW_SECONDS = 4.0
DEFAULT_MAX_WINDOWS = 512
DEFAULT_TIMEOUT_PER_WINDOW = 20.0
MAX_WINDOW_SECONDS = 60.0
MAX_WINDOWS = 2048


class DecoderRegionAnalysisError(RuntimeError):
    """Raised when bounded decoder-region analysis cannot be completed safely."""


@dataclass(frozen=True)
class DecoderErrorRegion:
    start_seconds: float
    end_seconds: float
    failed_windows: int
    diagnostic: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecoderRegionReport:
    artifact: Path
    size_bytes: int
    sha256: str
    sha512: str | None
    duration_seconds: float | None
    window_seconds: float
    stride_seconds: float | None
    window_count: int
    failed_window_count: int
    coverage_fraction: float
    sampling_complete: bool
    regions: tuple[DecoderErrorRegion, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "artifact": str(self.artifact),
            "size_bytes": self.size_bytes,
            "hashes": {"sha256": self.sha256, "sha512": self.sha512},
            "decoder_errors": {
                "duration_seconds": self.duration_seconds,
                "window_seconds": self.window_seconds,
                "stride_seconds": self.stride_seconds,
                "window_count": self.window_count,
                "failed_window_count": self.failed_window_count,
                "coverage_fraction": self.coverage_fraction,
                "sampling_complete": self.sampling_complete,
                "region_count": len(self.regions),
                "regions": [item.to_dict() for item in self.regions],
            },
        }

    def write_json(self, output: Path, *, replace: bool = False) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=replace)


def _window_starts(
    duration: float,
    *,
    window_seconds: float,
    max_windows: int,
) -> tuple[tuple[float, float], float]:
    if duration <= 0:
        return ((0.0, window_seconds),), window_seconds

    if duration <= window_seconds:
        return ((0.0, duration),), duration

    natural_count = int((duration + window_seconds - 1e-9) // window_seconds)
    if natural_count <= max_windows:
        stride = window_seconds
        starts = [i * stride for i in range(natural_count)]
    else:
        stride = duration / max_windows
        starts = [i * stride for i in range(max_windows)]

    windows: list[tuple[float, float]] = []
    for start in starts:
        end = min(duration, start + window_seconds)
        if end > start:
            windows.append((start, end))
    return tuple(windows), stride


def _merge_failures(
    failures: list[tuple[float, float, str]],
) -> tuple[DecoderErrorRegion, ...]:
    if not failures:
        return ()

    merged: list[DecoderErrorRegion] = []
    start, end, diagnostic = failures[0]
    count = 1
    for next_start, next_end, next_diagnostic in failures[1:]:
        if next_start <= end + 1e-6:
            end = max(end, next_end)
            count += 1
            if next_diagnostic and next_diagnostic not in diagnostic:
                diagnostic = f"{diagnostic}; {next_diagnostic}" if diagnostic else next_diagnostic
            continue
        merged.append(
            DecoderErrorRegion(
                start_seconds=start,
                end_seconds=end,
                failed_windows=count,
                diagnostic=diagnostic,
            )
        )
        start, end, diagnostic = next_start, next_end, next_diagnostic
        count = 1

    merged.append(
        DecoderErrorRegion(
            start_seconds=start,
            end_seconds=end,
            failed_windows=count,
            diagnostic=diagnostic,
        )
    )
    return tuple(merged)


def analyze_decoder_error_regions(
    path: Path,
    *,
    window_seconds: float = DEFAULT_WINDOW_SECONDS,
    max_windows: int = DEFAULT_MAX_WINDOWS,
    timeout_per_window: float = DEFAULT_TIMEOUT_PER_WINDOW,
) -> DecoderRegionReport:
    """Find time ranges whose bounded decode windows report decoder errors.

    The result is a sampled evidence map. Region boundaries identify failed decode
    windows, not exact byte/frame corruption boundaries, and a clean sample does not
    prove the absence of errors between sampled windows.
    """

    if not 0 < window_seconds <= MAX_WINDOW_SECONDS:
        raise ValueError(f"window_seconds must be between 0 and {MAX_WINDOW_SECONDS}")
    if not 1 <= max_windows <= MAX_WINDOWS:
        raise ValueError(f"max_windows must be between 1 and {MAX_WINDOWS}")
    if timeout_per_window <= 0:
        raise ValueError("timeout_per_window must be positive")

    artifact = path.expanduser().resolve(strict=True)
    if not artifact.is_file() or artifact.is_symlink():
        raise ValueError("media artifact must be a regular non-symlink file")

    before_hashes = forensic_hashes_stable(artifact)
    probe = probe_video(artifact)
    duration = probe.duration
    if probe.codec is None or duration is None or duration <= 0:
        after_hashes = forensic_hashes_stable(artifact)
        if before_hashes.sha256 != after_hashes.sha256 or before_hashes.sha512 != after_hashes.sha512:
            raise DecoderRegionAnalysisError("media artifact changed during decoder-region analysis")
        return DecoderRegionReport(
            artifact=artifact,
            size_bytes=artifact.stat().st_size,
            sha256=after_hashes.sha256,
            sha512=after_hashes.sha512,
            duration_seconds=duration,
            window_seconds=window_seconds,
            stride_seconds=None,
            window_count=0,
            failed_window_count=0,
            coverage_fraction=0.0,
            sampling_complete=False,
            regions=(),
        )

    windows, stride = _window_starts(
        duration,
        window_seconds=window_seconds,
        max_windows=max_windows,
    )
    failures: list[tuple[float, float, str]] = []
    covered_seconds = 0.0

    for start, end in windows:
        try:
            ok, error = decode_window(
                artifact,
                start_seconds=start,
                duration_seconds=max(0.001, end - start),
                timeout=timeout_per_window,
            )
        except subprocess.TimeoutExpired:
            ok = False
            error = f"decode window timed out after {timeout_per_window} seconds"
        except (OSError, RuntimeError, ValueError) as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"

        covered_seconds += max(0.0, end - start)
        if not ok:
            failures.append((start, end, error.strip()))

    after_hashes = forensic_hashes_stable(artifact)
    if before_hashes.sha256 != after_hashes.sha256 or before_hashes.sha512 != after_hashes.sha512:
        raise DecoderRegionAnalysisError("media artifact changed during decoder-region analysis")

    max_coverage = min(1.0, covered_seconds / duration)
    sampling_complete = stride <= window_seconds + 1e-9 and windows[-1][1] >= duration - 1e-6
    return DecoderRegionReport(
        artifact=artifact,
        size_bytes=artifact.stat().st_size,
        sha256=after_hashes.sha256,
        sha512=after_hashes.sha512,
        duration_seconds=duration,
        window_seconds=window_seconds,
        stride_seconds=stride,
        window_count=len(windows),
        failed_window_count=len(failures),
        coverage_fraction=max_coverage,
        sampling_complete=sampling_complete,
        regions=_merge_failures(failures),
    )
