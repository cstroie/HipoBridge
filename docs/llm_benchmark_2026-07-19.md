# On-device LLM survey — 2026-07-19

Latency/throughput survey of small (≤4B) Gemma / MedGemma / LFM models on the
configured OpenAI-compatible server, using a **real** discharge summary as
input and the app's exact production prompt. Goal: pick fast on-device models
for the per-item "AI" buttons, accounting for cold-load (model-swap) delay.

## Setup

- **Server**: LM Studio, `http://192.168.3.238:1234/v1` (per `local.cfg`).
- **Tool**: `benchmark_llm.py` (streaming, measures warm TTFT / tokens-sec /
  total wall time + a separately-reported cold-load TTFT).
- **Prompt**: `epicrisis` kind from `llm/prompts.py` (tier `default`,
  `max_tokens=220`, output language English) — identical to production.
- **Iterations**: 1 cold + 3 warm per model; medians reported.
- **Models loaded at 4096 context** on the server (see finding #2 below).

## Input (anonymised)

Real discharge letter (`/api/checkout/{id}`) for a paediatric surgery patient.
All identifying data (name, CNP, address, phone, IDs) removed for this report.

- **De-identified clinical gist**: ~6-month-old male infant, known **biliary
  atresia**, admitted to paediatric surgery (CHIRURGIE I) for investigation and
  treatment; abdomen distended by organomegaly; laparoscopic exploration with
  hepatic biopsy and cholangiography.
- **Size**: full letter ≈ 16 KB / ~6000 tokens. It **exceeds** the models'
  4096-token context, so the survey used a **truncated** ~7.5 KB / ~2668-token
  slice (fits with room for the 220-token output).

> The raw report was fetched with worklist credentials and is **not** stored in
> this repo. Working copies live only under `/tmp` on the operator's machine.

## Results

Median of 3 warm runs; cold load = first call after the model is (re)loaded
into VRAM (includes the swap cost). Sorted by warm TTFT.

| Model | Warm TTFT | tok/s | Total | Cold load | Out toks |
|---|---|---|---|---|---|
| **lfm2.5-230m** | **0.15s** | **73.2** | **2.53s** | 4.27s | 174 |
| lfm2.5-1.2b-instruct | 0.29s | 25.2 | 4.78s | 9.76s | 113 |
| google/gemma-3-1b | 0.34s | 33.2 | 5.54s | 14.56s | 172 |
| liquid/lfm2-1.2b | 0.43s | 35.6 | 4.81s | 10.31s | 156 |
| lfm2-2.6b-transcript | 0.71s | 12.0 | 19.03s | 18.84s | 220 |
| google/gemma-4-e4b | 1.04s | 8.0 | 28.67s | 31.88s | 220 |
| medgemma-4b-it | 1.13s | 9.4 | 17.26s | 13.94s | 151 |
| google/gemma-3-4b | 1.18s | 9.0 | 11.78s | 29.47s | 101 |
| google/gemma-3n-e4b | 1.36s | 7.9 | 13.33s | 38.10s | 94 |

_(Timings from the second run; matches the first within noise. gemma-4-e4b now
measured after the streaming fix — it streams under `reasoning_content`.)_

## Speed readout

- **Speed ranks smallest-first**: lfm2.5-230m is fastest (0.15s TTFT, 73 tok/s,
  2.5s total, 4s cold load); the 1.2B tier sits at ~0.3–0.4s TTFT / 25–35 tok/s
  / ~5s total / ~10s cold; the 4B tier is 5–8× slower to generate (~8–10 tok/s,
  11–29s total) with heavy **14–38s cold loads**.
- **Cold load = the "not always in memory" cost**: 4s (230M) → up to ~38s (4B).
  Every model swap pays this before the first token. (Note LM Studio caching
  varies run-to-run — medgemma's cold load was 24s then 14s.)

## Quality assessment

Each model's full summary was compared against a hand-written reference (see
`/tmp/reference_summary.txt`, reproduced in `/tmp/llm_outputs.md`) and the
source. Score is 0–10 for faithfulness + completeness + no hallucination.

| Model | Quality | Notes |
|---|---|---|
| **medgemma-4b-it** | **9** | Accurate arc: dx, findings, Kasai (07.11), prednisone, histology. Minor drain-date slip. |
| google/gemma-3n-e4b | 8.5 | Concise and fully accurate; dx, findings, Kasai, drains, prednisone. No hallucinations. |
| google/gemma-3-4b | 7.5 | Accurate and concise; one conceptual error ("portosystemic shunting" — Kasai is not a shunt). |
| liquid/lfm2-1.2b | 5.5 | Covers the arc + histology, but invents "hepatic encephalopathy" and says "obstruction" not atresia. |
| google/gemma-3-1b | 4.5 | Some correct facts but fabricates "RUQ obstruction", "hypoproteinemia", and calls an afebrile infant "acute febrile". |
| lfm2.5-1.2b-instruct | 4 | Invents "acute abdominal pain", "choledocholithiasis", "palpable scrotal mass"; misses the known dx. |
| lfm2-2.6b-transcript | 4 | Detailed but says "elective cholecystectomy" (wrong op) and "pulmonary hypertension" (source says none); truncated mid-sentence. |
| ⚠️ lfm2.5-230m | 2 | **Clinically dangerous confabulation** — invents a hepatocellular-carcinoma / malignancy workup with oncologists; never mentions biliary atresia, Kasai, or the infant. |
| ⚠️ google/gemma-4-e4b | 2 | Leaks its chain-of-thought ("Here's a thinking process…") and is cut off at the token cap before producing a summary. Content is accurate but unusable as output. |

**Key finding — quality is roughly the inverse of speed.** The models fast
enough for zero-friction on-device use (230M, 1.2B) are the ones that
hallucinate; usable clinical fidelity starts at the 4B tier. The fastest model
(lfm2.5-230m) is **unsafe** here: it fabricated an oncology narrative absent
from the record.

## Recommendation

- **Best overall for this task: `google/gemma-3n-e4b`** — accurate, concise,
  no hallucinations, and the least-bad 4B latency profile once resident.
  **`medgemma-4b-it`** is the top choice when maximal clinical precision
  outweighs its heavier/variable cold load.
- **Do not use the sub-2B models for clinical summarization** on their own
  output — acceptable only for non-safety-critical hints, and even then 230M
  should be dropped.
- **Keep the chosen 4B model resident** (pinned in VRAM) to avoid the 14–38s
  cold-load TTFT; the swap cost dwarfs generation time.

## Prompt optimization (v2)

The `epicrisis` system prompt in `llm/prompts.py` was rewritten and A/B-tested
(`benchmark_llm.py --system-file`). v2 adds an explicit 4-part structure and
STRICT RULES: use only facts in the source, never fill gaps with "textbook"
findings, copy procedure/diagnosis names verbatim, never contradict the source,
and output only the summary. Result on the same document:

| Model | Baseline | With v2 prompt |
|---|---|---|
| lfm2.5-230m | invented an HCC/cancer workup | **cancer confabulation gone**; copies Kasai, but output garbled (weak model) |
| google/gemma-3-1b | fabricated "RUQ obstruction", said afebrile infant was "febrile" | **now states biliary atresia + correctly afebrile**; still emits headings |
| google/gemma-3n-e4b | 8.5, accurate | **still excellent, cleaner** — no regression |
| lfm2.5-1.2b-instruct | invents pain/choledocholithiasis | still hallucinates (no gain) |
| google/gemma-4-e4b | leaks chain-of-thought | **still leaks** — model-level, not fixable by prompt |

**Takeaway:** v2 materially improves grounding/safety on the mid and small
models (biggest win: 230M no longer invents cancer) with **no regression** on
the 4B tier, so it was **promoted to production** (`_EPICRISIS_SUMMARY`). The
residual failures are model-capability limits, not prompt limits — reinforcing
"use a 4B model." The record-summary prompt (`_RECORD_SUMMARY`, used for the
`report` kind) has the same shape and should get the same treatment next.

## Findings to explore further

1. **~~gemma-4-e4b measurement invalid~~ (fixed)** — it streams visible text
   under `reasoning_content`, not `content`. The tool now accepts either and
   guards the tok/s window against divide-by-zero, so gemma-4-e4b is measured.
   It still leaks its chain-of-thought into the answer (see quality table).
2. **4096-context wall affects production** — the full ~6000-token discharge
   does **not** fit these models as loaded; the app's AI buttons would silently
   receive empty summaries on long records. Options: raise per-model context in
   LM Studio (8192+), or have the app truncate/chunk long inputs before sending.
   The tool now surfaces this as a hard `ERROR:` row instead of fake zeros.
3. **~~Quality not yet scored~~ (done)** — see the Quality assessment section
   above. Follow-ups: score more than one document (n=1 patient here), and
   consider an automated LLM-judge so quality can be re-scored on every run.
4. **Prompt guarding for reasoning models** — gemma-4-e4b (and any future
   reasoning model) needs its thinking stripped; the app already has
   `strip_think_block`, but these models emit a bare "thinking process" without
   `<think>` tags. Consider a stronger strip or a non-reasoning preset.

## Reproduce

```bash
export HYP_USER=<worklist-user> HYP_PASS=<worklist-pass>
# fetch a real discharge and save locally (kept out of the repo):
python3 -c "import asyncio,os;from benchmark_llm import fetch_report_text;\
open('/tmp/report.txt','w').write(asyncio.run(fetch_report_text(\
'http://localhost:44660','/api/checkout/{id}','<CHECKOUT_ID>',\
os.environ['HYP_USER'],os.environ['HYP_PASS'])))"
# truncate to fit 4096 ctx, then survey with full outputs for quality review:
python3 benchmark_llm.py --text-file /tmp/report.txt --kind epicrisis \
    --iterations 3 --out /tmp/llm_survey.json \
    --dump-outputs /tmp/llm_outputs.md --reference /tmp/reference_summary.txt
```

`--dump-outputs` writes each model's full summary (plus the source and the
`--reference`) to one markdown file for side-by-side quality scoring.

---

# Round 2 — all prompts optimized + per-task model choice (2026-07-20)

Extended the study to every AI kind (imaging, lab, report, pre_exam — epicrisis
already done), each with a real CIOBOTARU input, a hand-written reference, and a
baseline-vs-v2 A/B on a model subset followed by a full-field ranking. All four
v2 prompts were promoted into `llm/prompts.py`.

## What changed in the prompts
- **Shared grounding block** across all kinds: use only stated facts; never fill
  gaps with "textbook" findings; copy diagnoses/procedure names verbatim; never
  contradict the source. Format block is per-kind (kept the lab structure and the
  pre_exam headings — the anti-formatting clause is only for the free-text kinds).
- **imaging**: one-line label, "Suspected …" prefix rule, no trailing punctuation.
  v2 makes capable models emit exactly `Suspected biliary atresia`; baseline gave
  Romanian or an incidental finding.
- **lab**: reworked to send the model **only out-of-range analytes** (frontend
  already caps at the 5 most recent dates; tightened so abnormality is judged
  within those 5). Output is now a **concise prose interpretation ending in an
  `Impression:` (probable diagnosis)** — no table mirror. `max_tokens` 800→400.
- **report**: same shape as the validated epicrisis v2.
- **pre_exam**: kept exact headings, added strict grounding + `[not available]`
  discipline.

## Per-task ranking (full field, promoted prompts, medians of 2 warm runs)

Timing is model-intrinsic; **cold** = first-call load (VRAM swap). Quality from
the A/B scoring against the reference.

**imaging** (max_tokens 40) — quality needs ≥4B; small models emit Romanian/echo.
| Model | warm TTFT | tok/s | total | cold | quality |
|---|---|---|---|---|---|
| medgemma-4b-it | 4.07s | 38.4 | 4.28s | 4.5s | ✅ exact |
| google/gemma-3n-e4b | 6.11s | 30.3 | 6.38s | 20.0s | ✅ exact |
(small/1B models: fast but wrong — ruled out)

**lab** (prose + diagnosis) — medgemma best; correct terms + Impression.
| Model | warm TTFT | tok/s | total | cold | quality |
|---|---|---|---|---|---|
| medgemma-4b-it | 0.73s | 9.8 | 7.39s | 1.1s | ✅ best |
| google/gemma-3n-e4b | 0.74s | 7.9 | 11.53s | 27.4s | ✅ good |
| google/gemma-4-e4b | 1.00s | 7.8 | 52.33s | 24.2s | ✗ CoT leak (400 tok) |

**report** (3-4 sentence summary)
| Model | warm TTFT | tok/s | total | cold | quality |
|---|---|---|---|---|---|
| google/gemma-3n-e4b | 1.39s | 7.6 | 17.81s | 47.0s | ✅ tightest |
| medgemma-4b-it | 1.10s | 9.3 | 24.53s | 26.5s | ✅ accurate |

**pre_exam** (structured briefing, 900 tok — slow: ~100s on a 4B)
| Model | warm TTFT | tok/s | total | cold | quality |
|---|---|---|---|---|---|
| medgemma-4b-it | 1.04s | 8.8 | 103.6s | 25.5s | ✅ |
| google/gemma-3n-e4b | 1.43s | 7.1 | 128.4s | 45.1s | ✅ best structure |
(1B models hallucinate colonoscopy/ALT-AST — ruled out)

## Best model per task
| Task | Winner | Runner-up |
|---|---|---|
| imaging | gemma-3n-e4b | medgemma-4b-it |
| lab | **medgemma-4b-it** | gemma-3n-e4b |
| report / epicrisis | gemma-3n-e4b | medgemma-4b-it |
| pre_exam | gemma-3n-e4b | medgemma-4b-it |

The finalists are **medgemma-4b-it** and **google/gemma-3n-e4b**. Everything
<4B is ruled out (hallucination/garbling, even on the imaging one-liner);
gemma-4-e4b leaks chain-of-thought; gemma-3-4b is beaten by both.

## Deployment decision (Option A — applied)
medgemma-4b-it is **permanently resident** on the model host for the xrayvision
X-ray classifier, so HippoBridge pays **zero cold-load** for it. That flips its
only weakness and makes it the pragmatic default. Applied in `local.cfg`:
`default` tier repointed from `LFM2-2.6B-Transcript` (which hallucinated) to
`medgemma-4b-it`; `medical` was already medgemma. **Needs a HippoBridge restart.**

- Optional upgrade (Option B): pin `gemma-3n-e4b` on a second card for the
  free-text/pre_exam kinds where it edges medgemma on prose. Costs a card.

## Language
English output is enforced explicitly (not guessed): every prompt gets a
`_language_directive` appended ("Write your entire response in English …
translate rather than copy … never switch language mid-sentence"), with
`language = English` in config. Finalists comply; only the ruled-out sub-2B
models ignored it.

## Hardware notes (3× CUDA, 4 GB VRAM each)
- One ~4B Q4 model + KV cache per card; can't cleanly span a bigger model.
- Model sizes: medgemma-4b-it ≈ 2.5 GB (true 4B, tidy fit); gemma-3n-e4b ≈
  4.2 GB on disk / ~2-3 GB VRAM via Per-Layer-Embedding offload (7.85B total,
  ~4B effective); LFM2-8B-A1B ≈ 5.0 GB (won't fit one card).
- **Context**: 8k is enough for untrimmed report/epicrisis (~6.5k tokens incl.
  output). Enable **KV-cache Q8** so 8k fits alongside the weights on a 4 GB
  card. pre_exam (full assembled record) can still exceed 8k on complex patients.
- **pre_exam is expensive** (~100s at 900 tok on a 4B) — treat it as a
  deliberate "prepare briefing" action, not instant.

## Pending (running overnight)
Challenger round vs the finalists — **qwen/qwen3-4b** (strong multilingual,
RO→EN), **mistralai/ministral-3-3b** (faster 3B), **lfm2-8b-a1b** (8B MoE, 1B
active — fast in theory but ~5 GB won't fit a 4 GB card, so placement may
bottleneck it), and **google/gemma-3n-e2b** (downloading). Plus a **lean-prompt
experiment**: re-test the ≤1B models (230m, gemma-3-1b, the 1.2B LFMs) on
imaging + report with a drastically shorter prompt, to see whether prompt length
(not just capacity) was garbling them — and whether their speed earns them a
niche. Results to be folded in here.

---

# Round 3 — challengers + lean small-model experiment (2026-07-20)

Added four candidates to the full field and ran a separate lean-prompt test on
the ≤1B models. Inputs/references unchanged.

## Challenger results (promoted prompts)

| Model | imaging | lab | report | pre_exam | speed note |
|---|---|---|---|---|---|
| **mistralai/ministral-3-3b** | ✅ exact | ✅ **best terms**, no overcall | ✅ ok | ⚠️ server-errored (retest) | fast 3B, fits 4 GB |
| **lfm2-8b-a1b** | ✅ exact, **100 tok/s** | ✅ good | ✅ ok | ✅ structured, **~42s vs ~100s** | MoE fast; but ~5 GB, 23-28s cold; **leaks Romanian in long output** |
| **google/gemma-3n-e2b** | ~ adds extra finding | ✅ good (minor "WBC" overcall) | ✅ ok | ✅ | lighter/faster than e4b |
| ⚠️ **qwen/qwen3-4b** | ✗ CoT leak | ✗ CoT leak | ok | server-errored | **reasoning leaks on every task — needs `/no_think`** |
| medgemma-4b-it (ref) | ✅ | ✅ | ✅ | ✅ | resident → 0 cold |
| google/gemma-3n-e4b (ref) | ✅ | ✅ | ✅ | ✅ best structure | 20-47s cold |

Highlights:
- **ministral-3-3b is the standout new find** — nailed imaging and lab with
  terminology as good as medgemma, from a 3 B that fits a 4 GB card and runs
  faster than the 4 B models. (Its pre_exam run hit a transient server error, not
  a quality failure — worth a retest.)
- **lfm2-8b-a1b delivers MoE speed** (100 tok/s on imaging; pre_exam in ~42 s vs
  ~100 s for the dense 4 Bs) and is clinically decent, **but leaks Romanian into
  the longer factual sections** despite the English directive, and its ~5 GB
  footprint doesn't fit one 4 GB card (23-28 s cold). Hold unless language is
  tightened and VRAM allows.
- **qwen3-4b is out as-configured** — chain-of-thought leaks on every task (same
  failure mode as gemma-4-e4b). Revisit only with thinking disabled.
- **gemma-3n-e2b** is a viable lighter alternative to e4b (a touch more overcall).

## Lean-prompt experiment — does prompt LENGTH garble the ≤1B models?

Re-ran the ≤1B models (lfm2.5-230m, gemma-3-1b, lfm2.5-1.2b, liquid/lfm2-1.2b)
on imaging + report with a drastically shorter, single-instruction prompt.

**Answer: no — it's capacity, not prompt length.** The lean prompt did **not**
rescue them:
- **Still hallucinate**, some dangerously — lfm2.5-1.2b invented
  **"cholangiocarcinoma"**; lfm2.5-230m invented "peritoneal washout / increased
  bile flow"; gemma-3-1b invented "lymphadenopathy" and called an afebrile infant
  "feverish".
- **Still ignore the English instruction** — gemma-3-1b answered in Romanian
  ("Atrezie bilieră suspectată") even with the lean English prompt.
- **Still miss the finding** — lfm2.5-1.2b called the imaging "normal overall".

The one glimmer: gemma-3-1b *extracted the correct imaging finding* — but in
Romanian, so unusable. **Conclusion: no safe niche for the ≤1B models on these
clinical tasks; their speed cannot be spent safely here.** Length was a red
herring — the failures are model-capacity limits.

## Updated recommendation
- **Safe finalists unchanged**: medgemma-4b-it (lab + resident default) and
  gemma-3n-e4b (free-text/pre_exam).
- **New candidate worth adopting for imaging + lab: mistralai/ministral-3-3b** —
  faster, fits 4 GB, terminology on par with medgemma. Retest its pre_exam run.
- **lfm2-8b-a1b**: promising speed, but fix the Romanian leak (stronger language
  directive) and confirm VRAM before using; not for the English requirement yet.
- **qwen3-4b**: only with `/no_think`.
- **≤1B models**: do not use for clinical output, at any prompt length.

---

# Round 4 — targeted retests (2026-07-20)

## qwen3-4b with thinking disabled (`/no_think`)
Re-ran qwen3-4b with `/no_think` injected into the input (registry prompts).
**The chain-of-thought leak is fully fixed — and the model is excellent:**

| Kind | Result | warm TTFT | total |
|---|---|---|---|
| imaging | ✅ "Suspected biliary atresia" | 0.45s | 1.3s |
| lab | ✅ terse, all correct terms, `Impression: Cholestasis with renal impairment and systemic inflammation` (minor: called Na "hyponatremia") | 0.47s | 7.5s |
| report | ✅ faithful English summary, accurate arc (minor: "CVC placed" vs removed) | 0.51s | 20.7s |

With `/no_think`, **qwen3-4b jumps to top-tier**: fully English (strong
multilingual), fast TTFT, no CoT, correct clinical terms. Only caveat: it needs
`/no_think` plumbed in (system-prompt suffix or `enable_thinking:false`) — a
small backend change. Left thinking on, it's unusable.

## ministral-3-3b pre_exam (transient error retest)
Re-ran cleanly — the earlier failure was a server hiccup, not the model.
**Result: strong.** Full correct headings, accurate dated history, prior-imaging
findings quoted faithfully, sensible differential and reason-for-exam, all in
English, `[Not available]` used correctly for missing labs. Minor mistranslation
slips ("fatty liver" for the borderline-enlarged liver). **ministral-3-3b is now
confirmed good across all four kinds.**

## Revised shortlist
Four models are now viable, all ≤4B and 4 GB-friendly:
- **medgemma-4b-it** — resident default (free cold start), strongest on lab.
- **google/gemma-3n-e4b** — best free-text/pre_exam structure; heavy cold load.
- **mistralai/ministral-3-3b** — fast 3B, good across *all four* kinds, no special
  handling; best speed/fit/simplicity balance. Top pick if not relying on the
  resident medgemma.
- **qwen/qwen3-4b (`/no_think`)** — equally strong and fully English, but needs
  the no-think flag plumbed in.

≤1B models remain unusable (Round 3). qwen3-4b without `/no_think` and
gemma-4-e4b remain out (CoT leak).

## Round 4 addendum — qwen3-4b pre_exam (`/no_think`)
Filled the missing cell (the challenger run had errored transiently). Result:
**great structure, but fails the English requirement on long output.** All
headings correct and content faithful, but the History and Prior-imaging
sections came back almost entirely in **Romanian** (verbatim copy, not
translated); only Summary / Reason-for-exam / AI-suggestions were English.
Timing: 98s total, 9.2 tok/s, 32s cold.

This is the same long-output Romanian-leak seen in lfm2-8b-a1b. qwen3-4b holds
English on the short tasks (imaging/lab/report) but not on pre_exam.

**Pre_exam language compliance:** ✅ medgemma-4b-it, gemma-3n-e4b (full English);
✅ ministral-3-3b (English, minor mistranslation); ✗ qwen3-4b, lfm2-8b-a1b
(Romanian in the long sections). → For pre_exam, prefer medgemma / gemma-3n-e4b /
ministral-3-3b.

---

# Round 5 — LFM2.5-8B-A1B, qwen3.5-9b, qwen3-1.7b (2026-07-20)
(gemma-4-e4b excluded per decision — no viable CoT switch in LM Studio.)

## LFM2.5-8B-A1B — won't load
All four kinds errored ("Error loading model" / 400 / unloaded). The `lfm2moe`
(2.5) architecture isn't supported by the installed LM Studio runtime and/or its
~5.16 GB doesn't fit the 4 GB cards. Note the **2.0** A1B loaded and ran fine, so
this is a 2.5-specific arch/runtime gap. **Untestable until the LM Studio runtime
is updated** — so "does 2.5 fix the Romanian leak?" stays open.

## qwen3.5-9b — out
**Leaks chain-of-thought even with `/no_think`** (it output a "Thinking Process:"
block and literally monologued about the `/no_think` tag). Also a dense 9B: ~5
GB doesn't fit a 4 GB card → offloaded to ~5 tok/s (pre_exam 186 s, cold 34 s).
Not viable on-device here.

## qwen3-1.7b (`/no_think`) — imaging-only niche
- **imaging: ✅** "Suspected biliary atresia", 0.7 s — extraction works even at
  1.7 B, and fast.
- **lab: mediocre** — correct impression ("cholestasis with renal impairment and
  systemic inflammation") but falsely calls WBC elevated and restates the raw
  numbers (violates the prompt).
- **report: ✗** — doesn't summarize; dumps a verbose English transcription of the
  whole record. Abstraction/compression still needs ≥3-4 B.

## Net
No new winner. Shortlist stands: **medgemma-4b-it, gemma-3n-e4b,
ministral-3-3b, qwen3-4b (`/no_think`)**. qwen3-1.7b is a possible **fast
imaging-triage-only** fallback. LFM2.5 needs a runtime update before it can even
be evaluated.

---

# Round 6 — consolidated numeric fidelity scores (2026-07-20)

Every model/kind pair actually tested, scored 0–10 (faithfulness + completeness,
hallucination-penalized) against the hand-written reference and source for
that kind. Same rubric as the original Round-1 epicrisis scoring, now applied
uniformly. "—" = not runnable (load/timeout error) or CoT leak with no usable
final answer (scored 0 where a partial/garbled answer did appear).

| Model | imaging | lab | report | pre_exam |
|---|---|---|---|---|
| **medgemma-4b-it** | 10 | 9 | 7 | 7 |
| **google/gemma-3n-e4b** | 10 | 9 | 9 | 9 |
| **mistralai/ministral-3-3b** | 10 | 9 | 8 | 8 |
| **qwen/qwen3-4b (`/no_think`)** | 10 | 8 | 9 | 5 |
| google/gemma-3n-e2b | 8 | 8 | 8 | 8 |
| lfm2-8b-a1b (2.0) | 10 | 7 | 2 | 3 |
| google/gemma-3-4b | 8 | 8 | — | — |
| qwen/qwen3-1.7b (`/no_think`) | 10 | 8 | 3 | — |
| lfm2.5-1.2b-instruct | 5 | 7 | 2 | 1 |
| lfm2-2.6b-transcript | 4 | 3 | 4 | 2 |
| liquid/lfm2-1.2b | 1 | 5 | 2 | 1 |
| google/gemma-3-1b | 5 | 2 | 0 | 1 |
| lfm2.5-230m | 0 | 4 | 1 | 0 |
| qwen/qwen3.5-9b (`/no_think`) | 0 | 0 | — | 0 |
| google/gemma-4-e4b | 0 | 1 | 1 | 0 |
| lfm2.5-8b-a1b (2.5) | — | — | — | — |

(qwen3-4b's lab cell was filled in after a follow-up `/no_think` run: terse,
correct terms, correct `Impression: Cholestasis with renal impairment and
systemic inflammation` — matches the reference exactly. One minor slip:
mislabels a borderline sodium value as "hyponatremia".)

## Reading the table

- **Four models are consistently strong (≥7 everywhere they ran)**:
  medgemma-4b-it, gemma-3n-e4b, ministral-3-3b, and qwen3-4b (`/no_think`).
  This matches the shortlist from Rounds 2-4.
- **gemma-3n-e4b has the best and most even profile** — 9s and a 10, no weak
  kind. **ministral-3-3b** is close behind and is the fastest of the four
  (see Round 4/"fastest" answer above).
- **qwen3-4b's pre_exam score (5) confirms the Round-4 addendum finding**: great
  structure/accuracy, but reverts to Romanian in the long History/Prior-imaging
  sections — a language failure, not a content failure.
- **lfm2-8b-a1b (2.0)**: strong on the short tasks (imaging 10, lab 7) where
  its MoE speed is a real asset, but **collapses on long output** — report (2)
  is garbled mixed-language nonsense ("varțe", "hydo cel"), pre_exam (3) has
  heavy untranslated Romanian throughout. Confirms it's not safe for the
  longer kinds yet.
- **All ≤2B models cap around 1-5** even on their best kind, with severe,
  specific hallucinations newly documented here: gemma-3-1b invented "19890
  years old" (misreading an internal section code as age) and fabricated labs
  (ALT/AST, hypocalcemia) never in the source; lfm2.5-1.2b-instruct invented
  an age of "1989" and entirely fictitious lab values (AST 62, PCT 0.9, LDH
  92); liquid/lfm2-1.2b invented "58 years" and duplicated/malformed sections.
  lfm2.5-230m outright echoed the prompt template back as its pre_exam
  "answer" (0). These are more severe than the general "hallucinates" note
  from earlier rounds — worth having as documented, concrete failure examples.
- **Reasoning leakers are floored regardless of task**: gemma-4-e4b and
  qwen3.5-9b (even with `/no_think`) score 0-1 almost everywhere — the CoT
  leak makes the output structurally unusable even when the underlying
  analysis (visible in the leaked reasoning) is often accurate.
- **lfm2.5-8b-a1b (the 2.5 release)**: still untestable — fails to load on
  this LM Studio runtime.
