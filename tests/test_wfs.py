from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import json
import os
import struct

from vidrensic.plugins.wfs.codec import (
    FRAGMENT_SIZE,
    decode_timestamp_word,
    encode_timestamp_word,
    packet_info,
    parse_fragment_tail,
)
from vidrensic.plugins.wfs.reconstruct import extract_hevc
from vidrensic.plugins.wfs.recovery import recover_segment
from vidrensic.plugins.wfs.scanner import scan_recording_starts


def _fd_header(ts: datetime, payload_size: int = 32) -> bytes:
    header = bytearray(16)
    header[:4] = b"\x00\x00\x01\xfd"
    struct.pack_into("<I", header, 8, encode_timestamp_word(ts))
    struct.pack_into("<I", header, 12, payload_size)
    return bytes(header)


def _fc_packet(payload: bytes) -> bytes:
    return b"\x00\x00\x01\xfc" + struct.pack("<I", len(payload)) + payload


def test_timestamp_roundtrip() -> None:
    original = datetime(2026, 8, 9, 13, 27, 45)
    assert decode_timestamp_word(encode_timestamp_word(original)) == original


def test_packet_parser_and_padding_tail() -> None:
    payload = b"\x00\x00\x01\x26" + b"video" * 20
    packet = _fc_packet(payload)
    info = packet_info(packet)
    assert info is not None
    assert info.packet_type == 0xFC
    assert info.payload_size == len(payload)
    fragment = packet + bytes(FRAGMENT_SIZE - len(packet))
    assert parse_fragment_tail(fragment) is None


def test_scan_groups_simultaneous_starts(tmp_path: Path) -> None:
    raw = tmp_path / "wfs.raw"
    with raw.open("wb") as fh:
        fh.truncate(FRAGMENT_SIZE * 5)
    fd = os.open(raw, os.O_RDWR)
    try:
        os.pwrite(fd, _fd_header(datetime(2026, 8, 9, 9, 0, 0)), 0 * FRAGMENT_SIZE)
        os.pwrite(fd, _fd_header(datetime(2026, 8, 9, 9, 0, 1)), 1 * FRAGMENT_SIZE)
        os.pwrite(fd, _fd_header(datetime(2026, 8, 9, 10, 0, 0)), 3 * FRAGMENT_SIZE)
    finally:
        os.close(fd)

    boundaries = scan_recording_starts(raw, date(2026, 8, 9))
    assert [item.label for item in boundaries] == ["09-00", "10-00"]
    assert boundaries[0].start_fragments == (0, 1)
    assert boundaries[1].start_fragments == (3,)


def test_extract_native_payload(tmp_path: Path) -> None:
    payload = b"\x00\x00\x00\x01\x40" + b"native-hevc" * 10
    packet = _fc_packet(payload)
    raw = tmp_path / "source.raw"
    with raw.open("wb") as fh:
        fh.write(packet)
        fh.write(bytes(FRAGMENT_SIZE - len(packet)))

    out = tmp_path / "native.hevc"
    fd = os.open(raw, os.O_RDONLY)
    try:
        result = extract_hevc(fd, [0], out)
    finally:
        os.close(fd)
    assert out.read_bytes() == payload
    assert result.hevc_bytes == len(payload)
    assert result.video_packets == 1


def test_high_level_recovery_writes_manifest_without_false_pass(tmp_path: Path) -> None:
    payload = b"\x00\x00\x00\x01\x40" + b"candidate" * 16
    packet = _fc_packet(payload)
    raw = tmp_path / "source.raw"
    with raw.open("wb") as fh:
        fh.write(packet)
        fh.write(bytes(FRAGMENT_SIZE - len(packet)))

    candidates, manifest = recover_segment(
        raw,
        [0],
        1,
        tmp_path / "recovered",
        label="09-00",
    )
    assert len(candidates) == 1
    assert candidates[0].status == "UNKNOWN"
    assert candidates[0].native_output.read_bytes() == payload
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["plugin"] == "wfs"
    assert data["candidates"][0]["status"] == "UNKNOWN"
