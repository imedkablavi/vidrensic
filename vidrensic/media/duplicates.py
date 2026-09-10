from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from vidrensic.core.hashing import forensic_hashes_stable
from vidrensic.core.private_io import atomic_write_private_json
from vidrensic.media.probe import probe_video, run_media_tool_bounded


DEFAULT_SAMPLE_COUNT = 32
DEFAULT_SIMILARITY_THRESHOLD = 0.90
DEFAULT_FRAME_MATCH_THRESHOLD = 0.80
MAX_SAMPLE_COUNT = 128
MAX_INPUTS = 64
MAX_STDOUT_BYTES = MAX_SAMPLE_COUNT * 9 * 8 + 1
FRAME_WIDTH = 9
FRAME_HEIGHT = 8
FRAME_BYTES = FRAME_WIDTH * FRAME_HEIGHT


class DuplicateAnalysisError(RuntimeError):
    """Raised when duplicate analysis cannot be completed safely."""


@dataclass(frozen=True)
class MediaSignature:
    path: Path
    size_bytes: int
    sha256: str
    sha512: str | None
    duration_seconds: float | None
    frame_hashes: tuple[int, ...]


@dataclass(frozen=True)
class DuplicateComparison:
    left: str
    right: str
    classification: str
    exact_hash_match: bool
    median_similarity: float | None
    matched_frame_ratio: float | None
    duration_ratio: float | None
    sample_count: int
    similarity_threshold: float
    frame_match_threshold: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "left": self.left,
            "right": self.right,
            "classification": self.classification,
            "exact_hash_match": self.exact_hash_match,
            "median_similarity": self.median_similarity,
            "matched_frame_ratio": self.matched_frame_ratio,
            "duration_ratio": self.duration_ratio,
            "sample_count": self.sample_count,
            "similarity_threshold": self.similarity_threshold,
            "frame_match_threshold": self.frame_match_threshold,
        }


@dataclass(frozen=True)
class DuplicateAnalysisReport:
    sources: tuple[MediaSignature, ...]
    comparisons: tuple[DuplicateComparison, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "analysis": {
                "derived": True,
                "method": "exact SHA-256 match followed by aligned 64-bit dHash comparison on evenly sampled grayscale frames",
                "classification_semantics": {
                    "EXACT": "source files have identical SHA-256",
                    "NEAR_DUPLICATE_CANDIDATE": "visual frame similarity exceeds the configured thresholds; requires analyst review",
                    "DISTINCT": "visual similarity did not meet the candidate thresholds",
                    "REVIEW": "visual comparison could not produce a complete comparable frame set",
                },
            },
            "sources": [
                {
                    "path": str(source.path),
                    "size_bytes": source.size_bytes,
                    "sha256": source.sha256,
                    "sha512": source.sha512,
                    "duration_seconds": source.duration_seconds,
                    "sample_count": len(source.frame_hashes),
                }
                for source in self.sources
            ],
            "comparisons": [comparison.to_dict() for comparison in self.comparisons],
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


def _dhash(frame: bytes) -> int:
    if len(frame) != FRAME_BYTES:
        raise ValueError("unexpected frame size")
    value = 0
    for row in range(FRAME_HEIGHT):
        base = row * FRAME_WIDTH
        for column in range(FRAME_WIDTH - 1):
            value = (value << 1) | int(frame[base + column + 1] >= frame[base + column])
    return value


def _hamming(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _median(values: list[float]) -> float:
    if not values:
        raise ValueError("median requires values")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _sample_frame_hashes(path: Path, *, sample_count: int, duration: float) -> tuple[int, ...]:
    if duration <= 0:
        raise DuplicateAnalysisError("source duration must be positive for visual comparison")
    fps = sample_count / duration
    args = [
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        f"fps={fps:.12f},scale={FRAME_WIDTH}:{FRAME_HEIGHT}:flags=bilinear,format=gray",
        "-frames:v",
        str(sample_count),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    result = run_media_tool_bounded(
        "ffmpeg",
        args,
        timeout=max(30.0, min(180.0, duration * 2.0 + 10.0)),
        stdout_limit=MAX_STDOUT_BYTES,
        stderr_limit=64 * 1024,
    )
    if result.returncode != 0:
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        raise DuplicateAnalysisError(diagnostic or f"ffmpeg failed with exit code {result.returncode}")
    if result.stdout_truncated:
        raise DuplicateAnalysisError("sampled frame stream exceeded safety limit")
    usable = len(result.stdout) // FRAME_BYTES
    if usable == 0 or usable != sample_count or len(result.stdout) != sample_count * FRAME_BYTES:
        raise DuplicateAnalysisError(
            f"incomplete comparable frame set: expected={sample_count} actual={usable}"
        )
    return tuple(
        _dhash(result.stdout[offset : offset + FRAME_BYTES])
        for offset in range(0, len(result.stdout), FRAME_BYTES)
    )


def build_signature(path: Path, *, sample_count: int = DEFAULT_SAMPLE_COUNT) -> MediaSignature:
    if not 1 <= sample_count <= MAX_SAMPLE_COUNT:
        raise ValueError(f"sample_count must be between 1 and {MAX_SAMPLE_COUNT}")
    artifact = _validate_source(path)
    hashes = forensic_hashes_stable(artifact)
    probe = probe_video(artifact)
    frame_hashes: tuple[int, ...] = ()
    if probe.duration is not None and probe.duration > 0 and probe.codec:
        frame_hashes = _sample_frame_hashes(artifact, sample_count=sample_count, duration=probe.duration)
    return MediaSignature(
        path=artifact,
        size_bytes=artifact.stat().st_size,
        sha256=hashes.sha256,
        sha512=hashes.sha512,
        duration_seconds=probe.duration,
        frame_hashes=frame_hashes,
    )


def compare_signatures(
    left: MediaSignature,
    right: MediaSignature,
    *,
    sample_count: int,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    frame_match_threshold: float = DEFAULT_FRAME_MATCH_THRESHOLD,
) -> DuplicateComparison:
    if not 0 < similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be in (0, 1]")
    if not 0 < frame_match_threshold <= 1:
        raise ValueError("frame_match_threshold must be in (0, 1]")
    exact = left.sha256 == right.sha256
    if exact:
        return DuplicateComparison(
            left=str(left.path),
            right=str(right.path),
            classification="EXACT",
            exact_hash_match=True,
            median_similarity=1.0,
            matched_frame_ratio=1.0 if left.frame_hashes and right.frame_hashes else None,
            duration_ratio=1.0,
            sample_count=min(len(left.frame_hashes), len(right.frame_hashes), sample_count),
            similarity_threshold=similarity_threshold,
            frame_match_threshold=frame_match_threshold,
        )

    usable = min(len(left.frame_hashes), len(right.frame_hashes), sample_count)
    if usable != sample_count:
        return DuplicateComparison(
            left=str(left.path),
            right=str(right.path),
            classification="REVIEW",
            exact_hash_match=False,
            median_similarity=None,
            matched_frame_ratio=None,
            duration_ratio=None,
            sample_count=usable,
            similarity_threshold=similarity_threshold,
            frame_match_threshold=frame_match_threshold,
        )

    similarities = [
        1.0 - (_hamming(a, b) / 64.0)
        for a, b in zip(left.frame_hashes[:usable], right.frame_hashes[:usable])
    ]
    median_similarity = _median(similarities)
    matched_ratio = sum(value >= frame_match_threshold for value in similarities) / usable
    duration_ratio = None
    if left.duration_seconds and right.duration_seconds:
        duration_ratio = min(left.duration_seconds, right.duration_seconds) / max(
            left.duration_seconds, right.duration_seconds
        )

    if median_similarity >= similarity_threshold and matched_ratio >= 0.80:
        classification = "NEAR_DUPLICATE_CANDIDATE"
    else:
        classification = "DISTINCT"
    return DuplicateComparison(
        left=str(left.path),
        right=str(right.path),
        classification=classification,
        exact_hash_match=False,
        median_similarity=round(median_similarity, 6),
        matched_frame_ratio=round(matched_ratio, 6),
        duration_ratio=round(duration_ratio, 6) if duration_ratio is not None else None,
        sample_count=usable,
        similarity_threshold=similarity_threshold,
        frame_match_threshold=frame_match_threshold,
    )


def analyze_media_set(
    paths: Iterable[Path],
    *,
    sample_count: int = DEFAULT_SAMPLE_COUNT,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    frame_match_threshold: float = DEFAULT_FRAME_MATCH_THRESHOLD,
) -> DuplicateAnalysisReport:
    values = tuple(paths)
    if not values:
        raise ValueError("at least one media source is required")
    if len(values) > MAX_INPUTS:
        raise ValueError(f"at most {MAX_INPUTS} media sources are supported")
    signatures = tuple(build_signature(path, sample_count=sample_count) for path in values)
    comparisons: list[DuplicateComparison] = []
    for index, left in enumerate(signatures):
        for right in signatures[index + 1 :]:
            comparisons.append(
                compare_signatures(
                    left,
                    right,
                    sample_count=sample_count,
                    similarity_threshold=similarity_threshold,
                    frame_match_threshold=frame_match_threshold,
                )
            )
    return DuplicateAnalysisReport(sources=signatures, comparisons=tuple(comparisons))
