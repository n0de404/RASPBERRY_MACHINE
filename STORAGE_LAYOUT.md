# Client and Server Layout

## Client deployment

Everything required to build and run a Raspberry Pi client is under:

```text
client/
  client.py
  mappings.py
  ui_theme.py
  requirements.txt
  client_pi.spec
  build_client_pi.sh
  run_client_pi.sh
  update_pi_client.sh
  install_pi_client_autostart.sh
  Animations/
  Images/
  PDR_Icon/
```

Client runtime state is not stored in the checkout. Each Pi uses:

```text
~/.local/share/raspberry-machine-client/
```

The small `shift_carryover.json` runtime file is separate from completed-shift
history. It applies only to the same machine/job and is cleared by final job
completion.

## Server deployment

Everything required to install and launch the server is under:

```text
server/
  server.py
  requirements.txt
  run_server_pi.sh
  Database/                 # runtime only; ignored by Git
```

MySQL is authoritative for active sessions, processed event IDs, planning,
finished jobs and shifts, archives, profiles, roles, settings, and machine
status. `server/Database/` retains only machine-local configuration,
regenerable caches, and logs such as `sql_config.json`,
`product_api_config.json`, `product_catalog_cache.json`,
`low_stock_recommendations.json`, and `server_app_logs.jsonl`.

## Not deployed

`Archive_NotRuntime/` contains old source copies, recovery exports, obsolete SCP
watchers, diagnostic material, and manual maintenance tools. It is ignored by
Git and is not imported, built, or launched by either application.
