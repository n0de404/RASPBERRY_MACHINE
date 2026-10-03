#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # Use the local project environment when available.
  source ".venv/bin/activate"
fi

export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"
export MACHINE_DATA_DIR="${MACHINE_DATA_DIR:-$HOME/.local/share/raspberry-machine-client}"
export MACHINE_SERVER_URL="${MACHINE_SERVER_URL:-http://127.0.0.1:8000}"
export MACHINE_SCANNER_MODE="${MACHINE_SCANNER_MODE:-auto}"
export MACHINE_SCANNER_COM_PORT="${MACHINE_SCANNER_COM_PORT:-/dev/ttyACM0}"
export MACHINE_DEFAULT_GRAPHICS_MODE="${MACHINE_DEFAULT_GRAPHICS_MODE:-faster_quality}"

mkdir -p "$MACHINE_DATA_DIR"
exec python client.py
