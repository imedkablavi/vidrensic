from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import os

from vidrensic.acquisition.linux import require_safe_source
from vidrensic.plugins.wfs.codec import FRAGMENT_SIZE, fd_timestamp, packet_info, padding_here


@dataclass(frozen=True)
class AlignmentHypothesis:
    residue: int
    fragment_size: int
    sector_size: int
    tested_boundaries: int
    valid_record_starts: int
    timestamped_fd_starts: int
    fragment_end_padding_hits: int
    score: float
    confidence: float


@dataclass(frozen=True)
class WFSLayoutProfile:
    source: Path
    range_start: int
    range_size: int
    fragment_size: int
    sector_size: int
    hypotheses: tuple[AlignmentHypothesis, ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "range_start": self.range_start,
            "range_size": self.range_size,
            "fragment_size": self.fragment_size,
            "sector_size": self.sector_size,
            "hypotheses": [asdict(item) for item in self.hypotheses],
            "notes": list(self.notes),
        }

    def write_json(self, output: Path) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


def _candidate_positions(
    range_start: int,
    data_length: int,
    residue: int,
    fragment_size: int,
) -> list[int]:
    range_end = range_start + data_length
    first = range_start + ((residue - range_start) % fragment_size)
    if first >= range_end:
        return []
    return list(range(first, range_end, fragment_size))


def infer_wfs_fragment_alignment(
    source: Path,
    *,
    range_start: int = 0,
    range_size: int = 64 * 1024 * 1024,
    fragment_size: int = FRAGMENT_SIZE,
    sector_size: int = 512,
    top: int = 8,
) -> WFSLayoutProfile:
    """Rank fragment-alignment hypotheses from a bounded contiguous source range.

    The result is an alignment *hypothesis*, not a WFS data-base offset. It scores
    sector-aligned residues using valid WFS records exactly at candidate fragment
    boundaries, timestamped FD records, and padding near candidate fragment ends.
    """

    if range_start < 0 or range_start % sector_size:
        raise ValueError("range_start must be non-negative and sector aligned")
    if range_size <= 0 or range_size > 256 * 1024 * 1024:
        raise ValueError("range_size must be between 1 byte and 256 MiB")
    if fragment_size <= 0 or fragment_size % sector_size:
        raise ValueError("fragment_size must be a positive multiple of sector_size")
    if sector_size <= 0:
        raise ValueError("sector_size must be positive")
    if top <= 0 or top > 64:
        raise ValueError("top must be between 1 and 64")

    info = require_safe_source(source)
    if range_start >= info.size_bytes:
        raise ValueError("range_start is beyond source size")
    read_size = min(range_size, info.size_bytes - range_start)
    fd = os.open(info.path, os.O_RDONLY)
    try:
        data = os.pread(fd, read_size, range_start)
    finally:
        os.close(fd)

    raw: list[tuple[int, int, int, int, int, float]] = []
    for residue in range(0, fragment_size, sector_size):
        valid = 0
        timestamped_fd = 0
        padding_hits = 0
        positions = _candidate_positions(range_start, len(data), residue, fragment_size)
        for absolute in positions:
            local = absolute - range_start
            if local + 16 <= len(data):
                info_packet = packet_info(data, local)
                if info_packet is not None:
                    valid += 1
                    if info_packet.packet_type == 0xFD and fd_timestamp(data[local : local + 16]):
                        timestamped_fd += 1

            next_boundary = absolute + fragment_size
            end_probe_absolute = next_boundary - 64
            end_local = end_probe_absolute - range_start
            if 0 <= end_local < len(data) and padding_here(data, end_local, run=64):
                padding_hits += 1

        # Timestamped starts are much stronger than a generic packet sync. Long
        # padding at repeated fragment ends is weak supporting evidence only.
        score = valid * 2.0 + timestamped_fd * 8.0 + padding_hits * 0.5
        raw.append((residue, len(positions), valid, timestamped_fd, padding_hits, score))

    raw.sort(key=lambda item: (-item[5], -item[3], -item[2], item[0]))
    best_score = raw[0][5] if raw else 0.0
    second_score = raw[1][5] if len(raw) > 1 else 0.0

    hypotheses: list[AlignmentHypothesis] = []
    for residue, tested, valid, timestamped, padding_hits, score in raw[:top]:
        evidence = valid + timestamped
        if score <= 0 or evidence == 0:
            confidence = 0.0
        else:
            dominance = score / max(score + second_score, 1.0)
            evidence_factor = min(1.0, evidence / 6.0)
            confidence = dominance * evidence_factor
            if score < best_score:
                confidence *= score / best_score if best_score else 0.0
        hypotheses.append(
            AlignmentHypothesis(
                residue=residue,
                fragment_size=fragment_size,
                sector_size=sector_size,
                tested_boundaries=tested,
                valid_record_starts=valid,
                timestamped_fd_starts=timestamped,
                fragment_end_padding_hits=padding_hits,
                score=score,
                confidence=round(confidence, 6),
            )
        )

    notes = [
        "alignment ranking is based on a bounded contiguous range",
        "a residue is not itself the absolute WFS data-area start",
        "low evidence or close competing scores require additional sampling",
    ]
    if hypotheses and hypotheses[0].confidence < 0.5:
        notes.append("top alignment hypothesis has low confidence")

    return WFSLayoutProfile(
        source=info.path,
        range_start=range_start,
        range_size=len(data),
        fragment_size=fragment_size,
        sector_size=sector_size,
        hypotheses=tuple(hypotheses),
        notes=tuple(notes),
    )
