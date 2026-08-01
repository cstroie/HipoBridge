#!/usr/bin/env python3
"""Small ops CLI for LM Studio's native REST API (`/api/v1/...`), distinct
from the OpenAI-compatible `/v1/...` surface used by the app itself.

LM Studio only ever runs one or two models resident in VRAM at a time;
loading a new one without freeing an old one can OOM or contend with
whatever's already resident (e.g. medgemma-4b-it, kept loaded for
xrayvision). This tool lists what's currently loaded and unloads instances
by id, so a benchmark run can free VRAM before swapping in the next
candidate.

Reuses the app's own provider config (llm.config) to find the server host,
so it always points at whatever `local.cfg`/`llm.cfg` currently configure.

Usage:
    python3 lmstudio_ctl.py list
    python3 lmstudio_ctl.py unload medgemma-4b-it
    python3 lmstudio_ctl.py unload --all --keep medgemma-4b-it
"""
import argparse
import sys

import requests

from llm.config import init_llm, select_provider


def _api_base() -> tuple[str, dict]:
    """Resolve LM Studio's REST API root (`/api/v1`) and auth headers from
    the active provider's OpenAI-compat `url` (which ends in `/v1`)."""
    url, key, _ = select_provider(init_llm())
    host = url[:-len("/v1")] if url.endswith("/v1") else url
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return f"{host}/api/v1", headers


def list_models(base: str, headers: dict) -> list[dict]:
    resp = requests.get(f"{base}/models", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["models"]


def loaded_instances(models: list[dict]) -> list[dict]:
    """Flatten each model's `loaded_instances` into (key, instance) pairs."""
    out = []
    for m in models:
        for inst in m.get("loaded_instances", []):
            out.append({"key": m["key"], "instance_id": inst["id"],
                        "params": m.get("params_string", "?"),
                        "ttl": inst.get("config", {}).get("remaining_ttl_seconds")})
    return out


def cmd_list(args: argparse.Namespace) -> None:
    base, headers = _api_base()
    models = list_models(base, headers)
    loaded = loaded_instances(models)
    print(f"{len(models)} known models, {len(loaded)} loaded:\n")
    for inst in loaded:
        ttl = f"{inst['ttl']}s" if inst["ttl"] is not None else "?"
        print(f"  [loaded] {inst['instance_id']:<45} ({inst['key']}, {inst['params']}, ttl={ttl})")
    if not loaded:
        print("  (none)")


def cmd_unload(args: argparse.Namespace) -> None:
    base, headers = _api_base()

    if args.all:
        models = list_models(base, headers)
        targets = [inst["instance_id"] for inst in loaded_instances(models)
                   if inst["instance_id"] not in args.keep]
        if not targets:
            print("Nothing to unload.")
            return
    else:
        if not args.instance_id:
            sys.exit("unload: provide instance_id(s) or use --all")
        targets = [i for i in args.instance_id if i not in args.keep]

    for instance_id in targets:
        resp = requests.post(f"{base}/models/unload", headers=headers,
                              json={"instance_id": instance_id}, timeout=30)
        resp.raise_for_status()
        print(f"unloaded: {instance_id}")

    kept = set(args.instance_id or []) & set(args.keep) if not args.all else \
        {i["instance_id"] for i in loaded_instances(list_models(base, headers))} & set(args.keep)
    for k in sorted(kept):
        print(f"kept (excluded): {k}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List known models and which instances are currently loaded")

    p_unload = sub.add_parser("unload", help="Unload one or more loaded model instances")
    p_unload.add_argument("instance_id", nargs="*", help="Instance id(s) to unload (as shown by `list`)")
    p_unload.add_argument("--all", action="store_true", help="Unload every currently loaded instance")
    p_unload.add_argument("--keep", action="append", default=[], metavar="INSTANCE_ID",
                           help="Instance id to never unload (repeatable)")

    args = parser.parse_args()
    {"list": cmd_list, "unload": cmd_unload}[args.command](args)


if __name__ == "__main__":
    main()
