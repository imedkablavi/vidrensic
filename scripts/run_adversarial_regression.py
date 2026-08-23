from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

from vidrensic.media.elementary import classify_annexb
from vidrensic.plugins.dhav.codec import DHAVParseError, parse_extension, parse_header
from vidrensic.plugins.hikvision.master import MASTER_SIGNATURE, parse_master_candidate
from vidrensic.plugins.wfs.codec import WFSParseError, packet_info, parse_fragment_tail
from vidrensic.plugins.wfs.salvage import scan_bounded_annexb_units


DEFAULT_BASE_SEED = 0x56494452  # "VIDR"
MAX_INPUT_SIZE = 64 * 1024
MAX_ITERATIONS_PER_SEED = 100_000
MAX_SEEDS = 64
SALVAGE_MAX_UNITS = 64


def _random_bytes(rng: random.Random, size: int) -> bytes:
    return rng.randbytes(size)


def _exercise_one(data: bytes, rng: random.Random, counters: dict[str, int]) -> None:
    result = packet_info(data, 0) if data else None
    if result is not None:
        assert result.total_size > 0
        counters["wfs_packet_recognized"] += 1

    try:
        tail = parse_fragment_tail(data)
        assert tail is None or isinstance(tail, bytes)
        counters["wfs_tail_parsed"] += 1
    except WFSParseError:
        counters["wfs_declared_parse_errors"] += 1

    try:
        header = parse_header(data)
        assert header.frame_length >= 32
        counters["dhav_headers_parsed"] += 1
    except DHAVParseError:
        counters["dhav_declared_parse_errors"] += 1

    extension = parse_extension(data[:255])
    assert isinstance(extension.parsed_types, tuple)
    assert isinstance(extension.unknown_types, tuple)

    annexb = classify_annexb(data)
    assert 0.0 <= annexb.confidence <= 1.0

    salvage = scan_bounded_annexb_units(data, max_units=SALVAGE_MAX_UNITS)
    assert len(salvage.units) <= SALVAGE_MAX_UNITS
    for unit in salvage.units:
        assert 0 <= unit.offset < unit.end <= len(data)
    if salvage.scan_truncated:
        counters["salvage_truncated"] += 1

    # Exercise Hikvision field parsing with an exact public format signature but
    # randomized following bytes. This is synthetic parser stress, not evidence
    # that a recorder family is validated.
    if len(data) >= max(256, len(MASTER_SIGNATURE)) and rng.randrange(8) == 0:
        raw = bytearray(data[:256])
        raw[: len(MASTER_SIGNATURE)] = MASTER_SIGNATURE
        candidate = parse_master_candidate(
            bytes(raw),
            absolute_offset=rng.randrange(0, 1024 * 1024),
            source_size=2 * 1024**3,
        )
        assert 0.0 <= candidate.plausibility_score <= 1.0
        assert candidate.reasons
        counters["hikvision_signature_cases"] += 1


def run_regression(
    *,
    iterations_per_seed: int,
    seed_count: int,
    max_size: int,
    base_seed: int = DEFAULT_BASE_SEED,
) -> dict[str, object]:
    if not 1 <= iterations_per_seed <= MAX_ITERATIONS_PER_SEED:
        raise ValueError(
            f"iterations_per_seed must be between 1 and {MAX_ITERATIONS_PER_SEED}"
        )
    if not 1 <= seed_count <= MAX_SEEDS:
        raise ValueError(f"seed_count must be between 1 and {MAX_SEEDS}")
    if not 0 <= max_size <= MAX_INPUT_SIZE:
        raise ValueError(f"max_size must be between 0 and {MAX_INPUT_SIZE}")

    seeds = [base_seed + index for index in range(seed_count)]
    counters = {
        "wfs_packet_recognized": 0,
        "wfs_tail_parsed": 0,
        "wfs_declared_parse_errors": 0,
        "dhav_headers_parsed": 0,
        "dhav_declared_parse_errors": 0,
        "salvage_truncated": 0,
        "hikvision_signature_cases": 0,
    }

    started = time.monotonic()
    for seed in seeds:
        rng = random.Random(seed)
        for _ in range(iterations_per_seed):
            size = rng.randrange(max_size + 1) if max_size else 0
            _exercise_one(_random_bytes(rng, size), rng, counters)

    return {
        "schema_version": 1,
        "kind": "deterministic-adversarial-regression",
        "seeds": seeds,
        "iterations_per_seed": iterations_per_seed,
        "total_cases": iterations_per_seed * seed_count,
        "max_input_size": max_size,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "counters": counters,
        "claim_limit": (
            "Passing this deterministic malformed-input regression means only that the exercised "
            "synthetic cases stayed within declared parser/error invariants. It is not coverage-guided "
            "fuzzing, a proof of memory safety, or real-recorder validation."
        ),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic malformed-input regression across forensic parsers"
    )
    parser.add_argument("--iterations", type=int, default=1000, help="cases per deterministic seed")
    parser.add_argument("--seeds", type=int, default=4, help="number of consecutive seeds")
    parser.add_argument("--max-size", type=int, default=4096, help="maximum synthetic input bytes")
    parser.add_argument("--base-seed", type=lambda value: int(value, 0), default=DEFAULT_BASE_SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    payload = run_regression(
        iterations_per_seed=args.iterations,
        seed_count=args.seeds,
        max_size=args.max_size,
        base_seed=args.base_seed,
    )
    _write_json(args.out, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
