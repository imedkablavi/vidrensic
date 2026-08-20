from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ElementaryStreamEvidence:
    codec: str | None
    confidence: float
    start_codes: int
    h264_sps: int
    h264_pps: int
    h264_idr: int
    hevc_vps: int
    hevc_sps: int
    hevc_pps: int
    hevc_idr: int
    reasons: tuple[str, ...]

    @property
    def preferred_extension(self) -> str:
        if self.codec == "h264" and self.confidence >= 0.80:
            return ".h264"
        if self.codec == "hevc" and self.confidence >= 0.80:
            return ".h265"
        return ".es"


def _nal_headers(data: bytes):
    """Yield Annex-B NAL header bytes without double-counting 4-byte prefixes."""

    position = 0
    length = len(data)
    while position + 3 < length:
        if data[position : position + 4] == b"\x00\x00\x00\x01":
            header = position + 4
            position = header + 1
            if header < length:
                yield data[header]
            continue
        if data[position : position + 3] == b"\x00\x00\x01":
            header = position + 3
            position = header + 1
            if header < length:
                yield data[header]
            continue
        position += 1


def classify_annexb(data: bytes) -> ElementaryStreamEvidence:
    h264_sps = h264_pps = h264_idr = 0
    hevc_vps = hevc_sps = hevc_pps = hevc_idr = 0
    start_codes = 0

    for first in _nal_headers(data):
        start_codes += 1
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
        elif hevc_type in (19, 20, 21):
            hevc_idr += 1

    h264_sets = min(h264_sps, h264_pps)
    hevc_sets = min(hevc_vps, hevc_sps, hevc_pps)
    reasons = [
        f"Annex-B NAL starts={start_codes}",
        f"H.264 SPS/PPS/IDR={h264_sps}/{h264_pps}/{h264_idr}",
        f"HEVC VPS/SPS/PPS/IRAP={hevc_vps}/{hevc_sps}/{hevc_pps}/{hevc_idr}",
    ]

    codec: str | None = None
    confidence = 0.0
    if hevc_sets >= 2 and h264_sets == 0:
        codec = "hevc"
        confidence = 0.99
    elif hevc_sets >= 1 and h264_sets == 0:
        codec = "hevc"
        confidence = 0.94 if hevc_idr else 0.88
    elif h264_sets >= 2 and hevc_sets == 0:
        codec = "h264"
        confidence = 0.98
    elif h264_sets >= 1 and hevc_sets == 0:
        codec = "h264"
        confidence = 0.93 if h264_idr else 0.86
    elif hevc_sets and h264_sets:
        reasons.append("conflicting H.264 and HEVC parameter-set evidence observed")
        confidence = 0.30
    elif hevc_vps or hevc_sps or hevc_pps:
        codec = "hevc"
        confidence = 0.55
        reasons.append("HEVC hint lacks a complete VPS/SPS/PPS set")
    elif h264_sps or h264_pps:
        codec = "h264"
        confidence = 0.55
        reasons.append("H.264 hint lacks a complete SPS/PPS set")
    elif start_codes:
        reasons.append("Annex-B framing observed without codec-defining parameter sets")

    return ElementaryStreamEvidence(
        codec=codec,
        confidence=confidence,
        start_codes=start_codes,
        h264_sps=h264_sps,
        h264_pps=h264_pps,
        h264_idr=h264_idr,
        hevc_vps=hevc_vps,
        hevc_sps=hevc_sps,
        hevc_pps=hevc_pps,
        hevc_idr=hevc_idr,
        reasons=tuple(reasons),
    )


def classify_elementary_file(path: Path, *, max_bytes: int = 16 * 1024 * 1024) -> ElementaryStreamEvidence:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    path = path.expanduser().resolve()
    with path.open("rb") as fh:
        data = fh.read(max_bytes)
    return classify_annexb(data)
