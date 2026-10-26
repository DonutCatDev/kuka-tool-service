#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
python_bin=${PYTHON:-"$repo_dir/.venv/bin/python"}

if [[ ! -x "$python_bin" ]]; then
    echo "Python interpreter not found: $python_bin" >&2
    exit 1
fi

cd "$repo_dir"
PYTHONPYCACHEPREFIX="$repo_dir/validation/tmp/pycache" \
    "$python_bin" -m compileall -q src tests
PYTHONDONTWRITEBYTECODE=1 "$python_bin" -m pytest

if command -v docker >/dev/null 2>&1; then
    docker compose -f compose.yaml config --quiet
else
    echo "Docker unavailable; Compose validation skipped."
fi
