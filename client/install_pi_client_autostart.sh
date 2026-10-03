#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DATA_DIR="${MACHINE_DATA_DIR:-$HOME/.local/share/raspberry-machine-client}"
APP_NAME="Raspberry Machine Client"
DESKTOP_ID="RaspberryMachineClient"
SERVER_URL="${MACHINE_SERVER_URL:-http://127.0.0.1:8000}"
CLIENT_ID="${MACHINE_CLIENT_ID:-$(hostname)}"
CLIENT_ID_EXPLICIT=0
if [[ -n "${MACHINE_CLIENT_ID:-}" ]]; then
  CLIENT_ID_EXPLICIT=1
fi
SCANNER_PORT="${MACHINE_SCANNER_COM_PORT:-/dev/ttyACM0}"
SCANNER_MODE="${MACHINE_SCANNER_MODE:-auto}"
GRAPHICS_MODE="${MACHINE_DEFAULT_GRAPHICS_MODE:-faster_quality}"
PACK_SCAN_INTERVAL="${MACHINE_PACK_SCAN_INTERVAL_SECONDS:-10}"
DO_BUILD=0
DO_AUTOSTART=1
DO_DESKTOP=1

usage() {
  cat <<EOF
Usage: ./install_pi_client_autostart.sh [options]

Options:
  --server-url URL       Server URL for the client. Default: ${SERVER_URL}
  --client-id ID         Client identity reported to the server. Default: ${CLIENT_ID}
  --scanner-port PATH    Scanner serial port. Default: ${SCANNER_PORT}
  --scanner-mode MODE    Scanner mode. Default: ${SCANNER_MODE}
  --graphics-mode MODE   Graphics mode. Default: ${GRAPHICS_MODE}
  --pack-scan-interval N PACK QR scan lock interval in seconds. Default: ${PACK_SCAN_INTERVAL}
  --build               Run build_client_pi.sh before installing shortcut/autostart
  --no-autostart        Do not install boot/login autostart entry
  --no-desktop          Do not install desktop shortcut
  -h, --help            Show this help

Examples:
  ./install_pi_client_autostart.sh --server-url http://192.168.10.10:8000
  ./install_pi_client_autostart.sh --build --scanner-port /dev/ttyUSB0
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server-url)
      SERVER_URL="${2:?Missing value for --server-url}"
      shift 2
      ;;
    --client-id)
      CLIENT_ID="${2:?Missing value for --client-id}"
      CLIENT_ID_EXPLICIT=1
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
    --graphics-mode)
      GRAPHICS_MODE="${2:?Missing value for --graphics-mode}"
      shift 2
      ;;
    --pack-scan-interval)
      PACK_SCAN_INTERVAL="${2:?Missing value for --pack-scan-interval}"
      shift 2
      ;;
    --build)
      DO_BUILD=1
      shift
      ;;
    --no-autostart)
      DO_AUTOSTART=0
      shift
      ;;
    --no-desktop)
      DO_DESKTOP=0
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
chmod +x run_client_pi.sh build_client_pi.sh

if [[ "$DO_BUILD" -eq 1 ]]; then
  ./build_client_pi.sh
fi

mkdir -p "$HOME/.local/bin" "$HOME/.local/state/raspberry-machine-client" "$RUNTIME_DATA_DIR"
LAUNCHER="$HOME/.local/bin/raspberry-machine-client"

# Rebuilds preserve the identity already installed on this physical client.
# A genuinely new install asks the server for the next RPI-CLIENT-## name.
# The server includes offline and historical clients, so their IDs are never
# silently reused.
if [[ "$CLIENT_ID_EXPLICIT" -eq 0 && -f "$LAUNCHER" ]]; then
  EXISTING_CLIENT_ID="$(sed -n 's/^export MACHINE_CLIENT_ID="\(.*\)"$/\1/p' "$LAUNCHER" | head -n 1)"
  if [[ -n "$EXISTING_CLIENT_ID" ]]; then
    CLIENT_ID="$EXISTING_CLIENT_ID"
    echo "Preserving existing client ID: $CLIENT_ID"
  fi
elif [[ "$CLIENT_ID_EXPLICIT" -eq 0 ]]; then
  AUTO_CLIENT_ID="$(SERVER_URL="$SERVER_URL" python3 - <<'PY'
import json
import os
import urllib.request

base = str(os.environ.get("SERVER_URL") or "").strip().rstrip("/")
try:
    with urllib.request.urlopen(f"{base}/api/client-identities", timeout=8) as response:
        payload = json.load(response)
    print(str(payload.get("suggested_client_id") or "").strip())
except Exception:
    print("")
PY
)"
  if [[ -n "$AUTO_CLIENT_ID" ]]; then
    CLIENT_ID="$AUTO_CLIENT_ID"
    echo "Assigned next available server client ID: $CLIENT_ID"
  else
    echo "Server client-ID lookup unavailable; using fallback: $CLIENT_ID"
  fi
fi

cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

cd "$PROJECT_DIR"

export PYTHONUNBUFFERED=1
export MACHINE_DATA_DIR="$RUNTIME_DATA_DIR"
export MACHINE_SERVER_URL="$SERVER_URL"
export MACHINE_CLIENT_ID="$CLIENT_ID"
export MACHINE_SCANNER_COM_PORT="$SCANNER_PORT"
export MACHINE_SCANNER_MODE="$SCANNER_MODE"
export MACHINE_DEFAULT_GRAPHICS_MODE="$GRAPHICS_MODE"
export MACHINE_PACK_SCAN_INTERVAL_SECONDS="$PACK_SCAN_INTERVAL"

mkdir -p "\$HOME/.local/state/raspberry-machine-client" "$RUNTIME_DATA_DIR"
LOG_FILE="\$HOME/.local/state/raspberry-machine-client/client.log"
if [[ -f "\$LOG_FILE" ]] && [[ \$(wc -c <"\$LOG_FILE") -ge 10000000 ]]; then
  mv -f "\$LOG_FILE" "\${LOG_FILE}.1"
fi

if [[ -x "$PROJECT_DIR/dist/RaspberryMachineClient" ]]; then
  exec "$PROJECT_DIR/dist/RaspberryMachineClient" >>"\$LOG_FILE" 2>&1
fi

exec "$PROJECT_DIR/run_client_pi.sh" >>"\$LOG_FILE" 2>&1
EOF
chmod +x "$LAUNCHER"

ICON_PATH="$PROJECT_DIR/Images/machine.png"
if [[ ! -f "$ICON_PATH" ]]; then
  ICON_PATH="$PROJECT_DIR/Images/admin.ico"
fi

DESKTOP_FILE_CONTENT="[Desktop Entry]
Type=Application
Name=${APP_NAME}
Comment=Start the Raspberry Machine fullscreen client
Exec=${LAUNCHER}
Icon=${ICON_PATH}
Terminal=false
StartupNotify=false
Categories=Utility;
"

if [[ "$DO_DESKTOP" -eq 1 ]]; then
  DESKTOP_DIR="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
  mkdir -p "$DESKTOP_DIR"
  DESKTOP_FILE="$DESKTOP_DIR/${DESKTOP_ID}.desktop"
  printf "%s" "$DESKTOP_FILE_CONTENT" > "$DESKTOP_FILE"
  chmod +x "$DESKTOP_FILE"
fi

if [[ "$DO_AUTOSTART" -eq 1 ]]; then
  AUTOSTART_DIR="$HOME/.config/autostart"
  mkdir -p "$AUTOSTART_DIR"
  AUTOSTART_FILE="$AUTOSTART_DIR/${DESKTOP_ID}.desktop"
  printf "%s" "$DESKTOP_FILE_CONTENT" > "$AUTOSTART_FILE"
  chmod +x "$AUTOSTART_FILE"
fi

echo "Installed launcher: $LAUNCHER"
if [[ "$DO_DESKTOP" -eq 1 ]]; then
  echo "Installed desktop shortcut: ${DESKTOP_DIR:-$HOME/Desktop}/${DESKTOP_ID}.desktop"
fi
if [[ "$DO_AUTOSTART" -eq 1 ]]; then
  echo "Installed autostart entry: $HOME/.config/autostart/${DESKTOP_ID}.desktop"
fi
echo "Server URL: $SERVER_URL"
echo "Client ID: $CLIENT_ID"
echo "Scanner port: $SCANNER_PORT"
echo "PACK scan interval: $PACK_SCAN_INTERVAL seconds"
echo "Log file: $HOME/.local/state/raspberry-machine-client/client.log"
