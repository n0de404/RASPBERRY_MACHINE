#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # Use the local project environment when available.
  source ".venv/bin/activate"
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export QRGEN_BASE_URL="${QRGEN_BASE_URL:-http://127.0.0.1:5000}"

exec python server.py
