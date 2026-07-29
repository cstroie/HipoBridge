# CLAUDE.md

## Response style

Be concise. Never waste tokens — no restating the task, no narrating obvious steps, no trailing summaries unless asked. Answer directly.

## Server restarts

You may restart the server yourself, at your own judgment, using `./restart.sh` (see "Restarting the server" below) — do not `kill`/`pkill` the process directly or restart it any other way. Mention that you're doing it and why.

## Running the server

```bash
python3 hippobridge.py
```

The server itself takes no fixed credentials — `@require_auth` reads Basic Auth from each incoming request and forwards it to Hipocrate per-request. `HYP_USER`/`HYP_PASS` are only needed by client/test scripts (`runtests.py`, `client.py`, `tests/*.py`) calling the server, and as a fallback for the worklist SCP if `worklist.cfg`'s `[worklist] username`/`password` aren't set. Test credentials are in `worklist.cfg`. Server runs on `http://127.0.0.1:44660`.

Default: `http://0.0.0.0:44660`. Override with `local.cfg` (not tracked by git):

```ini
[server]
port = 8080
[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

CLI: `--port`, `--host`, `--service-url`, `--log-level DEBUG|INFO|WARNING|ERROR`, `--log-file PATH`, `--no-disk-cache`, `--no-worklist`, `--pidfile PATH`.

## Restarting the server

`--pidfile PATH` writes the PID on startup and removes it on clean shutdown; `SIGTERM`/`SIGINT` both resolve an asyncio event so `runner.cleanup()` runs (no abrupt kill). `./restart.sh` stops the process tracked by `hippobridge.pid`, waits up to `STOP_TIMEOUT` (default 15s, then SIGKILLs), and relaunches — extra args pass through to `hippobridge.py`. This exists so *the user* can restart quickly; it does not change the "never restart the server yourself" rule above.

For a background/boot-time service, `hippobridge.service` is a systemd unit template — copy it to `/etc/systemd/system/`, adjust `User=`/paths. `EnvironmentFile=hippobridge.env` is only needed if you want the worklist SCP's `HYP_USER`/`HYP_PASS` fallback instead of setting `[worklist] username`/`password` in `worklist.cfg` directly (create it, `chmod 600`, not tracked by git — never put credentials directly in the unit file). No custom fork-based daemon mode was added: forking after the asyncio event loop starts is fragile, and systemd's `Type=simple` + `Restart=on-failure` already covers backgrounding, restart-on-crash, and log capture without hand-rolled process-management code.

## Running tests

```bash
python3 runtests.py               # all tests
python3 runtests.py extractors    # no server needed (also: markdown, hippodata, worklist, llm)
```

## Architecture and gotchas

See `docs/ARCHITECTURE.md` for the routing table, concurrency/caching model, per-module gotchas, scraper-specific notes, frontend rules, and dated design decisions.
