# On-device LLM survey — new sub-4B models (2026-07-31)

Surveys every sub-4B-class model added to the LM Studio server since the
07-19/07-21/07-22 rounds (`docs/llm_benchmark_2026-07-19.md`), plus a few
previously-tested models worth a fresh look under the current prompts. Same
method as prior rounds: `benchmark_llm.py` against the app's real production
message assembly (`_build_messages()`), same real fixtures (biliary-atresia
case), 2 warm iterations per model per kind, cold-load timing reported
separately.

**Hardware**: the LM Studio server offloads exclusively to GPU on two NVIDIA
Quadro K2200 (4 GB VRAM each, no CPU fallback) — this constrains how many
models can be resident at once and explains why heavier/longer-context kinds
(`pre_exam`, 900–1300 tokens) are where crashes and VRAM contention
concentrate, consistent with prior rounds.

**Constraint driving model scope**: 4 GB VRAM per card, no CPU fallback,
means any model that doesn't fit a single card at a usable quantization
can't run here at all — hence "sub-4B" in the survey's own title. This is
why `lfm2-8b-a1b` (5.04 GB) and `google/gemma-4-e4b` (6.33 GB actual, despite
the "e4b" effective-param name) were excluded before testing rather than
run and found wanting, and why `qwen3.5-*-opus-reasoning-distilled` and
similar heavier finetunes were only tested at their smaller (2B/4B)
variants. It's a hardware ceiling, not a judgment that larger models
wouldn't perform better.

## Methodology

**Loading/unloading models.** LM Studio JIT-swaps models into VRAM on
request by default, but with only 4 GB per card and no CPU fallback, an
uncontrolled swap can leave a stale model resident and contending for VRAM
with the one under test. `lmstudio_ctl.py` (new this round, wraps LM
Studio's native REST API) makes this explicit: `unload --all --keep
<model>` is run before every model group so exactly one candidate is
resident at a time (production `medgemma-4b-it` is the standing exception —
kept resident throughout, since xrayvision also depends on it being loaded).
Models are run one-at-a-time, all iterations for a model before moving to
the next, so the VRAM-swap/load cost is paid exactly once per model rather
than once per call.

**Downloading models.** New candidates not already on the server are
pulled via `lmstudio_ctl.py download <HF link> --quantization Q4_K_M
--wait`. The HF download link from this server is flaky and routinely dies
mid-transfer (5-80% through); `--wait` auto-resumes on a `status: failed`
response, up to `--retries` (default 5), re-POSTing to the same job id so
LM Studio resumes from the partial bytes rather than restarting from zero.
Models over the ~4 GB single-card VRAM ceiling are excluded before download
even starts (checked against `lmstudio_ctl.py list` sizes).

**What's tested, and why.** Every model is run through `benchmark_llm.py`
against the app's *real* production code path — same message assembly
(`_build_messages()`), same per-kind system prompt and `max_tokens` the
live "AI" buttons actually use, not a synthetic prompt — so the numbers
reflect production behavior, not a benchmark-only approximation. The same
real fixture (a de-identified biliary-atresia case, referred to as "the
primary fixture") is used across every model in Phase 1, so results are
comparable model-to-model rather than confounded by fixture differences;
Phase 2 (below) exists specifically to check whether the Phase 1 ranking
generalizes beyond that one fixture.

Four "kinds" are tested, corresponding to the app's four AI output types,
each with production's real `max_tokens` budget: `imaging` (60 tokens, a
one-line impression), `lab` (600 tokens), `report` (340 tokens, plain
prose, tightest budget relative to input complexity), and `pre_exam` (1300
tokens, the heaviest/most structured kind — this is also where VRAM
contention and reasoning-leak failures concentrate, since it's the longest
generation).

**Disabling thinking/reasoning/CoT.** Several candidates are reasoning
finetunes that, left default, leak raw chain-of-thought/planning tokens
into the output and burn the entire `max_tokens` budget narrating instead
of answering — unusable for these short, tightly-budgeted kinds regardless
of underlying quality. Two independent suppression mechanisms were tried,
and neither is a universal fix:

1. `"chat_template_kwargs": {"enable_thinking": false}` — Qwen3's actual
   template-level reasoning switch, sent on *every* request this round
   (verified live: it alone suppresses reasoning on base
   `lmstudio-community/qwen3.5-4b`). Harmless no-op on non-Qwen3 models (an
   unknown extra field, silently ignored — confirmed against
   `medgemma-4b-it`).
2. `--no-think` (`benchmark_llm.py` flag, appends the `/no_think` text
   token to the input) — needed *in addition to* (1) for base `qwen3-0.6b`/
   `qwen3-1.7b`, which still leaked verbosely under `chat_template_kwargs`
   alone.

Neither mechanism, nor a guessed `enable_reasoning` parameter, suppresses
the `qwen3.5-*-claude-4.6-opus-reasoning-distilled` finetunes at all — that
distillation appears to have baked in always-on reasoning that ignores the
template variable entirely, not fixable via any request parameter tried.
`microsoft/phi-4-mini-reasoning` has the same unsuppressable-leak problem,
via its own `reasoning`/`reasoning_effort` mechanism (no parameter value
tried stops it either). Both are marked Tier F / ruled out on this basis,
not on output quality — the leak alone makes them unusable regardless of
what the answer underneath might have looked like.

**How many times, and why.** Each model/kind combination is run once cold
(first call after the model loads — includes the VRAM-swap cost, reported
separately as `cold_ttft` and *not* used for quality judgment, since a slow
first token is a load-time artifact, not a model-quality signal) followed
by 2 **warm** iterations (model already resident). Warm-run timing/token
metrics reported in results are the *median* of those 2 runs, not a single
sample, to smooth out per-call jitter; the output text used for hand-
verification is the final warm run's output. 2 iterations (rather than the
tool's own default of 3) was chosen to fit the full 33-model sweep in a
reasonable wall-clock window on 4 GB cards where every extra iteration
multiplies real GPU time — judged sufficient here because the quality
judgment (fabrication/fact-inversion/language-leak) is a categorical
per-output finding checked against source text, not a statistical claim
that needs many samples to stabilize.

## New tooling

- **`lmstudio_ctl.py`** (new): CLI against LM Studio's native REST API
  (`/api/v1/models` list/unload, distinct from the OpenAI-compatible `/v1/`
  surface the app itself uses) so a model can be explicitly unloaded before
  swapping in the next candidate, rather than relying on LM Studio's
  own JIT-swap-on-request behavior. `unload --all --keep medgemma-4b-it` was
  run before every model group in this round (medgemma stays resident for
  xrayvision, per standing practice). Built to be extended later with
  `load`/`download`/`download-status` subcommands.
- **`benchmark_llm.py`**: gained `--language` (per-run override, independent
  of `local.cfg`'s `[llm] language`) and `--no-think` (appends `/no_think` to
  the input text for Qwen3-family reasoning-leak suppression, matching the
  ad-hoc technique used in the 07-22 rounds, now a first-class flag).
- **`lmstudio_ctl.py`** grew further mid-round: `load` and `download`/
  `download-status` (all five documented native-REST endpoints besides
  `chat` are now wrapped), plus `swap` (unload-all-except-keep + load in one
  call) and `--json` output on `list`/`download-status`. `download --wait`
  now auto-resumes on a `status: failed` response (up to `--retries`, default
  5) — the HF download link from this server is flaky and routinely dies
  mid-transfer around 5-80% progress; LM Studio resumes from the partial
  bytes on the same job id when re-POSTed, so this used to require watching
  and manually re-running the request by hand.
- **`benchmark_llm.py`** now always sends `"chat_template_kwargs":
  {"enable_thinking": false}` on every request — this is Qwen3's actual
  template-level reasoning switch (verified live: it alone suppresses
  reasoning on base `lmstudio-community/qwen3.5-4b`, which the existing
  `reasoning`/`reasoning_effort` params don't need to touch since that model
  wasn't leaking anyway). It's a harmless no-op on non-Qwen3 models (an
  unknown extra field, silently ignored — confirmed against `medgemma-4b-it`).
  Important nuance discovered mid-round: **the two suppression mechanisms
  are not interchangeable** — `chat_template_kwargs` alone does *not*
  suppress base `qwen3-0.6b`/`qwen3-1.7b` (they still leaked verbosely
  without `/no_think` even with the flag set), and neither mechanism (nor
  `enable_reasoning`, tried as a guess) suppresses the
  `qwen3.5-*-claude-4.6-opus-reasoning-distilled` finetunes at all — that
  distillation appears to have baked in always-on reasoning that ignores
  the template variable entirely, not fixable via any request parameter.
  `--no-think` (the `/no_think` text-token trick) is therefore kept as a
  separate, still-necessary flag for `qwen3-0.6b`/`qwen3-1.7b`, used
  together with the now-standing `chat_template_kwargs`.

## New models found already on the server, and new downloads

A full re-check of `lmstudio_ctl.py list` turned up several models installed
but never benchmarked in any prior round, plus the user requested pulling in
a few models not yet on the server at all. Sizes were checked against the
4 GB-per-card VRAM ceiling before testing (`lfm2-8b-a1b` at 5.04 GB and
`google/gemma-4-e4b` at 6.33 GB / actually 7.5B total params despite the
"e4b" effective-param name were excluded as too large for a single card and
not tested).

**Already on the server, untested**: `medgemma-1.5-4b-it` (4.16 GB, same
size class as production `medgemma-4b-it`), `google/gemma-3-4b` (3.34 GB),
`qwen/qwen3-4b` (2.50 GB, distinct from the already-tested
`qwen3-4b-instruct-2507`), `llama-3.2-3b-instruct` (2.02 GB),
`llama-3.2-1b-instruct` (1.02 GB), `lfm2.5-1.2b-instruct` (0.96 GB, distinct
from the already-tested `-thinking` variant), `google/gemma-3-1b` (0.72 GB).

**Newly downloaded** via `lmstudio_ctl.py download <HF link> --quantization
Q4_K_M --wait`: `ibm-granite/granite-4.1-3b-GGUF` (2.10 GB — IBM's newest
Granite release, multilingual/tool-use focused),
`lmstudio-community/gemma-3-270m-it-GGUF` (0.25 GB — smallest Gemma-3),
`unsloth/functiongemma-270m-it-GGUF` (0.25 GB — Google's function-calling-
specialized Gemma), and `unsloth/Phi-4-mini-instruct-GGUF` (2.5 GB, distinct
from the already-tested `phi-4-mini-reasoning`). The first three downloaded
and loaded cleanly; Phi-4-mini's download needed 3 resumes after repeated
mid-transfer failures and the resulting file **fails to load server-side**
(`"Error loading model."`, identical signature to `gemma-4-e2b-it`) —
suspected corruption from the resume process. No delete endpoint exists in
the REST API and remote filesystem access wasn't available to remove the
file by hand, so it's untested this round; treat like `gemma-4-e2b-it`
below.

## Config gotcha caught mid-run

`local.cfg` currently has `[llm] language = Romanian` (not the `English`
default every prior round assumed). The first pass of this survey ran
against that config and every model "failed" by answering in Romanian — not
a model regression, just a stale/experimental local override. Re-ran with
`--language English` for all real results below. **Worth checking whether
`local.cfg`'s `language = Romanian` is intentional current production config
or leftover from unrelated testing** — it silently changes every AI button's
output language app-wide.

## Models tested

19 previously-untested (or effectively-untested) models, in three groups:

**Group 1** — primary new-generation candidates: `lmstudio-community/qwen3.5-4b`,
`lmstudio-community/qwen3.5-2b`, `nvidia/nemotron-3-nano-4b`,
`microsoft/phi-4-mini-reasoning`, `gemma-4-e2b-it`, `qwen3-4b-instruct-2507`,
`phi-3.1-mini-4k-instruct`.

**Group 2** — smaller/completeness candidates: `lfm2-2.6b-transcript` (retest
under current prompts — only ever speed-tested in 07-19), `lfm2.5-350m`,
`qwen3-0.6b`, `tinyllama-1.1b-chat-v1.0`, `lfm2.5-1.2b-thinking`,
`qwen3.5-2b-claude-4.6-opus-reasoning-distilled`,
`qwen3.5-4b-claude-4.6-opus-reasoning-distilled-v2`, `lfm2.5-8b-a1b`,
`qwen3-1.7b` (retest — was fully broken with `400` errors in 07-22),
`google/gemma-3n-e2b` (retest), `lfm2.5-vl-1.6b`, `qwen/qwen3-vl-4b`.

**Group 3** — added mid-run at the user's request: `lfm2-350m-extract`.

**Group 4** — added after the initial write-up: `medgemma-4b-it`, the current
production `medical`-tier model, kept resident throughout this whole round
(so `lmstudio_ctl.py unload --all --keep medgemma-4b-it` never touched it)
but not itself re-benchmarked until now, since it wasn't a "new" model — added
for a like-for-like baseline against this round's candidates.

**Group 5** — added later still, after the fact: `ministral-3-3b-instruct-2512`,
the model actually configured as production (`medgemma-4b-it` above is the
`medical`-tier baseline, not the same thing). Its omission from every earlier
round through this one was an oversight, not a judgment call — it was
benchmarked after the fact, on this round's fixture, at full Phase 1 parity
(imaging/lab/report/pre_exam, English + Romanian, same 2-warm-iteration
settings), and is folded into the tables below rather than kept as a
separate later addendum. Raw JSON/markdown dumps: `_testing_/r34_ministral_*`
(gitignored, retained locally).

The 4 Qwen3-family reasoning models that leaked chain-of-thought
(`qwen3-0.6b`, `qwen3-1.7b`, both `qwen3.5-*-opus-reasoning-distilled`
variants) were re-run with `--no-think` across all 4 kinds; those results
replace the leaked ones below.

## Results by kind

Sample outputs below; full text and timings in `_testing_/r31*.md`/`.json`
(gitignored, not committed).

### imaging (60 max_tokens, reference: "Suspected biliary atresia")

| Model | Result |
|---|---|
| `lmstudio-community/qwen3.5-4b` | ✅ "Ascites with suspected biliary atresia" — correct, English |
| `qwen/qwen3-vl-4b` | ✅ "Biliary atresia suspected" — exact match, English |
| `qwen3-4b-instruct-2507` | ✅ "Biliary atresia suspected" — correct, English |
| `nvidia/nemotron-3-nano-4b` | ⚠️ "Atresia biliare suspected" — term-level Romanian leak (same failure class as medgemma-4b-it's historical `pre_exam` leak, but here on `imaging`) |
| `qwen3-1.7b` (`/no_think`) | ❌ "Left lower lobe pneumonia" — wrong diagnosis, but no CoT leak |
| `qwen3-0.6b` (`/no_think`) | ❌ "Splenomegalie" — wrong diagnosis, still Romanian |
| `qwen3.5-2b`/`4b`-opus-distilled (`/no_think`) | ❌ reasoning leak persists — `/no_think` does not suppress it on these finetunes |
| `phi-4-mini-reasoning` | ❌ reasoning leak, consumes entire budget |
| `phi-3.1-mini-4k-instruct` | ⚠️ correct content but verbose, breaks the one-line format |
| `gemma-4-e2b-it` | ❌ **fails to load on the server** (`Error loading model`) — not a request-shape issue, the model itself won't load |
| `lfm2.5-350m` | ❌ "Pancreas" — nonsense one-word non-answer |
| `lfm2.5-vl-1.6b` | ⚠️ "Splenomegaly with mild ascites" — plausible but wrong diagnosis |
| `lfm2.5-1.2b-thinking`, `lfm2.5-8b-a1b` | ❌ reasoning leak |
| `tinyllama-1.1b-chat-v1.0` | ❌ echoes the prompt/role instructions back verbatim instead of answering |
| `lfm2-2.6b-transcript` | ⚠️ plausible finding but doesn't match reference framing |
| `google/gemma-3n-e2b` | ⚠️ "Right lobe liver enlargement" — vague, not the reference finding |
| `medgemma-4b-it` (production baseline) | ⚠️ "Liver with enlarged lob right prehepatic (8 cm), irregular contour" — accurate detail but doesn't state the suspected diagnosis, just describes the finding |
| `ministral-3-3b-instruct-2512` (current production, added late — see Group 5 note above) | ✅ correct |
| `medgemma-1.5-4b-it` | ⚠️ "...biliary duct dilation suspected due to enlarged hepatic artery and portal vein..." — **fact inversion**: the source explicitly says bile ducts are "nedilatate/nevizualizate" (non-dilated/not visualized), the opposite of what's claimed; also leaves an unclosed ` ```text ` code fence |
| `google/gemma-3-4b` | ❌ Romanian: "Suspectă atrezie biliară, splenomegalie" — correct content, wrong language despite `--language English` |
| `qwen/qwen3-4b` | ❌ Romanian: "Suspiciune de atrezie biliara" — same pattern |
| `llama-3.2-3b-instruct` | ❌ "Left lower lobe fatty infiltration" — wrong diagnosis, not even in the same organ system as the reference finding |
| `llama-3.2-1b-instruct` | ❌ "Splenohepatic cavernomatie" — garbled/invented term |
| `lfm2.5-1.2b-instruct` | ❌ "Left lower lobe pneumonia" — wrong diagnosis |
| `google/gemma-3-1b` | ❌ Romanian: "Atrezii biliare" — correct diagnosis, wrong language |
| `granite-4.1-3b` | ❌ "Fatty liver with hepatic artery enlargement" — coherent English but wrong diagnosis |
| `gemma-3-270m-it` | ❌ empty output (0 tokens generated) |
| `functiongemma-270m-it` | ❌ garbled function-call tokens (`<start_function_call>...`) followed by an echo of the source text — wrong tool for this task, see below |

### lab (600 max_tokens)

| Model | Result |
|---|---|
| `lmstudio-community/qwen3.5-4b` | ✅ correct terms and impression, English, well-structured |
| `google/gemma-3n-e2b` | ✅ correct, clean English |
| `qwen/qwen3-vl-4b` | ✅ correct, clean English |
| `nvidia/nemotron-3-nano-4b` | ✅ correct, terse |
| `qwen3-4b-instruct-2507` | ❌ **fact inversion**: states direct bilirubin "is within normal limits" — the source shows it severely elevated (~9-10 mg/dL vs. normal 0-0.2), the single most clinically important finding in this panel |
| `phi-3.1-mini-4k-instruct` | ✅ correct, clean |
| `phi-4-mini-reasoning` | ❌ reasoning leak, entire 600-token budget spent narrating |
| `qwen3-0.6b`/`qwen3-1.7b` (`/no_think`) | ✅ clean, correct — `/no_think` works here |
| `qwen3.5-*-opus-distilled` (`/no_think`) | ❌ reasoning leak persists |
| `lfm2.5-350m`, `lfm2.5-vl-1.6b`, `lfm2-2.6b-transcript`, `tinyllama-1.1b-chat-v1.0` | ✅ plausible/correct (tinyllama fits within lab's shorter context here, unlike `report`/`pre_exam`) |
| `lfm2.5-1.2b-thinking`, `lfm2.5-8b-a1b` | ❌ reasoning leak |
| `medgemma-4b-it` (production baseline) | ✅ correct terms and impression ("Cholestasis with renal impairment and systemic inflammation"), clean English |
| `ministral-3-3b-instruct-2512` (current production, added late — see Group 5 note above) | ✅ correct |
| `medgemma-1.5-4b-it` | ✅ correct terms, clean English, well-structured findings list |
| `google/gemma-3-4b` | ✅ correct, clean English |
| `qwen/qwen3-4b` | ✅ correct, clean English |
| `llama-3.2-3b-instruct` | ✅ correct, clean English |
| `llama-3.2-1b-instruct` | ✅ correct impression, clean English |
| `lfm2.5-1.2b-instruct` | ✅ correct, clean English |
| `google/gemma-3-1b` | ✅ correct impression, clean English |
| `granite-4.1-3b` | ✅ correct, clean English, clinically coherent |
| `gemma-3-270m-it` | ⚠️ just restates the abnormal-analyte list verbatim, no actual clinical impression |
| `functiongemma-270m-it` | ❌ outright refuses: "I cannot fulfill this request. My current capabilities are limited to..." |

### report (340 max_tokens, plain prose, no headings)

| Model | Result |
|---|---|
| `lmstudio-community/qwen3.5-4b` | ✅ faithful, correctly reports "mild central intrahepatic bile duct dilation" — verified against the source, this detail is real (confirmed in the 14.11 ultrasound note) |
| `lfm2-2.6b-transcript` | ✅ faithful, also correctly captures the bile duct dilation finding |
| `qwen/qwen3-vl-4b` | ❌ **fact inversion**: states "no intrahepatic biliary dilatation" — directly contradicts the source's "cai biliare intrahepatice usor dilatate" (slightly dilated) |
| `qwen3-4b-instruct-2507` | ❌ same fact inversion: "no evidence of intrahepatic bile duct dilation at 14.11.2025" — wrong, in the same direction as `qwen3-vl-4b`. (Interestingly, this same model got the *same* finding correct on `pre_exam` — see note below.) |
| `google/gemma-3n-e2b` | ⚠️ mostly faithful but calls the Kasai portoenterostomy a "Kasai liver transplant" — no transplant occurred; a terminology-level hallucination |
| `lfm2.5-vl-1.6b` | ❌ hallucinates "portal hypertension" and explicitly states "No evidence of biliary obstruction" — directly contradicts the case (biliary atresia *is* the diagnosis) |
| `lfm2.5-350m` | ❌ answers in **Romanian**, wrong language |
| `tinyllama-1.1b-chat-v1.0` | ❌ crashes: context length (2048) too small for this ~7500-char input |
| `phi-3.1-mini-4k-instruct` | ❌ **incoherent garbled output** ("for it3dultre, not the for and1void if4xigns...") — a serious generation failure, not just a format miss |
| `phi-4-mini-reasoning`, `lfm2.5-1.2b-thinking`, `lfm2.5-8b-a1b` | ❌ reasoning leak |
| `qwen3-0.6b`/`qwen3-1.7b` (`/no_think`) | ✅ clean, faithful English |
| `qwen3.5-*-opus-distilled` (`/no_think`) | ❌ reasoning leak persists |
| `medgemma-4b-it` (production baseline) | ✅ faithful, correct English summary; captures Kasai portoenterostomy, jaundice, ascites, bilateral hydrocele, postoperative course and prednisone, no fabrication |
| `ministral-3-3b-instruct-2512` (current production, added late — see Group 5 note above) | ❌ **fabricates family history** — "a history of paternal grandfather's unspecified cardiac conditions requiring long-term monitoring" appears nowhere in the source |
| `qwen/qwen3-4b` | ✅ faithful, correct, plausible inferences flagged as such |
| `medgemma-1.5-4b-it` | ⚠️ mostly faithful but **fabricates** "recurrence of biliary atresia" (atresia is a congenital defect, corrected surgically — it doesn't "recur") and "post-operative complications including bowel obstruction requiring drainage" (the drain was routine post-Kasai placement, not a bowel-obstruction complication) |
| `google/gemma-3-4b` | ❌ **hallucination**: misreads the Romanian ultrasound abbreviation "LDH" (lobul drept hepatic / right hepatic lobe measurement) as the lab test "LDH" (lactate dehydrogenase) — "elevated liver enzymes (LDH)" is not supported by the source at all |
| `llama-3.2-3b-instruct` | ❌ Romanian language leak, **and** a fact inversion within it: writes "febrilă" (febrile) where the source explicitly says "Afebril" (afebrile) |
| `llama-3.2-1b-instruct` | ❌ **fabricates** an ERCP procedure ("Cholangiopancreatography (CPA) and endoscopic retrograde cholangiopancreatography (ERCP) were performed") that never happened — the actual procedure was intraoperative cholangiography during the Kasai surgery; also mistranslates "colecist" (gallbladder) as "colon" |
| `lfm2.5-1.2b-instruct` | ❌ **fabricates** "Imaging confirmed biliary dilatation and pancreatic involvement" — no pancreatic finding anywhere in the source |
| `google/gemma-3-1b` | ❌ **fabricates** "laparoscopic cholecystectomy" (no gallbladder removal occurred — it was a Kasai portoenterostomy) |
| `granite-4.1-3b` | ✅ faithful, coherent English, no fabrication spotted |
| `gemma-3-270m-it` | ❌ empty output |
| `functiongemma-270m-it` | ❌ refuses: "I am sorry, but I cannot assist with drafting medical documentation..." |

### pre_exam (1300 max_tokens, heaviest kind)

| Model | Result |
|---|---|
| `lmstudio-community/qwen3.5-4b` | ⚠️ good structure, correctly surfaces the bile-duct-dilation finding here (unlike its confusion-free performance elsewhere), but garbles one date as "**19890**" and fabricates "graft rejection prevention" as the reason for prednisone — no transplant occurred, this is an ungrounded inference |
| `qwen3-4b-instruct-2507` | ✅ correctly states "mild intrahepatic biliary dilatation" here — i.e. its `report`-kind inversion was kind/context-specific, not a universal model failure (same "short-kind dilution" pattern documented for medgemma-4b-it in the 07-21/22 rounds) |
| `nvidia/nemotron-3-nano-4b` | ✅ reasonable structure and content |
| `lmstudio-community/qwen3.5-2b` | ❌ Summary line says "Liver cirrhosis and cholestatic liver disease" — misses the actual diagnosis (biliary atresia) entirely |
| `phi-3.1-mini-4k-instruct` | ❌ crashed: `RuntimeError: Model reloaded` (VRAM contention on the 4 GB cards under the heaviest kind, consistent with prior rounds) |
| `phi-4-mini-reasoning` | ❌ reasoning leak, plus fabricates "Cyclosporin" and "jejunostomy" — not in the source |
| `qwen3-0.6b`/`qwen3-1.7b` (`/no_think`) | ⚠️ clean English, no leak, but `qwen3-0.6b` is thin/generic content; `qwen3-1.7b` reasonably captures the diagnosis and specialty |
| `qwen3.5-*-opus-distilled` (`/no_think`) | ❌ reasoning leak persists, consumes the full 1300-token budget on both |
| `lfm2.5-vl-1.6b`, `qwen/qwen3-vl-4b`, `google/gemma-3n-e2b`, `lfm2-2.6b-transcript` | ✅ reasonable structure/content, no crashes |
| `lfm2.5-1.2b-thinking`, `lfm2.5-8b-a1b` | ❌ reasoning leak |
| `medgemma-4b-it` (production baseline) | ❌ **full Romanian-language leak** despite `--language English` — reproduces the source almost verbatim in Romanian rather than an English structured summary (same failure class documented in the 07-21/22 rounds for this exact model/kind combination); also fabricates the date "2019-12-17" for the biliary-atresia-operated history item, apparently misreading the "17/12/2025 12:00" header field and mangling the year. Slowest run of the whole survey: 174.9s total, 7.5 tok/s |
| `qwen/qwen3-4b` | ✅ cleanest of this whole group — faithful summary, correctly captures the mild bile-duct dilation, well-structured, no fabrication |
| `ministral-3-3b-instruct-2512` (current production, added late — see Group 5 note above) | ❌ **fabricates a liver-transplant workup** — "pediatric liver transplant evaluation," "follow-up liver transplant candidate" — this is a post-Kasai case, no transplant was ever considered in the source; also the recurring stray-header-date fabrication seen in other models on this kind |
| `llama-3.2-1b-instruct` | ⚠️ reasonable structure and mostly faithful, but one nonsensical line ("Where its course is heading: Chasing cai biliare") |
| `google/gemma-3-4b` | ❌ **serious fabrication**: invents "Fetal growth restriction" and "Gastroschisis" as diagnoses under 04.11.2025 — neither appears anywhere in the source (the actual source line there is birth history: gestational age 34 weeks, birth weight 1950g, unrelated to that date) |
| `llama-3.2-3b-instruct` | ❌ Romanian language leak (violates `--language English`) |
| `medgemma-1.5-4b-it` | ❌ **breaks entirely**: leaks raw chain-of-thought/planning tokens (`<unused94>thought The user wants me to act as a clinical assistant...`) and burns the full 1300-token budget on step-by-step planning without ever producing the actual briefing — a serious regression given production `medgemma-4b-it` is clean on this exact kind |
| `lfm2.5-1.2b-instruct` | ❌ **heavy fabrication**: invents a "CT scan" that was never performed, a "suspicious pancreatic mass" not in the source, and specific lab values ("elevated LDH... mild hyperbilirubinemia") not present anywhere — the same LDH-abbreviation misreading seen in `gemma-3-4b`'s `report` output |
| `google/gemma-3-1b` | ❌ **fabrication + fact inversion**: diagnoses "cirrhosis" (not stated; actual diagnosis is biliary atresia), invents "internal bleeding" as the reason for surgery, and claims the 04.11.2025 ultrasound "revealed no significant abnormalities" — the opposite of the source, which raised suspicion of biliary atresia with multiple abnormal findings |
| `granite-4.1-3b` | ✅ coherent structure, correct diagnosis ("Biliary atresia (post-Kasai)"), no fabrication spotted |
| `gemma-3-270m-it` | ❌ produces 1155 tokens of meta-commentary about the task instructions instead of the actual briefing |
| `functiongemma-270m-it` | ❌ refuses again |
| `phi-4-mini-instruct` | ❌ untested — **fails to load server-side** after a corrupted/resumed download, see below |

### `lfm2-350m-extract` (all 4 kinds) — wrong tool for this task

Added mid-round per request. This is a structured-JSON-extraction model, not
a prose-summarization one: every kind returned a raw JSON object with
invented, non-schema field names (`"problema_academico"`,
`"sistema_completo"`, `"diagnostica_principal"` — not real terms in either
language) instead of the plain-prose output every kind requires. Fast
(73-92 tok/s) but **structurally incompatible** with the app's prompts —
not a quality gap that prompt-tuning could close.

### `gemma-4-e2b-it` — unusable, server-side load failure

Every attempt returns `"Failed to load model \"gemma-4-e2b-it\". Error:
Error loading model."` — confirmed via a direct minimal `curl` call, so this
is not specific to `benchmark_llm.py`'s request shape. The model file/config
on the LM Studio server appears broken; not evaluable until re-downloaded or
fixed server-side.

### `gemma-3-270m-it` / `functiongemma-270m-it` — too small / wrong tool

`gemma-3-270m-it` (0.25 GB) is simply too small for this task: empty output
on `imaging`, a bare restatement of the input on `lab`, and 1155 tokens of
meta-commentary about the prompt's own instructions on `pre_exam` instead of
an actual answer. `functiongemma-270m-it` is Google's function-calling-
specialized Gemma variant — as its name suggests, it refuses free-text
summarization outright on every kind except `imaging` (where it emits
garbled `<start_function_call>` tokens and echoes the source back). Neither
is a fit for this app's prose-summarization prompts regardless of prompt
tuning — same class of mismatch as `lfm2-350m-extract`.

### `phi-4-mini-instruct` — untested, corrupted download

Distinct from the already-tested (and already-ruled-out) reasoning variant
`phi-4-mini-reasoning`. The download (`unsloth/Phi-4-mini-instruct-GGUF`,
Q4_K_M) needed 3 automatic resumes after repeated mid-transfer failures on
this network link; the file completed at the correct byte count but then
fails to load with the identical error signature as `gemma-4-e2b-it`
(`"Error loading model."`, confirmed via both `/v1/chat/completions` and
`/api/v1/models/load` directly). Suspected cause: LM Studio's resume-on-
`failed` mechanism doesn't cleanly stitch the partial chunks. There's no
delete endpoint in the native REST API, and remote filesystem access to the
LM Studio host wasn't available to remove the file by hand, so this model is
untested this round — treat as unresolved, not as a quality finding.

### `glm-edge-4b-chat` — new Chinese-origin candidate, hard context ceiling

Downloaded per user request as a multilingual candidate (Zhipu AI/`zai-org`,
`zai-org/glm-edge-4b-chat-gguf`, Q4_K_M, 2.63 GB). English-only tested this
round (context limitation below makes a Romanian rerun moot for 2 of the 4
kinds regardless of language). Results: ❌ wrong diagnosis on `imaging`
("Right lobe liver hypervascularity" vs. the reference "Suspected biliary
atresia") but coherent English; ✅ correct and clean on `lab`
("leukocytosis" identified accurately); ❌ **crashes on `report`** —
`RuntimeError: ... n_keep: 3534 >= n_ctx: 3072` — and would crash the same
way on `pre_exam` for the same reason, not separately tested. Checked
`max_context_length` directly via `/api/v1/models`: **3072 is a hard
architectural ceiling for this model**, not a configurable load default (no
`--context-length` override can raise it), so this is a permanent
disqualifier for the two longer kinds on this fixture — same failure class
as `tinyllama-1.1b-chat-v1.0`'s context crash, just a different underlying
model family.

## Key findings (Phase 1, English round)

Scoped to this round's English-only Phase 1 data — a snapshot, not the
final word. The Romanian-language rerun, Phase 2, Phase 2 extended, and
Phase 4 sections further down each have their own "New findings"/"What
this changes" writeups covering what came after this point; the current
overall verdict belongs in `llm_benchmark_2026-07-31_final_report.md`
(pending a rebuild from this now-complete doc), not here. Kept as-written
below since it was accurate for what it covered at the time.

1. **`qwen3-4b`-family fact inversions on `report`**: both `qwen/qwen3-vl-4b`
   and `qwen3-4b-instruct-2507` independently inverted the same clinical
   fact (bile duct dilation status) on the `report` kind specifically, while
   getting it right on `pre_exam`. This mirrors the "short-kind dilution"
   pattern already documented for medgemma-4b-it — worth treating as a
   known risk class, not a one-off.
2. **`/no_think` is not a universal fix**: it suppresses reasoning leakage
   on plain `qwen3-0.6b`/`qwen3-1.7b`, but the two
   `qwen3.5-*-claude-opus-reasoning-distilled` finetunes ignore it entirely
   and leak on every kind regardless — their distillation training appears
   to have baked in always-on reasoning that the standard suppression token
   doesn't reach.
3. **`phi-4-mini-reasoning` is unusable as configured**: leaks full CoT on
   every kind tested, consuming the entire token budget, matching the
   `reasoning: {"effort": "none"}` limitation already documented for other
   reasoning models. No suppression mechanism found for it in this round.
4. **Two outright-broken candidates**: `gemma-4-e2b-it` (server load
   failure) and `phi-3.1-mini-4k-instruct` (produces incoherent garbled text
   on `report`, and crashes outright on `pre_exam`) — not viable regardless
   of prompt work.
5. **`lmstudio-community/qwen3.5-4b` is the strongest new candidate**: clean
   English on `imaging`/`lab`/`report`, and the only model besides
   `lfm2-2.6b-transcript` to correctly catch the bile-duct-dilation finding
   on `report`. Its `pre_exam` output has two real but narrower issues (a
   garbled date, an ungrounded "graft rejection" inference) — not
   disqualifying on their own, but worth a second `pre_exam` pass before
   promoting it.
6. **`nvidia/nemotron-3-nano-4b`**: consistently correct and notably terse
   across kinds, with one Romanian term-leak on `imaging` — a smaller
   version of the medgemma-4b-it pattern, worth a closer look.
7. **Production baseline `medgemma-4b-it` reproduces its known `pre_exam`
   language leak**: added late as a like-for-like comparison point. It's
   solid on `lab`/`report` (best-in-round on `report`, no fabrication) and
   reasonable on `imaging`, but reproduces the exact `pre_exam`
   Romanian-language leak documented in the 07-21/22 rounds — `--language
   English` does not override it — plus a new date-mangling hallucination
   (17/12/2025 misread as 2019-12-17) and the slowest run of the entire
   survey (174.9s, 7.5 tok/s). Confirms the `pre_exam` weakness is a
   standing, reproducible issue with the current production model, not a
   one-off from the earlier rounds.
8. **`qwen/qwen3-4b` is fabrication-free on 3 of 4 English kinds, with the
   best-in-round faithful `pre_exam` output** (no other model this round or
   the last was fabrication-free on `pre_exam`) — correct on `lab`,
   `report`, and `pre_exam`. **Correction, caught during the final-report
   rebuild**: it is *not* clean on all 4 English kinds — its own `imaging`
   row above shows it answered in Romanian ("Suspiciune de atrezie
   biliara") despite `--language English`, the same language-leak failure
   class documented for several other models on this exact kind. The
   "cleanest model in the entire survey" framing used here and in the
   Romanian-rerun and Follow-ups sections below overstated this by missing
   its own imaging row; corrected there too. Still distinct from the
   already-tested `qwen3-4b-instruct-2507`, which *did* fact-invert on
   `report`, and still the strongest Phase 1 record once this leak is
   weighed against every other model's issues — just not a spotless one.
9. **The same "LDH" misreading hallucination appeared independently in two
   different model families**: `google/gemma-3-4b` (on `pre_exam`) and
   `lfm2.5-1.2b-instruct` (also on `pre_exam`) both invented "elevated liver
   enzymes (LDH)" by misreading the Romanian ultrasound abbreviation "LDH"
   (lobul drept hepatic / right hepatic lobe) as the lab test lactate
   dehydrogenase. Worth flagging as a known ambiguous-abbreviation risk in
   this specific source-document style, not a one-model quirk.
10. **`medgemma-1.5-4b-it` is a regression from production `medgemma-4b-it`
    on `pre_exam`**: it leaks raw chain-of-thought/planning tokens and burns
    its entire token budget without producing an answer, where the
    production model (despite its own known Romanian-leak issue there) at
    least attempts the task. Also fact-inverts on `imaging` ("biliary duct
    dilation suspected" vs. the source's explicit "non-dilated"). Not a
    drop-in upgrade candidate as tested.
11. **`granite-4.1-3b` and `functiongemma-270m-it`/`gemma-3-270m-it`**:
    Granite was consistently coherent and fabrication-free across all 4
    kinds (weaker only on `imaging`, wrong diagnosis but not incoherent) —
    a genuine new candidate. The two 270M models are not viable for this
    task at any prompt-tuning level: one is too small to hold enough context
    for a useful answer, the other is architecturally a function-calling
    model that refuses free-text summarization.

## Updated recommendation (Phase 1, English round snapshot)

Scoped to this round's English-only Phase 1 data, written before ministral
was ever benchmarked (Group 5), before the Romanian rerun, and before
either Phase 2 round. **Superseded** — kept as-written for the historical
record, not as current guidance. In short, here's what changed after this
snapshot: ministral (referenced below as "no change to production")
turned out to be the weakest of the five models seriously tested once
actually benchmarked (Phase 2 extended: 7 clean, 8 fail, 2 minor — see
Group 5 and the Phase 2 extended section); `qwen/qwen3-4b`'s "cleanest
model in the survey" standing here didn't fully generalize (it fabricates
on Case C, the no-clinical-content trap, both in Phase 2 and again in the
Phase 4 retest); and `qwen3.5-4b` picked up a recurring ICU-inflation
issue in Phase 2 extended that a Phase 4 prompt fix only partially
resolved before being reverted. See
`llm_benchmark_2026-07-31_final_report.md` (pending a rebuild) for the
current, full-data verdict.

**No change to production** (`ministral-3-3b-instruct-2512` /
`gemma-3n-e4b` fallback, per the 07-19/07-21 docs) — nothing tested this
round has a cleaner sheet than those two.

**Worth a follow-up round**: `qwen/qwen3-4b` is now the top overall
candidate — fabrication-free on all 4 kinds including `pre_exam`, where
every other model this round or last had at least one real issue. Re-test it
once more in isolation to confirm before considering promotion.
`lmstudio-community/qwen3.5-4b` and `granite-4.1-3b` are secondary
candidates (both fabrication-free except `qwen3.5-4b`'s narrower `pre_exam`
issues noted above); `nvidia/nemotron-3-nano-4b` and `qwen/qwen3-vl-4b`
remain tertiary options.

**Ruled out this round**: `gemma-4-e2b-it` (broken load), `phi-3.1-mini-4k-instruct`
(incoherent/crashes), `phi-4-mini-reasoning` (unsuppressable reasoning leak),
`qwen3.5-*-opus-reasoning-distilled` (unsuppressable reasoning leak),
`lfm2.5-1.2b-thinking`/`lfm2.5-8b-a1b` (reasoning leak), `tinyllama-1.1b-chat-v1.0`
(context too small for `report`/`pre_exam`), `lfm2.5-350m` (nonsense/wrong-language
output), `lfm2.5-vl-1.6b` (hallucinates contradicting the core diagnosis),
`lfm2-350m-extract` (wrong output format for this app entirely),
`medgemma-1.5-4b-it` (CoT leak on `pre_exam`, fact inversion on `imaging`),
`google/gemma-3-4b` (fabricated diagnosis on `pre_exam`), `llama-3.2-3b-instruct`
(Romanian leak + fact inversion), `llama-3.2-1b-instruct` (fabricated
procedure), `lfm2.5-1.2b-instruct` (fabricated findings), `google/gemma-3-1b`
(fabrication + fact inversion), `gemma-3-270m-it`/`functiongemma-270m-it`
(too small / wrong tool), `phi-4-mini-instruct` (untested, corrupted
download), `glm-edge-4b-chat` (hard 3072-token context ceiling, crashes
`report`/`pre_exam`).

## Romanian-language rerun

Production's actual default is `[llm] language = Romanian` (`local.cfg`,
still unconfirmed as intentional — see follow-up #1). Every result above was
run with `--language English` for a clean apples-to-apples comparison with
prior rounds, which means none of it tested what the app actually outputs
by default. This section re-runs every model that produced *usable* output
in English — i.e. excludes models that are structurally broken independent
of language (`gemma-4-e2b-it`/`phi-4-mini-instruct` don't load,
`lfm2-350m-extract`/`functiongemma-270m-it`/`gemma-3-270m-it` are wrong-
tool/too-small, reasoning-leak models leak regardless of language,
`tinyllama-1.1b-chat-v1.0` crashes from context length, `lfm2.5-350m`
produced nonsense even in English, `phi-3.1-mini-4k-instruct` was already
incoherent/crashing in English) — same method otherwise: just drop
`--language English` so it falls through to Romanian, same fixtures, same 2
warm iterations. 19 models × 4 kinds = 76 runs, in 4 batches (`_testing_/
r32_b{1,2,3,4}_<kind>.md`/`.json`), `--no-think` kept for `qwen3-0.6b`/
`qwen3-1.7b` since it's still needed regardless of output language.

**Judged against the same source facts as the English round** (not the
English reference text, since a faithful Romanian summary won't match it
word-for-word).

### Overall pattern: language leakage runs in *both* directions

The English round's leak direction was consistently non-English-into-the-
answer (Romanian terms/whole answers leaking into an English-requested
output). In Romanian, several models leaked the *opposite* way — answering
in English despite the Romanian directive — a failure mode that never
appeared in the English round because there was nothing to leak into:

- `lfm2.5-vl-1.6b`, `medgemma-1.5-4b-it`, and production `medgemma-4b-it`
  itself all answered in **English** on the Romanian `lab` run.
- `qwen3-0.6b` (`/no_think`) did the same on `lab`.
- `google/gemma-3-1b` produced a bizarre hybrid on `pre_exam` — English
  meta-commentary ("Okay, here's the Romanian translation of your provided
  briefing...") instead of ever actually answering.

This means language-instruction-following is inconsistent per kind per
model, not a fixed per-model trait — the same model can honor the language
directive on one kind and ignore it on another (`medgemma-4b-it` leaks only
on `pre_exam` in English but leaks on `lab` in Romanian; the reverse-leak
kind differs from the forward-leak kind).

### `medgemma-1.5-4b-it`'s `pre_exam` breakdown does not reproduce in Romanian

The single most significant delta: in English, `medgemma-1.5-4b-it` leaked
raw chain-of-thought/planning tokens on `pre_exam` and burned its entire
1300-token budget without ever producing an answer (see finding #10 above).
In Romanian, it produces a full, faithful, well-structured 1300-token
briefing with no CoT leak at all. This is a language-dependent failure, not
a universal defect in the model — worth real weight before writing this
model off entirely (see updated follow-up below).

### New hallucinations that only appeared in Romanian

Several models that were fabrication-free in English introduced new,
Romanian-only hallucinations — the language switch itself seems to be a
stress condition, not merely a style change:

- `granite-4.1-3b` — clean on all 4 kinds in English — fabricated
  "hidrocefalia" (hydrocephalus, a brain condition, completely unrelated to
  this abdominal case) on `lab`, and invented "Biliopancreatic obstruction
  (choledochal cyst)" on `pre_exam` (also reverting to English mid-answer
  for that one line) — neither finding exists anywhere in the source.
- `lfm2.5-1.2b-instruct` invented "colecistite"/"colecistectomie"
  (cholecystitis / cholecystectomy — neither occurred) on `report` and
  `pre_exam` respectively.
- `lfm2.5-vl-1.6b` fabricated a nonsensical patient weight ("var. de 19890
  kg") on `pre_exam` — garbling the same stray header field
  (`19890`/`17/12/2025`) that tripped up other models in the English round,
  but landing on an absurd, physically-impossible number here instead of a
  wrong date. It also lists a **surgical procedure** ("Portoanastomoza cu
  anse Y procedeu Kasai") under "Recommended imaging protocol" — a
  category-confusion error not seen in any English run.
- `nvidia/nemotron-3-nano-4b` degenerated into a **repetition loop** on
  `lab` ("azotemia, azotemia, azotemia..." repeated many times instead of a
  coherent impression) — was terse and clean in English; this is a
  generation-quality failure specific to Romanian output, not a translation
  or terminology issue.
- `medgemma-4b-it` still fabricates a spurious history date, just less
  severely than in English — invents "2025-12-17: Operatie de atrezie
  biliară" from the same stray `17/12/2025` header field (a
  more-plausible-but-still-wrong year here, vs. `2019-12-17` in English).
- `google/gemma-3-1b` also failed outright on `report` in Romanian
  ("Insufficient clinical information to summarize" — a flat non-answer for
  input it handled fine in English) in addition to the `pre_exam` mixed-
  language breakdown noted above.
- `llama-3.2-3b-instruct` fabricated a **"deteriorated condition"** on
  `pre_exam` in Romanian — not supported by the source, which documents a
  routine postoperative course. (Its English-round `report` result — a
  language leak plus the "febrilă"/"Afebril" fact inversion, documented
  above — was a separate, English-round failure, not this one.)
- `ministral-3-3b-instruct-2512` (current production, Group 5 — added late,
  see note above) fabricated **"hemolysis syndrome"** on `lab` in Romanian —
  a diagnosis the panel doesn't support (no reticulocyte count, LDH, or
  haptoglobin data to establish hemolysis) — despite being clean on `lab` in
  English. Its already-documented English fabrications (family history on
  `report`; the liver-transplant workup on `pre_exam`) persist in Romanian
  too, in altered form: `report` degrades to a minor nonsense compound term
  ("echocardiografia abdominală") rather than the English fabrication, while
  `pre_exam` keeps the correct primary diagnosis but invents a **duplicate
  surgical event** (a second, fabricated Kasai procedure under the same
  stray date that trips up other models). Unlike the other models in this
  list, ministral was not clean in English to begin with — this is a model
  that fabricates in both languages, just on different specifics.

### What held up well in Romanian

`qwen/qwen3-4b`, `qwen/qwen3-vl-4b`, and `google/gemma-3-4b` all stayed
faithful and coherent in Romanian across every kind checked, with no new
fabrications spotted — `qwen/qwen3-4b` in particular is confirmed clean
across all 4 kinds *when Romanian is the requested language*, still
strengthening its case as a top candidate. **Correction**: this is not the
same as "clean in both languages across all 4 kinds" as earlier drafts of
this doc claimed — its English-round `imaging` result leaks into Romanian
(see the Results-by-kind correction above), so its actual record is clean
Romanian throughout, clean English on 3 of 4 kinds. `qwen3-1.7b`
(`/no_think`) also held up cleanly on `report`/`pre_exam` in Romanian.

## Speed

Pulled directly from the benchmark JSON output for every model that
reached at least Tier D quality (Tier F models were ruled out on
correctness/architecture grounds before speed was a relevant factor, so no
comparable battery exists for them). **Σt** = total wall-clock seconds for
one full 4-kind battery (imaging+lab+report+pre_exam) at the warm-run
settings described in Methodology above. **tok/s** = weighted throughput
across those 4 kinds (`Σtokens / Σtime`, not an average of 4 per-kind
rates, so a couple of near-instant `imaging`-kind outputs can't skew it).
All 19 models below were retested in Romanian; every model that reached
Tier D or better in English has both columns.

| Model | EN Σt / tok/s | RO Σt / tok/s |
|---|---|---|
| `qwen/qwen3-4b` | 133s / 5.3 | 162s / 6.1 |
| `lmstudio-community/qwen3.5-4b` | 179s / 6.6 | 204s / 6.6 |
| `qwen/qwen3-vl-4b` | 118s / 7.6 | 177s / 8.3 |
| `qwen3-4b-instruct-2507` | 193s / 5.9 | 263s / 6.0 |
| `qwen3-1.7b` (`/no_think`) | 84s / 16.3 | 85s / 14.7 |
| `lfm2-2.6b-transcript` | 138s / 11.4 | 159s / 14.0 |
| `medgemma-4b-it` (production baseline) | 204s / 7.4 | 333s / 5.1 |
| `granite-4.1-3b` | 135s / 8.6 | 89s / 9.1 |
| `nvidia/nemotron-3-nano-4b` | 115s / 8.3 | 114s / 11.3 |
| `qwen3-0.6b` (`/no_think`) | 46s / 24.8 | 45s / 25.1 |
| `lmstudio-community/qwen3.5-2b` | 65s / 19.7 | 94s / 15.7 |
| `google/gemma-3n-e2b` | 62s / 12.3 | 62s / 14.1 |
| `llama-3.2-1b-instruct` | 54s / 26.8 | 106s / 15.4 |
| `llama-3.2-3b-instruct` | 119s / 8.9 | 127s / 10.7 |
| `medgemma-1.5-4b-it` | 246s / 7.0 | 160s / 11.7 |
| `google/gemma-3-4b` | 95s / 9.0 | 132s / 9.0 |
| `google/gemma-3-1b` | 45s / 24.7 | 34s / 29.6 |
| `lfm2.5-1.2b-instruct` | 20s / 30.0 | 34s / 23.8 |
| `lfm2.5-vl-1.6b` | 39s / 31.2 | 51s / 35.9 |

Fastest raw throughput (`lfm2.5-vl-1.6b`, `lfm2.5-1.2b-instruct`,
`google/gemma-3-1b`) belongs to Tier D models disqualified on correctness —
speed only matters as a tiebreaker within Tier A/B, where `qwen/qwen3-vl-4b`
is the fastest option holding up under fact-checking (see Follow-ups for
the caveat that it's Phase-1-only, not yet run through Phase 2).
`medgemma-4b-it`'s Romanian `pre_exam` run (folded into the 333s/5.1 RO
total here) was individually the slowest single run of the whole survey at
174.9s, 7.5 tok/s.

## Phase 2: confirmation on 4 independent real fixtures

Everything above (Phase 1) used a single fixture — the primary
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
2-warm-iteration settings. `ministral-3-3b-instruct-2512` (Group 5, added
late) was run against the same 4 cases separately — see its own column
below. Cases are referenced by letter only — the source `case_data.json`
files contain real patient names, kept out of anything committed, same
convention as the rest of this doc. Raw JSON/markdown dumps:
`_testing_/r33_case*` (the 4 original contenders), `_testing_/r34_case*`
(ministral) — both gitignored, retained locally.

### Results

| Case | `qwen/qwen3-4b` | `qwen3-4b-instruct-2507` | `qwen3.5-4b` | `medgemma-4b-it` | `ministral-3-3b-instruct-2512` (production) |
|---|---|---|---|---|---|
| A (ortho) | ✅ correct | ❌ mistranslates diagnosis as "polyneuropathy" (source: equinus **foot** deformity) | ✅ correct (verbose) | ✅ correct | ❌ **wrongly refuses** — "Insufficient clinical information to summarize" for a case that has a real diagnosis, a consult finding, and a treatment decision |
| B (cardio) | ✅ correct | ✅ correct | ✅ correct | ❌ **fabricates** "a pericardial effusion" — source explicitly says "Pericard liber" (pericardium clear, no effusion) | ✅ accurate, correctly avoids the pericardial-effusion trap that caught `medgemma-4b-it` |
| C (no clinical content) | ❌ **fabricates** an admission narrative ("admitted for respiratory symptoms... treated with a course of respiratory therapy") — none of this is in the source | ✅ correctly answers "Insufficient clinical information to summarize" | ✅ same correct non-answer | ❌ **fabricates** ("admitted for vaccination schedule and respiratory health management") | ✅ correctly declines — this is the one case where declining is right |
| D (oncology) | ✅ correct but thin (misses most of the clinical detail) | ✅ correct and detailed (tumor regression measurements, RS hypoplasia, port removal/reinsertion — all verified against source) | ✅ correct and detailed (transfer destination, wound status, port history — all verified) | ⚠️ **Romanian-language leak** again despite `--language English`; the portion produced before truncation appears factually sound | ✅ accurate and reasonably detailed |
| **Score** | **3/4** | **3/4** | **4/4** | **1/4** | **3/4** |

`ministral`'s 3/4 score needs a caveat the others don't: it declined twice
out of four cases, right once (C, genuinely empty) and wrong once (A, real
content present). That reads less like principled recognition of "nothing
to summarize" and more like a general bias toward declining — worth
treating this 3/4 with more caution than the same score earned by
`qwen3-4b`/`qwen3-4b-instruct-2507`, neither of which ever triggered a
false refusal.

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
6. **`ministral` (current production), tested here for the first time
   against this same battery, does not hold up well**: a false refusal on
   real content (Case A) alongside a correct refusal on genuinely empty
   content (Case C) — a pattern that reads as a general bias toward
   declining rather than principled recognition of "nothing to summarize."

## Phase 2 extended: 5 more cases, plus `pre_exam`

The original Phase 2 (4 cases, `report` only) was too small to trust a
ranking built on a single-case margin between the top 3 contenders. Added:
5 more real fixtures (Cases E-I, from the same `_testing_/cases_*` pool,
chosen for specialty/size diversity — hepatology, ENT, febrile-infant
pediatrics, cardiology/Holter, and a dense infant-respiratory case with a
confirmed pertussis co-infection) and the `pre_exam` kind on 8 of the 9
cases total (Case A excluded — at 345 bytes, too small to meaningfully
stress a 1300-token synthesis prompt). Same 4 models (`qwen/qwen3-4b`,
`qwen3-4b-instruct-2507`, `qwen3.5-4b`, `medgemma-4b-it`), same settings.
This brings the total evidence base to **17 independent test cells per
model** for these four. `ministral-3-3b-instruct-2512` (Group 5) was not
included when this section was originally written, but was closed out
later at full parity: `report` on Cases E-I and `pre_exam` on Cases B-I,
same settings, English. Raw JSON/markdown dumps: `_testing_/r35_case*`
(the original 4 contenders' batch), `_testing_/r36_case*` (ministral's
parity batch, run separately).

### Full scorecard

| | `report` (9 cases) | `pre_exam` (8 cases) | Combined |
|---|---|---|---|
| `qwen/qwen3-4b` | 6 clean, 2 fail, 1 minor | 5 clean, 0 fail, 3 minor | **11 clean, 2 fail, 4 minor** |
| `qwen3-4b-instruct-2507` | 5 clean, 3 fail, 1 minor | 4 clean, 2 fail, 2 minor | 9 clean, 5 fail, 3 minor |
| `lmstudio-community/qwen3.5-4b` | 7 clean, 1 fail, 1 minor | 3 clean, 3 fail, 2 minor | 10 clean, 4 fail, 3 minor |
| `ministral-3-3b-instruct-2512` (production) | 5 clean, 3 fail, 1 minor | 2 clean, 5 fail, 1 minor | 7 clean, 8 fail, 2 minor |
| `medgemma-4b-it` | 2 clean, 5 fail, 2 minor | 2 clean, 5 fail, 1 minor | 4 clean, 10 fail, 3 minor |

"Fail" = a real, verifiable error (fabrication, fact inversion, language
leak, or a mistranslation changing clinical meaning). "Minor" = a real but
lower-stakes issue (imprecise terminology, unsupported-but-plausible
inference in the AI-suggestions section, thinness/omission without an
active false claim).

`ministral`'s combined tally puts it second-worst of the five models
tested against this battery — closer to `medgemma-4b-it`'s failure rate
than to any of the three Qwen variants. Case-by-case: `report` — clean on
B/C/D (repeating its earlier Phase 2 results)/E/F; fails on A (already
documented, false refusal), G (Romanian-language leak despite `--language
English`, content otherwise accurate), and H (see finding below); minor on
I (an unsupported "may affect imaging interpretation" inference, though it
correctly surfaces the Bordetella pertussis finding other models dropped
under this same budget). `pre_exam` — clean on B and H; fails on C
(severe — see below), D, G, and I (see findings below); minor on E and F
(the already-documented date-fabrication trap, in two different flavors —
see below).

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
7. **`ministral-3-3b-instruct-2512`'s worst hallucination of its entire
   benchmark history, found on Case C's `pre_exam`**: given the same
   "no clinical content" administrative sheet that made it fabricate an
   admission narrative on `report`, `pre_exam` produced something more
   severe — a fabricated **"chronic respiratory disease"** diagnosis
   complete with a full differential (COPD exacerbation, interstitial lung
   disease, bronchiectasis, pulmonary embolism, post-viral sequelae) and an
   imaging-protocol recommendation, none of it grounded in anything the
   source contains. The larger `pre_exam` budget didn't give the model more
   room to notice there was nothing to summarize — it gave it more room to
   invent a plausible-sounding workup.
8. **`ministral` reproduces the RS-abbreviation ambiguity independently**:
   on Case D's `pre_exam`, it translated "RS" (glanda suprarenala / left
   suprarenal gland, per the source's own preceding "glandei suprarenale
   stangi") as "right kidney" — wrong organ, wrong side. Same case also
   shows a date conflation: the laparoscopic segmentectomy is dated
   "05.11.2024" in the model's output, but that's the source's MRI date —
   the actual surgery was "7.11.2024," documented one paragraph earlier and
   again correctly used elsewhere in the same output for the port-catheter
   procedure. Independent confirmation of the RS ambiguity already flagged
   for `medgemma-4b-it`, and a second instance of the "confuses two
   different dated events in the same source" pattern.
9. **A third, distinct flavor of the date-fabrication trap**: on Case F
   (another no-absolute-dates source), rather than inventing a specific
   wrong date like every other model on Cases E/F, `ministral` emitted the
   literal unfilled template string **"2026-MM"** three times in the
   `History` section — a broken-placeholder leak, not a fabricated value.
   Doesn't assert anything false, but it's a different way the same
   date-bullet format breaks under a dateless source, worth folding into
   the same prompt fix as the other date-trap findings.
10. **Recurring bronchiolitis/failure mistranslation on Case I**: across
    all three of its history's admission references, `ministral` rendered
    the source's "Bronsiolita acuta" (acute bronchiolitis) as "acute
    bronchitis" — a different, less severe pediatric diagnosis, repeated
    consistently rather than a one-off slip. The same entry also
    mistranslates "IRA" (insuficienta respiratorie acuta / acute
    respiratory failure) as "fever," understating the severity of that
    admission. The same output separately claims the pediatric cardiology
    evaluation is "pending," when the source shows it was completed with a
    normal result — a minor fact inversion on top of the terminology
    errors.

## Phase 4: prompt fixes for the ICU-inflation, date-fabrication, and no-content findings — attempted, reverted

**Not a clear win — reverted, not shipped.** Three of findings 1/4 above
(`qwen3.5-4b`'s ICU inflation, the universal date-fabrication trap, and
Case C's fabrication-instead-of-declining pattern) got prompt-level fixes
in `llm/prompts/pre_exam.md` and `llm/prompts/report.md`, tested below, and
then **reverted to the last working (production) version** once the
retest showed genuinely mixed results rather than a fix. `llm/prompts/*.md`
are unchanged from before this round; nothing here is in production. The
attempt and its findings are kept for the record and to inform the next
attempt — treat every "Fixed" cell below as "fixed in that one retest, on
an unshipped prompt version," not as a resolved issue.

- **ICU-inflation guard** (`pre_exam`, "Current clinical status"): added
  an explicit instruction not to state or imply a care level/unit unless
  the record names it, and that higher acuity must never be inferred from
  diagnosis or procedure alone.
- **Date-free `History` bullets** (`pre_exam`, "History"): added
  permission to write a bullet with no date when the source gives only a
  relative duration, with an explicit ban on inventing/back-calculating a
  date or emitting an unfilled placeholder.
- **Stronger no-clinical-content trigger** (`pre_exam`'s `[not available]`
  rule and `report`'s "Insufficient clinical information" fallback): both
  now explicitly name administrative/instructional material (vaccination
  schedules, hygiene/quarantine instructions, generic care guidelines) as
  not counting as clinical content unless it states a patient-specific
  finding — countering the failure mode where models treated
  medically-themed text as license to fabricate a workup.

Retested the two "keep/promote" candidates (`qwen/qwen3-4b`,
`lmstudio-community/qwen3.5-4b`) on exactly the cases each finding came
from: Case C (`report` + `pre_exam`), Cases D and H (`pre_exam`, the two
ICU-inflation sites), Cases E and F (`pre_exam`, the two date-trap sites).
Raw dumps: `_testing_/r37_case*`. **Results are mixed — not a clean fix**:

| Case / finding | `qwen/qwen3-4b` | `qwen3.5-4b` |
|---|---|---|
| C, no-content (`pre_exam`) | **Regressed**: the pre-fix baseline (`_testing_/r35_caseC_pre_exam.json`) was actually clean — "No main diagnosis or specialty involved," "None applicable" throughout. Under the new prompt it instead fabricates a full "idiopathic interstitial pneumonia" diagnosis + differential + imaging protocol, in Romanian despite `--language English` — the prompt change made this specific cell measurably *worse*, not just unfixed | **Fixed**: `[not available]` in every section |
| C, no-content (`report`) | Unchanged (already correct) | Unchanged (already correct) |
| D, ICU-inflation (`pre_exam`) | n/a (not the affected model) | **Fixed**: no ICU mention (was "ICU/PED setting") |
| H, ICU-inflation (`pre_exam`) | n/a (not the affected model) | **Not fixed**: still writes "Admission to **ICU**, Cardiology department" |
| E, date-free bullets (`pre_exam`) | **Partially fixed**: no longer invents a full date range, but still invents month-level dates ("2026-01", "2026-05") not in the source | **Fixed**: describes the treatment with no invented date at all |
| F, date-free bullets (`pre_exam`) | **Not fixed, new pattern**: silently wrote "2026-08-02" — today's actual system date — as if it were a source date | **Not fixed, new pattern, more blatant**: wrote "2026-08-01 (inferred as 'yesterday' relative to today's date of 2026-08-02)," narrating the fabrication logic in the output itself |

**What this means**: the prompt fixes measurably helped in 3 of 7 cells
(all `qwen3.5-4b`) but left the other 4 unresolved, including a mirror
case for the same failure on the same model (`qwen3.5-4b` fixed on D but
not H for the identical ICU pattern) — the instruction isn't reliably
followed, just sometimes followed. The Case C cell is worse than
"unresolved": it's a genuine regression on `qwen3-4b`, from clean to
severely fabricating plus a new language leak — a reminder that a prompt
change verified against one model/case can move a *different* failure
mode on a model it wasn't even targeting.

**Correction on the Case F finding**: it is *not* new to this round.
Checking the pre-fix baseline confirms `qwen3-4b` already reached for the
current system date on Case C's `pre_exam` under the original,
unmodified prompt — `_testing_/r35_caseC_pre_exam.json` (run 2026-08-01)
contains the bullet "2026-08-01: No relevant events documented," the exact
date it was run on. This pattern predates Phase 4 entirely; it just hadn't
been noticed before because it had only ever paired with otherwise-benign
content (Case C's correct non-answer), not a fabricated diagnosis. Case
F's retest is the first time it's been caught combining with real
fabricated clinical content, not the first time it's occurred. Still worth
a dedicated prompt fix (never treat the current date as a source of
patient history) — just not a "new" finding, an old one finally showing
its teeth.

**Decision: reverted, not shipped.** 3 of 7 fixed cells against 1
regression and 3 unresolved (one of them a brand-new failure mode) is not
a result to ship on the strength of this one retest round. `llm/prompts/
pre_exam.md` and `report.md` were reverted to the pre-Phase-4 version
(`git checkout`) — production is running the same prompts as every prior
round in this doc. The wording tried here is worth revisiting, but as a
second, tighter attempt (including the new current-date rule) rather than
promoting what was tested. See the todo file for the open items this
leaves.

## Follow-ups

1. **Resolved**: `local.cfg`'s `[llm] language = Romanian` is confirmed
   intentional current production config, not a leftover — the Romanian
   rerun above is therefore the one that matters for production behavior,
   not just a secondary check.
2. Re-test `lmstudio-community/qwen3.5-4b` on `pre_exam` alone (fresh model
   load, isolated) to see if the garbled-date/graft-rejection issues
   reproduce or were one-off.
3. Investigate whether `gemma-4-e2b-it`'s load failure is fixable
   server-side (re-download, or a config/quantization mismatch) — currently
   fully untestable.
4. **Resolved (investigated, not fixable)**: tried `chat_template_kwargs:
   {enable_thinking: false}` (Qwen3's real template switch — confirmed
   working on base `qwen3.5-4b`) and a guessed `enable_reasoning` variant
   against `qwen3.5-4b-claude-4.6-opus-reasoning-distilled-v2` directly via
   curl. Neither suppresses it — full CoT still leaks into
   `reasoning_content` every time. The opus-distillation appears to have
   baked in always-on reasoning at a level no request parameter reaches.
   These finetunes are not usable for this app's low-latency kinds without
   a different underlying checkpoint or a fine-tune to un-bake the behavior.
5. Re-test `qwen/qwen3-4b` on a second, different real fixture (not just
   this biliary-atresia case) before promoting it to production — one
   clean case isn't enough to rule out the same "short-kind dilution"
   pattern seen in `qwen3-4b-instruct-2507`/`qwen/qwen3-vl-4b`.
6. Delete and re-download `phi-4-mini-instruct` once filesystem/SSH access
   to the LM Studio host (`192.168.3.238`) is available, or remove it via
   LM Studio's own Model Manager UI — currently unresolved, not ruled out on
   quality grounds.
7. Investigate whether `medgemma-1.5-4b-it`'s `pre_exam` CoT leak is a
   one-off (VRAM contention, cold-load artifact) or a systematic issue with
   this specific finetune before writing it off — worth one isolated retest.
   **Update from the Romanian rerun**: the leak did *not* reproduce in
   Romanian — output was clean and faithful. This raises the earlier
   "one-off" question to a real possibility; worth an isolated English
   retest specifically (fresh load, no other models competing for VRAM)
   before ruling this model out on that basis alone.
8. **Corrected**: `qwen/qwen3-4b` is clean across all 4 kinds in Romanian,
   and clean on 3 of 4 in English (`imaging` leaks into Romanian — see the
   Results-by-kind and "What held up well in Romanian" corrections above)
   — not the "clean in both languages, all 4 kinds" claim originally made
   here. Still the strongest Phase 1 record once weighed against every
   other model's issues, just not spotless.
9. The reverse language-leak pattern (English output despite a Romanian
   directive: `lfm2.5-vl-1.6b`, `medgemma-1.5-4b-it`, `medgemma-4b-it`,
   `qwen3-0.6b` on `lab`; `google/gemma-3-1b` on `pre_exam`) and
   `nvidia/nemotron-3-nano-4b`'s repetition-loop degeneration on Romanian
   `lab` are new failure modes with no English-round precedent — worth
   tracking separately if any of these models stay in consideration, since
   they indicate the language switch itself is a stress condition, not a
   simple wording change.
10. **Resolved**: `zai-org/glm-edge-4b-chat-gguf` tested — ruled out. Its
    3072-token `max_context_length` is a hard architectural ceiling that
    crashes both `report` and `pre_exam` on this fixture, regardless of
    language; not viable for this app's longer kinds.
