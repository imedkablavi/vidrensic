from __future__ import annotations

import argparse
from pathlib import Path

from vidrensic.core.json_limits import BoundedJSONError, load_bounded_json
from vidrensic.validation.real_corpus import RealCorpusIndexError, validate_real_corpus_index


MAX_REAL_CORPUS_INDEX_BYTES = 8 * 1024 * 1024


def load_real_corpus_index(path: Path):
    try:
        return load_bounded_json(
            path,
            max_bytes=MAX_REAL_CORPUS_INDEX_BYTES,
            max_depth=48,
            max_nodes=250_000,
            max_string_chars=64 * 1024,
            label="real-recorder corpus index",
        )
    except BoundedJSONError as exc:
        raise RealCorpusIndexError(str(exc)) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate real-recorder corpus provenance index")
    parser.add_argument(
        "path",
        nargs="?",
        default="validation_corpus/real/real-corpus-index.json",
        type=Path,
    )
    args = parser.parse_args()
    data = load_real_corpus_index(args.path)
    validate_real_corpus_index(data)
    print(f"validated real-recorder corpus index: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
