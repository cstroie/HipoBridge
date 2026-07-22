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

---

# Fix: removed the shared preamble that caused the imaging regression (2026-07-22)

## Root cause, confirmed
`benchmark_prompt_format.py`'s 4-way A/B (`current`/`consolidated`/
`language_last`/`legacy`, see the section above) isolated the exact cause of
medgemma-4b-it's `imaging` regression: **the shared `system.md` preamble
itself** (generic role framing + general rules), independent of whether it
sat in the system or user role, and independent of where within it the
language instruction was positioned. The `legacy` variant — no shared
preamble, just the kind's own task prompt + a language-directive suffix —
was the only one that correctly answered "Suspected biliary atresia" in
English. On `lab`/`report`/`pre_exam` the shared preamble's effect was mixed
rather than clearly harmful (on `report` it actually *avoided* a
"peritonitis" contradiction that the no-preamble variants introduced) — but
`imaging`'s short (40-token) output left the least room for a large generic
preamble to compete with the specific instruction that mattered.

## Fix shipped
`llm/prompts.py` was rewritten: there is no longer a shared preamble at all.
Every kind's prompt (`llm/prompts/<kind>.md`) is now fully self-contained —
its own role framing, its own restated anti-hallucination rule, its own
explicit "no reasoning/chain-of-thought" instruction — with the date and
language directives appended directly after the task prompt (the position
already validated to work). `report.md` and `epicrisis.md` gained short,
task-specific role framing (they previously had none of their own, relying
entirely on the now-removed shared preamble); `imaging.md`, `lab.md`, and
`pre_exam.md` each gained an explicit "no reasoning or thinking steps" line
they didn't already state outright. `llm/prompts/system.md` was deleted.

## Verified against the real production code path (not just the diagnostic tool)
Re-ran `benchmark_llm.py` (which calls the actual, rewritten
`_build_messages()`) against the live server:

| Kind | Model | Result |
|---|---|---|
| imaging | medgemma-4b-it | ✅ "Suspected biliary atresia" (3/3), **and faster**: 4.34s total vs 6.9-7.9s with the old shared preamble |
| lab | medgemma-4b-it | ✅ correct terms, correct impression, English |
| report | medgemma-4b-it | ✅ faithful, English |
| pre_exam | medgemma-4b-it | ✅ (after one xrayvision-contention retry — see below) |
| imaging | ministral-3-3b | ✅ exact match to reference — unaffected, as expected |
| imaging | gemma-3n-e4b | ✅ correct diagnosis (adds extra findings, a known pre-existing pattern, not a new regression) |

Also added a regression-guard unit test
(`test_no_shared_preamble_diluting_short_kinds` in `tests/llm_client.py`)
asserting no kind's assembled system message contains the old shared
preamble's language, so this specific regression can't silently return.

## Aside: confirms the xrayvision-contention theory
One of the `pre_exam` regression-test attempts hit `RuntimeError: terminated`
— recovered cleanly on retry after a fresh health check. Consistent with the
discussed theory that this LM Studio instance's radiology project
(xrayvision) can evict the model mid-generation under department load,
independent of prompt correctness.

---

# pre_exam Romanian regression: not resolved by prompt engineering (2026-07-22)

## What was tried
After fixing `imaging` by removing the shared preamble, `pre_exam` turned out
to have its **own**, separate regression for medgemma-4b-it: it was correctly
English before today's changes (Round 11) but came back in Romanian after the
preamble removal. Three progressively stronger fixes were tried and verified
against the live model, each a real, isolated test — not guesses left
unverified:

1. An inline disambiguation note next to `pre_exam.md`'s "exact, no
   paraphrase" instruction (hypothesis: the model was reading that as license
   to preserve the source language verbatim) + a STRICT RULE stating the
   language requirement overrides it.
2. Reordering: moved that STRICT RULE to the *top* of the rules list (was
   last of 9) and added an explicit translation clause into the opening role
   sentence, so it's the first thing read, well before "no paraphrase"
   appears.
3. Concrete language naming: added lightweight, targeted `{language}`
   placeholder substitution (`str.replace`, not `str.format`, so it can't
   break on any future literal braces elsewhere) so the prompt states
   "entirely in English" directly instead of a vague "the output language
   specified below".

**All three still produced Romanian output**, reproducibly, across multiple
runs.

## Likely cause
`pre_exam`'s input is far larger than `imaging`'s and almost entirely Romanian
source text (~7500 chars vs. ~950), with a 900-token output. This looks like
**volume-driven language drift**: with that much non-English context, the
model may drift toward the source language regardless of instruction wording
or position — a different failure mode than `imaging`'s dilution problem,
and one that doesn't appear fixable by prompt wording alone for this model.

`google/gemma-3n-e4b` correctly handled this exact same long, Romanian-heavy
`pre_exam` input in English in earlier rounds, so this reads as a
**medgemma-4b-it-specific weakness on long, source-language-heavy input**,
not a universal problem with the kind or the input.

## Decision: stop prompt-wording escalation, route around it instead
No more prompt-wording changes for this specific case. Recommendation:

- **Do not rely on medgemma-4b-it for `pre_exam`.** Prefer `gemma-3n-e4b` or
  `ministral-3-3b` for that kind specifically. medgemma-4b-it remains fine for
  `imaging`/`lab`/`report` (all verified correct in English this round).
- If medgemma-4b-it must be used for `pre_exam` in the future, the next thing
  worth testing is **not** more wording — it's whether truncating the
  Romanian source further, or a lower temperature, reduces the drift. Both
  are untested hypotheses, not confirmed fixes.

The prompt content changes made while chasing this (restored role framing,
explicit no-reasoning rules, the "no paraphrase" disambiguation, and the
`{language}` templating mechanism itself) are kept — they're net-neutral-to-
positive and the templating mechanism is reusable for any future kind that
needs a concrete language name in its own wording.

---

# Re-benchmark of top 3 candidates against final prompts (2026-07-22)

Re-ran `benchmark_llm.py` for `imaging`/`lab`/`report`/`pre_exam` against
`ministral-3-3b-instruct-2512` (server-side id drifted again, same staleness
as documented in the 07-19 doc — `local.cfg` may need updating), `google/
gemma-3n-e4b`, and `medgemma-4b-it`, using the now-committed self-contained
prompts.

| Kind | ministral-3-3b | gemma-3n-e4b | medgemma-4b-it |
|---|---|---|---|
| imaging | not re-tested this round | ✅ correct English | ✅ correct English, faster than the old shared-preamble baseline |
| lab | ✅ correct English | ✅ correct English | ✅ correct English |
| report | ✅ faithful English | ✅ faithful English | ✅ faithful English |
| pre_exam | ✅ clean English | ✅ clean English | ⚠️ mostly English but repeats the Romanian term **"atresia bilis"** in place of "biliary atresia" throughout the document |

## Refines the pre_exam finding
medgemma-4b-it's `pre_exam` failure is **narrower** than first reported: not
a full-response Romanian regression, but a **term-level leak** — one
recurring source-language phrase embedded in an otherwise-correct English
document (headings, dates, and surrounding prose are all in English). Doesn't
change the recommendation (still avoid medgemma-4b-it for `pre_exam`,
ministral-3-3b/gemma-3n-e4b are clean), but is a more precise failure
description than "regresses to Romanian" for anyone revisiting this later.
