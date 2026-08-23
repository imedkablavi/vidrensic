from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic.media import probe


def test_probe_requests_only_required_fields_and_uses_timeout(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    observed: dict[str, object] = {}
    payload = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
            }
        ],
    }

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.probe_video(path, timeout=7.0)
    command = observed["command"]
    assert "-show_entries" in command
    assert "-show_format" not in command
    assert "-show_streams" not in command
    assert observed["timeout"] == 7.0
    assert result.codec == "h264"
    assert result.duration == 12.5


def test_probe_rejects_oversized_json_before_parsing(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="x" * (probe.MAX_PROBE_JSON_CHARS + 1),
            stderr="",
        ),
    )
    with pytest.raises(RuntimeError, match="safety limit"):
        probe.probe_video(path)


def test_probe_rejects_invalid_json(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="{", stderr=""),
    )
    with pytest.raises(RuntimeError, match="invalid JSON"):
        probe.probe_video(path)


def test_decode_window_stops_on_first_error_and_bounds_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    observed: dict[str, object] = {}
    huge = "E" * (probe.MAX_DIAGNOSTIC_CHARS + 500)

    def fake_run(command, **kwargs):
        observed["command"] = command
        return SimpleNamespace(returncode=1, stderr=huge)

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    ok, error = probe.decode_window(path, start_seconds=0.0)
    assert ok is False
    assert "-xerror" in observed["command"]
    assert "-nostdin" in observed["command"]
    assert error.endswith("[diagnostic output truncated]")
    assert len(error) < len(huge)


def test_external_media_timeouts_must_be_positive(tmp_path: Path) -> None:
    path = tmp_path / "candidate.mp4"
    with pytest.raises(ValueError, match="ffprobe timeout"):
        probe.probe_video(path, timeout=0)
    with pytest.raises(ValueError, match="decode timeout"):
        probe.decode_window(path, start_seconds=0.0, timeout=0)
