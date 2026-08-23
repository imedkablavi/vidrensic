from __future__ import annotations

import random
import struct

import pytest

from vidrensic.media.elementary import classify_annexb
from vidrensic.plugins.dhav.codec import DHAVParseError, parse_header
from vidrensic.plugins.wfs.codec import MAX_PACKET_SIZE, WFSParseError, packet_info, parse_fragment_tail
from vidrensic.plugins.wfs.salvage import scan_bounded_annexb_units


def test_wfs_rejects_oversized_declared_packet_without_allocation() -> None:
    raw = b"\x00\x00\x01\xfc" + struct.pack("<I", MAX_PACKET_SIZE + 1) + b"x" * 64
    assert packet_info(raw) is None
    with pytest.raises(WFSParseError):
        parse_fragment_tail(raw)


def test_dhav_rejects_frame_length_that_exceeds_parser_bound() -> None:
    raw = bytearray(24)
    raw[:4] = b"DHAV"
    struct.pack_into("<I", raw, 12, 64 * 1024 * 1024 + 1)
    with pytest.raises(DHAVParseError, match="implausible"):
        parse_header(bytes(raw))


def test_annexb_classifier_is_bounded_on_start_code_storm() -> None:
    data = b"\x00\x00\x01\x01" * 25_000
    evidence = classify_annexb(data)
    assert evidence.start_codes == 25_000
    assert 0.0 <= evidence.confidence <= 1.0


def test_salvage_limit_bounds_adversarial_start_code_storm() -> None:
    data = b"\x00\x00\x01\x01x" * 10_000
    result = scan_bounded_annexb_units(data, max_units=32)
    assert len(result.units) == 32
    assert any("max_units" in note for note in result.notes)


def test_deterministic_mutation_corpus_never_invents_unbounded_salvage_units() -> None:
    rng = random.Random(0xF04E51C)
    for _ in range(200):
        size = rng.randrange(0, 4096)
        data = bytearray(rng.randrange(256) for _ in range(size))
        if size >= 16 and rng.random() < 0.6:
            at = rng.randrange(0, size - 8)
            data[at : at + 4] = b"\x00\x00\x00\x01"
        result = scan_bounded_annexb_units(bytes(data), max_units=128)
        for unit in result.units:
            assert 0 <= unit.offset < unit.end <= len(data)
            assert unit.size > unit.prefix_length
