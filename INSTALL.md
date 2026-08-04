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

## Running as a systemd service

`hippobridge.service` is a unit template using a dedicated system account and `/opt/hippobridge` (standard FHS convention, no personal paths baked in):

```bash
useradd --system --home-dir /opt/hippobridge --shell /usr/sbin/nologin hippobridge
git clone https://github.com/cstroie/HipoBridge.git /opt/hippobridge
chown -R hippobridge:hippobridge /opt/hippobridge
sudo -u hippobridge /opt/hippobridge/install   # builds the .python venv
cp hippobridge.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hippobridge
```

`EnvironmentFile=hippobridge.env` (commented out by default) is only needed if you want the worklist SCP's `HYP_USER`/`HYP_PASS` fallback instead of setting `[worklist] username`/`password` in `worklist.cfg` directly — create it, `chmod 600`, not tracked by git, never put credentials directly in the unit file. There's no custom fork-based daemon mode: forking after the asyncio event loop starts is fragile, and systemd's `Type=simple` + `Restart=on-failure` already covers backgrounding, restart-on-crash, and log capture (`journalctl -u hippobridge`).

## Running under OpenRC (Alpine Linux)

`hippobridge.openrc` mirrors the systemd unit — same dedicated account, same `/opt/hippobridge` layout — using `supervise-daemon` for the non-forking foreground process:

```bash
adduser -S -D -H -h /opt/hippobridge -s /sbin/nologin hippobridge
git clone https://github.com/cstroie/HipoBridge.git /opt/hippobridge
chown -R hippobridge:hippobridge /opt/hippobridge
su -s /bin/sh hippobridge -c /opt/hippobridge/install   # builds the .python venv
cp hippobridge.openrc /etc/init.d/hippobridge
chmod +x /etc/init.d/hippobridge
rc-update add hippobridge default
rc-service hippobridge start
```

Optional overrides (e.g. `HYP_USER`/`HYP_PASS`, a different install path) go in `/etc/conf.d/hippobridge`, auto-sourced by `openrc-run`.

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
