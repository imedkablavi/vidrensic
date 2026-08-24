from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import log2
from pathlib import Path
from typing import Any
import os

from vidrensic.acquisition.linux import SourceInfo, require_safe_source
from vidrensic.core.private_io import atomic_write_private_json


SIGNATURES: dict[str, bytes] = {
    "wfs_0_4_ascii": b"WFS 0.4",
    "wfs_0_5_ascii": b"WFS 0.5",
    "dahua_dhav_header": b"DHAV",
    "dahua_dhav_footer": b"dhav",
    "h264_sps_annexb4": b"\x00\x00\x00\x01\x67",
    "h264_pps_annexb4": b"\x00\x00\x00\x01\x68",
    "h264_idr_annexb4": b"\x00\x00\x00\x01\x65",
    "hevc_vps_annexb4": b"\x00\x00\x00\x01\x40",
    "hevc_sps_annexb4": b"\x00\x00\x00\x01\x42",
    "hevc_pps_annexb4": b"\x00\x00\x00\x01\x44",
}


@dataclass(frozen=True)
class SampleProfile:
    offset: int
    size: int
    sha256: str
    entropy_bits_per_byte: float
    zero_fraction: float
    ff_fraction: float
    signatures: dict[str, int]
    first_hits: dict[str, tuple[int, ...]]
    annexb_start_codes: int


@dataclass(frozen=True)
class SourceProfile:
    source: Path
    size_bytes: int
    is_block_device: bool
    read_only: bool | None
    mounted_at: tuple[str, ...]
    sampling_only: bool
    sample_size: int
    samples: tuple[SampleProfile, ...]
    aggregate_signatures: dict[str, int]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "size_bytes": self.size_bytes,
            "is_block_device": self.is_block_device,
            "read_only": self.read_only,
            "mounted_at": list(self.mounted_at),
            "sampling_only": self.sampling_only,
            "sample_size": self.sample_size,
            "samples": [asdict(sample) for sample in self.samples],
            "aggregate_signatures": self.aggregate_signatures,
            "notes": list(self.notes),
        }

    def write_json(self, output: Path) -> Path:
        return atomic_write_private_json(output, self.to_dict(), allow_replace=True)


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for value in data:
        counts[value] += 1
    total = len(data)
    result = 0.0
    for count in counts:
        if not count:
            continue
        probability = count / total
        result -= probability * log2(probability)
    return result


def _find_hits(data: bytes, needle: bytes, *, limit: int = 16) -> tuple[int, ...]:
    hits: list[int] = []
    position = 0
    while len(hits) < limit:
        position = data.find(needle, position)
        if position < 0:
            break
        hits.append(position)
        position += max(1, len(needle))
    return tuple(hits)


def _count_overlapping(data: bytes, needle: bytes) -> int:
    count = 0
    position = 0
    while True:
        position = data.find(needle, position)
        if position < 0:
            return count
        count += 1
        position += 1


def _sample_offsets(size: int, sample_size: int, sample_count: int) -> tuple[int, ...]:
    if size <= 0:
        return (0,)
    width = min(size, sample_size)
    maximum = max(0, size - width)
    if sample_count <= 1 or maximum == 0:
        return (0,)
    raw = [round(maximum * index / (sample_count - 1)) for index in range(sample_count)]
    # Sector alignment makes block-device samples easier to reproduce and document.
    aligned = [max(0, min(maximum, (value // 512) * 512)) for value in raw]
    return tuple(dict.fromkeys(aligned))


def _profile_sample(data: bytes, absolute_offset: int) -> SampleProfile:
    signatures: dict[str, int] = {}
    first_hits: dict[str, tuple[int, ...]] = {}
    for name, needle in SIGNATURES.items():
        count = _count_overlapping(data, needle)
        signatures[name] = count
        if count:
            first_hits[name] = tuple(absolute_offset + item for item in _find_hits(data, needle))

    annexb = _count_overlapping(data, b"\x00\x00\x00\x01") + _count_overlapping(
        data, b"\x00\x00\x01"
    )
    size = len(data)
    zeros = data.count(0)
    ffs = data.count(0xFF)
    return SampleProfile(
        offset=absolute_offset,
        size=size,
        sha256=sha256(data).hexdigest(),
        entropy_bits_per_byte=_entropy(data),
        zero_fraction=(zeros / size) if size else 0.0,
        ff_fraction=(ffs / size) if size else 0.0,
        signatures=signatures,
        first_hits=first_hits,
        annexb_start_codes=annexb,
    )


def profile_source(
    source: Path,
    *,
    sample_size: int = 4 * 1024 * 1024,
    sample_count: int = 5,
) -> SourceProfile:
    """Create a bounded, reproducible profile without scanning the whole evidence source.

    The profile is deliberately hypothesis-oriented. A signature hit is evidence for
    further analysis, not automatic proof of a filesystem/vendor identity.
    """

    if sample_size <= 0 or sample_size > 64 * 1024 * 1024:
        raise ValueError("sample_size must be between 1 byte and 64 MiB")
    if sample_count <= 0 or sample_count > 33:
        raise ValueError("sample_count must be between 1 and 33")

    info: SourceInfo = require_safe_source(source)
    offsets = _sample_offsets(info.size_bytes, sample_size, sample_count)
    fd = os.open(info.path, os.O_RDONLY)
    samples: list[SampleProfile] = []
    try:
        for offset in offsets:
            size = min(sample_size, max(0, info.size_bytes - offset))
            data = os.pread(fd, size, offset)
            samples.append(_profile_sample(data, offset))
    finally:
        os.close(fd)

    aggregate = {name: 0 for name in SIGNATURES}
    for sample in samples:
        for name, count in sample.signatures.items():
            aggregate[name] += count

    notes: list[str] = [
        "profile is based on bounded samples, not a complete source scan",
        "signature presence is investigative evidence, not automatic format proof",
    ]
    if aggregate["wfs_0_4_ascii"] or aggregate["wfs_0_5_ascii"]:
        notes.append("WFS ASCII version marker observed in sampled bytes")
    if aggregate["dahua_dhav_header"]:
        notes.append("DHAV-like record signature observed in sampled bytes")

    return SourceProfile(
        source=info.path,
        size_bytes=info.size_bytes,
        is_block_device=info.is_block_device,
        read_only=info.read_only,
        mounted_at=info.mounted_at,
        sampling_only=True,
        sample_size=sample_size,
        samples=tuple(samples),
        aggregate_signatures=aggregate,
        notes=tuple(notes),
    )
