# On-device LLM survey — final report and rankings (2026-08-01)

Consolidates every model tested in the `docs/llm_benchmark_2026-07-31.md`
round: 33 models in English, 19 of them retested in Romanian (production's
actual `local.cfg` default). Ranked **quality first, speed second** — a
fast model that fabricates or leaks language is not a candidate, full stop.
Speed only breaks ties among models judged similarly reliable.

Quality tiers are assigned from the hand-verified findings in the detailed
doc (every claim there was checked against the real source text, not just
against the reference summary). Speed numbers are pulled directly from the
benchmark JSON output — weighted throughput (`Σtokens / Σtime` across all 4
kinds, so a handful of near-instant tiny outputs can't skew it) and total
wall-clock time to run one full 4-kind battery (imaging+lab+report+pre_exam
at the same 2-warm-iteration settings as every other round).

## The finish line

**Updated after Phase 2** (see below) — the original single-fixture verdict
did not fully hold up. **`lmstudio-community/qwen3.5-4b`** is now the
winner: it's the only model clean across *both* the original biliary-atresia
case (English + Romanian, all 4 kinds, one narrow `pre_exam` caveat) *and*
all 4 independent real fixtures pulled from `_testing_/cases_*` in Phase 2
(orthopedics, cardiology, a no-clinical-content edge case, and a complex
oncology case). `qwen/qwen3-4b` — the original Phase 1 winner — fabricated
an admission narrative on Phase 2's Case C (a discharge-instructions-only
fixture with no actual clinical content), the one case where the honest
answer was "insufficient clinical information to summarize." That's a real
failure the Phase 1 result didn't surface, since Phase 1 never tested a
malformed/edge-case input. `qwen3.5-4b` is roughly comparable in speed to
`qwen3-4b` (204s vs. 133s for a full English 4-kind battery — `qwen3-4b` is
somewhat faster, but that's no longer the deciding factor since `qwen3.5-4b`
is now the more broadly reliable one).

**Recommendation**: promote `lmstudio-community/qwen3.5-4b` to a staged
rollout — non-critical kinds first, full rollout after the `pre_exam`
garbled-date issue from Phase 1 is re-isolated and confirmed fixed or
one-off (follow-up #2 in the detailed doc). `qwen/qwen3-4b` and
`qwen3-4b-instruct-2507` are close seconds (each 3/4 clean on Phase 2,
different failure modes) — worth keeping in consideration but not the lead
pick anymore. `medgemma-4b-it` is the safer fallback of the two
already-in-use models — see Phase 3 below, current production
`ministral-3-3b-instruct-2512` tested for the first time this round and
fared markedly worse than either.

**If speed matters more than this report's tiering implies**: within
Tier A/B (the only tiers worth deploying), `qwen/qwen3-vl-4b` is the
fastest option that still holds up under real fact-checking in Phase 1 —
not yet Phase-2-tested, so treat that speed edge with the same caution
Phase 2 just taught us to apply to Phase-1-only results.

## Tier definitions

| Tier | Meaning |
|---|---|
| **S** | Fabrication-free, correct language, all 4 kinds, in every language tested |
| **A** | Fabrication-free; one narrow, contained issue (not a core-fact error) |
| **B** | Usable; one real but isolated failure (wrong diagnosis on the shortest kind, a terminology slip, or a language leak confined to one kind) |
| **C** | Real reliability problem — recurring fabrication, a language leak on a core kind, or a diagnosis miss — but still partially usable |
| **D** | Frequently broken — fabrication or a severe breakdown in at least one language, not safe to deploy as-is |
| **F** | Unusable — architectural failure (won't load, context ceiling, wrong output shape) or an unsuppressable reasoning leak that eats the entire token budget |

## Ranked comparison

Speed columns: **Σt** = total wall-clock seconds for one full 4-kind
battery (warm runs); **tok/s** = weighted throughput across those 4 kinds.
Dash = not retested in that language (excluded from the Romanian rerun
because already disqualified for language-independent reasons — see the
detailed doc's rerun-scope note).

### Tier S

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `qwen/qwen3-4b` | Clean, faithful, correct language on **all 4 kinds in both languages** — the only model in the survey to clear this bar | 133s / 5.3 | 162s / 6.1 |

### Tier A

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `lmstudio-community/qwen3.5-4b` | Clean on imaging/lab/report both languages; `pre_exam` has a narrow garbled-date + one ungrounded inference (English only) — not a core-fact error | 179s / 6.6 | 204s / 6.6 |

### Tier B

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `qwen/qwen3-vl-4b` | Correct on imaging/lab/pre_exam; one fact-inversion on `report` only (bile-duct-dilation status) — "short-kind dilution" pattern | 118s / 7.6 | 177s / 8.3 |
| `qwen3-4b-instruct-2507` | Same report-kind fact-inversion as `qwen3-vl-4b`; corrects itself on `pre_exam`; clean in Romanian | 193s / 5.9 | 263s / 6.0 |
| `qwen3-1.7b` (`/no_think`) | Clean, faithful, correct language on report/lab/pre_exam both languages; imaging diagnosis is off-target (not fabricated, just wrong) in both | 84s / 16.3 | 85s / 14.7 |
| `lfm2-2.6b-transcript` | Faithful on report/lab/pre_exam both languages; imaging finding plausible but doesn't match the reference framing | 138s / 11.4 | 159s / 14.0 |

### Tier C

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `medgemma-4b-it` (production) | Solid lab/report; vague (not wrong) on imaging. **Two real weaknesses**: leaks Romanian on `pre_exam` when asked for English, leaks English on `lab` when asked for Romanian, plus a recurring date-fabrication on `pre_exam` in both languages | 204s / 7.4 | 333s / 5.1 |
| `granite-4.1-3b` | Fabrication-free on lab/report/pre_exam in English, only wrong (not fabricated) on imaging. **Fabricates in Romanian**: invents hydrocephalus on `lab`, a choledochal cyst on `pre_exam` | 135s / 8.6 | 89s / 9.1 |
| `nvidia/nemotron-3-nano-4b` | Terse and correct in English (one Romanian term-leak on imaging). **Degenerates into a repetition loop** on Romanian `lab` | 115s / 8.3 | 114s / 11.3 |
| `qwen3-0.6b` (`/no_think`) | Clean but thin/generic content in English. Leaks English on Romanian `lab` | 46s / 24.8 | 45s / 25.1 |
| `lmstudio-community/qwen3.5-2b` | Misses the diagnosis entirely on English `pre_exam` ("liver cirrhosis"); correct on the same kind in Romanian — inconsistent | 65s / 19.7 | 94s / 15.7 |
| `google/gemma-3n-e2b` | Vague on imaging; **terminology hallucination** on `report` — calls the Kasai procedure a "liver transplant" (no transplant occurred) | 62s / 12.3 | 62s / 14.1 |
| `llama-3.2-1b-instruct` | Garbled/invented term on English imaging, otherwise decent. **Fabricates an ERCP procedure** that never happened, in Romanian `pre_exam` | 54s / 26.8 | 106s / 15.4 |
| `llama-3.2-3b-instruct` | Wrong diagnosis on English imaging. In Romanian: language leak **and** a fact inversion (claims "febrile" where source says "afebrile"), plus a fabricated "deteriorated condition" on `pre_exam` | 119s / 8.9 | 127s / 10.7 |

### Tier D

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `medgemma-1.5-4b-it` | **Breaks entirely** on English `pre_exam` — leaks raw chain-of-thought tokens, burns the full budget, never answers. Also fact-inverts on imaging, fabricates on report. Notably clean in Romanian on all 4 kinds — may be English-specific (see follow-up #7 in the detailed doc), not yet safe to write off or promote | 246s / 7.0 | 160s / 11.7 |
| `google/gemma-3-4b` | Mostly correct in English. **Fabricates a diagnosis** ("Fetal growth restriction", "Gastroschisis" — neither in the source) on Romanian `pre_exam` | 95s / 9.0 | 132s / 9.0 |
| `google/gemma-3-1b` | Correct diagnosis in English. In Romanian: **fabrication + fact inversion** on `pre_exam` (claims a normal ultrasound when the source shows multiple abnormal findings), and an outright non-answer on `report` | 45s / 24.7 | 34s / 29.6 |
| `lfm2.5-1.2b-instruct` | Wrong diagnosis on English imaging, otherwise decent. **Heavy fabrication in Romanian**: invents a CT scan, a pancreatic mass, and a cholecystectomy — none occurred | 20s / 30.0 | 34s / 23.8 |
| `lfm2.5-vl-1.6b` | Hallucinates portal hypertension and contradicts the core diagnosis on English `report`. In Romanian: fabricates an absurd patient weight and lists a surgical procedure under "imaging protocol" (category confusion) | 39s / 31.2 | 51s / 35.9 |

### Tier F — not viable, no further evaluation planned without a fix

| Model | Failure |
|---|---|
| `glm-edge-4b-chat` | Hard 3072-token context ceiling (architectural, not configurable) — crashes `report`/`pre_exam` |
| `tinyllama-1.1b-chat-v1.0` | Context length (2048) too small for `report`/`pre_exam` |
| `phi-3.1-mini-4k-instruct` | Incoherent garbled output on `report`, crashes on `pre_exam` |
| `microsoft/phi-4-mini-reasoning` | Unsuppressable reasoning leak, consumes entire token budget every kind |
| `qwen3.5-2b-claude-4.6-opus-reasoning-distilled` | Unsuppressable reasoning leak (confirmed: `/no_think`, `chat_template_kwargs`, and a guessed `enable_reasoning` all fail to stop it) |
| `qwen3.5-4b-claude-4.6-opus-reasoning-distilled-v2` | Same as above |
| `lfm2.5-1.2b-thinking` | Unsuppressable reasoning leak |
| `lfm2.5-8b-a1b` | Unsuppressable reasoning leak |
| `lfm2.5-350m` | Nonsense one-word non-answers |
| `lfm2-350m-extract` | Wrong output shape entirely — a JSON extractor, not a prose summarizer |
| `functiongemma-270m-it` | Function-calling model; refuses free-text summarization outright |
| `gemma-3-270m-it` | Too small — empty output or meta-commentary instead of an answer |
| `gemma-4-e2b-it` | Server-side load failure (`"Error loading model."`) |
| `phi-4-mini-instruct` | Untested — download corrupted after repeated resumes, fails to load; no delete endpoint or filesystem access available to retry cleanly |

## Phase 2: confirmation on 4 independent real fixtures

Everything above (Phase 1) used a single fixture — the `ciobotaru`
biliary-atresia case — repeated across every model and kind. That's real
production data, but it's one patient, one specialty, one writing style.
Before trusting Phase 1's `qwen/qwen3-4b` win, the four closest contenders
were re-tested on 4 more real, independent fixtures pulled from
`_testing_/cases_2`/`cases_3`/`cases_4`/`cases_replacement` (65 real,
previously de-identified-in-docs case folders used earlier to fine-tune the
production prompts) — chosen for size and content-style diversity, not
cherry-picked for outcome:

- **Case A** (345 B) — pediatric orthopedics, bilateral equinus foot
  deformity, clean narrative prose.
- **Case B** (1.6 KB) — pediatric cardiology, dense structured
  echocardiogram/ECG findings.
- **Case C** (4.0 KB) — a **discharge-instructions sheet with no clinical
  narrative at all** (vaccination schedule, sleep hygiene, quarantine
  rules) — found by accident during selection, kept deliberately because it
  tests whether a model can recognize "there's nothing to summarize here"
  rather than inventing content to fill the expected shape.
- **Case D** (9.4 KB) — pediatric oncology, high-risk hepatoblastoma,
  chemotherapy + surgery across a multi-month course — the most complex
  fixture tested in either phase.

Models: `qwen/qwen3-4b`, `qwen3-4b-instruct-2507`, `lmstudio-community/
qwen3.5-4b`, and production `medgemma-4b-it`, on `report` (the kind where
Phase 1's `qwen3-4b`-family discrepancy showed up), English, same
2-warm-iteration settings. Cases are referenced by letter only — the source
`case_data.json` files contain real patient names, kept out of anything
committed, same convention as the rest of this doc.

### Results

| Case | `qwen/qwen3-4b` | `qwen3-4b-instruct-2507` | `qwen3.5-4b` | `medgemma-4b-it` |
|---|---|---|---|---|
| A (ortho) | ✅ correct | ❌ mistranslates diagnosis as "polyneuropathy" (source: equinus **foot** deformity) | ✅ correct (verbose) | ✅ correct |
| B (cardio) | ✅ correct | ✅ correct | ✅ correct | ❌ **fabricates** "a pericardial effusion" — source explicitly says "Pericard liber" (pericardium clear, no effusion) |
| C (no clinical content) | ❌ **fabricates** an admission narrative ("admitted for respiratory symptoms... treated with a course of respiratory therapy") — none of this is in the source | ✅ correctly answers "Insufficient clinical information to summarize" | ✅ same correct non-answer | ❌ **fabricates** ("admitted for vaccination schedule and respiratory health management") |
| D (oncology) | ✅ correct but thin (misses most of the clinical detail) | ✅ correct and detailed (tumor regression measurements, RS hypoplasia, port removal/reinsertion — all verified against source) | ✅ correct and detailed (transfer destination, wound status, port history — all verified) | ⚠️ **Romanian-language leak** again despite `--language English`; the portion produced before truncation appears factually sound |
| **Score** | **3/4** | **3/4** | **4/4** | **1/4** |

### What this changes

1. **`qwen/qwen3-4b`'s Phase 1 perfection didn't generalize.** It fabricated
   on the one fixture that was genuinely different in kind (no real clinical
   content to summarize) rather than just different in specialty or length.
   This is exactly the failure mode Phase 1 couldn't have caught, since
   every Phase 1 kind always had real clinical content to work with.
2. **`qwen3-4b-instruct-2507`'s Phase 1 flaw (report-kind fact inversion) is
   confirmed as a real, recurring pattern** — Case A produced a *different*
   translation error (not a repeat of the same bile-duct-dilation mistake),
   meaning this model has a general reliability gap on terminology under
   translation pressure, not a one-off quirk tied to that specific finding.
   Notably, it also produced the most detailed, accurate summary of Case D,
   the hardest fixture in either phase — it's inconsistent, not uniformly
   weak.
3. **`qwen3.5-4b` is now the most-validated model across both phases** —
   clean on every kind of the original case and clean on all 4 independent
   fixtures, including correctly declining to summarize Case C rather than
   inventing content. It's the only model tested twice with a perfect
   second-round score.
4. **`medgemma-4b-it` picked up a new, previously undocumented failure
   mode**: fact-inversion by omission-reversal (claiming a finding that the
   source explicitly negates, not just a vague/incomplete answer as seen in
   Phase 1's `imaging` result). Combined with its two already-documented
   Phase 1 weaknesses (bidirectional language leaking, a recurring
   date-fabrication), this is the third distinct reliability issue found
   for the current production model across this whole survey.
5. **The Case C result is the most important methodological finding of
   Phase 2**: half the models tested (`qwen3-4b`, `medgemma-4b-it`)
   fabricate a clinical narrative rather than recognizing there's nothing to
   summarize. This is a real production risk independent of which model
   ships — worth a prompt-level fix (an explicit instruction to say "no
   clinical content to summarize" when the source is administrative/
   instructional rather than clinical) regardless of which model is chosen,
   since even the winner of this report could hit a similar edge case.

## Phase 3: current production (`ministral-3-3b-instruct-2512`) tested for the first time

Every prior round referenced production as the incumbent baseline without
ever actually benchmarking it under this methodology. Run here for the
first time: full Phase 1 parity (imaging/lab/report/pre_exam × English +
Romanian, same fixture as Phase 1) plus all 4 Phase 2 independent cases,
`report` kind, English — the same 12-run battery `qwen3.5-4b` and the other
top contenders went through.

### Phase 1 parity (Ciobotaru case, both languages)

| Kind | English | Romanian |
|---|---|---|
| imaging | ✅ correct | ✅ correct |
| lab | ✅ correct | ❌ **fabricates a "hemolysis syndrome" diagnosis** — not supported by the panel given (no reticulocyte count, LDH, or haptoglobin data to establish hemolysis) |
| report | ❌ **fabricates family history** — "a history of paternal grandfather's unspecified cardiac conditions requiring long-term monitoring" appears nowhere in the source | ⚠️ minor: nonsense compound term "echocardiografia abdominală" (mixes echocardiography/abdominal ultrasound); clinical content otherwise accurate |
| pre_exam | ❌ **fabricates a liver-transplant workup**: "pediatric liver transplant evaluation," "follow-up liver transplant candidate" — this is a post-Kasai case, no transplant was ever considered in the source; also the recurring stray-header-date fabrication | ⚠️ correct primary diagnosis, but invents a **duplicate surgical event** — lists a fabricated second Kasai procedure under the stray date, separate from the real 07/11/2025 surgery |

Score: **2/8 fully clean**, 3 clear fabrications, 3 minor-but-real issues.

### Phase 2 (4 independent cases, `report`, English)

| Case | Result |
|---|---|
| A (ortho) | ❌ **wrongly refuses** — "Insufficient clinical information to summarize" for a case that has a real diagnosis, a consult finding, and a treatment decision |
| B (cardio) | ✅ accurate, correctly avoids the pericardial-effusion trap that caught `medgemma-4b-it` |
| C (no clinical content) | ✅ correctly declines — this is the one case where declining is right |
| D (oncology) | ✅ accurate and reasonably detailed |

Score: **3/4**, but the A/C pattern is a flag on its own: ministral declined
twice out of four cases, right once (C, genuinely empty) and wrong once (A,
real content present). That reads less like principled recognition of
"nothing to summarize" and more like a general bias toward declining —
worth treating the 3/4 score with more caution than the same score earned
by `qwen3-4b`/`qwen3-4b-instruct-2507`, which never triggered a false
refusal.

### What this means

Production has now been tested apples-to-apples against every candidate in
this report, for the first time. It does **not** hold up well: 5 of the 12
runs had a real, verifiable problem — three outright fabrications
(including inventing an entire liver-transplant care pathway for a patient
who never needed one) and a refusal-bias pattern that misfires on real
content. This is the weakest showing of any Tier-A/B/C-caliber model tested
in either phase, `medgemma-4b-it` included. It reinforces rather than
weakens the case for moving off current production — the question is no
longer "is production good enough to keep by default," it's "which
candidate replaces it," and this report's answer is `qwen3.5-4b`.

`gemma-3n-e4b` (the documented fallback) remains untested — same caveat as
before, now narrower in scope.

Full evidence, source-text verification notes, and raw output samples for
every row above are in `docs/llm_benchmark_2026-07-31.md`; raw JSON/markdown
dumps are in `_testing_/r31*`/`r32_b*`/`r34_ministral_*` (Phase 1/Romanian/
Ministral) and `_testing_/r33_case*`/`r34_case*` (Phase 2, both
`qwen`-family models and ministral), gitignored but retained locally.
