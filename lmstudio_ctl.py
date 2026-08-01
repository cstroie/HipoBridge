#!/usr/bin/env python3
"""Small ops CLI for LM Studio's native REST API (`/api/v1/...`), distinct
from the OpenAI-compatible `/v1/...` surface used by the app itself.

LM Studio only ever runs one or two models resident in VRAM at a time;
loading a new one without freeing an old one can OOM or contend with
whatever's already resident (e.g. medgemma-4b-it, kept loaded for
xrayvision). This tool lists what's loaded, unloads instances by id (so a
benchmark run can free VRAM before swapping in the next candidate), loads a
model with explicit config, and downloads new models from the catalog/HF
with progress polling.

Reuses the app's own provider config (llm.config) to find the server host,
so it always points at whatever `local.cfg`/`llm.cfg` currently configure.

Usage:
    python3 lmstudio_ctl.py list
    python3 lmstudio_ctl.py unload medgemma-4b-it
    python3 lmstudio_ctl.py unload --all --keep medgemma-4b-it
    python3 lmstudio_ctl.py load qwen/qwen3-4b --context-length 8192
    python3 lmstudio_ctl.py swap qwen/qwen3-4b --keep medgemma-4b-it
    python3 lmstudio_ctl.py download google/gemma-3-4b
    python3 lmstudio_ctl.py download https://huggingface.co/unsloth/Phi-4-mini-instruct-GGUF \\
        --quantization Q4_K_M --wait
    python3 lmstudio_ctl.py download-status job_493c7c9ded
"""
import argparse
import json
import sys
import time

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
    if args.json:
        print(json.dumps({"models": models, "loaded": loaded}, indent=2))
        return
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


def cmd_load(args: argparse.Namespace) -> None:
    base, headers = _api_base()
    body = {"model": args.model, "echo_load_config": True}
    if args.context_length is not None:
        body["context_length"] = args.context_length
    if args.eval_batch_size is not None:
        body["eval_batch_size"] = args.eval_batch_size
    if args.flash_attention is not None:
        body["flash_attention"] = args.flash_attention
    if args.num_experts is not None:
        body["num_experts"] = args.num_experts

    resp = requests.post(f"{base}/models/load", headers=headers, json=body, timeout=args.timeout)
    resp.raise_for_status()
    data = resp.json()
    print(f"loaded: {data['instance_id']} in {data['load_time_seconds']:.2f}s")
    if "load_config" in data:
        print(f"  config: {data['load_config']}")


def _start_download(base: str, headers: dict, model: str, quantization: str | None) -> dict:
    body = {"model": model}
    if quantization:
        body["quantization"] = quantization
    resp = requests.post(f"{base}/models/download", headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def cmd_download(args: argparse.Namespace) -> None:
    base, headers = _api_base()
    data = _start_download(base, headers, args.model, args.quantization)

    if data["status"] == "already_downloaded":
        print(f"already downloaded: {args.model}")
        return

    job_id = data["job_id"]
    print(f"download started: job_id={job_id} total_size={data.get('total_size_bytes', '?')} bytes")
    if args.wait:
        _wait_for_download(base, headers, job_id, model=args.model, quantization=args.quantization,
                            max_retries=args.retries)


def _wait_for_download(base: str, headers: dict, job_id: str, poll_interval: float = 5.0,
                        model: str | None = None, quantization: str | None = None,
                        max_retries: int = 5) -> None:
    """Poll until the job reaches a terminal state. LM Studio's download link to HF
    is flaky on this network and jobs routinely die mid-transfer with status
    "failed" well before completion; when `model` is given, transparently
    restart (same job_id, server resumes from the partial bytes) up to
    `max_retries` times rather than surfacing a spurious failure."""
    retries = 0
    while True:
        status = _get_download_status(base, headers, job_id)
        done = status["downloaded_bytes"]
        total = status.get("total_size_bytes")
        pct = f"{100 * done / total:.1f}%" if total else "?"
        rate = status.get("bytes_per_second")
        rate_s = f", {rate / 1e6:.1f} MB/s" if rate else ""
        print(f"  {status['status']}: {done}/{total or '?'} bytes ({pct}{rate_s})")

        if status["status"] == "completed":
            break
        if status["status"] == "failed":
            if model and retries < max_retries:
                retries += 1
                print(f"  retrying ({retries}/{max_retries})...")
                time.sleep(5)
                data = _start_download(base, headers, model, quantization)
                job_id = data.get("job_id", job_id)
                continue
            break
        if status["status"] == "paused":
            break
        time.sleep(poll_interval)


def _get_download_status(base: str, headers: dict, job_id: str) -> dict:
    resp = requests.get(f"{base}/models/download/status/{job_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def cmd_download_status(args: argparse.Namespace) -> None:
    base, headers = _api_base()
    if args.wait:
        _wait_for_download(base, headers, args.job_id)
    elif args.json:
        print(json.dumps(_get_download_status(base, headers, args.job_id), indent=2))
    else:
        print(_get_download_status(base, headers, args.job_id))


def cmd_swap(args: argparse.Namespace) -> None:
    """Unload everything except `--keep`, then load `model`. The two-step
    dance every benchmark round does before testing a new candidate."""
    base, headers = _api_base()
    models = list_models(base, headers)
    targets = [inst["instance_id"] for inst in loaded_instances(models)
               if inst["instance_id"] not in args.keep and inst["instance_id"] != args.model]
    for instance_id in targets:
        resp = requests.post(f"{base}/models/unload", headers=headers,
                              json={"instance_id": instance_id}, timeout=30)
        resp.raise_for_status()
        print(f"unloaded: {instance_id}")

    body = {"model": args.model, "echo_load_config": True}
    if args.context_length is not None:
        body["context_length"] = args.context_length
    resp = requests.post(f"{base}/models/load", headers=headers, json=body, timeout=args.timeout)
    resp.raise_for_status()
    data = resp.json()
    print(f"loaded: {data['instance_id']} in {data['load_time_seconds']:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List known models and which instances are currently loaded")
    p_list.add_argument("--json", action="store_true", help="Print raw JSON instead of a table")

    p_unload = sub.add_parser("unload", help="Unload one or more loaded model instances")
    p_unload.add_argument("instance_id", nargs="*", help="Instance id(s) to unload (as shown by `list`)")
    p_unload.add_argument("--all", action="store_true", help="Unload every currently loaded instance")
    p_unload.add_argument("--keep", action="append", default=[], metavar="INSTANCE_ID",
                           help="Instance id to never unload (repeatable)")

    p_load = sub.add_parser("load", help="Load a model (as shown by `list`'s `key` column)")
    p_load.add_argument("model", help="Model key to load, e.g. qwen/qwen3-4b")
    p_load.add_argument("--context-length", type=int)
    p_load.add_argument("--eval-batch-size", type=int)
    p_load.add_argument("--flash-attention", type=lambda s: s.lower() in ("1", "true", "yes"),
                         default=None, metavar="BOOL")
    p_load.add_argument("--num-experts", type=int, help="Number of experts to use (MoE models)")
    p_load.add_argument("--timeout", type=int, default=300, help="Request timeout in seconds (default: 300)")

    p_dl = sub.add_parser("download", help="Download a model by catalog id or HF link")
    p_dl.add_argument("model", help="Catalog identifier (e.g. openai/gpt-oss-20b) or exact HF link")
    p_dl.add_argument("--quantization", help="Quantization level (e.g. Q4_K_M); HF links only")
    p_dl.add_argument("--wait", action="store_true", help="Poll and print progress until the download finishes")
    p_dl.add_argument("--retries", type=int, default=5,
                       help="Auto-resume this many times if the download dies mid-transfer "
                            "with status=failed (default: 5; only with --wait)")

    p_dls = sub.add_parser("download-status", help="Check the status of a download job")
    p_dls.add_argument("job_id", help="Job id returned by `download`")
    p_dls.add_argument("--wait", action="store_true", help="Poll and print progress until the download finishes")
    p_dls.add_argument("--json", action="store_true", help="Print raw JSON instead of the Python dict repr")

    p_swap = sub.add_parser("swap", help="Unload everything except --keep, then load `model` "
                                          "(the load/unload dance before testing a new candidate)")
    p_swap.add_argument("model", help="Model key to load, e.g. qwen/qwen3-4b")
    p_swap.add_argument("--keep", action="append", default=[], metavar="INSTANCE_ID",
                         help="Instance id to never unload (repeatable)")
    p_swap.add_argument("--context-length", type=int)
    p_swap.add_argument("--timeout", type=int, default=300, help="Load request timeout in seconds (default: 300)")

    args = parser.parse_args()
    {"list": cmd_list, "unload": cmd_unload, "load": cmd_load, "swap": cmd_swap,
     "download": cmd_download, "download-status": cmd_download_status}[args.command](args)


if __name__ == "__main__":
    main()
