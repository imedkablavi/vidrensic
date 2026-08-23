from __future__ import annotations

from dataclasses import dataclass

from vidrensic.media.elementary import classify_annexb


@dataclass(frozen=True)
class SalvagedNALUnit:
    """One bounded Annex-B unit recovered from a damaged byte span.

    The unit is emitted only when both its start and end are delimited by
    observed Annex-B start codes. The final unterminated candidate is never
    emitted because its byte extent is not proven.
    """

    offset: int
    end: int
    prefix_length: int
    codec: str | None
    nal_type: int | None
    parameter_set: bool
    random_access: bool

    @property
    def size(self) -> int:
        return self.end - self.offset


@dataclass(frozen=True)
class AnnexBSalvageResult:
    units: tuple[SalvagedNALUnit, ...]
    codec_hint: str | None
    codec_confidence: float
    bounded_bytes: int
    random_access_units: int
    discarded_unbounded_tail_bytes: int
    scan_truncated: bool
    notes: tuple[str, ...]


def _start_codes(data: bytes, *, limit: int | None = None) -> tuple[tuple[int, int], ...]:
    """Return Annex-B start-code offsets without unbounded match accumulation."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")

    found: list[tuple[int, int]] = []
    position = 0
    while position + 3 <= len(data):
        if data[position : position + 4] == b"\x00\x00\x00\x01":
            found.append((position, 4))
            if limit is not None and len(found) >= limit:
                break
            position += 4
            continue
        if data[position : position + 3] == b"\x00\x01"[:0] + b"\x00\x00\x01":
            found.append((position, 3))
            if limit is not None and len(found) >= limit:
                break
            position += 3
            continue
        position += 1
    return tuple(found)


def _nal_flags(codec: str | None, first: int) -> tuple[int | None, bool, bool]:
    if codec == "h264":
        nal_type = first & 0x1F
        return nal_type, nal_type in {7, 8}, nal_type == 5
    if codec == "hevc":
        nal_type = (first >> 1) & 0x3F
        return nal_type, nal_type in {32, 33, 34}, nal_type in {16, 17, 18, 19, 20, 21}
    return None, False, False


def scan_bounded_annexb_units(
    data: bytes,
    *,
    base_offset: int = 0,
    max_units: int = 100_000,
) -> AnnexBSalvageResult:
    """Recover only start-code-bounded Annex-B units from a damaged byte span.

    This is deliberately a salvage primitive, not a decoder and not evidence of
    chronological continuity. Codec-specific NAL/GOP labels are emitted only
    when the scanned byte span provides high-confidence parameter-set evidence.
    The last unbounded candidate is discarded. Enumeration retains at most
    ``max_units + 2`` start-code boundaries so adversarial start-code storms do
    not create an unbounded offset list.
    """

    if base_offset < 0:
        raise ValueError("base_offset cannot be negative")
    if max_units <= 0:
        raise ValueError("max_units must be positive")

    # max_units units require max_units + 1 boundaries. One extra boundary lets
    # us prove that additional bounded units exist and mark the scan incomplete.
    starts = _start_codes(data, limit=max_units + 2)
    scan_truncated = len(starts) == max_units + 2

    if scan_truncated:
        scan_end = starts[-1][0] + starts[-1][1]
        evidence_data = data[:scan_end]
    else:
        evidence_data = data
    evidence = classify_annexb(evidence_data)
    codec = evidence.codec if evidence.confidence >= 0.80 else None

    units: list[SalvagedNALUnit] = []
    available_units = max(0, len(starts) - 1)
    for index in range(min(max_units, available_units)):
        start, prefix_length = starts[index]
        end = starts[index + 1][0]
        header = start + prefix_length
        if header >= end:
            continue
        nal_type, parameter_set, random_access = _nal_flags(codec, data[header])
        units.append(
            SalvagedNALUnit(
                offset=base_offset + start,
                end=base_offset + end,
                prefix_length=prefix_length,
                codec=codec,
                nal_type=nal_type,
                parameter_set=parameter_set,
                random_access=random_access,
            )
        )

    bounded_bytes = sum(item.size for item in units)
    discarded_tail = 0
    if starts and not scan_truncated:
        last_start = starts[-1][0]
        discarded_tail = len(data) - last_start

    notes = [
        "salvage units are byte-range evidence only; recorder-frame continuity is not implied",
        "the final Annex-B candidate is discarded because its end is not bounded by a later start code",
        "codec/NAL/GOP labels require high-confidence parameter-set evidence from the scanned damaged span",
        "salvage output must remain REVIEW/UNKNOWN until validated against recorder-specific ground truth",
    ]
    if scan_truncated:
        notes.extend(
            (
                "unit enumeration reached max_units and is incomplete",
                "unbounded-tail byte count is not reported for a truncated scan because the final start code was not searched",
            )
        )

    return AnnexBSalvageResult(
        units=tuple(units),
        codec_hint=codec,
        codec_confidence=evidence.confidence,
        bounded_bytes=bounded_bytes,
        random_access_units=sum(item.random_access for item in units),
        discarded_unbounded_tail_bytes=discarded_tail,
        scan_truncated=scan_truncated,
        notes=tuple(notes),
    )
