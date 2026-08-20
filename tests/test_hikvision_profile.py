from __future__ import annotations

from pathlib import Path
import struct

from vidrensic.plugins.hikvision import HikvisionPlugin, find_master_candidates
from vidrensic.plugins.capabilities import SupportLevel


def test_hikvision_master_candidate_is_found_dynamically(tmp_path: Path) -> None:
    source = tmp_path / "hik.img"
    image = bytearray(8 * 1024 * 1024)
    offset = 0x2400
    master = bytearray(256)
    master[:18] = b"HIKVISION@HANGZHOU"
    struct.pack_into("<Q", master, 0x38, len(image))
    struct.pack_into("<Q", master, 0x50, 0x20000)
    struct.pack_into("<Q", master, 0x58, 0x10000)
    struct.pack_into("<Q", master, 0x68, 0x100000)
    struct.pack_into("<Q", master, 0x78, 0x200000)
    struct.pack_into("<Q", master, 0x80, 3)
    struct.pack_into("<Q", master, 0x88, 0x700000)
    struct.pack_into("<Q", master, 0x90, 0x10000)
    struct.pack_into("<I", master, 0xE0, 1_700_000_000)
    image[offset : offset + len(master)] = master
    source.write_bytes(image)

    candidates = find_master_candidates(source)
    assert len(candidates) == 1
    assert candidates[0].offset == offset
    assert candidates[0].video_data_offset == 0x100000
    assert candidates[0].plausibility_score > 0.7

    plugin = HikvisionPlugin()
    assert plugin.descriptor.support_level == SupportLevel.PROFILE
    result = plugin.detect(source)
    assert result.confidence > 0.75
    assert result.metadata["support_stage"] == "PROFILE"
