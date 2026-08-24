from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

import vidrensic.acquisition.ddrescue as dd
from vidrensic.acquisition.ddrescue import AcquisitionPlan, check_capacity, execute_plan


def _plan(tmp_path: Path, **kwargs) -> AcquisitionPlan:
    return AcquisitionPlan(
        source=kwargs.pop("source", tmp_path / "source.raw"),
        output=kwargs.pop("output", tmp_path / "out.raw"),
        mapfile=kwargs.pop("mapfile", tmp_path / "out.map"),
        **kwargs,
    )


def _tool(tmp_path: Path, *, content: bytes = b"synthetic-ddrescue-binary") -> dd.ExecutableIdentity:
    path = tmp_path / "ddrescue-synthetic"
    path.write_bytes(content)
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
        version="GNU ddrescue synthetic",
    )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"offset": -1}, "offset"),
        ({"size": 0}, "size"),
        ({"retry_passes": -1}, "retry_passes"),
        ({"retry_passes": 6}, "retry_passes"),
    ],
)
def test_plan_rejects_invalid_numeric_parameters(tmp_path: Path, kwargs, match) -> None:
    with pytest.raises(ValueError, match=match):
        _plan(tmp_path, **kwargs).validate()


def test_plan_rejects_source_output_map_aliases(tmp_path: Path) -> None:
    source = tmp_path / "evidence.raw"
    with pytest.raises(ValueError, match="output cannot"):
        _plan(tmp_path, source=source, output=source).validate()
    with pytest.raises(ValueError, match="mapfile cannot"):
        _plan(tmp_path, source=source, mapfile=source).validate()
    same = tmp_path / "same"
    with pytest.raises(ValueError, match="different"):
        _plan(tmp_path, output=same, mapfile=same).validate()


def test_plan_commands_preserve_bounded_offsets_and_retry_semantics(tmp_path: Path) -> None:
    plan = _plan(tmp_path, offset=4096, size=8192, retry_passes=2, direct=True)
    first = plan.first_pass_command()
    retry = plan.retry_command()
    assert first[:3] == ["ddrescue", "-f", "-n"]
    assert first[first.index("-i") + 1] == "4096"
    assert first[first.index("-o") + 1] == "0"
    assert first[first.index("-s") + 1] == "8192"
    assert "-d" in first
    assert retry is not None
    assert "-r2" in retry
    assert "-d" in retry
    assert retry[-3:] == [str(plan.source), str(plan.output), str(plan.mapfile)]

    pinned = plan.first_pass_command("/opt/forensic/ddrescue")
    assert pinned[0] == "/opt/forensic/ddrescue"

    no_retry = _plan(tmp_path)
    assert no_retry.retry_command() is None
    assert no_retry.required_output_bytes is None
    assert no_retry.additional_required_bytes is None


def test_partial_output_reduces_additional_capacity_requirement(tmp_path: Path) -> None:
    plan = _plan(tmp_path, size=1000)
    assert plan.existing_output_bytes == 0
    assert plan.additional_required_bytes == 1000
    plan.output.write_bytes(b"X" * 400)
    assert plan.existing_output_bytes == 400
    assert plan.additional_required_bytes == 600
    plan.output.write_bytes(b"X" * 1200)
    assert plan.additional_required_bytes == 0


def test_filesystem_probe_handles_failure_and_normalizes_output(tmp_path: Path, monkeypatch) -> None:
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=" EXT4\n")

    monkeypatch.setattr(dd.subprocess, "run", fake_run)
    assert dd._filesystem_type(tmp_path) == "ext4"
    assert calls[0][:4] == ["findmnt", "-n", "-o", "FSTYPE"]

    monkeypatch.setattr(
        dd.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert dd._filesystem_type(tmp_path) is None


def test_capacity_requires_source_geometry_for_unbounded_plan(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source_size is required"):
        check_capacity(_plan(tmp_path), reserve_bytes=0)
    with pytest.raises(ValueError, match="reserve_bytes"):
        check_capacity(_plan(tmp_path, size=1), reserve_bytes=-1)


def test_resolve_ddrescue_records_canonical_path_hash_and_bounded_version(
    tmp_path: Path, monkeypatch
) -> None:
    executable = tmp_path / "ddrescue"
    executable.write_bytes(b"synthetic executable")
    executable.chmod(0o755)
    monkeypatch.setattr(dd.shutil, "which", lambda name: str(executable))

    def fake_run(command, **kwargs):
        assert command == [str(executable.resolve()), "--version"]
        kwargs["stdout"].write(b"GNU ddrescue 1.29\nextra ignored\n")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(dd.subprocess, "run", fake_run)
    identity = dd.resolve_ddrescue_executable()
    assert identity.path == executable.resolve()
    assert identity.sha256 == dd.hash_file(executable, ("sha256",))["sha256"]
    assert identity.version == "GNU ddrescue 1.29"
    assert identity.to_dict()["claim_limit"]


def test_execute_plan_uses_one_resolved_absolute_binary_for_all_passes(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"X" * 10_000)
    plan = _plan(tmp_path, source=source, size=1000, retry_passes=2)
    identity = _tool(tmp_path)

    monkeypatch.setattr(
        dd,
        "require_safe_source",
        lambda path, allow_write_enabled=False: SimpleNamespace(size_bytes=10_000),
    )
    monkeypatch.setattr(dd, "check_capacity", lambda plan, source_size: None)
    monkeypatch.setattr(dd, "resolve_ddrescue_executable", lambda: identity)

    commands = []

    def success_run(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dd.subprocess, "run", success_run)
    results = execute_plan(plan, timeout=5)
    assert [item.returncode for item in results] == [0, 0]
    assert len(commands) == 2
    assert all(command[0] == str(identity.path) for command in commands)
    assert "-n" in commands[0]
    assert "-r2" in commands[1]

    commands.clear()

    def fail_first(cmd, **kwargs):
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 7)

    monkeypatch.setattr(dd.subprocess, "run", fail_first)
    failed = execute_plan(plan, executable_identity=identity)
    assert [item.returncode for item in failed] == [7]
    assert len(commands) == 1
    assert commands[0][0] == str(identity.path)


def test_execute_plan_fails_if_resolved_binary_changes_during_session(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"X" * 10_000)
    plan = _plan(tmp_path, source=source, size=1000)
    identity = _tool(tmp_path)

    monkeypatch.setattr(
        dd,
        "require_safe_source",
        lambda path, allow_write_enabled=False: SimpleNamespace(size_bytes=10_000),
    )
    monkeypatch.setattr(dd, "check_capacity", lambda plan, source_size: None)

    def replace_binary(cmd, **kwargs):
        identity.path.write_bytes(b"replacement executable bytes")
        identity.path.chmod(0o755)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(dd.subprocess, "run", replace_binary)
    with pytest.raises(RuntimeError, match="executable identity changed|executable bytes changed"):
        execute_plan(plan, executable_identity=identity)


def test_execute_plan_requires_ddrescue_binary(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.raw"
    source.write_bytes(b"X" * 4096)
    plan = _plan(tmp_path, source=source, size=1024)
    monkeypatch.setattr(
        dd,
        "require_safe_source",
        lambda path, allow_write_enabled=False: SimpleNamespace(size_bytes=4096),
    )
    monkeypatch.setattr(dd, "check_capacity", lambda plan, source_size: None)

    def missing():
        raise FileNotFoundError("GNU ddrescue executable was not found in PATH")

    monkeypatch.setattr(dd, "resolve_ddrescue_executable", missing)
    with pytest.raises(FileNotFoundError, match="ddrescue"):
        execute_plan(plan)


def test_source_geometry_rejects_nonpositive_and_out_of_bounds(tmp_path: Path) -> None:
    plan = _plan(tmp_path, offset=100)
    with pytest.raises(ValueError, match="source size"):
        plan.validate_source_geometry(0)
    with pytest.raises(ValueError, match="source end"):
        plan.validate_source_geometry(100)
