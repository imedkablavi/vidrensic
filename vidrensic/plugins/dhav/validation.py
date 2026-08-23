from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from vidrensic.plugins.dhav.scanner import DHAVFrameRecord


@dataclass(frozen=True)
class DHAVChronologyAssessment:
    status: str
    candidate_wrap_offset: int | None
    timestamped_frames: int
    timestamp_backwards: int
    frame_number_resets: int
    reordered_monotonic: bool | None
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DHAVAudioAssessment:
    status: str
    frames_with_audio_metadata: int
    sample_rates: tuple[int, ...]
    channel_counts: tuple[int, ...]
    codec_codes: tuple[int, ...]
    metadata_conflicts: int
    reasons: tuple[str, ...]


def assess_single_circular_wrap(records: Iterable[DHAVFrameRecord]) -> DHAVChronologyAssessment:
    """Assess whether physical-order timestamps support one circular-wrap pivot.

    The function never returns PASS and never mutates/reorders source evidence.
    A unique timestamp decrease can nominate a candidate pivot only when moving
    the post-pivot region before the pre-pivot region yields monotonic timestamps.
    Recorder-specific semantics and real fixtures are still required.
    """

    items = [record for record in records if record.header.timestamp is not None]
    if len(items) < 2:
        return DHAVChronologyAssessment(
            status="UNKNOWN",
            candidate_wrap_offset=None,
            timestamped_frames=len(items),
            timestamp_backwards=0,
            frame_number_resets=0,
            reordered_monotonic=None,
            reasons=("fewer than two timestamped frames; chronology cannot be assessed",),
        )

    decreases: list[int] = []
    resets: list[int] = []
    for index in range(1, len(items)):
        previous = items[index - 1]
        current = items[index]
        assert previous.header.timestamp is not None
        assert current.header.timestamp is not None
        if current.header.timestamp < previous.header.timestamp:
            decreases.append(index)
        if current.header.frame_number < previous.header.frame_number:
            resets.append(index)

    if not decreases:
        return DHAVChronologyAssessment(
            status="UNKNOWN",
            candidate_wrap_offset=None,
            timestamped_frames=len(items),
            timestamp_backwards=0,
            frame_number_resets=len(resets),
            reordered_monotonic=None,
            reasons=(
                "physical-order timestamps are monotonic; no circular-wrap pivot is proven",
                "absence of a backward jump does not prove the physical start is chronologically oldest",
            ),
        )

    if len(decreases) != 1:
        return DHAVChronologyAssessment(
            status="REVIEW",
            candidate_wrap_offset=None,
            timestamped_frames=len(items),
            timestamp_backwards=len(decreases),
            frame_number_resets=len(resets),
            reordered_monotonic=False,
            reasons=(
                f"multiple timestamp decreases observed ({len(decreases)}); a unique circular pivot is not established",
                "corruption, clock changes, mixed epochs or multiple wraps remain possible",
            ),
        )

    pivot = decreases[0]
    reordered = items[pivot:] + items[:pivot]
    timestamps: list[datetime] = [record.header.timestamp for record in reordered if record.header.timestamp]
    monotonic = all(
        current >= previous
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    )
    reasons = [
        f"one physical-order timestamp decrease nominates offset 0x{items[pivot].offset:X} as a candidate wrap pivot",
    ]
    if resets and pivot not in resets:
        reasons.append("frame-number reset evidence does not align with the timestamp pivot")
    elif pivot in resets:
        reasons.append("frame-number reset aligns with the timestamp pivot")
    if monotonic:
        reasons.extend(
            (
                "rotating at the candidate pivot yields monotonic observed timestamps",
                "this is a chronology hypothesis only; recorder-specific circular-buffer semantics remain unvalidated",
            )
        )
        status = "REVIEW"
        candidate = items[pivot].offset
    else:
        reasons.append("rotating at the candidate pivot does not yield monotonic timestamps")
        status = "REVIEW"
        candidate = None

    return DHAVChronologyAssessment(
        status=status,
        candidate_wrap_offset=candidate,
        timestamped_frames=len(items),
        timestamp_backwards=1,
        frame_number_resets=len(resets),
        reordered_monotonic=monotonic,
        reasons=tuple(reasons),
    )


def assess_audio_metadata(records: Iterable[DHAVFrameRecord]) -> DHAVAudioAssessment:
    """Assess declared DHAV audio metadata without claiming payload decoding."""

    sample_rates: set[int] = set()
    channel_counts: set[int] = set()
    codec_codes: set[int] = set()
    frames_with_metadata = 0
    conflicts = 0

    for record in records:
        extension = record.extension
        has_audio = any(
            value is not None
            for value in (extension.sample_rate, extension.audio_channels, extension.audio_codec_code)
        )
        if not has_audio:
            continue
        frames_with_metadata += 1
        if extension.sample_rate is not None:
            sample_rates.add(extension.sample_rate)
        if extension.audio_channels is not None:
            channel_counts.add(extension.audio_channels)
        if extension.audio_codec_code is not None:
            codec_codes.add(extension.audio_codec_code)
        if extension.audio_channels is not None and extension.audio_channels <= 0:
            conflicts += 1
        if extension.sample_rate is not None and extension.sample_rate <= 0:
            conflicts += 1

    if frames_with_metadata == 0:
        return DHAVAudioAssessment(
            status="UNKNOWN",
            frames_with_audio_metadata=0,
            sample_rates=(),
            channel_counts=(),
            codec_codes=(),
            metadata_conflicts=0,
            reasons=("no DHAV audio extension metadata was observed",),
        )

    reasons = [
        "audio fields are declared metadata only; payload codec/decoding has not been validated",
    ]
    if len(sample_rates) > 1:
        reasons.append("multiple declared audio sample rates were observed")
    if len(channel_counts) > 1:
        reasons.append("multiple declared audio channel counts were observed")
    if len(codec_codes) > 1:
        reasons.append("multiple declared audio codec codes were observed")
    if conflicts:
        reasons.append(f"invalid audio metadata values observed={conflicts}")

    return DHAVAudioAssessment(
        status="REVIEW",
        frames_with_audio_metadata=frames_with_metadata,
        sample_rates=tuple(sorted(sample_rates)),
        channel_counts=tuple(sorted(channel_counts)),
        codec_codes=tuple(sorted(codec_codes)),
        metadata_conflicts=conflicts,
        reasons=tuple(reasons),
    )
