from __future__ import annotations

import argparse
import json
from pathlib import Path

from vidrensic.validation.real_corpus import validate_real_corpus_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate real-recorder corpus provenance index")
    parser.add_argument(
        "path",
        nargs="?",
        default="validation_corpus/real/real-corpus-index.json",
        type=Path,
    )
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    validate_real_corpus_index(data)
    print(f"validated real-recorder corpus index: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
