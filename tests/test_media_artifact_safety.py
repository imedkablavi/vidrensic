from __future__ import annotations

from pathlib import Path

import pytest

from vidrensic.media import inventory, timeline


def test_media_inventory_rejects_symlink_before_resolution(tmp_path: Path) -> None:
    target = tmp_path / "target.mp4"
    link = tmp_path / "alias.mp4"
    target.write_bytes(b"fixture")
    link.symlink_to(target)

    with pytest.raises(ValueError, match="non-symlink"):
        inventory.inspect_media(link)


def test_media_timeline_rejects_symlink_before_resolution(tmp_path: Path) -> None:
    target = tmp_path / "target.mp4"
    link = tmp_path / "alias.mp4"
    target.write_bytes(b"fixture")
    link.symlink_to(target)

    with pytest.raises(ValueError, match="non-symlink"):
        timeline.analyze_media_timeline(link)
