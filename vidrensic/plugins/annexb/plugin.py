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


START4 = b"\x00\x00\x00\x01"
START3 = b"\x00\x00\x01"


def _count(data: bytes, needle: bytes) -> int:
    count = 0
    pos = 0
    while True:
        pos = data.find(needle, pos)
        if pos < 0:
            return count
        count += 1
        pos += 1


def _nal_parameter_sets(data: bytes) -> tuple[int, int, int, int, int, int]:
    h264_sps = h264_pps = h264_idr = 0
    hevc_vps = hevc_sps = hevc_pps = 0
    seen_positions: set[int] = set()
    for marker in (START4, START3):
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos < 0:
                break
            nal = pos + len(marker)
            if nal >= len(data) or nal in seen_positions:
                pos += 1
                continue
            seen_positions.add(nal)
            first = data[nal]
            h264_type = first & 0x1F
            hevc_type = (first >> 1) & 0x3F
            if h264_type == 7:
                h264_sps += 1
            elif h264_type == 8:
                h264_pps += 1
            elif h264_type == 5:
                h264_idr += 1
            if hevc_type == 32:
                hevc_vps += 1
            elif hevc_type == 33:
                hevc_sps += 1
            elif hevc_type == 34:
                hevc_pps += 1
            pos = nal + 1
    return h264_sps, h264_pps, h264_idr, hevc_vps, hevc_sps, hevc_pps


class AnnexBPlugin:
    name = "annexb"
    display_name = "Raw Annex-B H.264/H.265 elementary stream"
    descriptor = FormatDescriptor(
        family_id="annexb",
        display_name="Raw Annex-B H.264/H.265 elementary stream",
        support_level=SupportLevel.PARSE,
        topology=StorageTopology.ELEMENTARY_STREAM,
        aliases=("H.264 Annex-B", "H.265 Annex-B", "HEVC Annex-B", "raw .h264/.h265/.hevc"),
        codecs=("H.264/AVC", "H.265/HEVC"),
        strategies=(
            RecoveryStrategy.SIGNATURE_CARVE,
            RecoveryStrategy.STREAM_COPY,
            RecoveryStrategy.CONTROLLED_TRANSCODE,
        ),
        failure_modes=(
            FailureMode.BROKEN_CONTAINER_INDEX,
            FailureMode.DAMAGED_GOP,
            FailureMode.TRUNCATED_RECORD,
            FailureMode.MIXED_CODEC_OR_VARIANT,
        ),
        notes=(
            "This is a stream-level family, not a DVR vendor or filesystem identification.",
            "No native wall-clock timestamp is inferred from Annex-B NAL units alone.",
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

        start_codes = _count(data, START4) + _count(data, START3)
        h264_sps, h264_pps, h264_idr, hevc_vps, hevc_sps, hevc_pps = _nal_parameter_sets(data)
        h264_score = min(h264_sps, h264_pps) + min(h264_idr, max(1, h264_sps))
        hevc_score = min(hevc_vps, hevc_sps, hevc_pps)
        if hevc_score >= 2 or h264_score >= 3:
            confidence = 0.92
        elif hevc_score >= 1 or h264_score >= 2:
            confidence = 0.75
        elif start_codes >= 20:
            confidence = 0.35
        else:
            confidence = 0.0

        codec = "hevc" if hevc_score > h264_score else "h264" if h264_score else None
        return DetectionResult(
            plugin=self.name,
            confidence=confidence,
            reasons=(
                f"Annex-B start codes={start_codes}",
                f"H.264 SPS/PPS/IDR={h264_sps}/{h264_pps}/{h264_idr}",
                f"HEVC VPS/SPS/PPS={hevc_vps}/{hevc_sps}/{hevc_pps}",
                f"bounded sample bytes={sample_size}",
            ),
            metadata={
                "codec_hint": codec,
                "start_codes": start_codes,
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
        # Raw NAL units do not carry a generic recorder wall-clock timeline.
        return []
