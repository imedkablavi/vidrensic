from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import struct


FRAGMENT_SIZE = 2 * 1024 * 1024
MAX_PACKET_SIZE = 4 * 1024 * 1024
SYNC = b"\x00\x00\x01"
VIDEO_TYPES = frozenset({0xFC, 0xFD, 0xFE})
KNOWN_TYPES = frozenset(set(VIDEO_TYPES) | {0xFA, 0xF9})


class WFSParseError(ValueError):
    pass


@dataclass(frozen=True)
class PacketInfo:
    packet_type: int
    header_size: int
    payload_size: int
    total_size: int


def decode_timestamp_word(value: int) -> datetime | None:
    try:
        return datetime(
            2000 + ((value >> 26) & 0x3F),
            (value >> 22) & 0x0F,
            (value >> 17) & 0x1F,
            (value >> 12) & 0x1F,
            (value >> 6) & 0x3F,
            value & 0x3F,
        )
    except ValueError:
        return None


def encode_timestamp_word(value: datetime) -> int:
    year = value.year - 2000
    if not 0 <= year <= 0x3F:
        raise ValueError("WFS timestamp year must be between 2000 and 2063")
    return (
        (year << 26)
        | (value.month << 22)
        | (value.day << 17)
        | (value.hour << 12)
        | (value.minute << 6)
        | value.second
    )


def packet_info(data: bytes, offset: int = 0) -> PacketInfo | None:
    remain = len(data) - offset
    if remain < 4 or data[offset : offset + 3] != SYNC:
        return None

    packet_type = data[offset + 3]
    if packet_type in (0xFD, 0xFE):
        header_size = 16
        if remain < header_size:
            return None
        payload_size = struct.unpack_from("<I", data, offset + 12)[0]
    elif packet_type == 0xFC:
        header_size = 8
        if remain < header_size:
            return None
        payload_size = struct.unpack_from("<I", data, offset + 4)[0]
    elif packet_type in (0xFA, 0xF9):
        header_size = 8
        if remain < header_size:
            return None
        payload_size = struct.unpack_from("<H", data, offset + 6)[0]
    else:
        return None

    if not 0 < payload_size <= MAX_PACKET_SIZE:
        return None
    return PacketInfo(
        packet_type=packet_type,
        header_size=header_size,
        payload_size=payload_size,
        total_size=header_size + payload_size,
    )


def padding_here(data: bytes, offset: int, *, run: int = 64) -> bool:
    remain = len(data) - offset
    if remain <= 0:
        return True
    n = min(run, remain)
    if n < 16:
        sample = data[offset:]
    else:
        sample = data[offset : offset + n]
    return bool(sample) and all(byte in (0x00, 0xFF) for byte in sample)


def parse_fragment_tail(data: bytes) -> bytes | None:
    """Return None for terminal padding, b'' for an exact boundary, or a carry tail."""

    offset = 0
    while offset < len(data):
        if padding_here(data, offset):
            return None
        info = packet_info(data, offset)
        if info is None:
            # If fewer than a full candidate header remain, carry it forward;
            # otherwise this is a structural sync loss.
            if len(data) - offset < 16:
                return data[offset:]
            raise WFSParseError(
                f"WFS sync lost at 0x{offset:X}: {data[offset:offset+32].hex(' ')}"
            )
        end = offset + info.total_size
        if end > len(data):
            return data[offset:]
        offset = end
    return b""


def fd_timestamp(header: bytes) -> datetime | None:
    if len(header) < 12 or header[:4] not in (b"\x00\x00\x01\xfd", b"\x00\x00\x01\xfe"):
        return None
    return decode_timestamp_word(struct.unpack_from("<I", header, 8)[0])
