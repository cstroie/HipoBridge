# LLM re-survey — 2026-07-21

Re-tests the current shortlist against the app's **current** prompts (the
`llm/prompts/` restructuring: a shared `system.md` framing + per-kind task
prompt, assembled by `_build_messages()`), since prompts have changed
materially since the original `docs/llm_benchmark_2026-07-19.md` survey. Also
adds a new candidate, `medgemma-1.5-4b-it` (Q4_K_M, ~4.16 GB incl. mmproj).

Same real input/reference set as the main survey (CIOBOTARU discharge
excerpt, real abnormal-labs panel, a real chest X-ray report) — see
`docs/llm_benchmark_2026-07-19.md` for full provenance.

## Server instability this session (operational finding, not a model verdict)

The LM Studio server degraded over the course of this round: `mistralai/
ministral-3-3b`'s old id (`mistralai/ministral-3-3b`) had silently changed to
`ministral-3-3b-instruct-2512` (no org prefix), causing an instant failure
that cascaded 500s into the next two models queued behind it. After a clean
retry with the corrected id and health checks between each model, **every
model that reached the `pre_exam` kind (900 tokens) eventually got
`RuntimeError: terminated`** — ministral, medgemma-1.5-4b-it, and finally
`qwen/qwen3-4b` crashed outright and stayed crashed (`"terminated"` even on a
fresh, isolated health-check call after the run). This reads as a systemic
resource issue (VRAM/memory pressure accumulating from repeated model
swapping across this and prior benchmark rounds) rather than any one model's
fault — `pre_exam` is the heaviest kind (900 tokens) and is where every crash
occurred. **`qwen/qwen3-4b` needs a server-side reload before it can be
re-tested** — it would not answer even a trivial "say OK" after the crash.

## Results

| Model | imaging | lab | report | pre_exam |
|---|---|---|---|---|
| **google/gemma-3n-e4b** | ✅ correct, English | ✅ correct, English, exact impression | ✅ faithful, English | ✅ faithful, English (minor: mislabeled 2 consult dates as extra ultrasounds) |
| **mistralai/ministral-3-3b** | ✅ correct, English | ✅ correct, English | ✅ faithful, English | — (server crash, untested) |
| medgemma-4b-it | ❌ **Romanian** (regression) | ✅ correct, English | ✅ faithful, English | ✅ faithful, English |
| medgemma-1.5-4b-it | ❌ **Romanian** (same regression) | ✅ correct, English | ⚠️ faithful but violates "no headings/bullets" format rule | — (server crash, untested) |
| qwen/qwen3-4b (`/no_think`) | — (server crashed before it ran) | — | — | — |

## Key finding: a real regression in the current prompts

**Both medgemma models (4b and 1.5-4b) now answer the `imaging` kind in
Romanian**, e.g. `"Ficat cu contur neregulat si dimensiuni la limita
superioara a normalului."` instead of the required `"Suspected biliary
atresia"`. This is a regression from the original survey, where
medgemma-4b-it reliably answered in English on this exact input. **ministral
and gemma-3n-e4b are unaffected** — both still answer correctly in English on
`imaging`. Something in the restructured `system.md` + `imaging.md`
combination is weaker on language enforcement specifically for the medgemma
family on this short-task kind; worth investigating (e.g. whether the shared
system prompt's language instruction is positioned/worded differently than
the old per-kind `_language_directive` suffix that used to immediately follow
the task text).

`medgemma-1.5-4b-it`'s `report` output also broke the "no headings, no
preamble, no bullet points" rule (used `**Executive Summary:**` / `**Key
Points:**` with a bullet list) — a plain prose kind should never look like
this; ministral and gemma-3n-e4b both stayed correctly unstructured.

## medgemma-1.5-4b-it vs medgemma-4b-it

Roughly comparable in content quality on `lab` (both correctly named
lymphopenia/cholestasis/renal-impairment/inflammation and landed on the same
impression) and reasonably faithful on `report`, but 1.5 additionally fails
the report-kind's format rule where 4b doesn't. No evidence here that 1.5 is
an improvement over 4b-it for this app's kinds; both share the same
Romanian-on-imaging regression. Not recommended as a replacement.

## Updated recommendation

- **The production pick is unaffected: `ministral-3-3b`** — clean, correct,
  English throughout every kind it completed, no format violations. Still the
  fastest of the viable candidates (see the 07-19 doc's Round 4 timing).
- **`gemma-3n-e4b` remains the best all-rounder** and is now the *only* model
  in this round with clean full-4-kind data, including `pre_exam` (which
  crashed for everything else). Worth treating as the primary fallback.
- **medgemma-4b-it needs the imaging regression looked at** before relying on
  it for that kind specifically — it's currently producing Romanian output
  that would fail silently in production (the frontend doesn't currently
  detect wrong-language output).
- **medgemma-1.5-4b-it: no reason to adopt** — shares medgemma-4b-it's
  regression and adds a new format violation, with no clear quality upside.
- **qwen3-4b: status unknown** — crashed and needs a server-side model
  reload before it can be re-evaluated under the current prompts.

## Follow-ups

1. Investigate why the medgemma family regressed to Romanian on `imaging`
   under the new shared `system.md` prompt — likely a placement/emphasis
   issue in how the language instruction is now assembled relative to the
   old per-kind `_language_directive`.
2. Ask the LM Studio operator to reload/evict `qwen/qwen3-4b` (crashed,
   unresponsive even to a trivial health check) before any further testing.
3. `pre_exam` crashing across three different models in one session suggests
   genuine server resource pressure (VRAM/memory) worth monitoring
   independent of any single model's behavior — consider testing `pre_exam`
   in isolation (one model, fresh server state) rather than back-to-back
   with other kinds/models, until this is better understood.
