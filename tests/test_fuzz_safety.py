from __future__ import annotations

import random

from vidrensic.media.elementary import classify_annexb
from vidrensic.plugins.dhav.codec import DHAVParseError, parse_extension, parse_header
from vidrensic.plugins.hikvision.master import MASTER_SIGNATURE, parse_master_candidate
from vidrensic.plugins.wfs.codec import WFSParseError, packet_info, parse_fragment_tail


def _bytes(rng: random.Random, size: int) -> bytes:
    return bytes(rng.randrange(256) for _ in range(size))


def test_random_malformed_parser_inputs_do_not_escape_declared_errors() -> None:
    rng = random.Random(0x56494452)  # "VIDR" deterministic corpus seed.

    for _ in range(250):
        size = rng.randrange(0, 2049)
        data = _bytes(rng, size)

        # WFS packet inspection is a non-throwing recognizer.
        result = packet_info(data, 0) if data else None
        assert result is None or result.total_size > 0

        try:
            tail = parse_fragment_tail(data)
            assert tail is None or isinstance(tail, bytes)
        except WFSParseError:
            pass

        try:
            header = parse_header(data)
            assert header.frame_length >= 32
        except DHAVParseError:
            pass

        extension = parse_extension(data[:255])
        assert isinstance(extension.parsed_types, tuple)
        assert isinstance(extension.unknown_types, tuple)

        evidence = classify_annexb(data)
        assert 0.0 <= evidence.confidence <= 1.0


def test_hikvision_master_parser_handles_arbitrary_fields_after_exact_signature() -> None:
    rng = random.Random(0x48494B31)
    for _ in range(100):
        raw = bytearray(_bytes(rng, 256))
        raw[: len(MASTER_SIGNATURE)] = MASTER_SIGNATURE
        candidate = parse_master_candidate(
            bytes(raw),
            absolute_offset=rng.randrange(0, 1024 * 1024),
            source_size=2 * 1024**3,
        )
        assert 0.0 <= candidate.plausibility_score <= 1.0
        assert candidate.reasons
