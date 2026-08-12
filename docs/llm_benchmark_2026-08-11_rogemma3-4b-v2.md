# On-device LLM benchmark — RoGemma3-4B-Instruct-v2 (2026-08-11)

Follow-up to `llm_benchmark_2026-08-08_ro-tuned-candidates.md`, which left
`RoGemma3-4B-Instruct` as **blocked, not benchmarked** — every conversion
attempt failed to load on this project's LM Studio server with a generic
`Error loading model.`, suspected CUDA-runtime-specific bug in that LM
Studio build for Gemma 3. A newer build, `rogemma3-4b-instruct-v2`
("RoGemma3 4B Instruct B8733", `costinstroie/RoGemma3-4B-Instruct-GGUF`),
now **loads successfully** — this round actually benchmarks it.

## Loading: a new failure mode, and the fix

Loading via `lms.py load rogemma3-4b-instruct-v2` succeeds (default
`context_length=10240`), but the *first inference call* — even a trivial
`{"messages":[{"role":"user","content":"hi"}]}` sent directly to the LM
Studio REST API — crashes the model process:

```
"error": "The model has crashed without additional information. (Exit code: 18446744072635812000)"
```

Same crash-code signature as the earlier load-time failures, now
manifesting one stage later (load succeeds, generation crashes). Two
narrowing steps:

1. **Flash attention off**: blocked outright — this model's persisted
   server-side config has V-cache quantization enabled, which requires
   flash attention; `lms.py load --flash-attention false` fails at load
   time with `V Cache Quantization requires flash attention to be
   enabled.` `lms.py`'s load API doesn't expose a V-cache-quant override,
   so this path needs an LM Studio-side config change, not attempted.
2. **Lower context length**: `lms.py load rogemma3-4b-instruct-v2
   --context-length 4096` loads and **generates successfully** (`"hi"` →
   `"Salut!"`, clean, no crash). Re-tested at `--context-length 6144` (more
   headroom for the longer kinds — `pre_exam`'s 1300-token budget against
   a ~2270-token fixture) — also crash-free, used for the full run below.

**Fix**: load with an explicit, reduced `context_length` (6144 confirmed
working; the server's own default of 10240 crashes on generation). Not
root-caused further (no server-side crash log access from this side) — but
unlike the original load-time block, this one has a working mitigation.

## Method

Same as prior rounds: `benchmark_llm.py` against the app's real production
message assembly, same primary fixture (biliary-atresia case, `_testing_/
r31_report.md`'s Source section), 2 warm iterations per kind, all 4 kinds
(`imaging`/`lab`/`report`/`pre_exam`), both English and Romanian
requested-language runs. XRayVision was stopped and all models unloaded
before this round (this model needs its own explicit `context_length`, so
no other resident model should mask a config-dependent crash).

## Speed

Fast and consistent — no VRAM contention (XRayVision stopped, only this
model resident):

| Kind | tok/s (EN) | tok/s (RO) | warm total (EN) | warm total (RO) |
|---|---|---|---|---|
| `imaging` | 9.5 | 9.8 | 6.98s | 7.00s |
| `lab` | 8.9 | 9.3 | 29.99s | 38.82s |
| `report` | 8.7 | 8.8 | 40.74s | 40.72s |
| `pre_exam` | 8.2 | 8.2 | 92.10s | 94.36s |

Consistent ~8-10 tok/s across every kind and both languages — no
degradation pattern, no reasoning-leak-style slowdown.

## Quality — severe, consistent failures across every kind

Unlike prior rounds' "kind-dependent reliability" pattern (some kinds
clean, some not), this model fails **every kind tested, in both
languages**, in one of two ways: verbatim source/instruction echoing, or
outright fabrication.

| Kind | Result |
|---|---|
| `imaging` (EN + RO) | ❌ **complete task failure, both languages**: output is a verbatim quoted fragment of an unrelated pediatric consult note from the source (`"**Consult pediatric (14.11.2025; Dr. Pacurar):** Stare generala medicora..."`) — not an imaging impression, not even about imaging. Same failure shape in both languages, different verbatim fragment each time (14.11 vs 16.11 consult) — the input isn't cached/reused, it's independently mis-copying on each run. |
| `report` (EN + RO) | ❌ **complete task failure, both languages**: output is the raw source document copied near-verbatim from the top, including internal record metadata fields never meant to reach a clinician (`19890`, `True`, `stationar`) — no summarization, no translation (EN run stays in Romanian throughout), truncated mid-sentence at the 340-token budget. The Romanian run additionally **fabricates a leading date** (`16/08/2025`) that appears nowhere in the source (the source's own header date is `15/07/2026`). |
| `pre_exam` (EN + RO) | ❌ **complete task failure, both languages, and a language-inversion bug**: output is the *system prompt's own instruction template* echoed back — section headers and their instructional description text, verbatim, with zero patient content filled in (e.g. `"### Rezumat / Un singur rând: diagnostic principal și specialitate implicată — doar ceea ce este declarat..."`). Worse: it's language-inverted — the **English-requested** run echoes the instructions **in Romanian**, and the **Romanian-requested** run echoes them **in English**. Not a partial slip (as seen in the 08-08 RoQwen round's Case C/F template-echo failures) — 100% instruction-echo, 0% content, on both runs. |
| `lab` (EN) | ❌ **dangerous fabrication**: invents a `CRP level of 198 ng/ml` that appears nowhere in the source. Invents a `"GFR of 1950 ml/min/1.73m2"` by repurposing the patient's **birth weight** (`GN=1950 g`, from an unrelated `APF:` history line) as a lab value, with an implausible unit and magnitude for any patient. Mischaracterizes liver **ultrasound measurements** (`LDH 87 mm ap, 83 mm prerenal` — right hepatic lobe dimensions in mm) as `"significantly elevated levels of liver enzymes"` — conflating an imaging measurement with a lab result entirely. Three independent, unrelated numeric fields in the source misappropriated into a single confident-sounding fabricated "Impression". |
| `lab` (RO) | ⚠️ no numeric fabrication this run, but vague and unhelpful — doesn't extract or reference a single actual lab value from the source at all, just a generic paraphrase of clinical status (`"o afecțiune hepatică evidentă"`). Retains the English `"Impression:"` label despite the Romanian language request (minor language-consistency leak, distinct from the severe `pre_exam` inversion). |

## Recommendation

**Not usable, in any form tested.** This is a stronger, more uniform
failure than any model in the 08-08 or 07-31 rounds: every one of the 4
kinds fails completely in both languages (`imaging`/`report`/`pre_exam`),
and the one kind that doesn't just echo the input (`lab`) instead
fabricates a specific numeric lab value from an unrelated birth-weight
field — the single most clinically dangerous failure mode this project's
benchmarking has documented (prior rounds' worst findings were conflation/
inversion of *real* source facts, not invention of a plausible-looking lab
number from a completely unrelated field). Speed and load-stability are
no longer blockers (6144-context fix works cleanly), but that's now
irrelevant — the model does not perform the requested tasks at all for 3
of 4 kinds, and actively fabricates on the 4th.

Resolves the "left as an open item" note in
`llm_benchmark_2026-08-08_ro-tuned-candidates.md`: RoGemma3-4B-Instruct
**can** now be loaded and run (context-length fix), closing that
investigation — but the outcome is a clear **do not promote**, not a
"worth another look." No Phase 2 (9-case battery) extension is warranted
given Phase 1's near-total failure rate.

## Evidence

Raw JSON/markdown dumps (source + full untruncated output, one file per
kind × language): `_testing_/rogemma_bench/{imaging,lab,report,pre_exam}_
{English,Romanian}.{json,md}`.
