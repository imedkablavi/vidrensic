#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VIDRENSIC_VENV:-$ROOT/.venv}"
PYTHON="${PYTHON:-python3}"

if [[ ! -f "$ROOT/pyproject.toml" || ! -d "$ROOT/vidrensic" ]]; then
    printf '%s\n' '[setup] error: repository root could not be located.' >&2
    printf '%s\n' '[setup] clone once, enter that directory once, and retry.' >&2
    exit 2
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf '%s\n' "[setup] error: Python executable '$PYTHON' was not found." >&2
    exit 2
fi

if ! "$PYTHON" - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
    printf '%s\n' "[setup] error: Vidrensic requires Python 3.11 or newer; found $($PYTHON --version 2>&1)." >&2
    exit 2
fi

PYTHON_MINOR="$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PYTHON_MINOR" in
    3.11|3.12|3.13) ;;
    *)
        printf '%s\n' "[setup] warning: Python $PYTHON_MINOR satisfies package metadata but is not currently CI-qualified (3.11-3.13)." >&2
        ;;
esac

printf '%s\n' "[setup] repository=$ROOT"
printf '%s\n' "[setup] environment=$VENV"

if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -e "$ROOT[dev]"

"$VENV/bin/vidrensic" --version
"$VENV/bin/vidrensic" doctor

cat <<EOF

[setup] ready
Activate this environment in your current shell:
  source "$VENV/bin/activate"

Then run the synthetic public demo:
  bash "$ROOT/examples/run_demo.sh"
EOF

if [[ "${1:-}" == "--demo" ]]; then
    printf '\n%s\n' '[setup] running synthetic public demo'
    PATH="$VENV/bin:$PATH" PYTHON="$VENV/bin/python" bash "$ROOT/examples/run_demo.sh"
fi
