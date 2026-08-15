# Raspberry Pi Client

This folder is the complete Raspberry Pi client package. It does not require
the server source or the server's `Database` directory.

## First installation

```bash
git clone https://github.com/n0de404/RASPBERRY_MACHINE.git Raspberry_Machine
cd Raspberry_Machine/client
chmod +x update_pi_client.sh
./update_pi_client.sh \
  --server-url http://SERVER-IP:8000 \
  --scanner-port /dev/ttyACM0
```

Omit `--client-id` for a new Pi so the installer can request the next available
identity from the server. Use `--client-id RPI-CLIENT-07` only when deliberately
restoring that physical client.

The installer creates the environment, installs dependencies, builds
`dist/RaspberryMachineClient`, installs desktop/autostart launchers, and starts
the client.

## Update an installed Pi

```bash
cd "$HOME/Raspberry_Machine/client"
./update_pi_client.sh \
  --pull \
  --server-url http://SERVER-IP:8000 \
  --scanner-port /dev/ttyACM0 \
  --skip-system-setup
```

Git updates code and assets only. Machine data survives in:

```text
~/.local/share/raspberry-machine-client/
```

This directory owns active-session recovery, locally pending finished jobs and
shifts, the compact offline event queue, same-job shift carryover, settings,
and server-refreshed caches.
Successful server acknowledgements remove the matching finished record locally.

`shift_carryover.json` contains only remaining part balances, eligible BUTAL,
and temporary last-weight information. It is keyed by machine and job: another
job cannot consume it, and finishing the matching job clears it.

Scanning a machine automatically restores its active session. A server-only or
local-only snapshot is used directly. Matching server/local job snapshots keep
the highest cumulative counters and combine unique scans; different jobs are
never merged and the later saved session is selected.

`job_details_cache.json` stores at most 100 recent server job responses for
temporary offline fallback. Online scans still ask the server first, successful
responses refresh the cache, and entries expire according to the configured
job-cache TTL (seven days by default).

## Useful commands

Run from source:

```bash
./run_client_pi.sh
```

Build without launching:

```bash
./update_pi_client.sh --no-start
```

Client log:

```text
~/.local/state/raspberry-machine-client/client.log
```
