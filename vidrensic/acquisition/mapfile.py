from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


STATUS_NAMES = {
    "?": "non_tried",
    "*": "non_trimmed",
    "/": "non_scraped",
    "-": "bad_sector",
    "+": "finished",
}


@dataclass(frozen=True)
class MapBlock:
    position: int
    size: int
    status: str

    @property
    def end(self) -> int:
        return self.position + self.size


@dataclass(frozen=True)
class MapSummary:
    blocks: tuple[MapBlock, ...]
    status_bytes: dict[str, int]
    segment_count: int
    mapped_bytes: int
    first_position: int | None
    last_position: int | None
    overlap_bytes: int
    gap_bytes: int
    expected_start: int | None
    expected_size: int | None
    expected_covered_bytes: int | None
    expected_finished_bytes: int | None

    @property
    def unresolved_bytes(self) -> int:
        return sum(
            self.status_bytes.get(name, 0)
            for name in ("non_tried", "non_trimmed", "non_scraped", "bad_sector")
        )

    @property
    def complete_for_expected_range(self) -> bool | None:
        if self.expected_size is None:
            return None
        return (
            self.expected_covered_bytes == self.expected_size
            and self.expected_finished_bytes == self.expected_size
            and self.overlap_bytes == 0
        )

    def to_dict(self) -> dict:
        return {
            "segment_count": self.segment_count,
            "mapped_bytes": self.mapped_bytes,
            "first_position": self.first_position,
            "last_position": self.last_position,
            "status_bytes": self.status_bytes,
            "unresolved_bytes": self.unresolved_bytes,
            "overlap_bytes": self.overlap_bytes,
            "gap_bytes": self.gap_bytes,
            "expected_start": self.expected_start,
            "expected_size": self.expected_size,
            "expected_covered_bytes": self.expected_covered_bytes,
            "expected_finished_bytes": self.expected_finished_bytes,
            "complete_for_expected_range": self.complete_for_expected_range,
        }


def _number(value: str) -> int:
    return int(value, 0)


def parse_mapfile(
    path: Path,
    *,
    expected_start: int | None = None,
    expected_size: int | None = None,
) -> MapSummary:
    """Parse GNU ddrescue status-block lines without trusting comments/header text."""

    path = path.expanduser().resolve()
    if expected_start is not None and expected_start < 0:
        raise ValueError("expected_start cannot be negative")
    if expected_size is not None and expected_size <= 0:
        raise ValueError("expected_size must be positive")

    blocks: list[MapBlock] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        # The ddrescue current-position/current-status/current-pass line is not a
        # block line because its third field is a pass number, not a map status.
        if len(fields) < 3 or fields[2] not in STATUS_NAMES:
            continue
        try:
            position = _number(fields[0])
            size = _number(fields[1])
        except ValueError as exc:
            raise ValueError(f"invalid ddrescue map numeric field at line {line_no}") from exc
        if position < 0 or size <= 0:
            raise ValueError(f"invalid ddrescue map block geometry at line {line_no}")
        blocks.append(MapBlock(position, size, fields[2]))

    if not blocks:
        raise ValueError("no ddrescue status blocks found in mapfile")

    blocks.sort(key=lambda item: (item.position, item.end, item.status))
    status_bytes = {name: 0 for name in STATUS_NAMES.values()}
    mapped_bytes = 0
    overlap_bytes = 0
    gap_bytes = 0
    previous_end: int | None = None
    for block in blocks:
        status_bytes[STATUS_NAMES[block.status]] += block.size
        mapped_bytes += block.size
        if previous_end is not None:
            if block.position < previous_end:
                overlap_bytes += min(previous_end, block.end) - block.position
            elif block.position > previous_end:
                gap_bytes += block.position - previous_end
        previous_end = max(previous_end or block.end, block.end)

    expected_covered = None
    expected_finished = None
    if expected_size is not None:
        start = expected_start or 0
        end = start + expected_size
        covered_intervals: list[tuple[int, int]] = []
        finished_intervals: list[tuple[int, int]] = []
        for block in blocks:
            left = max(start, block.position)
            right = min(end, block.end)
            if left >= right:
                continue
            covered_intervals.append((left, right))
            if block.status == "+":
                finished_intervals.append((left, right))

        def union_size(intervals: list[tuple[int, int]]) -> int:
            if not intervals:
                return 0
            intervals.sort()
            total = 0
            left, right = intervals[0]
            for next_left, next_right in intervals[1:]:
                if next_left <= right:
                    right = max(right, next_right)
                else:
                    total += right - left
                    left, right = next_left, next_right
            return total + right - left

        expected_covered = union_size(covered_intervals)
        expected_finished = union_size(finished_intervals)

    return MapSummary(
        blocks=tuple(blocks),
        status_bytes=status_bytes,
        segment_count=len(blocks),
        mapped_bytes=mapped_bytes,
        first_position=blocks[0].position,
        last_position=max(block.end for block in blocks),
        overlap_bytes=overlap_bytes,
        gap_bytes=gap_bytes,
        expected_start=expected_start,
        expected_size=expected_size,
        expected_covered_bytes=expected_covered,
        expected_finished_bytes=expected_finished,
    )
