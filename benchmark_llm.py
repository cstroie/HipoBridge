#!/usr/bin/env python3
"""Benchmark small on-device LLMs on the configured OpenAI-compatible server.

Measures, per candidate model, using a *real* clinical document as input and
the *exact* production system prompt + max_tokens for a given AI "kind":

  - warm TTFT      time-to-first-token once the model is resident
  - tokens/sec     sustained generation throughput
  - total          full end-to-end wall time for the summary
  - cold TTFT      first call after (re)load — includes the VRAM swap cost

LM Studio (and similar) swap models in and out of VRAM, so models are run
one-at-a-time (all iterations for a model before the next) to pay the load
cost exactly once per model.

Reuses the app's own config layering (llm.config) and prompt registry
(llm.prompts) so the numbers reflect what the "AI" buttons actually do.

Usage:
    export HYP_USER=<u> HYP_PASS=<p>
    python3 benchmark_llm.py --report-id 12345 --kind epicrisis --iterations 3
    python3 benchmark_llm.py --text-file sample.txt --models lfm2.5-230m
"""
import argparse
import asyncio
import base64
import csv
import json
import os
import statistics
import sys
import time

import aiohttp

from llm.config import init_llm, select_provider
from llm.prompts import PROMPTS, _build_messages, _date_directive, _language_directive, DATE_AWARE_KINDS
from llm.backend import strip_think_block


class _ClientShim:
    """Minimal stand-in for llm.router.LLMClient — _build_messages() only
    reads .language off its `client` argument, so a real LLMClient (with its
    ServerBackend, tier map, etc.) would be needless ceremony here."""
    def __init__(self, language: str):
        self.language = language

# Curated candidates: Gemma / MedGemma / LFM families, 1B-4B or smaller.
# Any not present on the server are warned about and skipped at startup.
DEFAULT_MODELS = [
    "medgemma-4b-it",
    "google/gemma-3-4b",
    "google/gemma-4-e4b",
    "google/gemma-3n-e4b",
    "google/gemma-3-1b",
    "lfm2-2.6b-transcript",
    "lfm2.5-1.2b-instruct",
    "liquid/lfm2-1.2b",
    "lfm2.5-230m",
]


# --- input assembly -----------------------------------------------------

def _flatten_json(obj) -> list[str]:
    """Recursively collect non-empty string leaf values from a HipoData JSON."""
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(_flatten_json(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_flatten_json(v))
    elif isinstance(obj, str):
        s = obj.strip()
        if s:
            out.append(s)
    elif isinstance(obj, (int, float)):
        out.append(str(obj))
    return out


async def fetch_report_text(server: str, endpoint: str, report_id: str,
                            user: str, password: str) -> str:
    """Fetch a real report from the running HippoBridge server and flatten it
    to a single text blob for the LLM user message."""
    path = endpoint.replace("{id}", str(report_id))
    url = f"{server.rstrip('/')}{path}"
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=60)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    text = "\n".join(_flatten_json(data))
    if not text.strip():
        raise RuntimeError(f"{url} returned no usable text")
    return text


# --- one streaming call -------------------------------------------------

class CallResult:
    __slots__ = ("ttft", "total", "tps", "completion_tokens", "text")

    def __init__(self, ttft, total, tps, completion_tokens, text):
        self.ttft = ttft
        self.total = total
        self.tps = tps
        self.completion_tokens = completion_tokens
        self.text = text


async def stream_chat(session: aiohttp.ClientSession, base_url: str, key: str,
                      model: str, messages: list[dict], max_tokens: int,
                      timeout: float) -> CallResult:
    """POST a streaming /chat/completions and time TTFT / total / tokens-sec."""
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    start = time.perf_counter()
    ttft = None
    last_token_time = start
    completion_tokens = None
    parts: list[str] = []
    server_error = None

    async with session.post(f"{base_url}/chat/completions", json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
        resp.raise_for_status()
        async for raw in resp.content:
            line = raw.decode("utf-8", "ignore").strip()
            if not line:
                continue
            if not line.startswith("data:"):
                # LM Studio may emit an error as a plain (non-SSE) JSON body.
                try:
                    body = json.loads(line)
                    if body.get("error"):
                        err = body["error"]
                        server_error = err.get("message") if isinstance(err, dict) else str(err)
                        break
                except json.JSONDecodeError:
                    pass
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if chunk.get("error"):
                err = chunk["error"]
                server_error = err.get("message") if isinstance(err, dict) else str(err)
                break
            choices = chunk.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                # Some models stream visible text under reasoning_content
                # instead of content (e.g. gemma-4-e4b) — accept either.
                piece = delta.get("content") or delta.get("reasoning_content")
                if piece:
                    now = time.perf_counter()
                    if ttft is None:
                        ttft = now - start
                    last_token_time = now
                    parts.append(piece)
            usage = chunk.get("usage")
            if usage and usage.get("completion_tokens") is not None:
                completion_tokens = usage["completion_tokens"]

    total = time.perf_counter() - start
    if server_error:
        raise RuntimeError(server_error)
    if not parts and not completion_tokens:
        raise RuntimeError("empty completion (no content returned)")
    text = strip_think_block("".join(parts))
    if completion_tokens is None:
        completion_tokens = len(text.split())  # rough fallback
    # tokens/sec over the generation window (first content token -> last).
    # If no content was ever timed (parts empty), the window is undefined —
    # report 0 rather than a divide-by-near-zero blowup.
    gen_window = last_token_time - (start + ttft) if ttft is not None else 0.0
    tps = completion_tokens / gen_window if gen_window > 1e-3 else 0.0
    if ttft is None:
        ttft = total
    return CallResult(ttft, total, tps, completion_tokens, text)


# --- per-model benchmark ------------------------------------------------

async def benchmark_model(session, base_url, key, model, messages, max_tokens,
                          iterations, timeout) -> dict:
    result = {"model": model, "error": None}
    try:
        cold = await stream_chat(session, base_url, key, model, messages,
                                 max_tokens, timeout)
        result["cold_ttft"] = cold.ttft

        warm: list[CallResult] = []
        for _ in range(iterations):
            warm.append(await stream_chat(session, base_url, key, model,
                                          messages, max_tokens, timeout))
        result["warm_ttft"] = statistics.median(c.ttft for c in warm)
        result["tps"] = statistics.median(c.tps for c in warm)
        result["total"] = statistics.median(c.total for c in warm)
        result["tokens"] = int(statistics.median(c.completion_tokens for c in warm))
        result["output"] = warm[-1].text
        result["sample"] = warm[-1].text.replace("\n", " ")[:120]
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}" or "unreachable/timeout"
    except Exception as exc:  # noqa: BLE001 - report and continue
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# --- reporting ----------------------------------------------------------

SORT_KEYS = {"ttft": "warm_ttft", "tps": "tps", "total": "total"}


def print_table(results: list[dict], sort: str):
    key = SORT_KEYS[sort]
    ok = [r for r in results if not r["error"]]
    bad = [r for r in results if r["error"]]
    # tps sorts high-to-low (faster is better); latencies low-to-high.
    ok.sort(key=lambda r: r[key], reverse=(sort == "tps"))

    header = f"{'model':<26} {'warm TTFT':>10} {'tok/s':>8} {'total':>8} {'cold TTFT':>10} {'toks':>6}"
    print("\n" + header)
    print("-" * len(header))
    for r in ok:
        print(f"{r['model']:<26} {r['warm_ttft']:>9.2f}s {r['tps']:>8.1f} "
              f"{r['total']:>7.2f}s {r['cold_ttft']:>9.2f}s {r['tokens']:>6}")
    for r in bad:
        print(f"{r['model']:<26} ERROR: {r['error']}")
    print()
    for r in ok:
        print(f"  {r['model']}: {r['sample']}")


def write_out(results: list[dict], path: str):
    cols = ["model", "warm_ttft", "tps", "total", "cold_ttft", "tokens",
            "sample", "error"]
    if path.endswith(".json"):
        with open(path, "w") as f:
            json.dump(results, f, indent=2)
    else:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in results:
                w.writerow(r)
    print(f"Wrote {path}")


def dump_outputs(results: list[dict], input_text: str, path: str,
                 reference: str | None):
    """Write every model's full summary (plus the source and an optional
    reference) to a markdown file for side-by-side quality review."""
    with open(path, "w") as f:
        f.write("# Model outputs for quality review\n\n")
        if reference:
            f.write("## Reference summary\n\n")
            f.write(reference.strip() + "\n\n")
        f.write("## Source (input given to every model)\n\n")
        f.write("```\n" + input_text.strip() + "\n```\n\n")
        f.write("## Model summaries\n\n")
        for r in results:
            f.write(f"### {r['model']}\n\n")
            if r["error"]:
                f.write(f"_ERROR: {r['error']}_\n\n")
            else:
                f.write((r.get("output") or "").strip() + "\n\n")
    print(f"Wrote {path}")


# --- main ---------------------------------------------------------------

async def async_main(args):
    config = init_llm()
    base_url, key, _ = select_provider(config)
    base_url = base_url.rstrip("/")

    # Resolve input text.
    if args.text_file:
        with open(args.text_file) as f:
            text = f.read()
        source = args.text_file
    else:
        user = os.getenv("HYP_USER")
        password = os.getenv("HYP_PASS")
        if not (user and password):
            sys.exit("HYP_USER/HYP_PASS must be set to fetch a live report "
                     "(or use --text-file).")
        text = await fetch_report_text(args.server, args.endpoint,
                                       args.report_id, user, password)
        source = f"{args.endpoint.replace('{id}', str(args.report_id))}"
    print(f"Input: {source} ({len(text)} chars)")

    # Build the exact production message for --kind, reusing _build_messages()
    # so this tool's assembly can never silently drift from what the app
    # actually sends. --system-file overrides just the kind's task-specific
    # prompt (the date + language directives still apply, in the same
    # position) so a candidate task prompt can be A/B-tested before being
    # promoted into llm/prompts/<kind>.md.
    tier, task_prompt, max_tokens = PROMPTS[args.kind]
    language = config["llm"].get("language", "English") or "English"
    shim = _ClientShim(language)
    if args.system_file:
        with open(args.system_file) as f:
            task_prompt = f.read().strip()
        print(f"System prompt: OVERRIDE from {args.system_file}")
        system_content = task_prompt
        if args.kind in DATE_AWARE_KINDS:
            system_content += _date_directive()
        system_content += _language_directive(language)
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": text},
        ]
    else:
        messages = _build_messages(shim, args.kind, text)
    print(f"Kind: {args.kind} (tier={tier}, max_tokens={max_tokens}, lang={language})")

    models = ([m.strip() for m in args.models.split(",") if m.strip()]
              if args.models else list(DEFAULT_MODELS))

    async with aiohttp.ClientSession() as session:
        # Validate against the server's model list.
        try:
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            async with session.get(f"{base_url}/models", headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=10)) as resp:
                resp.raise_for_status()
                available = {m["id"] for m in (await resp.json()).get("data", [])}
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            sys.exit(f"Cannot reach LLM server at {base_url}: {exc}")

        run_models = []
        for m in models:
            if m in available:
                run_models.append(m)
            else:
                print(f"  ! skipping '{m}' — not on server", file=sys.stderr)
        if not run_models:
            sys.exit("No requested models are available on the server.")

        print(f"Benchmarking {len(run_models)} model(s), "
              f"{args.iterations} warm iteration(s) each...")
        results = []
        for m in run_models:
            print(f"  - {m} ...", flush=True)
            results.append(await benchmark_model(
                session, base_url, key, m, messages, max_tokens,
                args.iterations, args.timeout))

    print_table(results, args.sort)
    if args.out:
        write_out(results, args.out)
    if args.dump_outputs:
        reference = None
        if args.reference:
            with open(args.reference) as f:
                reference = f.read()
        dump_outputs(results, text, args.dump_outputs, reference)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report-id", help="Hipocrate report id to fetch as input")
    p.add_argument("--endpoint", default="/api/checkout/{id}",
                   help="HippoBridge path ({id} substituted); default /api/checkout/{id}")
    p.add_argument("--text-file", help="Use a local text file instead of a live report")
    p.add_argument("--kind", default="epicrisis", choices=list(PROMPTS),
                   help="AI prompt kind (default: epicrisis)")
    p.add_argument("--models", help="Comma-separated model ids (default: curated set)")
    p.add_argument("--iterations", type=int, default=3, help="Warm iterations (default 3)")
    p.add_argument("--server", default="http://localhost:44660",
                   help="Running HippoBridge base url")
    p.add_argument("--timeout", type=float, default=300.0,
                   help="Per-request timeout seconds (default 300)")
    p.add_argument("--sort", default="ttft", choices=list(SORT_KEYS),
                   help="Ranking metric (default ttft)")
    p.add_argument("--out", help="Write results to results.csv or results.json")
    p.add_argument("--dump-outputs",
                   help="Write every model's full summary (+ source and, with "
                        "--reference, a reference) to a markdown file for review")
    p.add_argument("--reference",
                   help="Reference-summary text file to include in --dump-outputs")
    p.add_argument("--system-file",
                   help="Override the registry system prompt with this text file "
                        "(for A/B prompt testing before promoting to llm/prompts.py)")
    args = p.parse_args()

    if not args.text_file and not args.report_id:
        p.error("provide --report-id (live fetch) or --text-file")

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
