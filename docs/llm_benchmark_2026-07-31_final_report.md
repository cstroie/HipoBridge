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

**`qwen/qwen3-4b`** is the winner. It is the only model in the entire
33-model survey that is fabrication-free and language-correct across all 4
kinds **in both English and Romanian** — no other model, including current
production `medgemma-4b-it`, reaches that bar. It is mid-pack on speed
(133s/76 tokens-per-second-weighted in English), not the fastest option,
but nothing faster is close to matching its reliability.

**Recommendation**: promote `qwen/qwen3-4b` to a staged rollout —
non-critical kinds first (`lab`, where it's fastest and cleanest), full
rollout after a second fixture confirms the result isn't specific to this
one case (see follow-up #5 in the detailed doc). Keep `medgemma-4b-it` as
fallback; it remains usable but has two known, real weaknesses (see Tier B
below) that `qwen3-4b` doesn't share.

**If speed matters more than this report's tiering implies**: within
Tier A/B (the only tiers worth deploying), `lmstudio-community/qwen3.5-4b`
and `qwen/qwen3-vl-4b` are the fastest options that still hold up under
real fact-checking — see the table.

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

## What this doesn't cover

Current production (`ministral-3-3b-instruct-2512` default/medical,
`gemma-3n-e4b` fallback, per the 07-19/07-21 rounds) was **not retested this
round** — this survey only covers newly-discovered and newly-downloaded
candidates plus `medgemma-4b-it` as a like-for-like baseline. If a
production swap is being considered, `ministral-3-3b-instruct-2512` needs a
fresh run under this exact methodology before it can be compared
apples-to-apples against `qwen/qwen3-4b`.

Full evidence, source-text verification notes, and raw output samples for
every row above are in `docs/llm_benchmark_2026-07-31.md`; raw JSON/markdown
dumps are in `_testing_/r31*` (English) and `_testing_/r32_b*` (Romanian),
gitignored but retained locally.
