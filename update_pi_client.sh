#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_URL="${MACHINE_SERVER_URL:-}"
SCANNER_PORT="${MACHINE_SCANNER_COM_PORT:-}"
SCANNER_MODE="${MACHINE_SCANNER_MODE:-}"
DO_PULL=0
DO_START=1
DO_INSTALL_LAUNCHER=1

usage() {
  cat <<EOF
Usage: ./update_pi_client.sh [options]

Stops the running client, rebuilds dist/RaspberryMachineClient, refreshes the
desktop/autostart launcher when available, and starts the rebuilt app.

Options:
  --pull                 Run git pull before rebuilding
  --server-url URL       Update shortcut/autostart launcher server URL
  --scanner-port PATH    Update shortcut/autostart scanner port
  --scanner-mode MODE    Update shortcut/autostart scanner mode: serial, keyboard, or auto
  --no-start             Rebuild only; do not start the client after build
  --no-launcher-install  Do not refresh desktop/autostart launcher
  -h, --help             Show this help

Examples:
  ./update_pi_client.sh
  ./update_pi_client.sh --pull
  ./update_pi_client.sh --server-url http://192.168.10.10:8000
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
    --scanner-port)
      SCANNER_PORT="${2:?Missing value for --scanner-port}"
      shift 2
      ;;
    --scanner-mode)
      SCANNER_MODE="${2:?Missing value for --scanner-mode}"
      shift 2
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

echo "Stopping running Raspberry Machine client..."
pkill -f "$PROJECT_DIR/dist/RaspberryMachineClient" 2>/dev/null || true
pkill -f "$PROJECT_DIR/client.py" 2>/dev/null || true
sleep 1

if [[ "$DO_PULL" -eq 1 ]]; then
  if [[ ! -d ".git" ]]; then
    echo "Cannot pull: $PROJECT_DIR is not a git checkout." >&2
    exit 1
  fi
  echo "Pulling latest code..."
  git pull --ff-only
fi

chmod +x build_client_pi.sh run_client_pi.sh
if [[ -f "install_pi_client_autostart.sh" ]]; then
  chmod +x install_pi_client_autostart.sh
fi

echo "Checking Python syntax..."
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi
python -m py_compile client.py mappings.py

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
  if [[ -n "$SCANNER_PORT" ]]; then
    install_args+=(--scanner-port "$SCANNER_PORT")
  fi
  if [[ -n "$SCANNER_MODE" ]]; then
    install_args+=(--scanner-mode "$SCANNER_MODE")
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
mkdir -p "$HOME/.local/state/raspberry-machine-client"
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
