# Raspberry Machine

The repository is separated by deployment role:

- `client/` — Raspberry Pi UI, assets, build files, and Pi installers.
- `server/` — FastAPI server and server-only dependencies.
- `Archive_NotRuntime/` — legacy, diagnostic, and recovery material; do not deploy it.

Runtime data is excluded from Git. The server uses `server/Database/`; clients
use `~/.local/share/raspberry-machine-client`.

New Raspberry Pi installation:

```bash
cd "$HOME"

git clone --filter=blob:none --no-checkout \
  https://github.com/n0de404/RASPBERRY_MACHINE.git Raspberry_Machine

cd Raspberry_Machine
git sparse-checkout init --no-cone
git sparse-checkout set /client /.gitignore /README.md
git checkout main

cd client
chmod +x *.sh
./update_pi_client.sh \
  --server-url http://192.168.10.49:8000 \
  --scanner-port /dev/ttyACM0
```

Server installation:

```bash
cd Raspberry_Machine/server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run_server_pi.sh
./run_server_pi.sh
```
