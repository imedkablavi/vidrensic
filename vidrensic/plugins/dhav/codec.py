from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import struct


HEADER_MAGIC = b"DHAV"
FOOTER_MAGIC = b"dhav"
BASE_HEADER_SIZE = 24
FOOTER_SIZE = 8
MIN_FRAME_SIZE = BASE_HEADER_SIZE + FOOTER_SIZE
MAX_FRAME_SIZE = 64 * 1024 * 1024


class DHAVParseError(ValueError):
    pass


@dataclass(frozen=True)
class DHAVHeader:
    frame_type: int
    subtype: int
    channel: int
    subchannel: int
    frame_number: int
    frame_length: int
    timestamp_word: int
    timestamp: datetime | None
    milliseconds: int
    extension_length: int
    checksum: int

    @property
    def payload_relative_offset(self) -> int:
        return BASE_HEADER_SIZE + self.extension_length

    @property
    def payload_length(self) -> int:
        return self.frame_length - FOOTER_SIZE - self.payload_relative_offset


def decode_timestamp_word(value: int) -> datetime | None:
    """Decode the packed DHAV date word used by FFmpeg's DHAV demuxer.

    The bit layout is the same year/month/day/hour/minute/second packing seen
    in several surveillance formats. Invalid calendar values remain unknown.
    """

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


def parse_header(data: bytes, offset: int = 0) -> DHAVHeader:
    if len(data) - offset < BASE_HEADER_SIZE:
        raise DHAVParseError("short DHAV header")
    if data[offset : offset + 4] != HEADER_MAGIC:
        raise DHAVParseError("missing DHAV header magic")

    frame_type = data[offset + 4]
    subtype = data[offset + 5]
    channel = data[offset + 6]
    subchannel = data[offset + 7]
    frame_number = struct.unpack_from("<I", data, offset + 8)[0]
    frame_length = struct.unpack_from("<I", data, offset + 12)[0]
    timestamp_word = struct.unpack_from("<I", data, offset + 16)[0]
    milliseconds = struct.unpack_from("<H", data, offset + 20)[0]
    extension_length = data[offset + 22]
    checksum = data[offset + 23]

    if not MIN_FRAME_SIZE <= frame_length <= MAX_FRAME_SIZE:
        raise DHAVParseError(f"implausible DHAV frame length: {frame_length}")
    payload_offset = BASE_HEADER_SIZE + extension_length
    if payload_offset > frame_length - FOOTER_SIZE:
        raise DHAVParseError(
            f"DHAV extension exceeds frame payload: ext={extension_length} frame={frame_length}"
        )

    return DHAVHeader(
        frame_type=frame_type,
        subtype=subtype,
        channel=channel,
        subchannel=subchannel,
        frame_number=frame_number,
        frame_length=frame_length,
        timestamp_word=timestamp_word,
        timestamp=decode_timestamp_word(timestamp_word),
        milliseconds=milliseconds,
        extension_length=extension_length,
        checksum=checksum,
    )


def validate_footer(footer: bytes, frame_length: int) -> tuple[bool, bool, int | None]:
    if len(footer) != FOOTER_SIZE:
        return False, False, None
    magic_ok = footer[:4] == FOOTER_MAGIC
    back_size = struct.unpack_from("<I", footer, 4)[0]
    return magic_ok, back_size == frame_length, back_size


def annexb_codec_hint(data: bytes) -> str | None:
    """Return a conservative H.264/HEVC hint from Annex-B parameter sets."""

    if not data:
        return None
    # Search both 3-byte and 4-byte start codes and inspect the following NAL
    # header. We only claim a codec when a characteristic parameter-set NAL is
    # observed; ordinary slice NAL values overlap too much for safe guessing.
    for marker in (b"\x00\x00\x00\x01", b"\x00\x00\x01"):
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos < 0:
                break
            nal = pos + len(marker)
            if nal >= len(data):
                break
            first = data[nal]
            h264_type = first & 0x1F
            hevc_type = (first >> 1) & 0x3F
            if h264_type in (7, 8):
                return "h264"
            if hevc_type in (32, 33, 34):
                return "hevc"
            pos = nal + 1
    return None
