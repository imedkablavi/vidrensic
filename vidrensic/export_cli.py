from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys

from vidrensic.export import export_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vidrensic export",
        description="Create and verify a byte-for-byte forensic evidence copy.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("master", "review"), default="master")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = export_evidence(
            args.source,
            args.out,
            args.manifest,
            profile=args.profile,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Unable to export evidence: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print("Export complete")
    print()
    print(f"Artifact     {args.out.name}")
    print(f"Profile      {args.profile.title()}")
    print("Integrity    Verified")
    print(f"Manifest     {args.manifest.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
