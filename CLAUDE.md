# CLAUDE.md

## Response style

Be concise. Never waste tokens — no restating the task, no narrating obvious steps, no trailing summaries unless asked. Answer directly.

## Server restarts

You may restart the server yourself, at your own judgment, using `./hippobridge restart` (see "Restarting the server" below) — do not `kill`/`pkill` the process directly or restart it any other way. Mention that you're doing it and why.

## Setup

`./install` creates the `.python` venv and installs `requirements.txt` into it — run it once after cloning, and again whenever `requirements.txt` changes. `./hippobridge` and `hippobridge.service`/`hippobridge.openrc` all use `.python/bin/python3` when it exists (falling back to plain `python3` on PATH in `./hippobridge` if `.python` hasn't been created yet).

## Running the server

```bash
python3 hippobridge.py
```

The server itself takes no fixed credentials — `@require_auth` reads Basic Auth from each incoming request and forwards it to Hipocrate per-request. `HYP_USER`/`HYP_PASS` are only needed by client/test scripts (`runtests.py`, `client.py`, `tests/*.py`) calling the server, and as a fallback for the worklist SCP if `worklist.cfg`'s `[worklist] username`/`password` aren't set. Test credentials are in `worklist.cfg`. Server runs on `http://127.0.0.1:44660`.

Default: `http://0.0.0.0:44660`. Configure via `hippobridge.cfg` (gitignored — copy from `examples/hippobridge.cfg`, which documents every option):

```ini
[server]
port = 8080
[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

Every subsystem follows the same pattern: `hippobridge.cfg` (server/hipocrate/cache/logging/radiology/pacs), `llm.cfg` (AI provider config), `regions.cfg` (imaging region keyword rules), `worklist.cfg` (DICOM MWL) are all gitignored — copy the matching `examples/*.cfg` and edit it. Unlike `worklist.cfg`, the PACS study-check subsystem (`pacs.py`) has no config file of its own — its `[pacs]` section lives directly in `hippobridge.cfg`, since there's exactly one PACS to talk to.

CLI: `--port`, `--host`, `--service-url`, `--log-level DEBUG|INFO|WARNING|ERROR`, `--log-file PATH`, `--no-disk-cache`, `--no-worklist`, `--no-pacs`, `--no-search-backfill`, `--pidfile PATH`.

`--log-level`/`LOG_LEVEL` only sets the console handler's level (default INFO). A configured log file (`--log-file` or `[logging] file` in `hippobridge.cfg`) always logs at `DEBUG` regardless — the root logger itself is always `DEBUG` internally so file logging never misses anything even when the console is quieter.

## Restarting the server

`--pidfile PATH` writes the PID on startup and removes it on clean shutdown; `SIGTERM`/`SIGINT` both resolve an asyncio event so `runner.cleanup()` runs (no abrupt kill). `./hippobridge {start|stop|restart|status}` uses the pidfile at `hippobridge.pid` (override with `PIDFILE=...`) to tell a running instance from a stale one. `start`/`restart` do **not** background the process themselves (no fork, no `nohup`) — they `exec` `hippobridge.py` in the foreground, so background it yourself if you need that (e.g. `./hippobridge restart &`). `stop`/`restart` wait up to `STOP_TIMEOUT` (default 15s, then SIGKILL). Extra args pass through to `hippobridge.py` (`./hippobridge start --port 8080`). This exists so *the user* can restart quickly; it does not change the "never restart the server yourself" rule above.

For a background/boot-time service, `hippobridge.service` is a systemd unit template — copy it to `/etc/systemd/system/`, adjust `User=`/paths. `EnvironmentFile=hippobridge.env` is only needed if you want the worklist SCP's `HYP_USER`/`HYP_PASS` fallback instead of setting `[worklist] username`/`password` in `worklist.cfg` directly (create it, `chmod 600`, not tracked by git — never put credentials directly in the unit file). No custom fork-based daemon mode was added: forking after the asyncio event loop starts is fragile, and systemd's `Type=simple` + `Restart=on-failure` already covers backgrounding, restart-on-crash, and log capture without hand-rolled process-management code.

## Running tests

```bash
python3 runtests.py               # all tests
python3 runtests.py extractors    # no server needed (also: markdown, hippodata, worklist, pacs, llm)
```

## Architecture and gotchas

See `docs/ARCHITECTURE.md` for the routing table, concurrency/caching model, per-module gotchas, scraper-specific notes, frontend rules, and dated design decisions.

## Verifying frontend changes

Playwright burns a lot of tokens (screenshots, page dumps). Never launch it implicitly to verify a frontend change — ask the user first, every time. Prefer cheaper verification first: grep-based before/after checks (class/id occurrence counts, no orphaned old names), CSS brace balance, `node --check` on JS. Reach for Playwright only when the user asks for it or explicitly agrees when you ask.
