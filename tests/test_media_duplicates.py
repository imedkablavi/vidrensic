from pathlib import Path

import pytest

from vidrensic.media import duplicates as duplicate_module
from vidrensic.media.duplicates import (
    DEFAULT_FRAME_MATCH_THRESHOLD,
    DEFAULT_SIMILARITY_THRESHOLD,
    MAX_INPUTS,
    MediaSignature,
    analyze_media_set,
    compare_signatures,
)


def _signature(path: Path, sha256: str, *hashes: int, duration: float = 30.0) -> MediaSignature:
    return MediaSignature(
        path=path,
        size_bytes=100,
        sha256=sha256,
        sha512=None,
        duration_seconds=duration,
        frame_hashes=tuple(hashes),
    )


def test_compare_exact_hashes_is_exact(tmp_path: Path) -> None:
    left = _signature(tmp_path / "a.mp4", "same", 1, 2, 3)
    right = _signature(tmp_path / "b.mp4", "same", 10, 20, 30)

    result = compare_signatures(left, right, sample_count=3)

    assert result.classification == "EXACT"
    assert result.exact_hash_match is True
    assert result.median_similarity == 1.0


def test_compare_identifies_near_duplicate_candidate(tmp_path: Path) -> None:
    hashes = tuple(range(16))
    left = _signature(tmp_path / "a.mp4", "left", *hashes)
    right = _signature(tmp_path / "b.mp4", "right", *hashes)

    result = compare_signatures(
        left,
        right,
        sample_count=len(hashes),
        similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
        frame_match_threshold=DEFAULT_FRAME_MATCH_THRESHOLD,
    )

    assert result.classification == "NEAR_DUPLICATE_CANDIDATE"
    assert result.matched_frame_ratio == 1.0
    assert result.duration_ratio == 1.0


def test_compare_identifies_distinct_pair(tmp_path: Path) -> None:
    left = _signature(tmp_path / "a.mp4", "left", *(0 for _ in range(16)))
    right = _signature(tmp_path / "b.mp4", "right", *((1 << 64) - 1 for _ in range(16)))

    result = compare_signatures(left, right, sample_count=16)

    assert result.classification == "DISTINCT"
    assert result.median_similarity == 0.0
    assert result.matched_frame_ratio == 0.0


def test_compare_incomplete_visual_signature_requires_review(tmp_path: Path) -> None:
    left = _signature(tmp_path / "a.mp4", "left", 1, 2)
    right = _signature(tmp_path / "b.mp4", "right", 1, 2, 3)

    result = compare_signatures(left, right, sample_count=3)

    assert result.classification == "REVIEW"
    assert result.median_similarity is None


def test_analyze_media_set_rejects_empty_and_large_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        analyze_media_set([])

    sources = [tmp_path / f"{index}.mp4" for index in range(MAX_INPUTS + 1)]
    for source in sources:
        source.write_bytes(b"x")
    with pytest.raises(ValueError):
        analyze_media_set(sources)


def test_compare_serializes_classification(tmp_path: Path) -> None:
    left = _signature(tmp_path / "a.mp4", "same")
    right = _signature(tmp_path / "b.mp4", "same")
    comparison = compare_signatures(left, right, sample_count=1)

    payload = comparison.to_dict()
    assert payload["classification"] == "EXACT"


def test_build_signature_rejects_source_mutation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    hashes = iter(
        [
            duplicate_module.MediaSignature.__annotations__,
        ]
    )
    del hashes
    stable_hashes = iter(
        [
            type("Hashes", (), {"sha256": "a", "sha512": "b"})(),
            type("Hashes", (), {"sha256": "changed", "sha512": "c"})(),
        ]
    )
    monkeypatch.setattr(duplicate_module, "forensic_hashes_stable", lambda _path: next(stable_hashes))
    monkeypatch.setattr(
        duplicate_module,
        "probe_video",
        lambda _path: type("Probe", (), {"duration": 1.0, "codec": "h264"})(),
    )
    monkeypatch.setattr(duplicate_module, "_sample_frame_hashes", lambda *args, **kwargs: (1,))

    with pytest.raises(duplicate_module.DuplicateAnalysisError, match="changed"):
        duplicate_module.build_signature(source, sample_count=1)
