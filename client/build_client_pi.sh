#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "Client virtual environment is missing: $SCRIPT_DIR/.venv" >&2
  echo "Run ./update_pi_client.sh without --skip-system-setup once to create it." >&2
  exit 1
fi

# Never install build packages into Debian's externally managed system Python.
# shellcheck disable=SC1091
source ".venv/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install pyinstaller requests pyserial PyMySQL cryptography "qrcode[pil]"
python -m py_compile client.py mappings.py ui_theme.py

if ! python - <<'PY'
import importlib.util
import sys
sys.exit(0 if importlib.util.find_spec("PyQt6") else 1)
PY
then
  echo "PyQt6 is not installed in this Python environment."
  echo "On Raspberry Pi, install it with: sudo apt install -y python3-pyqt6"
  exit 1
fi

rm -rf build dist
python -m PyInstaller --clean client_pi.spec

echo
echo "Build complete:"
echo "  dist/RaspberryMachineClient"
