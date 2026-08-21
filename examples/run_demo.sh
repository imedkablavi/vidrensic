#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/.vidrensic-demo}"
SOURCE="$OUT/synthetic-dhav.raw"
RECOVERED="$OUT/recovered"

mkdir -p "$OUT"
rm -rf "$RECOVERED"

printf '%s\n' '[demo] generating deterministic synthetic recorder source'
python "$ROOT/examples/generate_dhav_demo.py" --out "$SOURCE"

printf '\n%s\n' '[demo] format detection'
vidrensic formats detect "$SOURCE"

printf '\n%s\n' '[demo] recovery'
vidrensic recover dhav "$SOURCE" --out "$RECOVERED"

printf '\n%s\n' '[demo] recovered channels'
find "$RECOVERED" -maxdepth 1 -type f -printf '%f\n' | sort

printf '\n%s\n' '[demo] manifest summary'
python - "$RECOVERED/dhav_manifest.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(f"frame_count={manifest['frame_count']}")
print(f"channels={len(manifest['channels'])}")
for channel in manifest["channels"]:
    print(
        f"channel={channel['channel']} frames={channel['frame_count']} "
        f"native_sha256={channel['native_sha256'][:16]}..."
    )
PY

printf '\n[demo] output=%s\n' "$OUT"
