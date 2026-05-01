# Raspberry Pi Client Test Guide

This guide is for building and running the `client.py` PyQt fullscreen machine client on a Raspberry Pi.

## 1. Recommended Raspberry Pi

- Raspberry Pi 4 or Raspberry Pi 5
- 64-bit Raspberry Pi OS Bookworm
- Python 3.11 or newer preferred

## 2. Copy the project to the Pi

Example:

```bash
scp -r Raspberry_Machine pi@<pi-ip>:/home/pi/
```

Or copy it with a USB drive / shared folder.

## 3. Install system packages

Run on the Raspberry Pi:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo apt install -y libopenblas-dev libjpeg-dev zlib1g-dev libpng-dev libfreetype6-dev
sudo apt install -y libxcb-cursor0 libxkbcommon-x11-0 libegl1 libopengl0
```

If you want to run the GUI client on the Pi screen:

```bash
sudo apt install -y python3-pyqt6
```

Note:

- `PyQt6` from `pip` can be unreliable on Raspberry Pi depending on OS/image.
- `python3-pyqt6` from `apt` is usually the safer option for Pi.

## 4. Create a virtual environment

```bash
cd ~/Raspberry_Machine
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

## 5. Install Python packages

Install the client dependencies:

```bash
pip install requests pyserial PyMySQL cryptography
```

If you also want to reuse the existing repo requirements, you can try:

```bash
pip install -r requirements.txt
```

If `pip install -r requirements.txt` fails because of `PyQt6`, keep the Python installs above and install GUI support from `apt`:

```bash
sudo apt install -y python3-pyqt6
```

## 6. Set the client target server

This client still needs to connect to your FastAPI server somewhere on the network.

Example:

```bash
export MACHINE_SERVER_URL=http://192.168.1.213:8000
```

Important:

- the launcher now overrides saved client settings with these environment values
- this avoids Raspberry Pi using old Windows settings such as `Com2`

## 7. Build the client app on the Pi

The repo now includes a PyInstaller build script:

```bash
chmod +x build_client_pi.sh
./build_client_pi.sh
```

If the build succeeds, the packaged app will be created at:

```text
dist/RaspberryMachineClient
```

Run it with:

```bash
./dist/RaspberryMachineClient
```

## 8. Start the GUI client on the Pi from source

Only do this if the Pi has a desktop session and display attached.

```bash
chmod +x run_client_pi.sh
./run_client_pi.sh
```

Default launcher values:

- `MACHINE_SERVER_URL=http://127.0.0.1:8000`
- `MACHINE_SCANNER_MODE=auto`
- `MACHINE_SCANNER_COM_PORT=/dev/ttyACM0`
- `MACHINE_DEFAULT_GRAPHICS_MODE=faster`

If your scanner appears on a different port, check with:

```bash
ls /dev/ttyACM*
ls /dev/ttyUSB*
```

Then set the port before launching:

```bash
export MACHINE_SCANNER_COM_PORT=/dev/ttyUSB0
./run_client_pi.sh
```

## 9. Current client behavior that matters on Pi

- `client.py` runs fullscreen by default.
- `client.py` already defaults to Linux serial paths like `/dev/ttyACM0`.
- the client reads and writes files relative to the project folder, so keep `Database`, `Images`, `Animations`, and `PDR_Icon` together
- MySQL is optional. If MySQL is not available, the client still uses local JSON files for many functions.

## 10. Scanner setup

Check which serial device the scanner uses:

```bash
ls /dev/ttyACM*
ls /dev/ttyUSB*
```

Set it before launch if needed:

```bash
export MACHINE_SCANNER_COM_PORT=/dev/ttyUSB0
./run_client_pi.sh
```

If permissions block scanner access:

```bash
sudo usermod -aG dialout $USER
```

Then log out and back in.

## 11. MySQL optional setup

If you want SQL on the Pi, edit:

- `Database/sql_config.json`

Default database name in code:

- `rpimachineapp_db`

If you do not want SQL yet, set:

```json
{
  "enabled": false
}
```

## 12. First client test sequence

1. Log into the Raspberry Pi desktop
2. Set `MACHINE_SERVER_URL` to your server address
3. Set `MACHINE_SCANNER_COM_PORT` if the scanner is not on `/dev/ttyACM0`
4. Build with `./build_client_pi.sh`
5. Run `./dist/RaspberryMachineClient` or `./run_client_pi.sh`
6. Confirm the fullscreen UI opens
7. Confirm it can reach the server and receive profile/role data

## 13. Troubleshooting

If the GUI client does not open:

- Make sure the Pi is in desktop mode, not headless-only
- Check that `python3-pyqt6` is installed
- Try `echo $DISPLAY`

If the packaged build fails:

- make sure `pyinstaller` installed successfully in the active environment
- make sure `PyQt6` is available to that same Python interpreter
- on Raspberry Pi prefer `sudo apt install -y python3-pyqt6`

If the scanner does not work:

- Confirm the serial device path
- confirm the saved Windows `Com2` setting is being overridden by `MACHINE_SCANNER_COM_PORT`

If the client cannot reach the server:

- verify `MACHINE_SERVER_URL`
- open the server URL in the Pi browser
- make sure the server host allows connections on port `8000`

## 14. Next step after basic test

Once the client works on the Pi, the next sensible step is:

- add desktop autostart for `client.py`
- tune graphics mode for the Pi screen
- create a client-only Pi requirements file
