from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

import vidrensic.acquisition.linux as linux
from vidrensic.acquisition.linux import SourceInfo, inspect_source, require_safe_source


def test_regular_file_is_safe_and_reports_size(tmp_path: Path) -> None:
    source = tmp_path / "image.raw"
    source.write_bytes(b"X" * 123)
    info = inspect_source(source)
    assert info.exists is True
    assert info.is_block_device is False
    assert info.size_bytes == 123
    assert info.read_only is None
    assert info.safe_for_forensic_read is True


def test_missing_source_is_not_safe(tmp_path: Path) -> None:
    info = inspect_source(tmp_path / "missing.raw")
    assert info.exists is False
    assert info.safe_for_forensic_read is False
    with pytest.raises(FileNotFoundError):
        require_safe_source(tmp_path / "missing.raw")


def test_source_info_block_safety_requires_read_only_and_unmounted(tmp_path: Path) -> None:
    base = dict(path=tmp_path / "dev", exists=True, is_block_device=True, size_bytes=1)
    assert SourceInfo(**base, read_only=True, mounted_at=()).safe_for_forensic_read is True
    assert SourceInfo(**base, read_only=False, mounted_at=()).safe_for_forensic_read is False
    assert SourceInfo(**base, read_only=True, mounted_at=("/mnt/x",)).safe_for_forensic_read is False


def test_block_size_success_and_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="4096\n", stderr=""),
    )
    assert linux._block_size(tmp_path / "dev") == 4096
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="denied\n"),
    )
    with pytest.raises(OSError, match="denied"):
        linux._block_size(tmp_path / "dev")


def test_device_ids_adds_descendants_and_tolerates_lsblk_failure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="8:0\n8:1\ninvalid\n"),
    )
    assert linux._device_ids(tmp_path / "dev", 8, 0) == {"8:0", "8:1"}
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert linux._device_ids(tmp_path / "dev", 8, 0) == {"8:0"}


def test_mounted_paths_decodes_spaces_and_deduplicates(monkeypatch, tmp_path: Path) -> None:
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "24 22 8:1 / /mnt/Case\\040Disk rw,relatime - ext4 /dev/sda1 rw\n"
        "25 22 8:1 / /mnt/Case\\040Disk rw,relatime - ext4 /dev/sda1 rw\n"
        "bad line\n",
        encoding="utf-8",
    )
    real_path = linux.Path

    def fake_path(value):
        if value == "/proc/self/mountinfo":
            return mountinfo
        return real_path(value)

    monkeypatch.setattr(linux, "Path", fake_path)
    assert linux._mounted_paths({"8:1"}) == ("/mnt/Case Disk",)


def test_require_safe_source_rejects_mounted_and_write_enabled(monkeypatch, tmp_path: Path) -> None:
    device = tmp_path / "device"
    mounted = SourceInfo(device, True, True, 100, True, ("/mnt/evidence",), 8, 1)
    monkeypatch.setattr(linux, "inspect_source", lambda path: mounted)
    with pytest.raises(PermissionError, match="mounted"):
        require_safe_source(device)

    write_enabled = SourceInfo(device, True, True, 100, False, (), 8, 1)
    monkeypatch.setattr(linux, "inspect_source", lambda path: write_enabled)
    with pytest.raises(PermissionError, match="write-enabled"):
        require_safe_source(device)
    assert require_safe_source(device, allow_write_enabled=True) == write_enabled

    unknown = SourceInfo(device, True, True, 100, None, (), 8, 1)
    monkeypatch.setattr(linux, "inspect_source", lambda path: unknown)
    with pytest.raises(PermissionError, match="unknown"):
        require_safe_source(device)


def test_inspect_source_block_path_uses_geometry_ro_and_mount_helpers(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "fake-block"
    path.write_bytes(b"")
    real_stat = Path.stat

    class FakeStat:
        st_mode = stat.S_IFBLK
        st_rdev = 0x0801
        st_size = 0

    monkeypatch.setattr(Path, "stat", lambda self: FakeStat() if self == path.resolve() else real_stat(self))
    monkeypatch.setattr(linux.os, "major", lambda value: 8)
    monkeypatch.setattr(linux.os, "minor", lambda value: 1)
    monkeypatch.setattr(linux, "_block_size", lambda value: 10_000)
    monkeypatch.setattr(linux, "_sysfs_ro", lambda major, minor: True)
    monkeypatch.setattr(linux, "_device_ids", lambda value, major, minor: {"8:1", "8:2"})
    monkeypatch.setattr(linux, "_mounted_paths", lambda ids: ())
    info = inspect_source(path)
    assert info.is_block_device is True
    assert info.size_bytes == 10_000
    assert info.read_only is True
    assert (info.major, info.minor) == (8, 1)
