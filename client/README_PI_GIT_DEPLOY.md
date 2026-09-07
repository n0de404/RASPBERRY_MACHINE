# Raspberry Pi Git Deployment

The Git checkout contains client code, build scripts, and assets. Each
Raspberry Pi stores its own sessions, finished shifts, event
queue, settings, and server-refreshed caches outside Git at:

```text
/home/<user>/.local/share/raspberry-machine-client
```

Git updates never overwrite that directory.

## First installation

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

The installer installs dependencies, builds the ARM Linux executable, installs
desktop/autostart launchers, and starts `dist/RaspberryMachineClient`.
Sparse checkout keeps server source, server logs, and development-only files
out of the Pi working directory. Normal `git pull` updates the selected client
files without requiring SCP.

The client ID is intentionally omitted so a genuinely new Raspberry Pi asks
the server for the next available `RPI-CLIENT-##` identity automatically.

## Publish a patch

On the development computer, commit only source, scripts, assets, and safe
seeds. Never commit `Database`, logs, build output, or credentials.

```bash
git add client server .gitignore README.md STORAGE_LAYOUT.md
git commit -m "Describe the client update"
git push origin main
```

## Install a patch on a Pi

```bash
cd "$HOME/Raspberry_Machine/client"
./update_pi_client.sh \
  --pull \
  --server-url http://SERVER_IP:8000 \
  --scanner-port /dev/ttyACM0 \
  --skip-system-setup
```

The update stops the client, performs a fast-forward-only pull, validates the
Python source, rebuilds the executable locally for the Pi, refreshes its
launcher, and starts it. Existing runtime data remains untouched.

Use `--skip-system-setup` only after the first successful installation has
created `client/.venv`. If that directory is missing, omit the flag so the
installer can install `python3-venv` and create the isolated environment.

## Product and operator caches

The client creates product, profile, operator, and daily-role cache files only
when it first receives that data from the server. No placeholder database
files are shipped in Git.

## Logs and troubleshooting

```text
~/.local/state/raspberry-machine-client/client.log
```

```bash
tail -f "$HOME/.local/state/raspberry-machine-client/client.log"
```
