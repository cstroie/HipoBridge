# On-device LLM survey — final report and rankings (2026-08-02)

Consolidates every model, phase, and fix attempt in `docs/llm_benchmark_2026-07-31.md`:
33 models in English (Phase 1), 19 retested in Romanian, 5 models on 9
independent real fixtures across `report` and `pre_exam` (Phase 2 +
Phase 2 extended), and one prompt-fix attempt that was tested and reverted
(Phase 4). Ranked **quality first, speed second** — a fast model that
fabricates or leaks language is not a candidate, full stop. Speed only
breaks ties among models judged similarly reliable.

This is a rebuild, not a patch. The prior version of this report split its
evidence across this file and the detailed doc, drifted into an internal
contradiction (naming both `qwen/qwen3-4b` and `qwen3.5-4b` as "the"
answer in different sections), and overstated `qwen/qwen3-4b`'s Phase 1
record as clean on all 4 kinds in both languages when its own `imaging`
row shows an English-round Romanian leak. All of that is fixed in the
detailed doc and carried through here. Every table below is pulled
verbatim from `llm_benchmark_2026-07-31.md`, not re-derived.

## The finish line

**`qwen/qwen3-4b`** is the recommendation, but not on the strength of a
spotless record — it doesn't have one, and no model in this survey does.
Across the 17-cell Phase 2 extended battery (9 cases × `report`, 8 of
those 9 also × `pre_exam`, run against `qwen/qwen3-4b`,
`qwen3-4b-instruct-2507`, `lmstudio-community/qwen3.5-4b`,
`medgemma-4b-it`, and `ministral-3-3b-instruct-2512`) it has the fewest
hard failures (2/17: a language leak on one case, and a fabrication on the
one case with no real clinical content to summarize) and, critically, no
severe or dangerous hallucination on a fixture with real patient content —
its worst failure is confined to Case C, the one fixture deliberately
constructed to have nothing clinical in it at all. It also has a
**confirmed, uncorrected gap**: an English-round `imaging` language leak
in Phase 1 (answered in Romanian despite `--language English`), and the
Case C fabrication recurred, unresolved, in the Phase 4 retest on an
attempted (then reverted) prompt fix. Neither is severe enough to change
the recommendation, but neither should be forgotten either.

`lmstudio-community/qwen3.5-4b` remains the strongest alternative and, on
a narrower reading, the more careful model in Phase 1 (Tier A vs.
`qwen3-4b`'s corrected Tier B — see below). It picked up a real, clinically
meaningful problem in Phase 2 extended: a recurring **ICU-inflation**
pattern, independently repeated on two unrelated cases (D and H),
inflating a routine ward admission or hospital transfer into an ICU stay
with no acuity evidence. A Phase 4 prompt fix resolved it on Case D but
**not** on Case H — same model, same fabrication, prompt guard only
partially effective — so this is not yet a solved problem, and the fix
that partially addressed it was reverted rather than shipped (see Phase 4
below).

`qwen3-4b-instruct-2507` has the most hard failures of the three Qwen
variants (5/17) but none severe — a "death by a thousand cuts" profile
(translation slips, a recurring "HTP"→general-hypertension confusion, one
serious organ conflation on Phase 2's Case A). `medgemma-4b-it` is
decisively worst of the four originally-tested candidates: 10/17 hard
failures, including two of the most severe hallucinations found anywhere
in this survey (a fully invented pneumonia hospitalization for a source
with zero patient history, and a self-contradicting epilepsy diagnosis).
`ministral-3-3b-instruct-2512` — current production, benchmarked at full
parity for the first time this round — is second-worst: 7 clean, 8 fail, 2
minor across the same 17 cells, including its own worst hallucination of
the whole survey (a fabricated "chronic respiratory disease" diagnosis
with a full differential, invented from the same no-content Case C
fixture that only produced a minor fabrication from the other models).

**Recommendation**: promote `qwen/qwen3-4b` — non-critical kinds first
(`lab`, its cleanest kind with zero recorded failures anywhere in this
survey), full rollout contingent on a fix for the Case C no-content trap,
which is a real production risk independent of which model ships (see
Phase 2's finding #5 and the Phase 4 retest, both in the detailed doc).
`qwen3.5-4b` is the strongest second choice, contingent on actually fixing
(not just partially fixing) the ICU-inflation pattern. Do not carry
`ministral` or `medgemma-4b-it` forward as production/fallback without a
fresh, favorable re-test — the evidence here doesn't support either.

## Tier definitions

| Tier | Meaning |
|---|---|
| **S** | Fabrication-free, correct language, all 4 kinds, in every language tested |
| **A** | Fabrication-free; one narrow, contained issue (not a core-fact error) |
| **B** | Usable; one real but isolated failure (wrong diagnosis on the shortest kind, a terminology slip, or a language leak confined to one kind) |
| **C** | Real reliability problem — recurring fabrication, a language leak on a core kind, or a diagnosis miss — but still partially usable |
| **D** | Frequently broken — fabrication or a severe breakdown in at least one language, not safe to deploy as-is |
| **F** | Unusable — architectural failure (won't load, context ceiling, wrong output shape) or an unsuppressable reasoning leak that eats the entire token budget |

## Ranked comparison — Phase 1 (corrected)

Speed columns: **Σt** = total wall-clock seconds for one full 4-kind
battery (warm runs); **tok/s** = weighted throughput across those 4 kinds.
Dash = not retested in that language. **Correction from the prior version
of this report**: `qwen/qwen3-4b` was previously listed alone in Tier S
("clean on all 4 kinds in both languages"). Its own `imaging` result
(English round) answers in Romanian — a language leak confined to one
kind, matching the Tier B definition exactly, not Tier S. Tier S has no
occupant this round.

### Tier A

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `lmstudio-community/qwen3.5-4b` | Clean on imaging/lab/report both languages; `pre_exam` has a narrow garbled-date + one ungrounded inference (English only) — not a core-fact error. **Since this tier assignment**: picked up a recurring ICU-inflation pattern in Phase 2 extended (see below) — a real, more clinically consequential issue than anything found in Phase 1 | 179s / 6.6 | 204s / 6.6 |

### Tier B

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `qwen/qwen3-4b` | Clean on `lab`/`report`/`pre_exam` in both languages (best-in-round faithful `pre_exam` output); `imaging` leaks into Romanian despite `--language English` — a language leak confined to one kind. **Since this tier assignment**: best combined record in Phase 2 extended (11 clean/2 fail/4 minor, fewest hard failures of any model tested there) but its one hard failure recurs on the same case (Case C) across both Phase 2 and the Phase 4 retest | 133s / 5.3 | 162s / 6.1 |
| `qwen/qwen3-vl-4b` | Correct on imaging/lab/pre_exam; one fact-inversion on `report` only (bile-duct-dilation status) — "short-kind dilution" pattern | 118s / 7.6 | 177s / 8.3 |
| `qwen3-4b-instruct-2507` | Same report-kind fact-inversion as `qwen3-vl-4b`; corrects itself on `pre_exam`; clean in Romanian. **Since this tier assignment**: highest hard-fail rate of the three Qwen variants in Phase 2 extended (5/17), none severe | 193s / 5.9 | 263s / 6.0 |
| `qwen3-1.7b` (`/no_think`) | Clean, faithful, correct language on report/lab/pre_exam both languages; imaging diagnosis is off-target (not fabricated, just wrong) in both | 84s / 16.3 | 85s / 14.7 |
| `lfm2-2.6b-transcript` | Faithful on report/lab/pre_exam both languages; imaging finding plausible but doesn't match the reference framing | 138s / 11.4 | 159s / 14.0 |

### Tier C

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `medgemma-4b-it` (production baseline) | Solid lab/report; vague (not wrong) on imaging. Leaks Romanian on `pre_exam` when asked for English, leaks English on `lab` when asked for Romanian, plus a recurring date-fabrication on `pre_exam` in both languages. **Since this tier assignment**: decisively worst of the 5 models in Phase 2 extended (10/17 hard failures, including two of the most severe hallucinations in this whole survey) | 204s / 7.4 | 333s / 5.1 |
| `granite-4.1-3b` | Fabrication-free on lab/report/pre_exam in English, only wrong (not fabricated) on imaging. Fabricates in Romanian: invents hydrocephalus on `lab`, a choledochal cyst on `pre_exam` | 135s / 8.6 | 89s / 9.1 |
| `nvidia/nemotron-3-nano-4b` | Terse and correct in English (one Romanian term-leak on imaging). Degenerates into a repetition loop on Romanian `lab` | 115s / 8.3 | 114s / 11.3 |
| `qwen3-0.6b` (`/no_think`) | Clean but thin/generic content in English. Leaks English on Romanian `lab` | 46s / 24.8 | 45s / 25.1 |
| `lmstudio-community/qwen3.5-2b` | Misses the diagnosis entirely on English `pre_exam` ("liver cirrhosis"); correct on the same kind in Romanian — inconsistent | 65s / 19.7 | 94s / 15.7 |
| `google/gemma-3n-e2b` | Vague on imaging; terminology hallucination on `report` — calls the Kasai procedure a "liver transplant" | 62s / 12.3 | 62s / 14.1 |
| `llama-3.2-1b-instruct` | Garbled/invented term on English imaging, otherwise decent. Fabricates an ERCP procedure that never happened, in Romanian `pre_exam` | 54s / 26.8 | 106s / 15.4 |
| `llama-3.2-3b-instruct` | Wrong diagnosis on English imaging. In Romanian: language leak and a fact inversion (claims "febrile" where source says "afebrile"), plus a fabricated "deteriorated condition" on `pre_exam` | 119s / 8.9 | 127s / 10.7 |

### Tier D

| Model | Quality note | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|---|
| `medgemma-1.5-4b-it` | Breaks entirely on English `pre_exam` — leaks raw chain-of-thought tokens, burns the full budget, never answers. Also fact-inverts on imaging, fabricates on report. Clean in Romanian on all 4 kinds | 246s / 7.0 | 160s / 11.7 |
| `google/gemma-3-4b` | Mostly correct in English. Fabricates a diagnosis ("Fetal growth restriction", "Gastroschisis") on Romanian `pre_exam` | 95s / 9.0 | 132s / 9.0 |
| `google/gemma-3-1b` | Correct diagnosis in English. In Romanian: fabrication + fact inversion on `pre_exam`, and an outright non-answer on `report` | 45s / 24.7 | 34s / 29.6 |
| `lfm2.5-1.2b-instruct` | Wrong diagnosis on English imaging, otherwise decent. Heavy fabrication in Romanian: invents a CT scan, a pancreatic mass, and a cholecystectomy | 20s / 30.0 | 34s / 23.8 |
| `lfm2.5-vl-1.6b` | Hallucinates portal hypertension and contradicts the core diagnosis on English `report`. In Romanian: fabricates an absurd patient weight and category-confuses a procedure into "imaging protocol" | 39s / 31.2 | 51s / 35.9 |

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
| `gemma-4-e2b-it` | Server-side load failure. **Checked, not retested**: 4.41 GB on disk, over this hardware's ~4 GB single-card VRAM ceiling — the failure is consistent with genuinely not fitting, not a transient issue |
| `phi-4-mini-instruct` | Untested — download corrupted after repeated resumes, fails to load; no delete endpoint or filesystem access available to retry cleanly |
| `google/gemma-3n-e4b` | The documented fallback model, referenced but never benchmarked in any round through 07-19/07-21. **Checked, not tested**: 4.24 GB on disk, also over the ~4 GB VRAM ceiling — not a realistic candidate for this hardware regardless of quality |

## Phase 2: 4 independent real fixtures, `report` kind

Everything in Phase 1 used a single fixture repeated across every model
and kind. Phase 2 re-tests the four closest Phase 1 contenders, plus
`ministral-3-3b-instruct-2512` (current production, tested separately),
on 4 more real, independent fixtures: Case A (pediatric orthopedics),
Case B (pediatric cardiology), Case C (a discharge-instructions sheet
with **no clinical narrative at all** — tests whether a model recognizes
"nothing to summarize" instead of inventing content), and Case D
(pediatric oncology, the most complex fixture in either phase).

| Case | `qwen/qwen3-4b` | `qwen3-4b-instruct-2507` | `qwen3.5-4b` | `medgemma-4b-it` | `ministral-3-3b-instruct-2512` (production) |
|---|---|---|---|---|---|
| A (ortho) | ✅ correct | ❌ mistranslates diagnosis as "polyneuropathy" | ✅ correct (verbose) | ✅ correct | ❌ wrongly refuses — real content present |
| B (cardio) | ✅ correct | ✅ correct | ✅ correct | ❌ fabricates a pericardial effusion the source explicitly negates | ✅ accurate, avoids the same trap |
| C (no clinical content) | ❌ fabricates an admission narrative | ✅ correctly declines | ✅ correctly declines | ❌ fabricates an admission narrative | ✅ correctly declines |
| D (oncology) | ✅ correct but thin | ✅ correct and detailed | ✅ correct and detailed | ⚠️ Romanian-language leak | ✅ accurate and reasonably detailed |
| **Score** | **3/4** | **3/4** | **4/4** | **1/4** | **3/4** |

`ministral`'s 3/4 needs a caveat the others don't: it declined twice (once
right, on genuinely-empty Case C; once wrong, on Case A which has real
content) — a general refusal bias, not principled recognition of "nothing
to summarize."

**Most important finding**: half the models tested (`qwen3-4b`,
`medgemma-4b-it`) fabricate a clinical narrative on Case C rather than
recognizing there's nothing to summarize — a real production risk
independent of which model ships, and one that recurred, unfixed, in the
Phase 4 retest (see below). Full findings: `llm_benchmark_2026-07-31.md`'s
"Phase 2" section.

## Phase 2 extended: 5 more cases, plus `pre_exam`, all 5 models

Adds Cases E-I (hepatology, ENT, febrile-infant pediatrics,
cardiology/Holter, and a dense infant-respiratory case with confirmed
pertussis) and the `pre_exam` kind on 8 of the 9 cases (Case A excluded —
too small to stress the format). `ministral` was closed out to full parity
after the fact — all 5 models below now have the same 17-cell evidence
base (9 `report` + 8 `pre_exam`).

| | `report` (9 cases) | `pre_exam` (8 cases) | Combined |
|---|---|---|---|
| `qwen/qwen3-4b` | 6 clean, 2 fail, 1 minor | 5 clean, 0 fail, 3 minor | **11 clean, 2 fail, 4 minor** |
| `qwen3-4b-instruct-2507` | 5 clean, 3 fail, 1 minor | 4 clean, 2 fail, 2 minor | 9 clean, 5 fail, 3 minor |
| `lmstudio-community/qwen3.5-4b` | 7 clean, 1 fail, 1 minor | 3 clean, 3 fail, 2 minor | 10 clean, 4 fail, 3 minor |
| `ministral-3-3b-instruct-2512` (production) | 5 clean, 3 fail, 1 minor | 2 clean, 5 fail, 1 minor | 7 clean, 8 fail, 2 minor |
| `medgemma-4b-it` | 2 clean, 5 fail, 2 minor | 2 clean, 5 fail, 1 minor | 4 clean, 10 fail, 3 minor |

"Fail" = fabrication, fact inversion, language leak, or a mistranslation
changing clinical meaning. "Minor" = imprecise terminology,
unsupported-but-plausible inference, or thinness/omission without an
active false claim.

**Headline findings** (full detail, including `ministral`'s own findings
7-10, in the detailed doc):

1. `qwen3.5-4b`'s recurring **ICU-inflation** pattern, independently on
   Cases D and H — a clinically meaningful acuity-escalation error.
2. `medgemma-4b-it`'s two most severe hallucinations in the whole survey:
   a fully invented pneumonia hospitalization on Case C, and a
   self-contradicting epilepsy diagnosis on Case H.
3. `qwen3-4b-instruct-2507`'s "HTP" (pulmonary hypertension) terminology
   confusion, confirmed recurring across both `report` and `pre_exam` on
   Case B.
4. A second universal, prompt-induced fabrication trap: Cases E/F have
   real content but no absolute dates, and every model invented specific
   dates to fill the `pre_exam` History format.
5. Case I's `report`-kind pertussis omission (seen in the first extension
   pass) turned out to be a token-budget artifact — `report`'s 340-token
   budget is tight enough to drop the single most decisive finding on a
   dense case, even for otherwise-correct models. `ministral` was the
   exception here — it correctly surfaced pertussis under `report`'s tight
   budget where the original 4 models missed it.
6. `medgemma-4b-it` alone produced 3 mistranslations in one case (Case H):
   "maternal aunt"→"maternal grandmother," Apgar 9→"length 9cm," and
   "hipotonie" (low tone)→"hypotension" (low BP).
7. `ministral`'s worst hallucination of its entire benchmark history: on
   Case C's `pre_exam`, it fabricated a "chronic respiratory disease"
   diagnosis with a full 5-item differential, from a source with zero
   clinical content.
8. `ministral` independently reproduces the "RS" abbreviation ambiguity
   (suprarenal gland vs. right side) already flagged for `medgemma-4b-it`,
   on Case D, plus a date conflation between its MRI and surgery dates.
9. `ministral` recurringly mistranslates "bronsiolita" (bronchiolitis) as
   "bronchitis" and "IRA" (acute respiratory failure) as "fever" across
   all three admission references on Case I — understating severity.

## Phase 4: prompt fixes for ICU-inflation, date-fabrication, and no-content — attempted, reverted

**Not shipped.** Three prompt-level fixes were written into
`llm/prompts/pre_exam.md` and `report.md` (ICU-inflation guard, date-free
`History` bullets, a stronger no-clinical-content trigger), then retested
against `qwen/qwen3-4b` and `qwen3.5-4b` on exactly the cases each finding
came from. Results were genuinely mixed — 3 of 7 retested cells improved,
1 regressed, 3 stayed broken (one revealing a new pattern: both models,
when a source has no dates, will anchor a fabricated date on the *current
system date* rather than a real one or `[not available]`). Given a
regression (Case C on `qwen/qwen3-4b`: went from clean to a severe
fabrication plus a new language leak) against only partial wins elsewhere,
the changes were **reverted via `git checkout`** — production prompts are
unchanged from every prior round in this survey.

| Case / finding | `qwen/qwen3-4b` | `qwen3.5-4b` |
|---|---|---|
| C, no-content (`pre_exam`) | **Regressed**: clean pre-fix ("No main diagnosis... None applicable"), fabricates a full diagnosis + differential post-fix, now also in Romanian | **Fixed**: `[not available]` throughout |
| D, ICU-inflation (`pre_exam`) | n/a | **Fixed**: no ICU mention (was "ICU/PED setting") |
| H, ICU-inflation (`pre_exam`) | n/a | **Not fixed**: still "Admission to ICU, Cardiology department" |
| E, date-free bullets (`pre_exam`) | Partially fixed: no full date range, but still invents month-level dates | **Fixed**: no invented date at all |
| F, date-free bullets (`pre_exam`) | **Not fixed**: anchors on today's actual system date | **Not fixed**: same, and narrates the fabrication in the output |

Full table, methodology, and the correction that the current-date-anchor
pattern actually predates this round (found in the pre-fix Case C
baseline too, just paired with benign content) are in the detailed doc's
Phase 4 section. Open items for a second, tighter attempt: fix the Case C
regression, get the ICU guard to hold on Case H as well as Case D, and add
an explicit "never use the current date as a source of patient history"
rule.

## Best all-round, best per language, best per kind

**Best all-round**: `qwen/qwen3-4b` — fewest hard failures across the
largest, most diverse evidence base (17 independent cells in Phase 2
extended), and its one recurring failure (Case C) is confined to a fixture
deliberately constructed to have no clinical content, not a real patient
case. This is a severity call, not a spotless-record call — see "The
finish line" above for the tradeoff against `qwen3.5-4b`.

**Best per language**:
- **Romanian**: `qwen/qwen3-4b` — clean across all 4 Phase 1 kinds when
  Romanian is the requested language (no language leaks, no fabrications
  found in the Romanian rerun).
- **English**: no model is clean across every English kind or phase.
  Judged purely on *language-correctness* (leak-freedom), `qwen3.5-4b` is
  the pick — it has zero recorded English-round language leaks anywhere in
  this survey, where `qwen/qwen3-4b` has one (Phase 1 `imaging`) plus a
  second one that surfaced on the reverted Phase 4 prompt (Case C
  `pre_exam`). Judged on overall English clinical-content reliability
  (fabrication/fact-inversion rate, not just language), `qwen/qwen3-4b`
  still leads on the Phase 2 extended combined tally.

**Best per kind** (Phase 1 data, since `imaging`/`lab` were only tested
there):
- **`imaging`**: not `qwen/qwen3-4b` (leaks Romanian here). Clean options:
  `qwen/qwen3-vl-4b` (exact match to the reference finding, fastest of the
  three at 118s Σt / 7.6 tok/s EN), `lmstudio-community/qwen3.5-4b`, and
  `qwen3-4b-instruct-2507`.
- **`lab`**: `qwen/qwen3-4b` — clean in both languages, zero recorded
  failures on this kind anywhere in the survey.
- **`report`**: `lmstudio-community/qwen3.5-4b` — best score across the
  largest evidence base for this kind (7 clean/1 fail/1 minor over 9
  cases, vs. `qwen/qwen3-4b`'s 6/2/1).
- **`pre_exam`**: `qwen/qwen3-4b` — zero hard failures across 8 independent
  cases (5 clean, 0 fail, 3 minor), the cleanest record on the heaviest,
  most failure-prone kind in the entire survey.

Per-kind winners diverging from the overall pick is expected, not a
contradiction — it's exactly why this survey tests kind-by-kind rather
than reporting one aggregate score.

## Keep vs. remove

Based on all evidence in this report (Phase 1 English + Romanian, Phase 2,
Phase 2 extended's full 5-model/17-cell battery, and the reverted Phase 4
prompt attempt):

**Keep / promote**:
- **`qwen/qwen3-4b`** — recommended for staged production rollout, `lab`
  first. Fewest hard failures across the largest evidence base; the one
  recurring failure (Case C) needs a fix before full rollout.
- **`lmstudio-community/qwen3.5-4b`** — strong second candidate, blocked
  on actually resolving (not just partially resolving) the ICU-inflation
  pattern before trusting it for `pre_exam`.

**Keep in consideration, not lead candidates**:
- **`qwen3-4b-instruct-2507`** — no severe errors, highest hard-fail rate
  of the three Qwen variants (5/17). Fallback option only.
- **`nvidia/nemotron-3-nano-4b`, `qwen/qwen3-vl-4b`** — Phase 1 only, not
  yet subjected to Phase 2/2-extended scrutiny; treat any Phase-1-only
  standing with the same caution this report demonstrated is warranted for
  every other model here.

**Remove from consideration**:
- **`medgemma-4b-it`** — decisively worst of the five models seriously
  tested: 10/17 hard failures including two of the most severe,
  self-contradicting or fully-invented hallucinations in this survey.
- **`ministral-3-3b-instruct-2512`** (current production) — now tested at
  full parity with every other candidate for the first time. Second-worst
  of the five (7/17 clean), including its own worst hallucination of the
  whole survey on Case C. The question is no longer whether to replace it,
  it's which candidate replaces it — this report's answer is
  `qwen/qwen3-4b`.
- **Every Tier D/F model** — architecturally broken, wrong-tool,
  unsuppressable reasoning leaks, over the VRAM ceiling, or frequent
  fabrication already documented above.

## Evidence

Full findings, source-text verification notes, and raw output samples for
every claim above are in `docs/llm_benchmark_2026-07-31.md`. Raw
JSON/markdown dumps, all gitignored and retained locally:

| Batch | Covers |
|---|---|
| `_testing_/r31*` | Phase 1, English |
| `_testing_/r32_b*` | Phase 1, Romanian rerun |
| `_testing_/r33_case*` | Phase 2 (4 cases), original 4 contenders |
| `_testing_/r34_case*` | Phase 2 (4 cases), ministral |
| `_testing_/r34_ministral_*` | Ministral's Phase 1 parity |
| `_testing_/r35_case*` | Phase 2 extended (5 more cases + `pre_exam`), original 4 contenders |
| `_testing_/r36_case*` | Phase 2 extended, ministral's parity closeout |
| `_testing_/r37_case*` | Phase 4 prompt-fix retest (reverted) |

`docs/llm_benchmark_2026-07-31_todo.md` tracks what's still open:
the `report`-budget question, the new current-date-anchor fix, a parked
medical-abbreviation glossary idea, and the second, tighter Phase 4
attempt this report's Phase 4 section calls for.
