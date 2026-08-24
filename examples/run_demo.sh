#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/.vidrensic-demo}"
SOURCE="$OUT/synthetic-dhav.raw"
RECOVERED="$OUT/recovered"
PYTHON="${PYTHON:-python}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf '%s\n' "[demo] error: Python executable '$PYTHON' was not found." >&2
    exit 2
fi

if command -v vidrensic >/dev/null 2>&1; then
    VIDRENSIC=(vidrensic)
elif "$PYTHON" -c 'import vidrensic' >/dev/null 2>&1; then
    VIDRENSIC=("$PYTHON" -m vidrensic.cli_ext)
else
    cat >&2 <<EOF
[demo] error: Vidrensic is not installed for $($PYTHON --version 2>&1).
[demo] from the repository root, run:
  bash scripts/setup_dev.sh
  source .venv/bin/activate
  bash examples/run_demo.sh
EOF
    exit 2
fi

mkdir -p "$OUT"
rm -rf "$RECOVERED"

printf '%s\n' '[demo] generating deterministic synthetic recorder source'
"$PYTHON" "$ROOT/examples/generate_dhav_demo.py" --out "$SOURCE"

printf '\n%s\n' '[demo] format detection'
"${VIDRENSIC[@]}" formats detect "$SOURCE"

printf '\n%s\n' '[demo] recovery'
"${VIDRENSIC[@]}" recover dhav "$SOURCE" --out "$RECOVERED"

printf '\n%s\n' '[demo] recovered channels'
find "$RECOVERED" -maxdepth 1 -type f -printf '%f\n' | sort

printf '\n%s\n' '[demo] manifest summary'
"$PYTHON" - "$RECOVERED/dhav_manifest.json" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(f"frame_count={manifest['frame_count']}")
print(f"channels={len(manifest['channels'])}")
for channel in manifest["channels"]:
    print(
        f"channel={channel['channel']} frames={channel['frames']} "
        f"native_sha256={channel['native_sha256'][:16]}..."
    )
PY

printf '\n[demo] output=%s\n' "$OUT"
