from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from vidrensic.core import doctor


def _executable(tmp_path: Path, name: str = "ffmpeg") -> Path:
    path = tmp_path / name
    path.write_bytes(b"synthetic executable")
    path.chmod(0o755)
    return path


def test_doctor_version_probe_uses_absolute_path_and_not_pipe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["stdin"] = kwargs["stdin"]
        assert kwargs["stdout"] is not doctor.subprocess.PIPE
        assert kwargs["stderr"] is not doctor.subprocess.PIPE
        kwargs["stdout"].write(b"ffmpeg version synthetic\nsecond line\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    check = doctor._first_version_line("ffmpeg", str(executable), ("-version",))

    assert check.available is True
    assert check.path == str(executable.resolve())
    assert check.version == "ffmpeg version synthetic"
    assert observed["command"][0] == str(executable.resolve())
    assert observed["stdin"] is doctor.subprocess.DEVNULL


def test_doctor_rejects_oversized_version_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)
    monkeypatch.setattr(doctor, "MAX_TOOL_VERSION_STDOUT_BYTES", 8)

    def fake_run(command, **kwargs):
        kwargs["stdout"].write(b"X" * 9)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    check = doctor._first_version_line("ffmpeg", str(executable), ("-version",))

    assert check.available is False
    assert check.version is None
    assert check.error == "version command output exceeded safety limit"


def test_doctor_accepts_output_at_exact_safety_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)
    monkeypatch.setattr(doctor, "MAX_TOOL_VERSION_STDOUT_BYTES", 8)

    def fake_run(command, **kwargs):
        kwargs["stdout"].write(b"VERSION\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    check = doctor._first_version_line("ffmpeg", str(executable), ("-version",))

    assert check.available is True
    assert check.version == "VERSION"


def test_doctor_nonzero_version_command_uses_bounded_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = _executable(tmp_path)

    def fake_run(command, **kwargs):
        kwargs["stderr"].write(b"synthetic version failure\nmore details")
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)

    check = doctor._first_version_line("ffmpeg", str(executable), ("-version",))

    assert check.available is False
    assert check.version == "synthetic version failure"
    assert check.error == "version command returned 7"


def test_doctor_missing_resolved_tool_is_unavailable(tmp_path: Path) -> None:
    missing = tmp_path / "missing-ffmpeg"

    check = doctor._first_version_line("ffmpeg", str(missing), ("-version",))

    assert check.available is False
    assert check.error == "FileNotFoundError"
