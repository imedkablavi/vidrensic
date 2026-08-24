from __future__ import annotations

from pathlib import Path

import pytest

import vidrensic.acquisition.mapfile as mapfile_module
from vidrensic.acquisition.mapfile import parse_mapfile


def test_streamed_mapfile_preserves_completion_semantics(tmp_path: Path) -> None:
    path = tmp_path / "image.map"
    path.write_text(
        "# synthetic ddrescue map\n"
        "0x00000010 + 1\n"
        "0x00000000 0x00000008 +\n"
        "0x00000008 0x00000008 +\n",
        encoding="utf-8",
    )

    summary = parse_mapfile(path, expected_start=0, expected_size=16)

    assert summary.segment_count == 2
    assert summary.mapped_bytes == 16
    assert summary.expected_finished_bytes == 16
    assert summary.complete_for_expected_range is True


def test_mapfile_accepts_line_exactly_at_safety_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mapfile_module, "MAX_MAPFILE_LINE_BYTES", 8)
    path = tmp_path / "image.map"
    # Eight bytes including newline. The exact documented limit is accepted;
    # the following status row remains within the same limit as well.
    path.write_bytes(b"#123456\n0 1 +\n")

    summary = parse_mapfile(path, expected_start=0, expected_size=1)

    assert summary.complete_for_expected_range is True
    assert summary.segment_count == 1


def test_mapfile_rejects_oversized_logical_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mapfile_module, "MAX_MAPFILE_LINE_BYTES", 16)
    path = tmp_path / "image.map"
    path.write_bytes(b"#" + (b"X" * 16) + b"\n0 1 +\n")

    with pytest.raises(ValueError, match="line 1 exceeds safety limit"):
        parse_mapfile(path)


def test_mapfile_rejects_total_input_over_byte_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mapfile_module, "MAX_MAPFILE_BYTES", 20)
    monkeypatch.setattr(mapfile_module, "MAX_MAPFILE_LINE_BYTES", 64)
    path = tmp_path / "image.map"
    path.write_text("#1234567890\n#abcdefghij\n0 1 +\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mapfile exceeds safety limit"):
        parse_mapfile(path)


def test_mapfile_rejects_excess_status_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mapfile_module, "MAX_MAP_BLOCKS", 2)
    path = tmp_path / "image.map"
    path.write_text("0 1 +\n1 1 -\n2 1 ?\n", encoding="utf-8")

    with pytest.raises(ValueError, match="2 status blocks"):
        parse_mapfile(path)


def test_mapfile_argument_validation_remains_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "image.map"
    path.write_text("0 1 +\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected_start"):
        parse_mapfile(path, expected_start=-1)
    with pytest.raises(ValueError, match="expected_size"):
        parse_mapfile(path, expected_size=0)
