from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic import __product__, __version__
from vidrensic.profiler.bundle import build_anonymized_bundle
from vidrensic.profiler.triage import triage_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic-profiler",
        description="Analyze a recorder source and create a shareable anonymized profiler bundle.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=4 * 1024 * 1024)
    parser.add_argument("--sample-count", type=int, default=5)
    parser.add_argument("--hitmap-size", type=int, default=512 * 1024 * 1024)
    parser.add_argument("--full-hitmap", action="store_true")
    parser.add_argument("--hitmap-chunk-size", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--max-offsets", type=int, default=128)
    parser.add_argument("--minimum-confidence", type=float, default=0.60)
    parser.add_argument("--minimum-margin", type=float, default=0.15)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        triage = triage_source(
            args.source,
            sample_size=args.sample_size,
            sample_count=args.sample_count,
            hitmap_size=None if args.full_hitmap else args.hitmap_size,
            hitmap_chunk_size=args.hitmap_chunk_size,
            max_offsets_per_signature=args.max_offsets,
            minimum_confidence=args.minimum_confidence,
            minimum_margin=args.minimum_margin,
        )
        bundle = build_anonymized_bundle(triage)
        output = bundle.write_json(args.out, replace=args.replace)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to create profiler bundle: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(bundle.to_dict(), indent=2, sort_keys=True))
        return 0

    print("Profiler bundle ready")
    print()
    print(f"Vidrensic    {__product__} {__version__}")
    print(f"Source       {bundle.source['kind']}")
    print(f"Size         {bundle.source['size_bucket']}")
    print(f"Detection    {bundle.format_detection['results'][0]['plugin'] if bundle.format_detection['results'] else 'No clear match'}")
    print(f"Assessment   {'Review required' if bundle.workflow['review_required'] else 'Ready for next step'}")
    print("Privacy      Evidence not included")
    print(f"Bundle       {output.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
