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

SAMPLE_RATES = (
    8000,
    4000,
    8000,
    11025,
    16000,
    20000,
    22050,
    32000,
    44100,
    48000,
    96000,
    192000,
    64000,
)
VIDEO_CODEC_NAMES = {
    0x01: "mpeg4",
    0x02: "h264",
    0x03: "mjpeg",
    0x04: "h264",
    0x08: "h264",
    0x0C: "hevc",
}


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


@dataclass(frozen=True)
class DHAVExtensionInfo:
    width: int | None = None
    height: int | None = None
    video_codec_code: int | None = None
    video_codec: str | None = None
    frame_rate: int | None = None
    audio_channels: int | None = None
    audio_codec_code: int | None = None
    sample_rate: int | None = None
    parsed_types: tuple[int, ...] = ()
    unknown_types: tuple[int, ...] = ()
    truncated: bool = False


def decode_timestamp_word(value: int) -> datetime | None:
    """Decode the packed DHAV date word used by FFmpeg's DHAV demuxer."""

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


def _sample_rate(index: int) -> int | None:
    return SAMPLE_RATES[index] if 0 <= index < len(SAMPLE_RATES) else None


def parse_extension(data: bytes) -> DHAVExtensionInfo:
    """Parse documented DHAV extension records conservatively.

    Record widths follow FFmpeg's DHAV demuxer. Unknown types terminate parsing
    because their size is not safely known; raw frame bytes remain preserved.
    """

    pos = 0
    width = height = None
    video_codec_code = frame_rate = None
    audio_channels = audio_codec_code = sample_rate = None
    parsed: list[int] = []
    unknown: list[int] = []
    truncated = False

    while pos < len(data):
        record_type = data[pos]
        if record_type == 0x80:
            length = 4
            if pos + length > len(data):
                truncated = True
                break
            width = 8 * data[pos + 2]
            height = 8 * data[pos + 3]
        elif record_type == 0x81:
            length = 4
            if pos + length > len(data):
                truncated = True
                break
            video_codec_code = data[pos + 2]
            frame_rate = data[pos + 3]
        elif record_type == 0x82:
            length = 8
            if pos + length > len(data):
                truncated = True
                break
            width = struct.unpack_from("<H", data, pos + 4)[0]
            height = struct.unpack_from("<H", data, pos + 6)[0]
        elif record_type == 0x83:
            length = 4
            if pos + length > len(data):
                truncated = True
                break
            audio_channels = data[pos + 1]
            audio_codec_code = data[pos + 2]
            sample_rate = _sample_rate(data[pos + 3])
        elif record_type == 0x8C:
            length = 8
            if pos + length > len(data):
                truncated = True
                break
            audio_channels = data[pos + 2]
            audio_codec_code = data[pos + 3]
            sample_rate = _sample_rate(data[pos + 4])
        elif record_type in {0x88, 0x91, 0x92, 0x93, 0x95, 0x9A, 0x9B, 0xB3}:
            length = 8
            if pos + length > len(data):
                truncated = True
                break
        elif record_type in {0x84, 0x85, 0x8B, 0x94, 0x96, 0xA0, 0xB2, 0xB4}:
            length = 4
            if pos + length > len(data):
                truncated = True
                break
        else:
            unknown.append(record_type)
            break

        parsed.append(record_type)
        pos += length

    return DHAVExtensionInfo(
        width=width,
        height=height,
        video_codec_code=video_codec_code,
        video_codec=VIDEO_CODEC_NAMES.get(video_codec_code),
        frame_rate=frame_rate,
        audio_channels=audio_channels,
        audio_codec_code=audio_codec_code,
        sample_rate=sample_rate,
        parsed_types=tuple(parsed),
        unknown_types=tuple(unknown),
        truncated=truncated,
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
    for marker in (b"\x00\x00\x00\x01", b"\x00\x01"):
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
