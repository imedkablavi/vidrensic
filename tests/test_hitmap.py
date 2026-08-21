from __future__ import annotations

from pathlib import Path

from vidrensic.profiler.hitmap import SignatureDefinition, scan_signature_hitmap


def test_hitmap_counts_cross_chunk_hits_without_duplicates(tmp_path: Path) -> None:
    source = tmp_path / "evidence.raw"
    chunk_size = 4096
    data = bytearray(b"X" * (chunk_size * 3))
    pattern = b"HIKVISION@HANGZHOU"
    offsets = [100, chunk_size - 8, chunk_size + 500, chunk_size * 2 + 100]
    for offset in offsets:
        data[offset : offset + len(pattern)] = pattern
    source.write_bytes(data)

    report = scan_signature_hitmap(
        source,
        signatures=(SignatureDefinition("hik", pattern, "test"),),
        chunk_size=chunk_size,
        max_offsets_per_signature=10,
    )
    row = report.signatures[0]
    assert row["count"] == len(offsets)
    assert row["retained_offsets"] == offsets
    assert not row["offsets_truncated"]


def test_hitmap_caps_retained_offsets_but_counts_every_hit(tmp_path: Path) -> None:
    source = tmp_path / "many.raw"
    source.write_bytes(b"ABCD" * 1000)
    report = scan_signature_hitmap(
        source,
        signatures=(SignatureDefinition("abcd", b"ABCD", "test"),),
        chunk_size=4096,
        max_offsets_per_signature=7,
    )
    row = report.signatures[0]
    assert row["count"] == 1000
    assert len(row["retained_offsets"]) == 7
    assert row["offsets_truncated"]


def test_hitmap_range_limits_physical_scan(tmp_path: Path) -> None:
    source = tmp_path / "range.raw"
    data = bytearray(b"Z" * 20_000)
    data[100:104] = b"DHAV"
    data[10_000:10_004] = b"DHAV"
    source.write_bytes(data)

    report = scan_signature_hitmap(
        source,
        signatures=(SignatureDefinition("dhav", b"DHAV", "test"),),
        range_start=8000,
        range_size=5000,
        chunk_size=4096,
    )
    row = report.signatures[0]
    assert row["count"] == 1
    assert row["first_offset"] == 10_000
    assert report.scanned_bytes == 5000
