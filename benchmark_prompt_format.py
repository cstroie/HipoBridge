#!/usr/bin/env python3
"""Benchmark PROMPT-FORMAT variants for one model — a companion to
benchmark_llm.py, which measures MODEL differences. This tool holds the
model fixed and varies how the same instructions are packaged into the chat
messages, to diagnose format-sensitive regressions (e.g. medgemma-4b-it
answering the `imaging` kind in Romanian after llm/prompts/ moved to a
shared system.md + per-kind task prompt).

Two variants, both built from the exact production prompt content
(llm.prompts) so neither can silently drift from what the app sends:

  current       — today's production shape: one system-role message (shared
                  system.md + optional date directive + the kind's task
                  prompt), one user-role message (the clinical text).
  consolidated  — no system role at all: everything (framing + task prompt +
                  clinical text) folded into a single user-role message,
                  separated by a clear "---" marker. Tests the hypothesis
                  that this model instruction-follows more reliably on
                  user-role content than system-role content.

Retries transient "terminated" / engine-restart failures a bounded number of
times with a short backoff — this LM Studio instance also serves another
project (xrayvision) that can evict the loaded model under radiology load,
which shows up as a mid-generation crash unrelated to prompt quality.

Usage:
    python3 benchmark_prompt_format.py --model medgemma-4b-it
    python3 benchmark_prompt_format.py --model medgemma-4b-it --kind imaging
"""
import argparse
import asyncio
import json
import statistics
import sys
import time

from llm.config import init_llm, select_provider
from llm.backend import ServerBackend
from llm.prompts import PROMPTS, _system_prompt, _date_directive, DATE_AWARE_KINDS

# Real inputs/references reused from the main benchmark rounds (see
# docs/llm_benchmark_2026-07-19.md for provenance) — same document set every
# round has used, so results stay comparable across the whole survey.
KIND_FILES = {
    "imaging":  ("/tmp/imaging_report.txt", "/tmp/reference_imaging.txt"),
    "lab":      ("/tmp/lab_panel_abn.txt", "/tmp/reference_lab.txt"),
    "report":   ("/tmp/ciobotaru_report_trim.txt", "/tmp/reference_report.txt"),
    "pre_exam": ("/tmp/ciobotaru_report_trim.txt", "/tmp/reference_pre_exam.txt"),
}

# Substrings of transient failures caused by another project evicting the
# model mid-generation (not a prompt/quality issue) — bounded retry only.
TRANSIENT_MARKERS = ("terminated", "Engine protocol", "unloaded")
MAX_RETRIES = 3
RETRY_DELAY_S = 8


def _task_prompt_block(kind: str, language: str) -> str:
    _tier, task_prompt, _max_tokens = PROMPTS[kind]
    block = _system_prompt(language)
    if kind in DATE_AWARE_KINDS:
        block += _date_directive()
    block += "\n\n" + task_prompt
    return block


def build_current(kind: str, text: str, language: str):
    _tier, _task_prompt, max_tokens = PROMPTS[kind]
    messages = [
        {"role": "system", "content": _task_prompt_block(kind, language)},
        {"role": "user", "content": text},
    ]
    return messages, max_tokens


def build_consolidated(kind: str, text: str, language: str):
    _tier, _task_prompt, max_tokens = PROMPTS[kind]
    combined = (
        f"{_task_prompt_block(kind, language)}\n\n---\n\n"
        f"CLINICAL RECORD TO ANALYZE:\n\n{text}"
    )
    messages = [{"role": "user", "content": combined}]
    return messages, max_tokens


def build_language_last(kind: str, text: str, language: str):
    """Mirrors the pre-restructuring prompt shape: the language instruction
    is the LAST thing before the user turn, not stated once early in a
    shared preamble. In the old design, _language_directive() was appended
    AFTER the task prompt; in the current design, system.md's language rule
    comes BEFORE the task prompt (whose own trailing format instructions —
    e.g. imaging.md's "Respond with ONLY the phrase...— now come after it,
    giving the language rule no recency advantage. Tests whether restoring
    that position (independent of system-vs-user role) fixes the
    regression."""
    _tier, task_prompt, max_tokens = PROMPTS[kind]
    role_and_rules = _system_prompt(language).split("Output language:")[0].strip()
    if kind in DATE_AWARE_KINDS:
        role_and_rules += "\n" + _date_directive().strip()
    language_reminder = (
        f" IMPORTANT: Write your entire response in {language}, regardless of "
        f"the language of the source document — translate the content into "
        f"{language} rather than copying phrases verbatim, and never switch "
        f"language mid-response."
    )
    system_content = role_and_rules + "\n\n" + task_prompt + "\n\n" + language_reminder
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": text},
    ]
    return messages, max_tokens


def build_legacy(kind: str, text: str, language: str):
    """The pre-restructuring shape, verbatim: NO shared role-framing or
    general-rules preamble at all — just the kind's own task prompt, with a
    short language-directive suffix appended, exactly as
    llm/prompts.py looked before the system.md extraction. Tests whether the
    regression is caused by the *added preamble content* itself (crowding a
    small model's limited instruction-following budget), independent of
    where the language rule sits within it."""
    _tier, task_prompt, max_tokens = PROMPTS[kind]
    language_directive = (
        f" IMPORTANT: Write your entire response in {language}, regardless of "
        f"the language of the source document — translate the content into "
        f"{language} rather than copying phrases verbatim, and never switch "
        f"language mid-sentence."
    )
    messages = [
        {"role": "system", "content": task_prompt + language_directive},
        {"role": "user", "content": text},
    ]
    return messages, max_tokens


VARIANTS = {
    "current": build_current,
    "consolidated": build_consolidated,
    "language_last": build_language_last,
    "legacy": build_legacy,
}


async def call_with_retry(backend: ServerBackend, model: str, messages: list,
                          max_tokens: int, temperature: float = 0.1) -> dict:
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            start = time.perf_counter()
            ttft = None
            parts = []
            async for piece in backend.chat_stream(
                    model, messages, max_tokens=max_tokens, temperature=temperature):
                if ttft is None:
                    ttft = time.perf_counter() - start
                parts.append(piece)
            total = time.perf_counter() - start
            text = "".join(parts).strip()
            if not text:
                raise RuntimeError("empty completion (no content returned)")
            return {"text": text, "ttft": ttft or total, "total": total,
                    "attempts": attempt, "error": None}
        except Exception as exc:  # noqa: BLE001 - classify below
            last_exc = exc
            msg = str(exc)
            transient = any(marker in msg for marker in TRANSIENT_MARKERS)
            if transient and attempt < MAX_RETRIES:
                print(f"    transient failure ({msg[:70]!r}), "
                      f"retry {attempt}/{MAX_RETRIES} in {RETRY_DELAY_S}s...",
                      file=sys.stderr)
                await asyncio.sleep(RETRY_DELAY_S)
                continue
            return {"text": None, "ttft": None, "total": None,
                    "attempts": attempt, "error": f"{type(exc).__name__}: {exc}"}
    return {"text": None, "ttft": None, "total": None,
            "attempts": MAX_RETRIES, "error": str(last_exc)}


async def run_one(backend, model, kind, variant_name, variant_fn, text,
                  language, iterations):
    messages, max_tokens = variant_fn(kind, text, language)
    results = []
    for i in range(iterations):
        r = await call_with_retry(backend, model, messages, max_tokens)
        results.append(r)
        status = "OK" if r["error"] is None else f"ERROR {r['error'][:50]}"
        print(f"    [{kind}/{variant_name}] iter {i+1}/{iterations}: {status}"
              + (f" ttft={r['ttft']:.2f}s total={r['total']:.2f}s" if r["error"] is None else ""))
    ok = [r for r in results if r["error"] is None]
    summary = {
        "kind": kind, "variant": variant_name, "model": model,
        "n_ok": len(ok), "n_total": iterations,
        "median_ttft": statistics.median([r["ttft"] for r in ok]) if ok else None,
        "median_total": statistics.median([r["total"] for r in ok]) if ok else None,
        "sample_text": ok[-1]["text"] if ok else None,
        "errors": [r["error"] for r in results if r["error"]],
    }
    return summary


async def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="medgemma-4b-it")
    ap.add_argument("--kind", choices=list(KIND_FILES), default=None,
                    help="Single kind to test (default: all four)")
    ap.add_argument("--iterations", type=int, default=2)
    ap.add_argument("--out", default="/tmp/prompt_format_results.json")
    ap.add_argument("--dump", default="/tmp/prompt_format_outputs.md")
    args = ap.parse_args()

    config = init_llm()
    base_url, key, _models = select_provider(config)
    language = config["llm"].get("language", "English") or "English"
    backend = ServerBackend(base_url=base_url, key=key, timeout=300)

    kinds = [args.kind] if args.kind else list(KIND_FILES)
    all_summaries = []
    dump_sections = []

    for kind in kinds:
        input_path, ref_path = KIND_FILES[kind]
        with open(input_path) as f:
            text = f.read()
        with open(ref_path) as f:
            reference = f.read().strip()
        print(f"\n=== {kind} (model={args.model}, input={len(text)} chars) ===")

        kind_dump = [f"## {kind}\n\n**Reference:**\n\n{reference}\n"]
        for variant_name, variant_fn in VARIANTS.items():
            print(f"  --- variant: {variant_name} ---")
            summary = await run_one(backend, args.model, kind, variant_name,
                                    variant_fn, text, language, args.iterations)
            all_summaries.append(summary)
            kind_dump.append(f"### {variant_name}\n\n")
            if summary["sample_text"]:
                kind_dump.append(summary["sample_text"] + "\n\n")
            if summary["errors"]:
                kind_dump.append(f"_Errors: {summary['errors']}_\n\n")
        dump_sections.append("\n".join(kind_dump))

    await backend.close()

    with open(args.out, "w") as f:
        json.dump(all_summaries, f, indent=2)
    with open(args.dump, "w") as f:
        f.write(f"# Prompt-format comparison — {args.model}\n\n")
        f.write("\n---\n\n".join(dump_sections))
    print(f"\nWrote {args.out}")
    print(f"Wrote {args.dump}")

    print("\n=== Summary ===")
    for s in all_summaries:
        ttft = f"{s['median_ttft']:.2f}s" if s["median_ttft"] else "—"
        total = f"{s['median_total']:.2f}s" if s["median_total"] else "—"
        print(f"  {s['kind']:10} {s['variant']:12} ok={s['n_ok']}/{s['n_total']} "
              f"ttft={ttft} total={total}")


if __name__ == "__main__":
    asyncio.run(main())
