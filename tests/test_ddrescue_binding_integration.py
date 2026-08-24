from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

import vidrensic.acquisition.ddrescue as dd
from vidrensic.acquisition.binding import PENDING_LEGACY, load_source_binding, source_binding_path
from vidrensic.acquisition.ddrescue import AcquisitionPlan, execute_plan


def _tool(tmp_path: Path) -> dd.ExecutableIdentity:
    path = tmp_path / "synthetic-ddrescue"
    path.write_bytes(b"synthetic-ddrescue")
    path.chmod(0o755)
    stat_result = path.stat()
    return dd.ExecutableIdentity(
        name="ddrescue",
        path=path.resolve(),
        sha256=dd.hash_file(path, ("sha256",))["sha256"],
        size_bytes=stat_result.st_size,
        filesystem_device=stat_result.st_dev,
        inode=stat_result.st_ino,
        mtime_ns=stat_result.st_mtime_ns,
        version="synthetic",
    )


def _prepare(monkeypatch, source_size: int, tool: dd.ExecutableIdentity) -> None:
    monkeypatch.setattr(
        dd,
        "require_safe_source",
        lambda path, allow_write_enabled=False: SimpleNamespace(size_bytes=source_size),
    )
    monkeypatch.setattr(dd, "check_capacity", lambda plan, source_size: None)
    monkeypatch.setattr(dd, "resolve_ddrescue_executable", lambda: tool)


def test_new_acquisition_binds_source_before_ddrescue_runs(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    plan = AcquisitionPlan(source, tmp_path / "image.bin", tmp_path / "image.map", size=1000)
    _prepare(monkeypatch, source.stat().st_size, _tool(tmp_path))

    observed = {"called": False}

    def fake_run(command, **kwargs):
        assert source_binding_path(plan.mapfile).is_file()
        observed["called"] = True
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dd.subprocess, "run", fake_run)
    results = execute_plan(plan, timeout=5)
    assert observed["called"] is True
    assert [item.returncode for item in results] == [0]


def test_legacy_unbound_state_never_invokes_ddrescue_on_first_encounter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"A" * 200_000)
    output = tmp_path / "image.bin"
    output.write_bytes(b"partial")
    mapfile = tmp_path / "image.map"
    mapfile.write_text("legacy map placeholder\n", encoding="utf-8")
    plan = AcquisitionPlan(source, output, mapfile, size=1000)
    _prepare(monkeypatch, source.stat().st_size, _tool(tmp_path))

    called = False

    def should_not_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("ddrescue must not execute before legacy source binding confirmation")

    monkeypatch.setattr(dd.subprocess, "run", should_not_run)
    with pytest.raises(RuntimeError, match="ddrescue was NOT executed"):
        execute_plan(plan)
    assert called is False
    binding = load_source_binding(source_binding_path(mapfile))
    assert binding.state == PENDING_LEGACY
