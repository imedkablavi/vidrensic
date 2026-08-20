from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from vidrensic.plugins.base import DetectionResult, RecordingBoundary
from vidrensic.plugins.capabilities import (
    FailureMode,
    FormatDescriptor,
    FormatOperation,
    RecoveryStrategy,
    StorageTopology,
    SupportLevel,
)
from vidrensic.plugins.dhav.scanner import scan_dhav_frames


class DHAVPlugin:
    name = "dhav"
    display_name = "DHAV surveillance frame stream"
    descriptor = FormatDescriptor(
        family_id="dhav",
        display_name="DHAV surveillance frame stream",
        support_level=SupportLevel.RECONSTRUCT,
        topology=StorageTopology.RAW_INTERLEAVED,
        operations=(
            FormatOperation.DETECT,
            FormatOperation.PROFILE,
            FormatOperation.DATE_SCAN,
            FormatOperation.STREAM_PARSE,
            FormatOperation.NATIVE_RECOVER,
            FormatOperation.CHANNEL_DEMUX,
            FormatOperation.MEDIA_QC,
        ),
        aliases=("DHAV", "DHFS/DHAV frame layer", ".dav DHAV container"),
        vendor_hints=("Dahua-family devices and OEM variants",),
        codecs=("H.264", "H.265/HEVC", "audio/metadata frame variants"),
        timestamp_kinds=("DHAV packed date word + millisecond field",),
        strategies=(
            RecoveryStrategy.SIGNATURE_CARVE,
            RecoveryStrategy.TIMESTAMP_GUIDED,
            RecoveryStrategy.CHANNEL_DEMUX,
            RecoveryStrategy.STREAM_COPY,
        ),
        failure_modes=(
            FailureMode.MISSING_OR_CORRUPT_INDEX,
            FailureMode.DELETED_RECORDING,
            FailureMode.INTERLEAVED_CAMERAS,
            FailureMode.BAD_SECTORS,
            FailureMode.TRUNCATED_RECORD,
            FailureMode.TIMESTAMP_GAPS,
            FailureMode.MIXED_CODEC_OR_VARIANT,
            FailureMode.UNKNOWN_VENDOR_VARIANT,
        ),
        notes=(
            "Frame-level validation requires both DHAV header and dhav footer with matching frame length.",
            "Current demultiplexing preserves physical order; chronological circular-wrap solving is a separate milestone.",
            "Vendor identity is a hint, not proof, because DHAV can appear in OEM/rebranded systems.",
        ),
    )

    def detect(self, source: Path) -> DetectionResult:
        source = source.expanduser().resolve()
        if not source.exists():
            return DetectionResult(self.name, 0.0, ("source does not exist",))

        sample_stop = min(
            source.stat().st_size if source.is_file() else 256 * 1024 * 1024,
            256 * 1024 * 1024,
        )
        try:
            frames = scan_dhav_frames(
                source,
                start=0,
                stop=sample_stop,
                max_frames=64,
                strict_footer=True,
            )
        except (OSError, PermissionError):
            return DetectionResult(self.name, 0.0, ("unable to safely scan source",))

        timestamps = sum(frame.header.timestamp is not None for frame in frames)
        codecs = sorted({frame.codec_hint for frame in frames if frame.codec_hint})
        channels = sorted({frame.header.channel for frame in frames})
        if len(frames) >= 16 and timestamps >= 8:
            confidence = 0.98
        elif len(frames) >= 8:
            confidence = 0.92
        elif len(frames) >= 3:
            confidence = 0.78
        elif len(frames) == 1:
            confidence = 0.55
        else:
            confidence = 0.0
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=(
                f"validated DHAV frames={len(frames)}",
                f"frames with plausible timestamps={timestamps}",
                f"channels observed={channels or 'none'}",
                f"codec hints={codecs or 'none'}",
                f"bounded scan bytes={sample_stop}",
            ),
            metadata={
                "validated_frames": len(frames),
                "timestamp_frames": timestamps,
                "channels": channels,
                "codec_hints": codecs,
                "sampled_bytes": sample_stop,
            },
        )

    def scan_date(
        self,
        source: Path,
        target_date: date,
        *,
        data_offset: int = 0,
    ) -> list[RecordingBoundary]:
        frames = scan_dhav_frames(source, start=data_offset, strict_footer=True)
        groups: dict[tuple[int, int], list[int]] = defaultdict(list)
        timestamps = {}
        for frame in frames:
            timestamp = frame.header.timestamp
            if timestamp is None or timestamp.date() != target_date:
                continue
            key = (timestamp.hour, timestamp.minute)
            groups[key].append(frame.offset)
            timestamps[key] = min(timestamp, timestamps.get(key, timestamp))

        return [
            RecordingBoundary(
                label=f"{hour:02d}-{minute:02d}",
                timestamp=timestamps[(hour, minute)],
                start_fragments=tuple(sorted(offsets)),
                data_offset=data_offset,
                metadata={
                    "units": "byte-offset",
                    "format_family": "dhav",
                    "frame_candidates": len(offsets),
                    "note": "start_fragments contains physical byte offsets for DHAV, not fixed-size WFS fragments",
                },
            )
            for (hour, minute), offsets in sorted(groups.items())
        ]
