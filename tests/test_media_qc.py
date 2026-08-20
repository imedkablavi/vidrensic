from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from vidrensic.core.models import EvidenceStatus
from vidrensic.media import qc
from vidrensic.media.probe import VideoProbe


def _probe(path: Path, duration: float = 3600.0) -> VideoProbe:
    return VideoProbe(
        path=path,
        duration=duration,
        codec="hevc",
        width=1280,
        height=1440,
        avg_frame_rate=15.0,
        r_frame_rate=15.0,
        stream_count=1,
        raw={},
    )


def test_three_point_clean_is_review_not_pass(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))
    monkeypatch.setattr(qc, "decode_window", lambda *args, **kwargs: (True, ""))

    report = qc.fast_three_point_check(path, expected_duration=3600.0)
    assert report.decision.status is EvidenceStatus.REVIEW
    assert len(report.checkpoints) == 3
    assert any("full decode not performed" in reason for reason in report.decision.reasons)


def test_three_point_decode_failure_is_fail(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))

    calls = 0

    def fake_decode(*args, **kwargs):
        nonlocal calls
        calls += 1
        return (False, "decoder error") if calls == 2 else (True, "")

    monkeypatch.setattr(qc, "decode_window", fake_decode)
    report = qc.fast_three_point_check(path, expected_duration=3600.0)
    assert report.decision.status is EvidenceStatus.FAIL
    assert any("middle" in reason for reason in report.decision.reasons)


def test_full_decode_can_pass_only_with_timing_and_no_reconstruction_flags(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))
    monkeypatch.setattr(
        qc.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    report = qc.full_decode_check(path, expected_duration=3600.0)
    assert report.decision.status is EvidenceStatus.PASS

    ambiguous = qc.full_decode_check(
        path,
        expected_duration=3600.0,
        reconstruction_ambiguous=True,
    )
    assert ambiguous.decision.status is EvidenceStatus.REVIEW


def test_full_decode_without_expected_duration_is_review(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))
    monkeypatch.setattr(
        qc.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr=""),
    )

    report = qc.full_decode_check(path)
    assert report.decision.status is EvidenceStatus.REVIEW
    assert "expected duration not supplied" in report.decision.reasons
