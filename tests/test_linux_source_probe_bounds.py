from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import vidrensic.acquisition.linux as linux


def _tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(linux.shutil, "which", lambda name: f"/opt/test-tools/{name}")


def _fake_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
    def run(command, **kwargs):
        assert command[0].startswith("/opt/test-tools/")
        assert kwargs["stdout"] is not linux.subprocess.PIPE
        assert kwargs["stderr"] is not linux.subprocess.PIPE
        kwargs["stdout"].write(stdout)
        kwargs["stderr"].write(stderr)
        return SimpleNamespace(returncode=returncode)

    return run


def test_block_size_uses_file_backed_bounded_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tools(monkeypatch)
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(b"4096\n"))

    assert linux._block_size(tmp_path / "device") == 4096


def test_block_size_rejects_output_amplification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tools(monkeypatch)
    monkeypatch.setattr(linux, "MAX_BLOCKDEV_STDOUT_BYTES", 8)
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(b"1" * 9))

    with pytest.raises(OSError, match="blockdev stdout exceeded safety limit"):
        linux._block_size(tmp_path / "device")


def test_device_ids_parse_descendants_and_fail_closed_on_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tools(monkeypatch)
    monkeypatch.setattr(
        linux.subprocess,
        "run",
        _fake_process(b"8:0\n8:1\n253:0\n"),
    )
    assert linux._device_ids(tmp_path / "device", 8, 0) == {"8:0", "8:1", "253:0"}

    monkeypatch.setattr(
        linux.subprocess,
        "run",
        _fake_process(stderr=b"synthetic lsblk failure", returncode=32),
    )
    with pytest.raises(OSError, match="synthetic lsblk failure"):
        linux._device_ids(tmp_path / "device", 8, 0)


def test_device_ids_reject_malformed_or_oversized_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tools(monkeypatch)
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(b"8:0\nnot-an-id\n"))
    with pytest.raises(OSError, match="malformed MAJ:MIN"):
        linux._device_ids(tmp_path / "device", 8, 0)

    monkeypatch.setattr(linux, "MAX_LSBLK_IDS_STDOUT_BYTES", 8)
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(b"8:0\n8:1\n"))
    with pytest.raises(OSError, match="lsblk stdout exceeded safety limit"):
        linux._device_ids(tmp_path / "device", 8, 0)


def test_block_identity_is_bounded_but_remains_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tools(monkeypatch)
    payload = b'{"blockdevices":[{"serial":"SER-1","wwn":"WWN-1","model":"Disk"}]}'
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(payload))
    assert linux._block_identity(tmp_path / "device") == ("SER-1", "WWN-1", "Disk")

    monkeypatch.setattr(linux, "MAX_LSBLK_IDENTITY_STDOUT_BYTES", 8)
    monkeypatch.setattr(linux.subprocess, "run", _fake_process(b"{" + (b"X" * 20)))
    assert linux._block_identity(tmp_path / "device") == (None, None, None)


def test_mountinfo_streaming_detects_descendant_mounts(tmp_path: Path) -> None:
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(
        "20 19 0:5 / / rw - rootfs rootfs rw\n"
        "36 20 8:1 / /mnt/evidence\\040disk ro - ext4 /dev/sda1 ro\n"
        "37 20 253:0 / /mnt/lv ro - ext4 /dev/dm-0 ro\n",
        encoding="utf-8",
    )

    mounts = linux._mounted_paths({"8:0", "8:1", "253:0"}, mountinfo=mountinfo)

    assert mounts == ("/mnt/evidence disk", "/mnt/lv")


def test_mountinfo_missing_malformed_or_oversized_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(OSError, match="mount information is unavailable"):
        linux._mounted_paths({"8:0"}, mountinfo=tmp_path / "missing")

    malformed = tmp_path / "malformed"
    malformed.write_text("too few fields\n", encoding="utf-8")
    with pytest.raises(OSError, match="is malformed"):
        linux._mounted_paths({"8:0"}, mountinfo=malformed)

    monkeypatch.setattr(linux, "MAX_MOUNTINFO_LINE_BYTES", 8)
    oversized = tmp_path / "oversized"
    oversized.write_bytes(b"X" * 9)
    with pytest.raises(OSError, match="mountinfo line 1 exceeded safety limit"):
        linux._mounted_paths({"8:0"}, mountinfo=oversized)


def test_regular_file_inspection_does_not_require_linux_probe_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "image.raw"
    source.write_bytes(b"forensic-image")

    def no_tools(name: str):
        raise AssertionError(f"regular file inspection unexpectedly requested {name}")

    monkeypatch.setattr(linux.shutil, "which", no_tools)
    info = linux.inspect_source(source)

    assert info.exists is True
    assert info.is_block_device is False
    assert info.size_bytes == len(b"forensic-image")
    assert info.safe_for_forensic_read is True
