from __future__ import annotations

from datetime import datetime

from vidrensic.plugins.dhav.codec import DHAVExtensionInfo, DHAVHeader
from vidrensic.plugins.dhav.scanner import DHAVFrameRecord
from vidrensic.plugins.dhav.validation import assess_audio_metadata, assess_single_circular_wrap


def _record(
    offset: int,
    timestamp: datetime | None,
    frame_number: int,
    *,
    sample_rate: int | None = None,
    audio_channels: int | None = None,
    audio_codec_code: int | None = None,
) -> DHAVFrameRecord:
    header = DHAVHeader(
        frame_type=0xFD,
        subtype=0,
        channel=0,
        subchannel=0,
        frame_number=frame_number,
        frame_length=64,
        timestamp_word=0,
        timestamp=timestamp,
        milliseconds=0,
        extension_length=0,
        checksum=0,
    )
    extension = DHAVExtensionInfo(
        sample_rate=sample_rate,
        audio_channels=audio_channels,
        audio_codec_code=audio_codec_code,
    )
    return DHAVFrameRecord(
        offset=offset,
        header=header,
        extension=extension,
        footer_magic_valid=True,
        footer_size_valid=True,
        footer_back_size=64,
        payload_codec_hint=None,
        codec_hint=None,
    )


def test_single_wrap_nominates_review_pivot_without_pass_claim() -> None:
    records = [
        _record(0x100, datetime(2026, 8, 24, 12, 2), 102),
        _record(0x200, datetime(2026, 8, 24, 12, 3), 103),
        _record(0x300, datetime(2026, 8, 24, 12, 0), 1),
        _record(0x400, datetime(2026, 8, 24, 12, 1), 2),
    ]
    result = assess_single_circular_wrap(records)
    assert result.status == "REVIEW"
    assert result.candidate_wrap_offset == 0x300
    assert result.reordered_monotonic is True
    assert result.timestamp_backwards == 1
    assert result.frame_number_resets == 1


def test_monotonic_physical_order_does_not_prove_circular_start() -> None:
    records = [
        _record(0x100, datetime(2026, 8, 24, 12, 0), 1),
        _record(0x200, datetime(2026, 8, 24, 12, 1), 2),
    ]
    result = assess_single_circular_wrap(records)
    assert result.status == "UNKNOWN"
    assert result.candidate_wrap_offset is None


def test_multiple_timestamp_decreases_are_not_forced_into_one_wrap() -> None:
    records = [
        _record(0x100, datetime(2026, 8, 24, 12, 5), 5),
        _record(0x200, datetime(2026, 8, 24, 12, 1), 1),
        _record(0x300, datetime(2026, 8, 24, 12, 4), 4),
        _record(0x400, datetime(2026, 8, 24, 12, 2), 2),
    ]
    result = assess_single_circular_wrap(records)
    assert result.status == "REVIEW"
    assert result.candidate_wrap_offset is None
    assert result.timestamp_backwards == 2


def test_audio_metadata_assessment_is_review_not_decode_claim() -> None:
    records = [
        _record(0x100, None, 1, sample_rate=8000, audio_channels=1, audio_codec_code=7),
        _record(0x200, None, 2, sample_rate=8000, audio_channels=1, audio_codec_code=7),
    ]
    result = assess_audio_metadata(records)
    assert result.status == "REVIEW"
    assert result.frames_with_audio_metadata == 2
    assert result.sample_rates == (8000,)
    assert result.channel_counts == (1,)
    assert result.codec_codes == (7,)
    assert any("not been validated" in reason for reason in result.reasons)


def test_absent_audio_metadata_is_unknown() -> None:
    result = assess_audio_metadata([_record(0x100, None, 1)])
    assert result.status == "UNKNOWN"
