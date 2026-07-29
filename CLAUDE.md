# CLAUDE.md

## Response style

Be concise. Never waste tokens — no restating the task, no narrating obvious steps, no trailing summaries unless asked. Answer directly.

## Server restarts

**Never restart the server yourself.** Tell the user when a restart is needed and wait for them to do it.

## Running the server

```bash
export HYP_USER=<username> HYP_PASS=<password>
python3 hippobridge.py
```

Test credentials are in `worklist.cfg` (`username` / `password` fields under `[worklist]`). Server runs on `http://127.0.0.1:44660`.

Default: `http://0.0.0.0:44660`. Override with `local.cfg` (not tracked by git):

```ini
[server]
port = 8080
[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

CLI: `--port`, `--host`, `--service-url`, `--log-level DEBUG|INFO|WARNING|ERROR`, `--log-file PATH`, `--no-disk-cache`, `--no-worklist`.

## Running tests

```bash
python3 runtests.py               # all tests
python3 runtests.py extractors    # no server needed (also: markdown, hippodata, worklist, llm)
```

## Architecture and gotchas

See `docs/ARCHITECTURE.md` for the routing table, concurrency/caching model, per-module gotchas, scraper-specific notes, frontend rules, and dated design decisions.
