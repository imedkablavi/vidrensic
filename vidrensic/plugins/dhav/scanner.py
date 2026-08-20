from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
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
    DHAVExtensionInfo,
    DHAVHeader,
    DHAVParseError,
    annexb_codec_hint,
    parse_extension,
    parse_header,
    validate_footer,
)


@dataclass(frozen=True)
class DHAVFrameRecord:
    offset: int
    header: DHAVHeader
    extension: DHAVExtensionInfo
    footer_magic_valid: bool
    footer_size_valid: bool
    footer_back_size: int | None
    payload_codec_hint: str | None
    codec_hint: str | None

    @property
    def structurally_valid(self) -> bool:
        return self.footer_magic_valid and self.footer_size_valid and not self.extension.truncated

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
    codec_conflicts: int = 0
    extension_truncated: int = 0
    frame_types: dict[int, int] = field(default_factory=dict)
    codec_hints: set[str] = field(default_factory=set)
    declared_codecs: set[str] = field(default_factory=set)
    resolutions: set[str] = field(default_factory=set)
    frame_rates: set[int] = field(default_factory=set)
    audio_sample_rates: set[int] = field(default_factory=set)
    unknown_extension_types: set[int] = field(default_factory=set)
    first_offset: int | None = None
    last_offset: int | None = None
    _last_frame_number: int | None = field(default=None, repr=False)

    def observe(self, frame: DHAVFrameRecord, *, wrote_payload: bool) -> None:
        self.frames += 1
        self.frame_types[frame.header.frame_type] = self.frame_types.get(frame.header.frame_type, 0) + 1
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

        extension = frame.extension
        if extension.truncated:
            self.extension_truncated += 1
        self.unknown_extension_types.update(extension.unknown_types)
        if extension.video_codec:
            self.declared_codecs.add(extension.video_codec)
        if extension.width and extension.height:
            self.resolutions.add(f"{extension.width}x{extension.height}")
        if extension.frame_rate:
            self.frame_rates.add(extension.frame_rate)
        if extension.sample_rate:
            self.audio_sample_rates.add(extension.sample_rate)

        if frame.codec_hint:
            self.codec_hints.add(frame.codec_hint)
        if (
            extension.video_codec
            and frame.payload_codec_hint
            and extension.video_codec != frame.payload_codec_hint
        ):
            self.codec_conflicts += 1
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
            "codec_conflicts": self.codec_conflicts,
            "extension_truncated": self.extension_truncated,
            "frame_types": {f"0x{key:02X}": value for key, value in sorted(self.frame_types.items())},
            "codec_hints": sorted(self.codec_hints),
            "declared_codecs": sorted(self.declared_codecs),
            "resolutions": sorted(self.resolutions),
            "frame_rates": sorted(self.frame_rates),
            "audio_sample_rates": sorted(self.audio_sample_rates),
            "unknown_extension_types": [f"0x{value:02X}" for value in sorted(self.unknown_extension_types)],
            "first_offset": self.first_offset,
            "last_offset": self.last_offset,
        }


def validate_frame_at(
    fd: int,
    offset: int,
    source_size: int,
    *,
    range_stop: int | None = None,
    codec_probe_bytes: int = 4096,
) -> DHAVFrameRecord | None:
    limit = source_size if range_stop is None else min(source_size, range_stop)
    if offset < 0 or offset + BASE_HEADER_SIZE > limit:
        return None
    header_bytes = os.pread(fd, BASE_HEADER_SIZE, offset)
    if len(header_bytes) != BASE_HEADER_SIZE:
        return None
    try:
        header = parse_header(header_bytes)
    except DHAVParseError:
        return None
    end = offset + header.frame_length
    if end > limit:
        return None

    extension_bytes = os.pread(fd, header.extension_length, offset + BASE_HEADER_SIZE)
    if len(extension_bytes) != header.extension_length:
        return None
    extension = parse_extension(extension_bytes)

    footer = os.pread(fd, FOOTER_SIZE, end - FOOTER_SIZE)
    magic_ok, size_ok, back_size = validate_footer(footer, header.frame_length)
    payload_probe = os.pread(
        fd,
        min(codec_probe_bytes, max(0, header.payload_length)),
        offset + header.payload_relative_offset,
    )
    payload_codec = annexb_codec_hint(payload_probe)
    declared_codec = extension.video_codec
    codec_hint = declared_codec or payload_codec
    return DHAVFrameRecord(
        offset=offset,
        header=header,
        extension=extension,
        footer_magic_valid=magic_ok,
        footer_size_valid=size_ok,
        footer_back_size=back_size,
        payload_codec_hint=payload_codec,
        codec_hint=codec_hint,
    )


def iter_dhav_frames(
    source: Path,
    *,
    start: int = 0,
    stop: int | None = None,
    chunk_size: int = 8 * 1024 * 1024,
    max_frames: int | None = None,
    strict_footer: bool = True,
) -> Iterator[DHAVFrameRecord]:
    """Yield DHAV records in physical order using bounded memory."""

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
    carry = b""
    position = start
    last_examined_offset: int | None = None
    emitted = 0
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
                if absolute < start:
                    continue
                if last_examined_offset is not None and absolute <= last_examined_offset:
                    continue
                last_examined_offset = absolute
                record = validate_frame_at(
                    fd,
                    absolute,
                    info.size_bytes,
                    range_stop=end,
                )
                if record is None:
                    continue
                if strict_footer and not record.structurally_valid:
                    continue
                yield record
                emitted += 1
                if max_frames is not None and emitted >= max_frames:
                    return
            carry = data[-3:]
            position += len(chunk)
    finally:
        os.close(fd)


def scan_dhav_frames(
    source: Path,
    *,
    start: int = 0,
    stop: int | None = None,
    chunk_size: int = 8 * 1024 * 1024,
    max_frames: int | None = None,
    strict_footer: bool = True,
) -> list[DHAVFrameRecord]:
    return list(
        iter_dhav_frames(
            source,
            start=start,
            stop=stop,
            chunk_size=chunk_size,
            max_frames=max_frames,
            strict_footer=strict_footer,
        )
    )


def _reserve_output(path: Path, created: list[Path]) -> None:
    if path.exists() or path.with_name(path.name + ".partial").exists():
        raise FileExistsError(f"DHAV output already exists: {path}")
    created.append(path)


def demux_dhav_range(
    source: Path,
    output_dir: Path,
    *,
    start: int = 0,
    stop: int | None = None,
    include_unvalidated: bool = False,
) -> Path:
    """Stream validated DHAV records into per-channel native and ES copies."""

    info = require_safe_source(source)
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "dhav_manifest.json"
    if manifest_path.exists() or manifest_path.with_name(manifest_path.name + ".partial").exists():
        raise FileExistsError(f"DHAV manifest already exists: {manifest_path}")

    native_handles: dict[int, Any] = {}
    es_handles: dict[int, Any] = {}
    stats: dict[int, ChannelStats] = {}
    frame_count = 0
    created: list[Path] = []
    fd = os.open(info.path, os.O_RDONLY)
    try:
        for frame in iter_dhav_frames(
            info.path,
            start=start,
            stop=stop,
            strict_footer=not include_unvalidated,
        ):
            frame_count += 1
            channel = frame.header.channel
            stat = stats.setdefault(channel, ChannelStats(channel=channel))
            native = native_handles.get(channel)
            if native is None:
                native_path = output_dir / f"channel_{channel:02d}.native.dhav"
                _reserve_output(native_path, created)
                native = native_path.open("xb")
                native_handles[channel] = native

            raw_frame = os.pread(fd, frame.header.frame_length, frame.offset)
            if len(raw_frame) != frame.header.frame_length:
                continue
            native.write(raw_frame)

            wrote_payload = False
            if frame.header.frame_type == 0xFD and frame.codec_hint and frame.payload_length > 0:
                es = es_handles.get(channel)
                if es is None:
                    es_path = output_dir / f"channel_{channel:02d}.video.es"
                    _reserve_output(es_path, created)
                    es = es_path.open("xb")
                    es_handles[channel] = es
                payload = raw_frame[
                    frame.header.payload_relative_offset : frame.header.frame_length - FOOTER_SIZE
                ]
                es.write(payload)
                wrote_payload = True
            stat.observe(frame, wrote_payload=wrote_payload)
    except Exception:
        for handle in (*native_handles.values(), *es_handles.values()):
            try:
                handle.close()
            except Exception:
                pass
        for path in created:
            if path.exists():
                partial = path.with_name(path.name + ".partial")
                if not partial.exists():
                    path.rename(partial)
        raise
    finally:
        os.close(fd)
        for handle in (*native_handles.values(), *es_handles.values()):
            if not handle.closed:
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
        if item["codec_conflicts"]:
            reasons.append("DHAV extension codec metadata conflicts with Annex-B payload evidence")
        if item["extension_truncated"]:
            reasons.append("one or more DHAV extension blocks were truncated")
        if len(item["codec_hints"]) > 1:
            reasons.append("mixed codec hints observed")
        item["status"] = "REVIEW" if reasons else "UNKNOWN"
        item["reasons"] = reasons or ["full media validation has not been performed"]
        channels.append(item)

    manifest = {
        "schema_version": 2,
        "format_family": "dhav",
        "source": str(info.path),
        "source_size": info.size_bytes,
        "scan_start": start,
        "scan_stop": info.size_bytes if stop is None else min(stop, info.size_bytes),
        "ordering": "physical",
        "streaming_scan": True,
        "include_unvalidated": include_unvalidated,
        "frame_count": frame_count,
        "channels": channels,
        "forensic_notes": [
            "native outputs are derived channel-demultiplexed copies; source evidence is unchanged",
            "physical ordering is preserved; chronological circular-buffer reconstruction is not implied",
            "DHAV extension codec/resolution/fps/audio metadata is retained as evidence and cross-checked with payload hints",
            "a bounded scan never accepts a frame whose end extends beyond the requested stop offset",
            "UNKNOWN is used when no discontinuity was observed because full QC has not yet run",
        ],
    }
    temp = manifest_path.with_name(manifest_path.name + ".partial")
    try:
        with temp.open("x", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        temp.replace(manifest_path)
    except Exception:
        if temp.exists():
            temp.unlink()
        raise
    return manifest_path
