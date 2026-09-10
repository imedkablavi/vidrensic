from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.media import decoder_regions


def _hashes(sha: str = "stable") -> SimpleNamespace:
    return SimpleNamespace(sha256=sha, sha512=f"{sha}-512")


def _probe(duration: float = 20.0) -> SimpleNamespace:
    return SimpleNamespace(duration=duration, codec="h264")


def test_decoder_regions_merge_adjacent_failed_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(decoder_regions, "forensic_hashes_stable", lambda _: _hashes())
    monkeypatch.setattr(decoder_regions, "probe_video", lambda _: _probe(12.0))

    failed = {4.0, 8.0}

    def fake_decode(path: Path, *, start_seconds: float, **_: object) -> tuple[bool, str]:
        assert path == source
        if start_seconds in failed:
            return False, "decoder error"
        return True, ""

    monkeypatch.setattr(decoder_regions, "decode_window", fake_decode)

    report = decoder_regions.analyze_decoder_error_regions(source, window_seconds=4.0, max_windows=8)

    assert report.window_count == 3
    assert report.failed_window_count == 2
    assert report.coverage_fraction == pytest.approx(1.0)
    assert report.sampling_complete is True
    assert len(report.regions) == 1
    assert report.regions[0].start_seconds == pytest.approx(4.0)
    assert report.regions[0].end_seconds == pytest.approx(12.0)
    assert report.regions[0].failed_windows == 2


def test_decoder_regions_report_partial_sampling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "long.mp4"
    source.write_bytes(b"fixture")
    monkeypatch.setattr(decoder_regions, "forensic_hashes_stable", lambda _: _hashes())
    monkeypatch.setattr(decoder_regions, "probe_video", lambda _: _probe(100.0))
    monkeypatch.setattr(decoder_regions, "decode_window", lambda *_args, **_kwargs: (True, ""))

    report = decoder_regions.analyze_decoder_error_regions(
        source,
        window_seconds=2.0,
        max_windows=10,
    )

    assert report.window_count == 10
    assert report.stride_seconds == pytest.approx(10.0)
    assert report.coverage_fraction == pytest.approx(0.2)
    assert report.sampling_complete is False
    assert report.regions == ()


def test_decoder_regions_reject_invalid_bounds(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fixture")

    with pytest.raises(ValueError):
        decoder_regions.analyze_decoder_error_regions(source, window_seconds=0)
    with pytest.raises(ValueError):
        decoder_regions.analyze_decoder_error_regions(source, max_windows=0)
    with pytest.raises(ValueError):
        decoder_regions.analyze_decoder_error_regions(source, timeout_per_window=0)


def test_decoder_regions_fail_closed_when_artifact_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fixture")
    calls = iter(("before", "after"))
    monkeypatch.setattr(decoder_regions, "forensic_hashes_stable", lambda _: _hashes(next(calls)))
    monkeypatch.setattr(decoder_regions, "probe_video", lambda _: _probe(4.0))
    monkeypatch.setattr(decoder_regions, "decode_window", lambda *_args, **_kwargs: (True, ""))

    with pytest.raises(decoder_regions.DecoderRegionAnalysisError, match="changed during"):
        decoder_regions.analyze_decoder_error_regions(source)
