from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import stat

import pytest

import vidrensic.plugins.wfs.scanner as scanner


def test_regular_source_size_uses_descriptor_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scanner.os,
        "fstat",
        lambda fd: SimpleNamespace(st_size=4096, st_mode=stat.S_IFREG),
    )

    def unexpected_probe(path: Path) -> int:
        raise AssertionError(f"regular file unexpectedly invoked blockdev probe for {path}")

    monkeypatch.setattr(scanner, "block_device_size", unexpected_probe)

    assert scanner.source_size(123, tmp_path / "image.raw") == 4096


def test_empty_regular_source_does_not_invoke_blockdev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scanner.os,
        "fstat",
        lambda fd: SimpleNamespace(st_size=0, st_mode=stat.S_IFREG),
    )

    def unexpected_probe(path: Path) -> int:
        raise AssertionError(f"empty regular file unexpectedly invoked blockdev for {path}")

    monkeypatch.setattr(scanner, "block_device_size", unexpected_probe)

    assert scanner.source_size(123, tmp_path / "empty.raw") == 0


def test_block_device_source_uses_shared_bounded_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "device"
    monkeypatch.setattr(
        scanner.os,
        "fstat",
        lambda fd: SimpleNamespace(st_size=0, st_mode=stat.S_IFBLK),
    )
    observed: list[Path] = []

    def bounded_probe(path: Path) -> int:
        observed.append(path)
        return 1024 * 1024

    monkeypatch.setattr(scanner, "block_device_size", bounded_probe)

    assert scanner.source_size(123, source) == 1024 * 1024
    assert observed == [source]


def test_block_device_probe_failure_propagates_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        scanner.os,
        "fstat",
        lambda fd: SimpleNamespace(st_size=0, st_mode=stat.S_IFBLK),
    )

    def failed_probe(path: Path) -> int:
        raise OSError("bounded block-size probe failed")

    monkeypatch.setattr(scanner, "block_device_size", failed_probe)

    with pytest.raises(OSError, match="bounded block-size probe failed"):
        scanner.source_size(123, tmp_path / "device")
