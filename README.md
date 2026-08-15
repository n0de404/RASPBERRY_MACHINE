# Raspberry Machine

The repository is separated by deployment role:

- `client/` — Raspberry Pi UI, assets, build files, and Pi installers.
- `server/` — FastAPI server and server-only dependencies.
- `Archive_NotRuntime/` — legacy, diagnostic, and recovery material; do not deploy it.

Runtime data is excluded from Git. The server uses `server/Database/`; clients
use `~/.local/share/raspberry-machine-client`.

New Raspberry Pi installation:

```bash
git clone https://github.com/n0de404/RASPBERRY_MACHINE.git Raspberry_Machine
cd Raspberry_Machine/client
chmod +x update_pi_client.sh
./update_pi_client.sh --server-url http://SERVER-IP:8000
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
