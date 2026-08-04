# Installing and running HippoBridge

## Prerequisites

- Python 3.8+
- Access to a Hipocrate instance
- Hipocrate credentials
- `pynetdicom` + `pydicom` — optional, required only for the DICOM MWL server (see [WORKLIST.md](WORKLIST.md))

## Install

```bash
git clone https://github.com/cstroie/HipoBridge.git hippobridge
cd hippobridge
./install
```

`./install` creates a `.python` virtualenv and installs `requirements.txt` into it. Re-run it whenever `requirements.txt` changes — it's idempotent, reusing the existing venv if present. `./hippobridge` and the systemd/OpenRC service files all use `.python/bin/python3` automatically once it exists.

## Configuration

Server defaults live in `hippobridge.cfg`; override them in `local.cfg` (not tracked by git):

```ini
[server]
port = 8080

[hipocrate]
service_url = http://192.168.3.230/hipocrate
```

The server itself takes no fixed credentials — `@require_auth` reads Basic Auth off each incoming request and forwards it to Hipocrate per-request. `HYP_USER`/`HYP_PASS` are only needed by client/test scripts (`runtests.py`, `client.py`, `tests/*.py`) and as a fallback for the worklist SCP if `worklist.cfg`'s `[worklist] username`/`password` aren't set:

```bash
export HYP_USER=<username> HYP_PASS=<password>
```

## Running directly

```bash
python3 hippobridge.py
```

Listens on `http://0.0.0.0:44660` by default. CLI switches take precedence over config files:

```bash
python3 hippobridge.py --port 8080 --host 127.0.0.1
python3 hippobridge.py --service-url http://192.168.3.230/hipocrate
python3 hippobridge.py --log-level DEBUG    # DEBUG | INFO | WARNING | ERROR — console only
python3 hippobridge.py --log-file hippobridge.log  # also log to file, always at DEBUG regardless of --log-level
python3 hippobridge.py --no-disk-cache      # disable FilesystemCache even if configured
python3 hippobridge.py --no-worklist        # skip DICOM MWL SCP even if worklist.cfg exists
python3 hippobridge.py --pidfile hippobridge.pid  # write PID for ./hippobridge, remove on clean exit
```

`--log-level`/`LOG_LEVEL` only controls the console; a configured log file (`--log-file` or `[logging] file` in `local.cfg`) always captures everything at `DEBUG`, so the console can stay quiet while the file keeps full detail.

## Running via ./hippobridge

`SIGTERM`/`SIGINT` trigger a graceful shutdown (`runner.cleanup()` runs, in-flight requests finish) — no abrupt kill.

```bash
./hippobridge start [extra args]     # foreground; refuses if already running
./hippobridge stop
./hippobridge restart [extra args]   # stop, then start (foreground)
./hippobridge status
```

`start`/`restart` do **not** background the process themselves (no fork, no `nohup`) — they `exec` `hippobridge.py` in the foreground, same as `Type=simple` in the systemd unit below. Background it yourself if you need that:

```bash
./hippobridge start &
nohup ./hippobridge start &
```

The pidfile at `hippobridge.pid` (override with `PIDFILE=...`) distinguishes a running instance from a stale one. `stop`/`restart` wait up to `STOP_TIMEOUT` (default 15s) before escalating to `SIGKILL`. Extra args after the subcommand pass straight through to `hippobridge.py` (`./hippobridge start --port 8080`).

## System-wide install (systemd or OpenRC)

`./install systemd` and `./install openrc` (alias: `alpine`) automate the whole
system-wide setup on top of the regular venv install:

```bash
git clone https://github.com/cstroie/HipoBridge.git /opt/hippobridge
cd /opt/hippobridge
sudo ./install systemd     # or: sudo ./install openrc
```

These modes need root (creating a system user, chowning the checkout, and
writing into `/etc` all require it) and, for each:

- create a dedicated, unprivileged system account (`hippobridge`, no shell,
  home = the checkout directory) if it doesn't already exist
- `chown -R` the checkout to that account and `chmod 600` any `local.cfg`/
  `worklist.cfg`/`hippobridge.env` found (they hold credentials)
- create `log/` under the checkout, owned by that account — logs (both the
  app's own `--log-file` output and, for OpenRC, `supervise-daemon`'s
  captured stdout/stderr) stay there rather than under `/var/log`
- render and install the unit/init script:
  - systemd: `hippobridge.service` → `/etc/systemd/system/`, with its
    `/opt/hippobridge` paths rewritten to wherever the checkout actually is,
    then `systemctl daemon-reload`
  - OpenRC: `hippobridge.openrc` → `/etc/init.d/hippobridge`, plus
    `/etc/conf.d/hippobridge` with a `hippobridge_home` override if the
    checkout isn't at `/opt/hippobridge`; then `rc-update add hippobridge
    default`
- write `UNINSTALL.md` in the checkout (gitignored) with the exact commands
  to reverse everything the run just did

The install script does **not** enable or start the service itself — do that
last, once you've reviewed the installed unit file:

```bash
sudo systemctl enable --now hippobridge     # systemd
sudo rc-service hippobridge start           # OpenRC
```

`EnvironmentFile=hippobridge.env` in the systemd unit (commented out by
default) and `HYP_USER`/`HYP_PASS` exports in the OpenRC script are only
needed for the worklist SCP's fallback if `worklist.cfg`'s `[worklist]
username`/`password` aren't set — never put credentials directly in the
unit/init file itself. Neither deployment uses a custom fork-based daemon
mode: forking after the asyncio event loop starts is fragile, and
`Type=simple` (systemd) / `supervise-daemon` (OpenRC) already cover
backgrounding, restart-on-crash, and log capture.

Re-running `./install systemd`/`openrc` is safe — it skips user creation if
the account already exists and just re-renders the unit/init file and
`UNINSTALL.md`.

## Running tests

```bash
python3 runtests.py               # all groups
python3 runtests.py extractors    # offline
python3 runtests.py markdown      # offline
python3 runtests.py hippodata     # offline
python3 runtests.py worklist      # offline
python3 runtests.py llm           # offline
```

Groups requiring a live server: `root`, `auth`, `patients`, `analyses`, `reports`, `checkout`, `checkin`, `checkup`, `cnp`.
