from __future__ import annotations

from pathlib import Path
import struct

from vidrensic.profiler.triage import triage_source


def _packed_time() -> int:
    return (
        (26 << 26)
        | (8 << 22)
        | (9 << 17)
        | (12 << 12)
    )


def _dhav_frame(channel: int, frame_number: int) -> bytes:
    payload = b"\x00\x00\x00\x01\x67\x42\x00\x1f" + bytes([channel]) * 64
    frame_length = 24 + len(payload) + 8
    header = bytearray(24)
    header[:4] = b"DHAV"
    header[4] = 0xFD
    header[6] = channel
    struct.pack_into("<I", header, 8, frame_number)
    struct.pack_into("<I", header, 12, frame_length)
    struct.pack_into("<I", header, 16, _packed_time())
    struct.pack_into("<H", header, 20, 100)
    footer = b"dhav" + struct.pack("<I", frame_length)
    return bytes(header) + payload + footer


def test_triage_ranks_dhav_and_recommends_demux(tmp_path: Path) -> None:
    source = tmp_path / "unknown-dvr.raw"
    source.write_bytes(b"noise" + b"".join(_dhav_frame(index % 2, index) for index in range(16)))

    report = triage_source(
        source,
        sample_size=512,
        sample_count=3,
        hitmap_size=None,
        hitmap_chunk_size=4096,
    )
    assert report.source_info["safe_for_forensic_read"]
    assert report.format_detection["results"][0]["plugin"] == "dhav"
    assert not report.format_detection["requires_review"]
    assert any("demultiplex" in action for action in report.recommended_actions)
    dhav_hits = next(
        row for row in report.hitmap["signatures"] if row["signature_id"] == "dhav_header"
    )
    assert dhav_hits["count"] == 16
