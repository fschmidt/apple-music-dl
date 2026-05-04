#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PY=""
for cand in python3.13 python3.12 python3.11; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done
if [ -z "$PY" ]; then
    echo "✗ Need Python 3.11+. Install with: brew install python@3.13" >&2
    exit 1
fi

if [ ! -d .venv ]; then
    echo "→ Creating virtualenv with $PY"
    "$PY" -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "⚠  ffmpeg not found on PATH — MP3 conversion will fail."
    echo "   Install with: brew install ffmpeg"
fi

exec .venv/bin/python -m apple_music_dl
