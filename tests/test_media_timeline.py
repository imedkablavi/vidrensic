from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.media import timeline
from vidrensic.media.probe import VideoProbe


def _probe(path: Path) -> VideoProbe:
    return VideoProbe(
        path=path,
        duration=2.0,
        codec="h264",
        width=1920,
        height=1080,
        avg_frame_rate=25.0,
        r_frame_rate=25.0,
        stream_count=1,
        raw={"streams": [{"codec_type": "video", "codec_name": "h264"}]},
    )


def _stable_hash(*_args, **_kwargs):
    return SimpleNamespace(sha256="a" * 64, sha512="b" * 128)


def _frames(count: int = 30):
    return [
        (index / 25.0, index / 25.0, index in {0, 10, 20}, 0.04)
        for index in range(count)
    ]


def test_timeline_infers_rate_and_keyframes(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"fixture")
    monkeypatch.setattr(timeline, "forensic_hashes_stable", _stable_hash)
    monkeypatch.setattr(timeline, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(timeline, "_run_frame_probe", lambda *args, **kwargs: iter(_frames()))

    report = timeline.analyze_media_timeline(artifact, timeout=10)

    assert report.frame_count == 30
    assert report.keyframe_count == 3
    assert report.keyframes == (0.0, 0.4, 0.8)
    assert report.inferred_frame_rate == pytest.approx(25.0)
    assert report.frame_rate_confidence == "High"
    assert report.pts_non_monotonic == 0
    assert report.dts_non_monotonic == 0
    assert report.duplicate_pts == 0
    assert report.large_gaps == 0
    assert report.truncated is False


def test_timeline_records_timing_anomalies(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"fixture")
    frames = [
        (0.00, 0.00, True, 0.04),
        (0.04, 0.04, False, 0.04),
        (0.08, 0.08, False, 0.04),
        (0.08, 0.12, False, 0.04),
        (0.02, 0.02, False, 0.04),
        (1.50, 1.50, True, 0.04),
    ]
    monkeypatch.setattr(timeline, "forensic_hashes_stable", _stable_hash)
    monkeypatch.setattr(timeline, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(timeline, "_run_frame_probe", lambda *args, **kwargs: iter(frames))

    report = timeline.analyze_media_timeline(artifact)

    assert report.pts_non_monotonic == 1
    assert report.dts_non_monotonic == 0
    assert report.duplicate_pts == 1
    assert report.large_gaps == 1
    assert {item.kind for item in report.anomalies} == {
        "duplicate-pts",
        "pts-backwards",
        "large-gap",
    }
    assert report.frame_rate_confidence == "Low"


def test_timeline_is_bounded(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"fixture")
    monkeypatch.setattr(timeline, "forensic_hashes_stable", _stable_hash)
    monkeypatch.setattr(timeline, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(
        timeline,
        "MAX_FRAME_RECORDS",
        3,
    )
    monkeypatch.setattr(
        timeline,
        "_run_frame_probe",
        lambda *args, **kwargs: iter(_frames(10)),
    )

    report = timeline.analyze_media_timeline(artifact)

    assert report.frame_count == 3
    assert report.truncated is True


def test_timeline_rejects_artifact_change(monkeypatch, tmp_path: Path) -> None:
    artifact = tmp_path / "candidate.mp4"
    artifact.write_bytes(b"fixture")
    hashes = iter(
        [
            SimpleNamespace(sha256="a" * 64, sha512="b" * 128),
            SimpleNamespace(sha256="c" * 64, sha512="d" * 128),
        ]
    )
    monkeypatch.setattr(timeline, "forensic_hashes_stable", lambda *_a, **_k: next(hashes))
    monkeypatch.setattr(timeline, "probe_video", lambda _path: _probe(artifact))
    monkeypatch.setattr(timeline, "_run_frame_probe", lambda *args, **kwargs: iter(_frames()))

    with pytest.raises(timeline.TimelineAnalysisError, match="changed"):
        timeline.analyze_media_timeline(artifact)
