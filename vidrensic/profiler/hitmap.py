from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json
import os

from vidrensic.acquisition.linux import require_safe_source


@dataclass(frozen=True)
class SignatureDefinition:
    signature_id: str
    pattern: bytes
    category: str
    evidence_strength: str = "lead"
    description: str = ""

    def __post_init__(self) -> None:
        if not self.signature_id.strip():
            raise ValueError("signature_id cannot be empty")
        if not self.pattern:
            raise ValueError("signature pattern cannot be empty")
        if len(self.pattern) > 4096:
            raise ValueError("signature pattern is too large for hit-map scanning")
        if self.evidence_strength not in {"lead", "supporting", "strong-structural-marker"}:
            raise ValueError("invalid evidence_strength")


@dataclass
class SignatureHitStats:
    definition: SignatureDefinition
    count: int = 0
    first_offset: int | None = None
    last_offset: int | None = None
    retained_offsets: list[int] = field(default_factory=list)
    offsets_truncated: bool = False
    _last_counted_offset: int | None = field(default=None, repr=False)

    def observe(self, offset: int, *, max_offsets: int) -> None:
        # Cross-chunk overlap can expose the same hit twice. Scanning is
        # monotonic, so this single value avoids a memory-heavy global set.
        if self._last_counted_offset is not None and offset <= self._last_counted_offset:
            return
        self._last_counted_offset = offset
        self.count += 1
        if self.first_offset is None:
            self.first_offset = offset
        self.last_offset = offset
        if len(self.retained_offsets) < max_offsets:
            self.retained_offsets.append(offset)
        else:
            self.offsets_truncated = True

    def to_dict(self, *, scanned_bytes: int) -> dict[str, Any]:
        gib = scanned_bytes / (1024**3) if scanned_bytes else 0.0
        density = self.count / gib if gib else 0.0
        return {
            "signature_id": self.definition.signature_id,
            "category": self.definition.category,
            "evidence_strength": self.definition.evidence_strength,
            "description": self.definition.description,
            "pattern_hex": self.definition.pattern.hex(),
            "pattern_length": len(self.definition.pattern),
            "count": self.count,
            "first_offset": self.first_offset,
            "last_offset": self.last_offset,
            "retained_offsets": self.retained_offsets,
            "offsets_truncated": self.offsets_truncated,
            "hits_per_gib_scanned": density,
        }


@dataclass(frozen=True)
class HitMapReport:
    source: Path
    source_size: int
    range_start: int
    range_stop: int
    scanned_bytes: int
    chunk_size: int
    max_offsets_per_signature: int
    signatures: tuple[dict[str, Any], ...]
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": str(self.source),
            "source_size": self.source_size,
            "range_start": self.range_start,
            "range_stop": self.range_stop,
            "scanned_bytes": self.scanned_bytes,
            "chunk_size": self.chunk_size,
            "max_offsets_per_signature": self.max_offsets_per_signature,
            "signatures": list(self.signatures),
            "notes": list(self.notes),
        }

    def write_json(self, output: Path) -> Path:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(output.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(output)
        return output


def builtin_signatures() -> tuple[SignatureDefinition, ...]:
    """Return conservative built-in structural/signature leads.

    A hit is never equivalent to format proof. Some values intentionally have
    `lead` strength because they are common codec/container byte sequences.
    """

    return (
        SignatureDefinition(
            "wfs_0_4_ascii",
            b"WFS 0.4",
            "storage-family",
            "supporting",
            "WFS 0.4 ASCII marker",
        ),
        SignatureDefinition(
            "wfs_0_5_ascii",
            b"WFS 0.5",
            "storage-family",
            "supporting",
            "WFS 0.5 ASCII marker",
        ),
        SignatureDefinition(
            "dhav_header",
            b"DHAV",
            "record-family",
            "supporting",
            "DHAV frame header marker; footer/length validation is still required",
        ),
        SignatureDefinition(
            "dhav_footer",
            b"dhav",
            "record-family",
            "lead",
            "DHAV footer marker; case-sensitive lowercase bytes can occur elsewhere",
        ),
        SignatureDefinition(
            "hikvision_master",
            b"HIKVISION@HANGZHOU",
            "storage-family",
            "strong-structural-marker",
            "Hikvision Master Sector signature candidate",
        ),
        SignatureDefinition(
            "hikbtree",
            b"HIKBTREE",
            "index-family",
            "supporting",
            "Hikvision index-tree marker candidate",
        ),
        SignatureDefinition(
            "mpegps_pack",
            b"\x00\x00\x01\xba",
            "container-family",
            "lead",
            "MPEG Program Stream pack start code",
        ),
        SignatureDefinition(
            "h264_sps_annexb4",
            b"\x00\x00\x00\x01\x67",
            "codec",
            "lead",
            "H.264 Annex-B SPS-like sequence",
        ),
        SignatureDefinition(
            "h264_pps_annexb4",
            b"\x00\x00\x00\x01\x68",
            "codec",
            "lead",
            "H.264 Annex-B PPS-like sequence",
        ),
        SignatureDefinition(
            "hevc_vps_annexb4",
            b"\x00\x00\x00\x01\x40",
            "codec",
            "lead",
            "HEVC Annex-B VPS-like NAL header sequence",
        ),
        SignatureDefinition(
            "hevc_sps_annexb4",
            b"\x00\x00\x00\x01\x42",
            "codec",
            "lead",
            "HEVC Annex-B SPS-like NAL header sequence",
        ),
    )


def scan_signature_hitmap(
    source: Path,
    *,
    signatures: tuple[SignatureDefinition, ...] | None = None,
    range_start: int = 0,
    range_size: int | None = None,
    chunk_size: int = 16 * 1024 * 1024,
    max_offsets_per_signature: int = 256,
) -> HitMapReport:
    """Stream a physical source range and count structural signatures.

    Memory use is bounded by the chunk size plus a small retained offset sample.
    All hits are counted, but only the first `max_offsets_per_signature` physical
    offsets are retained in the report.
    """

    if range_start < 0:
        raise ValueError("range_start cannot be negative")
    if range_size is not None and range_size <= 0:
        raise ValueError("range_size must be positive")
    if not 4096 <= chunk_size <= 256 * 1024 * 1024:
        raise ValueError("chunk_size must be between 4 KiB and 256 MiB")
    if not 1 <= max_offsets_per_signature <= 100_000:
        raise ValueError("max_offsets_per_signature must be between 1 and 100000")

    definitions = signatures if signatures is not None else builtin_signatures()
    if not definitions:
        raise ValueError("at least one signature is required")
    ids = [item.signature_id for item in definitions]
    if len(ids) != len(set(ids)):
        raise ValueError("signature IDs must be unique")

    info = require_safe_source(source)
    if range_start > info.size_bytes:
        raise ValueError("range_start is beyond source end")
    requested_stop = info.size_bytes if range_size is None else range_start + range_size
    range_stop = min(info.size_bytes, requested_stop)

    overlap = max(len(item.pattern) for item in definitions) - 1
    stats = {item.signature_id: SignatureHitStats(item) for item in definitions}
    fd = os.open(info.path, os.O_RDONLY)
    position = range_start
    carry = b""
    scanned = 0
    try:
        while position < range_stop:
            wanted = min(chunk_size, range_stop - position)
            chunk = os.pread(fd, wanted, position)
            if not chunk:
                break
            scanned += len(chunk)
            data = carry + chunk
            base = position - len(carry)

            for definition in definitions:
                record = stats[definition.signature_id]
                cursor = 0
                while True:
                    cursor = data.find(definition.pattern, cursor)
                    if cursor < 0:
                        break
                    absolute = base + cursor
                    if range_start <= absolute < range_stop:
                        record.observe(absolute, max_offsets=max_offsets_per_signature)
                    cursor += 1

            carry = data[-overlap:] if overlap else b""
            position += len(chunk)
    finally:
        os.close(fd)

    rows = tuple(
        stats[item.signature_id].to_dict(scanned_bytes=scanned)
        for item in definitions
    )
    return HitMapReport(
        source=info.path,
        source_size=info.size_bytes,
        range_start=range_start,
        range_stop=range_stop,
        scanned_bytes=scanned,
        chunk_size=chunk_size,
        max_offsets_per_signature=max_offsets_per_signature,
        signatures=rows,
        notes=(
            "signature counts are physical evidence leads, not automatic vendor/filesystem proof",
            "all hits are counted while retained offset lists are capped to bound memory/report size",
            "codec start-code hits can occur inside proprietary records and should be interpreted with stronger structural evidence",
        ),
    )
