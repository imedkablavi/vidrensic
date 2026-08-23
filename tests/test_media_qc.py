from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

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


def test_full_decode_defaults_to_finite_timeout_and_xerror(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(qc.subprocess, "run", fake_run)
    report = qc.full_decode_check(path, expected_duration=3600.0)
    assert report.decision.status is EvidenceStatus.PASS
    assert observed["timeout"] == qc.DEFAULT_FULL_DECODE_TIMEOUT
    assert "-xerror" in observed["command"]
    assert "-nostdin" in observed["command"]
    assert report.decision.measurements["full_decode_timeout_seconds"] == qc.DEFAULT_FULL_DECODE_TIMEOUT


def test_full_decode_rejects_unbounded_or_nonpositive_timeout(tmp_path: Path) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    with pytest.raises(ValueError, match="timeout"):
        qc.full_decode_check(path, timeout=0)
    with pytest.raises(ValueError, match="timeout"):
        qc.full_decode_check(path, timeout=-1)


def test_full_decode_diagnostics_are_truncated(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(qc, "probe_video", lambda _path: _probe(path))
    huge = "E" * (qc.MAX_FULL_DECODE_DIAGNOSTIC_CHARS + 1000)
    monkeypatch.setattr(
        qc.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr=huge),
    )
    report = qc.full_decode_check(path, expected_duration=3600.0)
    assert report.decision.status is EvidenceStatus.FAIL
    assert report.full_decode_error is not None
    assert report.full_decode_error.endswith("[diagnostic output truncated]")
    assert len(report.full_decode_error) < len(huge)
