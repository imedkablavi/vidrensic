from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from vidrensic.media import probe


def _result(
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
    returncode: int = 0,
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
):
    return SimpleNamespace(
        executable=Path("/opt/test-tools/ffmpeg"),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


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

    def fake_run(name, args, **kwargs):
        observed["name"] = name
        observed["command"] = args
        observed["timeout"] = kwargs["timeout"]
        observed["stdout_limit"] = kwargs["stdout_limit"]
        return _result(stdout=json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(probe, "run_media_tool_bounded", fake_run)
    result = probe.probe_video(path, timeout=7.0)
    command = observed["command"]
    assert observed["name"] == "ffprobe"
    assert "-show_entries" in command
    assert "-show_format" not in command
    assert "-show_streams" not in command
    assert observed["timeout"] == 7.0
    assert observed["stdout_limit"] == probe.MAX_PROBE_JSON_BYTES
    assert result.codec == "h264"
    assert result.duration == 12.5


def test_probe_rejects_oversized_json_before_parsing(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(
        probe,
        "run_media_tool_bounded",
        lambda *args, **kwargs: _result(
            stdout=b"x" * probe.MAX_PROBE_JSON_BYTES,
            stdout_truncated=True,
        ),
    )
    with pytest.raises(RuntimeError, match="safety limit"):
        probe.probe_video(path)


def test_probe_rejects_invalid_json(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "candidate.mp4"
    path.write_bytes(b"synthetic")
    monkeypatch.setattr(
        probe,
        "run_media_tool_bounded",
        lambda *args, **kwargs: _result(stdout=b"{"),
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

    def fake_run(name, args, **kwargs):
        observed["name"] = name
        observed["command"] = args
        return _result(
            returncode=1,
            stderr=b"E" * probe.MAX_DIAGNOSTIC_BYTES,
            stderr_truncated=True,
        )

    monkeypatch.setattr(probe, "run_media_tool_bounded", fake_run)
    ok, error = probe.decode_window(path, start_seconds=0.0)
    assert ok is False
    assert observed["name"] == "ffmpeg"
    assert "-xerror" in observed["command"]
    assert "-nostdin" in observed["command"]
    assert error.endswith("[diagnostic output truncated]")
    assert len(error) < probe.MAX_DIAGNOSTIC_BYTES + 100


def test_external_media_timeouts_must_be_positive(tmp_path: Path) -> None:
    path = tmp_path / "candidate.mp4"
    with pytest.raises(ValueError, match="ffprobe timeout"):
        probe.probe_video(path, timeout=0)
    with pytest.raises(ValueError, match="decode timeout"):
        probe.decode_window(path, start_seconds=0.0, timeout=0)


def test_media_tool_runner_uses_absolute_executable_and_not_pipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "ffprobe"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o755)
    monkeypatch.setattr(probe.shutil, "which", lambda name: str(executable))
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["stdin"] = kwargs["stdin"]
        observed["stdout"] = kwargs["stdout"]
        observed["stderr"] = kwargs["stderr"]
        assert kwargs["stdout"] is not probe.subprocess.PIPE
        assert kwargs["stderr"] is not probe.subprocess.PIPE
        kwargs["stdout"].write(b'{"streams": []}')
        kwargs["stderr"].write(b"diagnostic")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.run_media_tool_bounded(
        "ffprobe",
        ["-version"],
        timeout=5.0,
        stdout_limit=1024,
        stderr_limit=1024,
    )

    assert observed["command"][0] == str(executable.resolve())
    assert observed["stdin"] is probe.subprocess.DEVNULL
    assert result.executable == executable.resolve()
    assert result.stdout == b'{"streams": []}'
    assert result.stderr == b"diagnostic"
    assert result.stdout_truncated is False
    assert result.stderr_truncated is False


def test_media_tool_runner_reads_only_bounded_prefixes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "ffmpeg"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o755)
    monkeypatch.setattr(probe.shutil, "which", lambda name: str(executable))

    def fake_run(command, **kwargs):
        kwargs["stdout"].write(b"O" * 9)
        kwargs["stderr"].write(b"E" * 7)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.run_media_tool_bounded(
        "ffmpeg",
        [],
        timeout=5.0,
        stdout_limit=8,
        stderr_limit=6,
    )

    assert result.stdout == b"O" * 8
    assert result.stderr == b"E" * 6
    assert result.stdout_truncated is True
    assert result.stderr_truncated is True
