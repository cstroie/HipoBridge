#!/usr/bin/env bash
# Restart the HippoBridge server: gracefully stop the process tracked by the
# pidfile (SIGTERM, so hippobridge.py's shutdown handler runs runner.cleanup()
# and in-flight requests get a chance to finish), then relaunch it.
#
# The server itself takes no fixed credentials — @require_auth reads Basic
# Auth from each incoming request and forwards it to Hipocrate per-request.
# HYP_USER/HYP_PASS are only needed by client/test scripts and by the
# worklist SCP's fallback when worklist.cfg has no [worklist] username/
# password set — irrelevant here, so this script doesn't require them.
#
# Usage:
#   ./restart.sh                  # uses ./hippobridge.pid
#   PIDFILE=/run/hippobridge.pid ./restart.sh
#   ./restart.sh --port 8080      # extra args are passed through to hippobridge.py
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PIDFILE="${PIDFILE:-hippobridge.pid}"
STOP_TIMEOUT="${STOP_TIMEOUT:-15}"

if [[ -f "$PIDFILE" ]]; then
    old_pid="$(cat "$PIDFILE")"
    if kill -0 "$old_pid" 2>/dev/null; then
        echo "Stopping HippoBridge (pid $old_pid)..."
        kill -TERM "$old_pid"
        waited=0
        while kill -0 "$old_pid" 2>/dev/null; do
            if (( waited >= STOP_TIMEOUT )); then
                echo "warning: pid $old_pid did not exit after ${STOP_TIMEOUT}s, sending SIGKILL" >&2
                kill -KILL "$old_pid" 2>/dev/null || true
                break
            fi
            sleep 1
            waited=$((waited + 1))
        done
    else
        echo "Stale pidfile ($old_pid not running), ignoring"
    fi
    rm -f "$PIDFILE"
else
    echo "No pidfile at $PIDFILE — starting fresh (not stopping anything)"
fi

echo "Starting HippoBridge..."
nohup python3 hippobridge.py --pidfile "$PIDFILE" "$@" >> hippobridge.out 2>&1 &
disown
sleep 1

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "HippoBridge restarted (pid $(cat "$PIDFILE"))"
else
    echo "error: HippoBridge did not start — check hippobridge.out / hippobridge.log" >&2
    exit 1
fi
