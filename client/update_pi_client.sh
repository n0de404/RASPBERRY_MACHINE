#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$PROJECT_DIR/.." && pwd)"
RUNTIME_DATA_DIR="${MACHINE_DATA_DIR:-$HOME/.local/share/raspberry-machine-client}"
SERVER_URL="${MACHINE_SERVER_URL:-}"
CLIENT_ID="${MACHINE_CLIENT_ID:-}"
SCANNER_PORT="${MACHINE_SCANNER_COM_PORT:-}"
SCANNER_MODE="${MACHINE_SCANNER_MODE:-}"
PACK_SCAN_INTERVAL="${MACHINE_PACK_SCAN_INTERVAL_SECONDS:-}"
DO_PULL=0
DO_START=1
DO_INSTALL_LAUNCHER=1
DO_SYSTEM_SETUP=1

usage() {
  cat <<EOF
Usage: ./update_pi_client.sh [options]

Installs Raspberry Pi system/Python dependencies, creates the project virtual
environment, stops the running client, rebuilds dist/RaspberryMachineClient,
refreshes the desktop/autostart launcher, and starts the rebuilt app.

Options:
  --pull                 Run git pull before rebuilding
  --server-url URL       Update shortcut/autostart launcher server URL
  --client-id ID         Update shortcut/autostart client identity
  --scanner-port PATH    Update shortcut/autostart scanner port
  --scanner-mode MODE    Update shortcut/autostart scanner mode: serial, keyboard, or auto
  --pack-scan-interval N Update PACK QR scan lock interval in seconds
  --skip-system-setup    Skip apt packages, virtualenv creation, and pip setup
  --no-start             Rebuild only; do not start the client after build
  --no-launcher-install  Do not refresh desktop/autostart launcher
  -h, --help             Show this help

Examples:
  ./update_pi_client.sh
  ./update_pi_client.sh --pull
  ./update_pi_client.sh --server-url http://192.168.10.49:8000 --scanner-port /dev/ttyACM0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull)
      DO_PULL=1
      shift
      ;;
    --server-url)
      SERVER_URL="${2:?Missing value for --server-url}"
      shift 2
      ;;
    --client-id)
      CLIENT_ID="${2:?Missing value for --client-id}"
      shift 2
      ;;
    --scanner-port)
      SCANNER_PORT="${2:?Missing value for --scanner-port}"
      shift 2
      ;;
    --scanner-mode)
      SCANNER_MODE="${2:?Missing value for --scanner-mode}"
      shift 2
      ;;
    --pack-scan-interval)
      PACK_SCAN_INTERVAL="${2:?Missing value for --pack-scan-interval}"
      shift 2
      ;;
    --skip-system-setup)
      DO_SYSTEM_SETUP=0
      shift
      ;;
    --no-start)
      DO_START=0
      shift
      ;;
    --no-launcher-install)
      DO_INSTALL_LAUNCHER=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

cd "$PROJECT_DIR"

if [[ "$DO_SYSTEM_SETUP" -eq 1 ]]; then
  echo "Updating Raspberry Pi package index..."
  sudo apt update

  echo "Installing Raspberry Pi client system dependencies..."
  sudo apt install -y \
    cron python3 python3-venv python3-pip python3-pyqt6 \
    libopenblas-dev libjpeg-dev zlib1g-dev libpng-dev libfreetype6-dev \
    libxcb-cursor0 libxkbcommon-x11-0 libegl1 libopengl0

  echo "Creating/updating the project virtual environment..."
  if [[ ! -f ".venv/bin/activate" ]]; then
    python3 -m venv --system-site-packages .venv
  elif ! grep -Eq '^include-system-site-packages[[:space:]]*=[[:space:]]*true' ".venv/pyvenv.cfg"; then
    python3 -m venv --upgrade --system-site-packages .venv
  fi

  # shellcheck disable=SC1091
  source ".venv/bin/activate"
  python -m pip install --upgrade pip setuptools wheel
  python -m pip install requests pyserial PyMySQL cryptography pyinstaller "qrcode[pil]"
fi

echo "Stopping running Raspberry Machine client..."
pkill -f "$PROJECT_DIR/dist/RaspberryMachineClient" 2>/dev/null || true
pkill -f "$PROJECT_DIR/client.py" 2>/dev/null || true
sleep 1

if [[ "$DO_PULL" -eq 1 ]]; then
  if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "Cannot pull: $REPO_DIR is not a git checkout." >&2
    exit 1
  fi
  echo "Pulling latest code..."
  git -C "$REPO_DIR" pull --ff-only
fi

chmod +x update_pi_client.sh build_client_pi.sh run_client_pi.sh
if [[ -f "install_pi_client_autostart.sh" ]]; then
  chmod +x install_pi_client_autostart.sh
fi

echo "Checking Python syntax..."
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi
python -m py_compile client.py mappings.py ui_theme.py

echo "Rebuilding client from: $PROJECT_DIR/client.py"
./build_client_pi.sh

if [[ ! -x "$PROJECT_DIR/dist/RaspberryMachineClient" ]]; then
  echo "Build failed: dist/RaspberryMachineClient was not created." >&2
  exit 1
fi

echo "Build timestamp:"
ls -lh "$PROJECT_DIR/dist/RaspberryMachineClient"

if [[ "$DO_INSTALL_LAUNCHER" -eq 1 && -x "$PROJECT_DIR/install_pi_client_autostart.sh" ]]; then
  echo
  echo "Refreshing desktop shortcut/autostart launcher..."
  install_args=()
  if [[ -n "$SERVER_URL" ]]; then
    install_args+=(--server-url "$SERVER_URL")
  fi
  if [[ -n "$CLIENT_ID" ]]; then
    install_args+=(--client-id "$CLIENT_ID")
  fi
  if [[ -n "$SCANNER_PORT" ]]; then
    install_args+=(--scanner-port "$SCANNER_PORT")
  fi
  if [[ -n "$SCANNER_MODE" ]]; then
    install_args+=(--scanner-mode "$SCANNER_MODE")
  fi
  if [[ -n "$PACK_SCAN_INTERVAL" ]]; then
    install_args+=(--pack-scan-interval "$PACK_SCAN_INTERVAL")
  fi
  "$PROJECT_DIR/install_pi_client_autostart.sh" "${install_args[@]}"
fi

if [[ "$DO_START" -ne 1 ]]; then
  echo
  echo "Build complete. Not starting client because --no-start was used."
  exit 0
fi

echo
echo "Starting rebuilt client..."
mkdir -p "$HOME/.local/state/raspberry-machine-client" "$RUNTIME_DATA_DIR"
export MACHINE_DATA_DIR="$RUNTIME_DATA_DIR"
if [[ -n "$SERVER_URL" ]]; then
  export MACHINE_SERVER_URL="$SERVER_URL"
fi
if [[ -n "$CLIENT_ID" ]]; then
  export MACHINE_CLIENT_ID="$CLIENT_ID"
fi
if [[ -n "$SCANNER_PORT" ]]; then
  export MACHINE_SCANNER_COM_PORT="$SCANNER_PORT"
fi
if [[ -n "$SCANNER_MODE" ]]; then
  export MACHINE_SCANNER_MODE="$SCANNER_MODE"
fi
if [[ -n "$PACK_SCAN_INTERVAL" ]]; then
  export MACHINE_PACK_SCAN_INTERVAL_SECONDS="$PACK_SCAN_INTERVAL"
fi
nohup "$PROJECT_DIR/dist/RaspberryMachineClient" \
  >>"$HOME/.local/state/raspberry-machine-client/client.log" 2>&1 &

sleep 1
if pgrep -f "$PROJECT_DIR/dist/RaspberryMachineClient" >/dev/null 2>&1; then
  echo "Started rebuilt client."
else
  echo "Client did not stay running. Check log:" >&2
  echo "  $HOME/.local/state/raspberry-machine-client/client.log" >&2
  exit 1
fi
echo "Log file: $HOME/.local/state/raspberry-machine-client/client.log"
