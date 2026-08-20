from __future__ import annotations

from datetime import date
from pathlib import Path
import os

from vidrensic.acquisition.linux import require_safe_source
from vidrensic.plugins.base import DetectionResult, RecordingBoundary
from vidrensic.plugins.capabilities import (
    FailureMode,
    FormatDescriptor,
    RecoveryStrategy,
    StorageTopology,
    SupportLevel,
)


PACK = b"\x00\x00\x01\xba"
SYSTEM = b"\x00\x00\x01\xbb"
VIDEO_PES_PREFIX = b"\x00\x00\x01"


def _count(data: bytes, needle: bytes) -> int:
    count = 0
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            return count
        count += 1
        pos += 1


def _count_video_pes(data: bytes) -> int:
    count = 0
    pos = 0
    while True:
        pos = data.find(VIDEO_PES_PREFIX, pos)
        if pos < 0 or pos + 4 > len(data):
            return count
        stream_id = data[pos + 3]
        if 0xE0 <= stream_id <= 0xEF:
            count += 1
        pos += 4


class MPEGPSPlugin:
    name = "mpegps"
    display_name = "MPEG Program Stream / PES surveillance container"
    descriptor = FormatDescriptor(
        family_id="mpegps",
        display_name="MPEG Program Stream / PES surveillance container",
        support_level=SupportLevel.PARSE,
        topology=StorageTopology.CONTAINER_ONLY,
        aliases=("MPEG-PS", "PS", "PES", "program stream"),
        codecs=("H.264 commonly", "MPEG video variants", "vendor-specific PES payloads"),
        timestamp_kinds=("PTS/DTS when present", "vendor metadata may carry wall-clock time"),
        strategies=(
            RecoveryStrategy.SIGNATURE_CARVE,
            RecoveryStrategy.STREAM_COPY,
            RecoveryStrategy.CONTROLLED_TRANSCODE,
        ),
        failure_modes=(
            FailureMode.BROKEN_CONTAINER_INDEX,
            FailureMode.TRUNCATED_RECORD,
            FailureMode.DAMAGED_GOP,
            FailureMode.TIMESTAMP_GAPS,
            FailureMode.AUDIO_VIDEO_DESYNC,
            FailureMode.UNKNOWN_VENDOR_VARIANT,
        ),
        notes=(
            "MPEG-PS detection is container-level and does not by itself prove a recorder vendor.",
            "Vendor DAV/PS variations require separate timestamp and metadata profiles.",
        ),
    )

    def detect(self, source: Path) -> DetectionResult:
        info = require_safe_source(source)
        sample_size = min(info.size_bytes, 64 * 1024 * 1024)
        fd = os.open(info.path, os.O_RDONLY)
        try:
            data = os.pread(fd, sample_size, 0)
        finally:
            os.close(fd)
        packs = _count(data, PACK)
        systems = _count(data, SYSTEM)
        video_pes = _count_video_pes(data)
        if packs >= 8 and video_pes >= 8:
            confidence = 0.93
        elif packs >= 3 and video_pes >= 3:
            confidence = 0.78
        elif packs >= 1 and video_pes >= 1:
            confidence = 0.55
        else:
            confidence = 0.0
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=(
                f"MPEG-PS pack headers={packs}",
                f"system headers={systems}",
                f"video PES packets={video_pes}",
                f"bounded sample bytes={sample_size}",
            ),
            metadata={
                "pack_headers": packs,
                "system_headers": systems,
                "video_pes": video_pes,
                "sampled_bytes": sample_size,
            },
        )

    def scan_date(
        self,
        source: Path,
        target_date: date,
        *,
        data_offset: int = 0,
    ) -> list[RecordingBoundary]:
        return []
