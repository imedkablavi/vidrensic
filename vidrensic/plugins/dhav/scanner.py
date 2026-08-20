from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import json
import os

from vidrensic.acquisition.linux import require_safe_source
from vidrensic.core.hashing import forensic_hashes
from vidrensic.plugins.dhav.codec import (
    BASE_HEADER_SIZE,
    FOOTER_SIZE,
    HEADER_MAGIC,
    DHAVHeader,
    DHAVParseError,
    annexb_codec_hint,
    parse_header,
    validate_footer,
)


@dataclass(frozen=True)
class DHAVFrameRecord:
    offset: int
    header: DHAVHeader
    footer_magic_valid: bool
    footer_size_valid: bool
    footer_back_size: int | None
    codec_hint: str | None

    @property
    def structurally_valid(self) -> bool:
        return self.footer_magic_valid and self.footer_size_valid

    @property
    def payload_offset(self) -> int:
        return self.offset + self.header.payload_relative_offset

    @property
    def payload_length(self) -> int:
        return self.header.payload_length


@dataclass
class ChannelStats:
    channel: int
    frames: int = 0
    structurally_valid_frames: int = 0
    video_payload_frames: int = 0
    native_bytes: int = 0
    elementary_bytes: int = 0
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    timestamp_backwards: int = 0
    frame_number_gaps: int = 0
    frame_number_resets: int = 0
    codec_hints: set[str] = field(default_factory=set)
    first_offset: int | None = None
    last_offset: int | None = None
    _last_frame_number: int | None = field(default=None, repr=False)

    def observe(self, frame: DHAVFrameRecord, *, wrote_payload: bool) -> None:
        self.frames += 1
        if frame.structurally_valid:
            self.structurally_valid_frames += 1
        self.native_bytes += frame.header.frame_length
        self.first_offset = frame.offset if self.first_offset is None else self.first_offset
        self.last_offset = frame.offset

        timestamp = frame.header.timestamp
        if timestamp is not None:
            if self.first_timestamp is None:
                self.first_timestamp = timestamp
            if self.last_timestamp is not None and timestamp < self.last_timestamp:
                self.timestamp_backwards += 1
            self.last_timestamp = timestamp

        if self._last_frame_number is not None:
            if frame.header.frame_number < self._last_frame_number:
                self.frame_number_resets += 1
            elif frame.header.frame_number > self._last_frame_number + 1:
                self.frame_number_gaps += 1
        self._last_frame_number = frame.header.frame_number

        if frame.codec_hint:
            self.codec_hints.add(frame.codec_hint)
        if wrote_payload:
            self.video_payload_frames += 1
            self.elementary_bytes += frame.payload_length

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "frames": self.frames,
            "structurally_valid_frames": self.structurally_valid_frames,
            "video_payload_frames": self.video_payload_frames,
            "native_bytes": self.native_bytes,
            "elementary_bytes": self.elementary_bytes,
            "first_timestamp": self.first_timestamp.isoformat() if self.first_timestamp else None,
            "last_timestamp": self.last_timestamp.isoformat() if self.last_timestamp else None,
            "timestamp_backwards": self.timestamp_backwards,
            "frame_number_gaps": self.frame_number_gaps,
            "frame_number_resets": self.frame_number_resets,
            "codec_hints": sorted(self.codec_hints),
            "first_offset": self.first_offset,
            "last_offset": self.last_offset,
        }


def validate_frame_at(
    fd: int,
    offset: int,
    source_size: int,
    *,
    codec_probe_bytes: int = 4096,
) -> DHAVFrameRecord | None:
    header_bytes = os.pread(fd, BASE_HEADER_SIZE, offset)
    if len(header_bytes) != BASE_HEADER_SIZE:
        return None
    try:
        header = parse_header(header_bytes)
    except DHAVParseError:
        return None
    end = offset + header.frame_length
    if end > source_size:
        return None

    footer = os.pread(fd, FOOTER_SIZE, end - FOOTER_SIZE)
    magic_ok, size_ok, back_size = validate_footer(footer, header.frame_length)
    payload_probe = os.pread(
        fd,
        min(codec_probe_bytes, max(0, header.payload_length)),
        offset + header.payload_relative_offset,
    )
    return DHAVFrameRecord(
        offset=offset,
        header=header,
        footer_magic_valid=magic_ok,
        footer_size_valid=size_ok,
        footer_back_size=back_size,
        codec_hint=annexb_codec_hint(payload_probe),
    )


def scan_dhav_frames(
    source: Path,
    *,
    start: int = 0,
    stop: int | None = None,
    chunk_size: int = 8 * 1024 * 1024,
    max_frames: int | None = None,
    strict_footer: bool = True,
) -> list[DHAVFrameRecord]:
    """Scan a source range for DHAV frames using header/footer validation.

    This function intentionally returns physical-order records. Chronological
    reordering is a separate reconstruction decision because circular recording
    stores can wrap and timestamps can themselves be damaged.
    """

    if start < 0:
        raise ValueError("start cannot be negative")
    if chunk_size < 4096 or chunk_size > 128 * 1024 * 1024:
        raise ValueError("chunk_size must be between 4 KiB and 128 MiB")
    if max_frames is not None and max_frames <= 0:
        raise ValueError("max_frames must be positive")

    info = require_safe_source(source)
    end = info.size_bytes if stop is None else min(stop, info.size_bytes)
    if end < start:
        raise ValueError("stop cannot precede start")

    fd = os.open(info.path, os.O_RDONLY)
    records: list[DHAVFrameRecord] = []
    carry = b""
    position = start
    emitted: set[int] = set()
    try:
        while position < end:
            wanted = min(chunk_size, end - position)
            chunk = os.pread(fd, wanted, position)
            if not chunk:
                break
            data = carry + chunk
            data_base = position - len(carry)
            cursor = 0
            while True:
                cursor = data.find(HEADER_MAGIC, cursor)
                if cursor < 0:
                    break
                absolute = data_base + cursor
                cursor += 1
                if absolute < start or absolute in emitted:
                    continue
                emitted.add(absolute)
                record = validate_frame_at(fd, absolute, info.size_bytes)
                if record is None:
                    continue
                if strict_footer and not record.structurally_valid:
                    continue
                records.append(record)
                if max_frames is not None and len(records) >= max_frames:
                    return records
            carry = data[-3:]
            position += len(chunk)
    finally:
        os.close(fd)
    return records


def demux_dhav_range(
    source: Path,
    output_dir: Path,
    *,
    start: int = 0,
    stop: int | None = None,
    include_unvalidated: bool = False,
) -> Path:
    """Demultiplex a DHAV physical range into per-channel native and ES copies.

    Native `.dhav` outputs preserve complete validated frame records. Elementary
    stream files contain only payloads that exhibit a conservative Annex-B codec
    signature. Output remains REVIEW when timestamp/frame-number discontinuities
    or mixed codec hints are observed.
    """

    info = require_safe_source(source)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    records = scan_dhav_frames(
        info.path,
        start=start,
        stop=stop,
        strict_footer=not include_unvalidated,
    )

    native_handles: dict[int, Any] = {}
    es_handles: dict[int, Any] = {}
    stats: dict[int, ChannelStats] = {}
    fd = os.open(info.path, os.O_RDONLY)
    try:
        for frame in records:
            channel = frame.header.channel
            stat = stats.setdefault(channel, ChannelStats(channel=channel))
            native = native_handles.get(channel)
            if native is None:
                native_path = output_dir / f"channel_{channel:02d}.native.dhav"
                native = native_path.open("wb")
                native_handles[channel] = native

            raw_frame = os.pread(fd, frame.header.frame_length, frame.offset)
            if len(raw_frame) != frame.header.frame_length:
                continue
            native.write(raw_frame)

            wrote_payload = False
            if frame.codec_hint and frame.payload_length > 0:
                es = es_handles.get(channel)
                if es is None:
                    es_path = output_dir / f"channel_{channel:02d}.video.es"
                    es = es_path.open("wb")
                    es_handles[channel] = es
                payload = raw_frame[
                    frame.header.payload_relative_offset : frame.header.frame_length - FOOTER_SIZE
                ]
                es.write(payload)
                wrote_payload = True
            stat.observe(frame, wrote_payload=wrote_payload)
    finally:
        os.close(fd)
        for handle in (*native_handles.values(), *es_handles.values()):
            handle.close()

    channels: list[dict[str, Any]] = []
    for channel in sorted(stats):
        item = stats[channel].to_dict()
        native_path = output_dir / f"channel_{channel:02d}.native.dhav"
        es_path = output_dir / f"channel_{channel:02d}.video.es"
        if native_path.exists():
            hashes = forensic_hashes(native_path)
            item["native_output"] = str(native_path)
            item["native_sha256"] = hashes.sha256
            item["native_sha512"] = hashes.sha512
        if es_path.exists():
            hashes = forensic_hashes(es_path)
            item["elementary_output"] = str(es_path)
            item["elementary_sha256"] = hashes.sha256
            item["elementary_sha512"] = hashes.sha512
        reasons: list[str] = []
        if item["timestamp_backwards"]:
            reasons.append("timestamp decreases observed in physical order; circular wrap or corruption possible")
        if item["frame_number_gaps"]:
            reasons.append("frame-number gaps observed")
        if item["frame_number_resets"]:
            reasons.append("frame-number resets observed")
        if len(item["codec_hints"]) > 1:
            reasons.append("mixed codec hints observed")
        item["status"] = "REVIEW" if reasons else "UNKNOWN"
        item["reasons"] = reasons or ["full media validation has not been performed"]
        channels.append(item)

    manifest = {
        "schema_version": 1,
        "format_family": "dhav",
        "source": str(info.path),
        "source_size": info.size_bytes,
        "scan_start": start,
        "scan_stop": info.size_bytes if stop is None else min(stop, info.size_bytes),
        "ordering": "physical",
        "include_unvalidated": include_unvalidated,
        "frame_count": len(records),
        "channels": channels,
        "forensic_notes": [
            "native outputs are derived channel-demultiplexed copies; source evidence is unchanged",
            "physical ordering is preserved; chronological circular-buffer reconstruction is not implied",
            "UNKNOWN is used when no discontinuity was observed because full QC has not yet run",
        ],
    }
    manifest_path = output_dir / "dhav_manifest.json"
    temp = manifest_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(manifest_path)
    return manifest_path
