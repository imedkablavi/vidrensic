from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import subprocess

import pytest

import vidrensic.acquisition.smart as smart


def _safe_info(path: Path):
    return SimpleNamespace(path=path.resolve())


def test_capture_smart_uses_file_backed_output_and_parses_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(smart, "require_safe_source", lambda path: _safe_info(path))
    monkeypatch.setattr(smart.shutil, "which", lambda name: "/usr/bin/smartctl")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        assert "capture_output" not in kwargs
        assert "stdout" in kwargs and "stderr" in kwargs
        kwargs["stdout"].write(
            json.dumps(
                {
                    "model_name": "Synthetic Disk",
                    "serial_number": "SER-1",
                    "smart_status": {"passed": True},
                }
            ).encode("utf-8")
        )
        kwargs["stderr"].write(b"")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(smart.subprocess, "run", fake_run)
    snapshot = smart.capture_smart(source, timeout=5)

    assert snapshot.captured is True
    assert snapshot.model == "Synthetic Disk"
    assert snapshot.serial == "SER-1"
    assert snapshot.smart_passed is True
    assert calls[0][0][:3] == ["/usr/bin/smartctl", "-j", "-a"]
    assert calls[0][1]["timeout"] == 5


def test_capture_smart_rejects_oversized_stdout_without_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(smart, "require_safe_source", lambda path: _safe_info(path))
    monkeypatch.setattr(smart.shutil, "which", lambda name: "/usr/bin/smartctl")
    monkeypatch.setattr(smart, "MAX_SMARTCTL_STDOUT_BYTES", 32)

    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(b"X" * 33)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(smart.subprocess, "run", fake_run)
    snapshot = smart.capture_smart(source)
    assert snapshot.captured is False
    assert snapshot.raw == {}
    assert "stdout exceeded safety limit" in (snapshot.error or "")


def test_capture_smart_rejects_oversized_stderr_and_invalid_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(smart, "require_safe_source", lambda path: _safe_info(path))
    monkeypatch.setattr(smart.shutil, "which", lambda name: "/usr/bin/smartctl")
    monkeypatch.setattr(smart, "MAX_SMARTCTL_STDERR_BYTES", 16)

    def too_much_stderr(cmd, **kwargs):
        kwargs["stdout"].write(b"{}")
        kwargs["stderr"].write(b"E" * 17)
        return subprocess.CompletedProcess(cmd, 8)

    monkeypatch.setattr(smart.subprocess, "run", too_much_stderr)
    oversized = smart.capture_smart(source)
    assert oversized.captured is False
    assert "stderr exceeded safety limit" in (oversized.error or "")

    monkeypatch.setattr(smart, "MAX_SMARTCTL_STDERR_BYTES", 256)

    def invalid_json(cmd, **kwargs):
        kwargs["stdout"].write(b"not-json")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(smart.subprocess, "run", invalid_json)
    malformed = smart.capture_smart(source)
    assert malformed.captured is False
    assert malformed.error == "smartctl returned invalid JSON"


def test_capture_smart_timeout_and_timeout_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"source")
    monkeypatch.setattr(smart, "require_safe_source", lambda path: _safe_info(path))
    monkeypatch.setattr(smart.shutil, "which", lambda name: "/usr/bin/smartctl")

    with pytest.raises(ValueError, match="timeout must be positive"):
        smart.capture_smart(source, timeout=0)

    def timed_out(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(smart.subprocess, "run", timed_out)
    snapshot = smart.capture_smart(source, timeout=2)
    assert snapshot.captured is False
    assert snapshot.smartctl_returncode is None
    assert "timed out after 2" in (snapshot.error or "")
