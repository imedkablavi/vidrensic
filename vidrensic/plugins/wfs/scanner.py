from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import os
import stat

from vidrensic.acquisition.linux import block_device_size
from vidrensic.plugins.base import RecordingBoundary
from vidrensic.plugins.wfs.codec import FRAGMENT_SIZE, fd_timestamp


def source_size(fd: int, path: Path) -> int:
    """Return source size without a second unbounded native-tool subprocess path.

    Regular files use descriptor metadata directly. Linux block devices commonly
    report ``st_size == 0`` through ``fstat``; only those device descriptors fall
    back to the shared bounded ``blockdev --getsize64`` probe used by acquisition
    source inspection.
    """

    st = os.fstat(fd)
    if st.st_size:
        return st.st_size
    if stat.S_ISBLK(st.st_mode):
        return block_device_size(path)
    return 0


def scan_recording_starts(
    source: Path,
    target_date: date,
    *,
    data_offset: int = 0,
    fragment_size: int = FRAGMENT_SIZE,
    start_fragment: int = 0,
    stop_fragment: int | None = None,
) -> list[RecordingBoundary]:
    """Scan WFS fragment boundaries for FD recording-start records.

    This scanner intentionally performs a 16-byte pread per fragment rather than
    reading the whole source into memory. Callers should acquire a bounded source
    range first when the evidence device is fragile.
    """

    if data_offset < 0 or data_offset % 512:
        raise ValueError("data_offset must be a non-negative 512-byte aligned value")
    if fragment_size <= 0:
        raise ValueError("fragment_size must be positive")
    if start_fragment < 0:
        raise ValueError("start_fragment cannot be negative")

    source = source.expanduser().resolve()
    fd = os.open(source, os.O_RDONLY)
    try:
        size = source_size(fd, source)
        available = max(0, size - data_offset)
        total_fragments = available // fragment_size
        stop = total_fragments if stop_fragment is None else min(stop_fragment, total_fragments)
        if stop < start_fragment:
            raise ValueError("stop_fragment precedes start_fragment")

        groups: dict[tuple[int, int], dict[int, object]] = defaultdict(dict)
        for fragment in range(start_fragment, stop):
            offset = data_offset + fragment * fragment_size
            header = os.pread(fd, 16, offset)
            if len(header) < 16 or header[:4] != b"\x00\x00\x01\xfd":
                continue
            timestamp = fd_timestamp(header)
            if timestamp is None or timestamp.date() != target_date:
                continue
            groups[(timestamp.hour, timestamp.minute)][fragment] = timestamp

        boundaries: list[RecordingBoundary] = []
        for hour_minute in sorted(groups):
            fragments = tuple(sorted(groups[hour_minute]))
            timestamps = [groups[hour_minute][frag] for frag in fragments]
            timestamp = min(timestamps)
            boundaries.append(
                RecordingBoundary(
                    label=f"{hour_minute[0]:02d}-{hour_minute[1]:02d}",
                    timestamp=timestamp,
                    start_fragments=fragments,
                    data_offset=data_offset,
                    metadata={
                        "fragment_size": fragment_size,
                        "candidate_count": len(fragments),
                    },
                )
            )
        return boundaries
    finally:
        os.close(fd)
