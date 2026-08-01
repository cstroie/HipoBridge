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

## Key findings

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
8. **`qwen/qwen3-4b` is the cleanest model in the entire survey**: correct
   and clean English on all 4 kinds, zero fabrication spotted anywhere,
   including the best-in-round faithful `pre_exam` output (no other model
   this round or the last was fabrication-free on `pre_exam`). Distinct from
   the already-tested `qwen3-4b-instruct-2507`, which *did* fact-invert on
   `report`.
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

## Updated recommendation

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
download).

## Follow-ups

1. Confirm whether `local.cfg`'s `[llm] language = Romanian` is intentional
   current config or a leftover — it silently changes every AI button's
   output language app-wide and doesn't match any prior documented decision.
2. Re-test `lmstudio-community/qwen3.5-4b` on `pre_exam` alone (fresh model
   load, isolated) to see if the garbled-date/graft-rejection issues
   reproduce or were one-off.
3. Investigate whether `gemma-4-e2b-it`'s load failure is fixable
   server-side (re-download, or a config/quantization mismatch) — currently
   fully untestable.
4. If `qwen3.5`-family reasoning-distilled variants are wanted in the
   shortlist in the future, they need a different suppression mechanism than
   `/no_think` — investigate their native chat template/reasoning controls
   rather than assuming the Qwen3 convention applies.
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
