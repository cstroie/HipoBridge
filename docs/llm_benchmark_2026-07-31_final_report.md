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

**Updated again after Phase 2's extension** (5 more cases, 9 total, plus the
`pre_exam` kind added on top of `report` — see below). The verdict changed
twice over the course of this report, each time because more evidence
surfaced a failure mode the prior round couldn't see. The final read,
weighing **severity, not just raw fail count**:

**`qwen/qwen3-4b`** is the recommendation. Across 17 independent test cells
(9 cases × `report`, 8 of those 9 also × `pre_exam`) it had the fewest hard
failures (2 of 17) and — critically — **zero severe or dangerous
hallucinations**. Its failures are a language leak on one case and a
fabricated narrative on the one case that had no real clinical content to
summarize (and even that one self-corrected under `pre_exam`'s stricter
format on the same case). `lmstudio-community/qwen3.5-4b`, this report's
prior pick, looked cleanest on `report` alone (7/9) but a **specific,
twice-independently-observed pattern** emerged under `pre_exam`: it inflates
a routine ward readmission into an "ICU" admission when the source never
says ICU (Cases D and H, unrelated specialties, same specific error) — a
clinically meaningful acuity-escalation error, not just an omission.
`qwen3-4b-instruct-2507` has the most hard failures (5/17) but none severe —
a "death by a thousand cuts" profile (translation slips, a recurring
"HTP"→general-hypertension terminology confusion, one serious organ
conflation). `medgemma-4b-it` is decisively worst: 10/17 hard failures,
including two of the most severe hallucinations found anywhere in this
survey — a fully invented pneumonia hospitalization for a source with zero
patient history, and an asserted epilepsy diagnosis that contradicts its
own correctly-quoted "normal EEG" finding two lines later in the same
output.

**Recommendation**: promote `qwen/qwen3-4b` — non-critical kinds first
(`lab`, its fastest and cleanest kind), full rollout after a third fixture
confirms the pattern holds. `qwen3.5-4b` is a strong second choice but the
ICU-inflation pattern needs a prompt-level fix (explicit instruction not to
infer care-level/unit from an unstated admission) before it's trusted for
`pre_exam`-style outputs specifically. `qwen3-4b-instruct-2507` is usable
but the higher error frequency makes it the third choice among the three
Qwen variants. `medgemma-4b-it` should not continue as a recommended
fallback — see the keep/remove list below.

**If speed matters more than this report's tiering implies**: within
Tier A/B (the only tiers worth deploying), `qwen/qwen3-vl-4b` was the
fastest option holding up under fact-checking in Phase 1 — not
Phase-2-tested, so treat that speed edge with the same caution this report
just demonstrated is necessary for any Phase-1-only result.

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
3. **`qwen3.5-4b` looked like the most-validated model at this point** —
   clean on every kind of the original case and clean on all 4 independent
   fixtures, including correctly declining to summarize Case C rather than
   inventing content. **This did not hold up under the Phase 2 extension**
   (5 more cases, plus `pre_exam`) — see below, a recurring acuity-inflation
   pattern emerged that this narrower 4-case batch was too small to catch.
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

## Phase 2 extended: 5 more cases, plus `pre_exam`

The original Phase 2 (4 cases, `report` only) was too small to trust a
ranking built on a single-case margin between the top 3 contenders. Added:
5 more real fixtures (Cases E-I, from the same `_testing_/cases_*` pool,
chosen for specialty/size diversity — hepatology, ENT, febrile-infant
pediatrics, cardiology/Holter, and a dense infant-respiratory case with a
confirmed pertussis co-infection) and the `pre_exam` kind on 8 of the 9
cases total (Case A excluded — at 345 bytes, too small to meaningfully
stress a 1300-token synthesis prompt). Same 4 models, same settings. This
brings the total evidence base to **17 independent test cells per model**.

### Full scorecard

| | `report` (9 cases) | `pre_exam` (8 cases) | Combined |
|---|---|---|---|
| `qwen/qwen3-4b` | 6 clean, 2 fail, 1 minor | 5 clean, 0 fail, 3 minor | **11 clean, 2 fail, 4 minor** |
| `qwen3-4b-instruct-2507` | 5 clean, 3 fail, 1 minor | 4 clean, 2 fail, 2 minor | 9 clean, 5 fail, 3 minor |
| `lmstudio-community/qwen3.5-4b` | 7 clean, 1 fail, 1 minor | 3 clean, 3 fail, 2 minor | 10 clean, 4 fail, 3 minor |
| `medgemma-4b-it` | 2 clean, 5 fail, 2 minor | 2 clean, 5 fail, 1 minor | 4 clean, 10 fail, 3 minor |

"Fail" = a real, verifiable error (fabrication, fact inversion, language
leak, or a mistranslation changing clinical meaning). "Minor" = a real but
lower-stakes issue (imprecise terminology, unsupported-but-plausible
inference in the AI-suggestions section, thinness/omission without an
active false claim).

### New findings from the extension

1. **`qwen3.5-4b`'s recurring "ICU inflation" pattern** — the most
   significant new finding. On Case H (`pre_exam`) it wrote "readmitted to
   the Cardiology **ICU**" when the source says "secția Cardiologie" (a
   ward, not an ICU, and no acuity escalation is documented). On Case D
   (`pre_exam`), independently, the same pattern: "Postoperative recovery...
   in the **ICU**/PED setting" when the source only documents a hospital
   transfer, not an ICU admission. Two unrelated cases, same specific
   fabricated detail — this reads as a systematic bias (perhaps toward
   assuming post-op pediatric patients default to ICU-level care) rather
   than a one-off. This is a clinically meaningful error class: it could
   cause a clinician to over-triage or misjudge acuity from an AI summary.
2. **`medgemma-4b-it`'s two most severe hallucinations in the entire
   survey, both found in this extension**: on Case C's `pre_exam` (a source
   with zero patient history — vaccination/hygiene instructions only), it
   invented a complete fictional pneumonia hospitalization with specific
   dates and a chest X-ray. On Case H's `pre_exam`, it asserted "**Epileptic
   seizures**" as the lead diagnosis while its own `History` section, two
   lines later, correctly quotes the source's normal EEG and normal
   neurology consult that specifically ruled epilepsy out — a
   self-contradicting hallucination within a single output.
3. **`qwen3-4b-instruct-2507`'s "HTP" terminology confusion is confirmed
   recurring, not a one-off**: it appeared on Case B under both `report`
   ("no evidence of hypertension") and `pre_exam` ("hypertensive crisis
   unlikely") — the source's "HTP" abbreviation means pulmonary
   hypertension in this context, not general/systemic hypertension. Same
   specific misreading, twice, independently.
4. **A second universal, prompt-induced fabrication trap, distinct from
   Case C's "no content" trap**: Cases E and F have real clinical content
   but **no dates anywhere** in the source (only relative durations like
   "on Entecavir for 4 years"). Every model, on every kind, invented
   specific absolute dates to fill the `pre_exam` template's date-bullet
   `History` format — none consistently used `[not available]` for missing
   dates the way several did for Case C's missing content overall. This is
   a second, independent prompt-level fix worth making regardless of model
   choice: the History section's format should explicitly permit
   date-free entries when the source only gives relative timing.
5. **The Case I `report`-kind omission (missing the confirmed Bordetella
   pertussis diagnosis, noted in the first Phase 2 extension pass) turned
   out to be a token-budget artifact, not a blind spot**: under `pre_exam`'s
   1300-token budget on the same case, all 4 models correctly surfaced the
   pertussis PCR result. `report`'s 340-token budget is tight enough that
   even correct models can drop the single most decisive finding when a
   case is this information-dense — worth knowing independent of which
   model ships, since it affects prompt/budget design for `report` specifically.
6. **Genuine mistranslations, not just omissions, recur across models and
   cases**: `medgemma-4b-it` alone produced three in one case (Case H) —
   "maternal aunt" → "maternal grandmother," an Apgar score of 9 → "length
   9cm," and "hipotonie" (low muscle tone) → "hypotension" (low blood
   pressure). These are Romanian medical-abbreviation and terminology traps
   independent of the broader hallucination-vs-fabrication distinction —
   worth a targeted glossary/prompt hint (SA = Apgar score, HTP = pulmonary
   hypertension, RS = context-dependent for suprarenal gland vs. right
   side) if any model in this family stays under consideration.

## Keep vs. remove

Based on all evidence in this report (Phase 1 English + Romanian, Phase 2's
9-case/17-cell extension, and Phase 3's ministral test):

**Keep / promote**:
- **`qwen/qwen3-4b`** — recommended for staged production rollout. Fewest
  hard failures, zero severe hallucinations found across 17 test cells in
  either phase.
- **`lmstudio-community/qwen3.5-4b`** — keep as a strong second candidate,
  contingent on fixing the ICU-inflation pattern (prompt-level: explicit
  instruction against inferring care level/unit from an unstated
  admission) before trusting it for `pre_exam`-style outputs.

**Keep in consideration, not lead candidates**:
- **`qwen3-4b-instruct-2507`** — no severe errors, but the highest hard-fail
  rate of the three Qwen variants (5/17). Usable as a fallback option if
  either of the above is unavailable, not a first choice.
- **`nvidia/nemotron-3-nano-4b`, `qwen/qwen3-vl-4b`** (Phase 1 only,
  Tier B/C) — plausible secondary options per the original tier ranking,
  not yet subjected to the Phase 2 extension's scrutiny; treat any
  Phase-1-only standing with the same caution this report just
  demonstrated is warranted.

**Remove from consideration**:
- **`medgemma-4b-it`** — despite being the current de facto fallback
  referenced in the 07-19/07-21 rounds, this survey found it decisively
  the worst of the four seriously-tested candidates: 10/17 hard failures,
  including two of the most severe, dangerous hallucinations found
  anywhere in this whole survey (a fully fabricated hospitalization, and a
  self-contradicting epilepsy diagnosis). Do not carry forward as a
  fallback without a fresh, favorable re-test — the evidence here doesn't
  support it.
- **`ministral-3-3b-instruct-2512`** (current production) — Phase 3 found
  it the weakest model tested against the incumbent-candidate battery: 3
  outright fabrications (including inventing an entire liver-transplant
  care pathway) and a refusal-bias pattern that misfires on real clinical
  content. The question is no longer whether to replace it, but which
  candidate replaces it — this report's answer is `qwen/qwen3-4b`.
- **Every Tier D/F model** from the original 33-model survey (see the
  Ranked Comparison section above) — architecturally broken, wrong-tool,
  unsuppressable reasoning leaks, or frequent fabrication already
  documented there; nothing in Phase 2/3 changes that assessment.

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
