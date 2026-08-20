from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import struct

from vidrensic.acquisition.linux import require_safe_source


MASTER_SIGNATURE = b"HIKVISION@HANGZHOU"
MASTER_SIZE = 256
HIKBTREE_SIGNATURE = b"HIKBTREE"


@dataclass(frozen=True)
class HikvisionMasterCandidate:
    offset: int
    hdd_capacity: int
    system_logs_offset: int
    system_logs_size: int
    video_data_offset: int
    data_block_size: int
    total_data_blocks: int
    hikbtree1_offset: int
    hikbtree1_size: int
    hikbtree2_offset: int
    hikbtree2_size: int
    initialization_time: int
    plausibility_score: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "offset": self.offset,
            "hdd_capacity": self.hdd_capacity,
            "system_logs_offset": self.system_logs_offset,
            "system_logs_size": self.system_logs_size,
            "video_data_offset": self.video_data_offset,
            "data_block_size": self.data_block_size,
            "total_data_blocks": self.total_data_blocks,
            "hikbtree1_offset": self.hikbtree1_offset,
            "hikbtree1_size": self.hikbtree1_size,
            "hikbtree2_offset": self.hikbtree2_offset,
            "hikbtree2_size": self.hikbtree2_size,
            "initialization_time": self.initialization_time,
            "plausibility_score": self.plausibility_score,
            "reasons": list(self.reasons),
        }


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def parse_master_candidate(data: bytes, *, absolute_offset: int, source_size: int) -> HikvisionMasterCandidate:
    if len(data) < MASTER_SIZE:
        raise ValueError("short Hikvision master-sector candidate")
    if data[: len(MASTER_SIGNATURE)] != MASTER_SIGNATURE:
        raise ValueError("missing Hikvision master-sector signature")

    hdd_capacity = _u64(data, 0x38)
    logs_offset = _u64(data, 0x50)
    logs_size = _u64(data, 0x58)
    video_offset = _u64(data, 0x68)
    block_size = _u64(data, 0x78)
    total_blocks = _u64(data, 0x80)
    tree1_offset = _u64(data, 0x88)
    tree1_size = _u64(data, 0x90)
    tree2_offset = _u64(data, 0x98)
    tree2_size = _u64(data, 0xA0)
    init_time = _u32(data, 0xE0)

    score = 0.35  # the exact master signature is already strong evidence
    reasons = ["exact HIKVISION@HANGZHOU master signature"]

    if hdd_capacity and abs(hdd_capacity - source_size) <= max(16 * 1024 * 1024, source_size // 100):
        score += 0.18
        reasons.append("stored HDD capacity is close to evidence-source size")
    elif 0 < hdd_capacity <= source_size * 2:
        score += 0.08
        reasons.append("stored HDD capacity is nonzero and broadly plausible")
    else:
        reasons.append("stored HDD capacity is zero or inconsistent with source size")

    if 0 < video_offset < source_size:
        score += 0.12
        reasons.append("video-data offset is inside source bounds")
    else:
        reasons.append("video-data offset is zero/out of source bounds or partition-relative")

    if block_size and block_size % 512 == 0 and block_size <= source_size:
        score += 0.10
        reasons.append("data-block size is sector-aligned and bounded")
    else:
        reasons.append("data-block size requires variant review")

    if 0 < total_blocks < 10_000_000:
        score += 0.05
        reasons.append("data-block count is plausible")

    if tree1_offset and tree1_size:
        score += 0.08
        reasons.append("primary HIKBTREE location/size fields are populated")
    if tree2_offset and tree2_size:
        score += 0.04
        reasons.append("secondary HIKBTREE location/size fields are populated")

    if logs_offset and logs_size:
        score += 0.03
        reasons.append("system-log area fields are populated")

    # Common Unix timestamp sanity window for deployed DVR generations. This is
    # only a plausibility signal; zero and unusual values remain valid evidence.
    if 946684800 <= init_time <= 2082758400:
        score += 0.05
        reasons.append("initialization timestamp is calendar-plausible")

    return HikvisionMasterCandidate(
        offset=absolute_offset,
        hdd_capacity=hdd_capacity,
        system_logs_offset=logs_offset,
        system_logs_size=logs_size,
        video_data_offset=video_offset,
        data_block_size=block_size,
        total_data_blocks=total_blocks,
        hikbtree1_offset=tree1_offset,
        hikbtree1_size=tree1_size,
        hikbtree2_offset=tree2_offset,
        hikbtree2_size=tree2_size,
        initialization_time=init_time,
        plausibility_score=min(score, 1.0),
        reasons=tuple(reasons),
    )


def find_master_candidates(
    source: Path,
    *,
    search_start: int = 0,
    search_size: int = 64 * 1024 * 1024,
    max_candidates: int = 8,
) -> tuple[HikvisionMasterCandidate, ...]:
    if search_start < 0 or search_size <= 0:
        raise ValueError("invalid Hikvision search range")
    info = require_safe_source(source)
    end = min(info.size_bytes, search_start + search_size)
    fd = os.open(info.path, os.O_RDONLY)
    candidates: list[HikvisionMasterCandidate] = []
    chunk_size = 4 * 1024 * 1024
    overlap = len(MASTER_SIGNATURE) - 1
    carry = b""
    pos = search_start
    seen: set[int] = set()
    try:
        while pos < end and len(candidates) < max_candidates:
            chunk = os.pread(fd, min(chunk_size, end - pos), pos)
            if not chunk:
                break
            data = carry + chunk
            base = pos - len(carry)
            cursor = 0
            while len(candidates) < max_candidates:
                cursor = data.find(MASTER_SIGNATURE, cursor)
                if cursor < 0:
                    break
                absolute = base + cursor
                cursor += 1
                if absolute in seen or absolute < search_start:
                    continue
                seen.add(absolute)
                raw = os.pread(fd, MASTER_SIZE, absolute)
                if len(raw) != MASTER_SIZE:
                    continue
                try:
                    candidate = parse_master_candidate(raw, absolute_offset=absolute, source_size=info.size_bytes)
                except ValueError:
                    continue
                candidates.append(candidate)
            carry = data[-overlap:] if overlap else b""
            pos += len(chunk)
    finally:
        os.close(fd)
    candidates.sort(key=lambda item: (-item.plausibility_score, item.offset))
    return tuple(candidates)
