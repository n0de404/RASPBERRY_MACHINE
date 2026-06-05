#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="Raspberry Machine Client"
DESKTOP_ID="RaspberryMachineClient"
SERVER_URL="${MACHINE_SERVER_URL:-http://127.0.0.1:8000}"
SCANNER_PORT="${MACHINE_SCANNER_COM_PORT:-/dev/ttyACM0}"
SCANNER_MODE="${MACHINE_SCANNER_MODE:-auto}"
GRAPHICS_MODE="${MACHINE_DEFAULT_GRAPHICS_MODE:-faster_quality}"
DO_BUILD=0
DO_AUTOSTART=1
DO_DESKTOP=1

usage() {
  cat <<EOF
Usage: ./install_pi_client_autostart.sh [options]

Options:
  --server-url URL       Server URL for the client. Default: ${SERVER_URL}
  --scanner-port PATH    Scanner serial port. Default: ${SCANNER_PORT}
  --scanner-mode MODE    Scanner mode. Default: ${SCANNER_MODE}
  --graphics-mode MODE   Graphics mode. Default: ${GRAPHICS_MODE}
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

mkdir -p "$HOME/.local/bin" "$HOME/.local/state/raspberry-machine-client"

LAUNCHER="$HOME/.local/bin/raspberry-machine-client"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

cd "$PROJECT_DIR"

export PYTHONUNBUFFERED=1
export MACHINE_SERVER_URL="$SERVER_URL"
export MACHINE_SCANNER_COM_PORT="$SCANNER_PORT"
export MACHINE_SCANNER_MODE="$SCANNER_MODE"
export MACHINE_DEFAULT_GRAPHICS_MODE="$GRAPHICS_MODE"

mkdir -p "\$HOME/.local/state/raspberry-machine-client"
LOG_FILE="\$HOME/.local/state/raspberry-machine-client/client.log"

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
echo "Scanner port: $SCANNER_PORT"
echo "Log file: $HOME/.local/state/raspberry-machine-client/client.log"
