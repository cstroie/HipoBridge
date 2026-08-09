# On-device LLM benchmark — Romanian-tuned candidates (2026-08-08)

Follow-up to `llm_benchmark_2026-08-08_lfm2.5-2.6b.md`. That model was ruled
out on architectural grounds (unsuppressable reasoning leak), which prompted
a different angle: candidates specifically tuned for Romanian, since no
public model is fine-tuned for *both* Romanian and medical content.
**OpenLLM-Ro** (a Romanian academic/industry consortium) publishes
Romanian-continual-pretrained variants of recent strong base models;
three sub-4B candidates from that project were evaluated here, all novel
GGUF quantizations (none existed pre-made and load-compatible with this
project's LM Studio server, see below):

- `OpenLLM-Ro/RoGemma3-4B-Instruct` (Gemma 3 4B base) — **blocked**, see below
- `OpenLLM-Ro/RoQwen2.5-VL-3B-Instruct` (Qwen2.5-VL 3B base, text half only)
- `OpenLLM-Ro/RoQwen3-VL-2B-Instruct` (Qwen3-VL 2B base, text half only)

Same method as prior rounds: `benchmark_llm.py` against the app's real
production message assembly, same primary fixture (the biliary-atresia
case, reconstructed from `_testing_/r31_report.md`'s Source section), 2
warm iterations per kind, all 4 kinds (`imaging`/`lab`/`report`/`pre_exam`),
both English and Romanian requested-language runs (unlike most of the
07-31 survey, both languages were run here since these are Romanian
specialists and a language-following regression was actually observed —
see Key finding 1).

## Quantization pipeline (new this round)

All three GGUFs were built locally with `/opt/LLM/quant/llama.cpp`'s
`convert_hf_to_gguf.py` + `llama-quantize` and uploaded to public HF repos
under `costinstroie/` (same re-upload pattern as existing community GGUFs
like `Andarwarm99/RoGemma3-4B-Instruct-Q4_K_M-GGUF`) since the LM Studio
server (`192.168.3.238`) is a separate machine from this dev box with no
SSH access, and `lms.py download` only pulls from HF — uploading through
the user's own HF account was confirmed with the user first. The
benchmark runs below used text-only GGUFs throughout (no vision capability
needed for text summarization) — `Qwen2VLModel`/`Qwen3VLTextModel`'s
`modify_tensors()` skip `visual.*` tensors automatically without needing
a `--mmproj` flag. A reusable `/opt/LLM/quant/quantize_ro_model.sh` script
was added afterward and used to also produce paired `mmproj-F16.gguf`
vision-projector files for both RoQwen models (`--mmproj` flag),
uploaded alongside the text GGUFs and registered in
`/opt/LLM/llama-cpu/models.ini`, in case vision use is wanted later —
these weren't part of the text-summarization benchmark. Two tokenizer
conversion issues came up and were worked around:

1. **RoQwen3-VL-2B-Instruct's `tokenizer_config.json`** has
   `extra_special_tokens` as a JSON list where current `transformers`
   (4.57.3) expects a dict — crashes `AutoTokenizer.from_pretrained()`.
   Patched to `{token.strip('<|>'): token for token in list}` before
   conversion; doesn't touch the actual vocab/merges, just the field
   shape `transformers` walks during load.
2. **RoGemma3-4B-Instruct ships no `tokenizer.model`** (fast/BPE tokenizer
   only), and this `llama.cpp` checkout's pre-tokenizer hash table doesn't
   have Gemma 3's BPE hash registered, so the default GPT-2/BPE vocab path
   raised `NotImplementedError`. Worked around by copying the
   `tokenizer.model` (SentencePiece) from a local `medgemma-4b-it`
   checkout — RoGemma3 is continually pretrained from `google/gemma-3-4b`
   with an unmodified 262208-token vocab (confirmed via `config.json`), so
   this routes `set_vocab()` through the SPM path instead, which is exact,
   not approximate.

## RoGemma3-4B-Instruct — blocked, not benchmarked

**Five independent conversion attempts all fail to load on this project's
LM Studio server with the same generic `Error loading model.`** Not a
quality finding — a load-compatibility gap, same category as
`gemma-4-e2b-it`/`phi-4-mini-instruct` in the 07-31 survey (documented as
blocked, not scored). Root-caused as far as possible without server-side
log access; summarized here so the investigation doesn't need repeating.

1. `Andarwarm99/RoGemma3-4B-Instruct-Q4_K_M-GGUF` (pre-made community
   quant): bundles vision tensors into the single file with no separate
   `mmproj` — plausible cause, but not the whole story (see below).
2. Self-converted, text-only, tokenizer-fixed (SPM workaround): same error.
3. Same, with the extra `output.weight` tensor stripped to match the
   working `gemma-3-4b-it-Q4_K_M.gguf`'s exact tensor set (444 tensors,
   verified identical names via `gguf-py`): same error.
4. Same, with **all 44 extra metadata keys** stripped to exactly match the
   working file's 32-key schema (no `gemma3.rope.freq_base_swa`, no
   `general.dataset.*` citation arrays, nothing informational left that
   the working file doesn't also carry): same error. This ruled out
   metadata/tensor-schema mismatch as the cause entirely — the two files
   were now structurally indistinguishable (same GGUF version 3, same 444
   tensors, same alignment, same KV schema) yet LM Studio still rejected
   mine.
5. **Version-matched rebuild.** The user identified LM Studio's CUDA
   runtime as "llama.cpp 2.13.0" — LM Studio's own internal runtime
   versioning, confirmed via its public bug tracker to correspond to
   upstream `ggml-org/llama.cpp` build **b8733** (commit `26229755c`,
   2026-04-09). This project's `/opt/LLM/quant/llama.cpp` checkout was
   building `b8808` — 75 commits newer. Checked out `26229755c` exactly,
   rebuilt `llama-quantize`/`llama-cli` from source at that commit
   (`llama-cli --version` confirms `8733 (26229755c)`), and redid the full
   conversion + quantization with that exact toolchain. Loads and
   generates correctly with the freshly-built local `llama-cli` (`"hi" →
   "Salut! Este o zi minunată..."`, clean) — **but still the identical
   `Error loading model.` on the actual LM Studio server.**

Re-confirmed the server itself is healthy and Gemma 3 GGUFs in general
load fine on it: `google/gemma-3-4b` (the exact base model RoGemma3 is
continually pretrained from, same architecture/dims/vocab) loads and runs
without issue on the same server, before and after these attempts.

**Conclusion**: every explanation reachable from the file side has been
ruled out — tokenizer format, tensor tying, full metadata schema,
tensor-type distribution, and even the exact upstream `llama.cpp` build
version. The remaining plausible explanation is a **CUDA-runtime-specific
bug in this LM Studio build**, not a property of the GGUF file: LM
Studio's own bug tracker documents real, unresolved issues with this
runtime version specific to Gemma 3 on CUDA (garbled output on dual RTX
A5000, GPU-detection failures on other cards) that a CPU-only local
`llama-cli` test — the only verification available from this side — can't
reproduce. **Left as an open item, not fixable from this side**: the final
version-matched build is on HF at `costinstroie/RoGemma3-4B-Instruct-GGUF`
if someone wants to retry after an LM Studio update, or test directly
against a CUDA-enabled local build to see whether the same failure
reproduces there too (which would confirm the runtime-bug theory
conclusively).

## Key finding 1: both RoQwen models ignore `--language English`

Neither model can be made to answer in English — every English-requested
run came back in Romanian regardless of the `_language_directive()` sent
in the system prompt (same directive that works for every other model in
this survey). Confirmed on all 4 kinds, both models. This is a real
regression for an English-language deployment, but this project's actual
production config (`local.cfg`: `[llm] language = Romanian`) already
defaults to Romanian — so for *this* deployment the failure mode is closer
to "can't be pointed at English if ever needed" than "breaks the
common case."

## RoQwen2.5-VL-3B-Instruct

| Kind | Result | warm total | tok/s |
|---|---|---|---|
| `imaging` | ✅ correct, terse ("Atrezie de cai biliare") — fast, 124 tok/s | 2.6s | 124.5 |
| `lab` | ✅ plausible impression, no fabrication spotted | 36.0s | 5.0 |
| `report` | ⚠️ correct diagnosis/procedure, but **status inversion**: states the patient "is now [`acum`] in the ICU ward following surgery" — the source shows ICU was immediately post-op only; the patient was back on the surgical ward by 13.11, drains out by 15–19.11, improving at discharge. Same class of error as `qwen3.5-4b`'s documented ICU-inflation pattern in the 07-31 survey. | 15.6s | 5.0 |
| `pre_exam` | ❌ **severe**: the stray header field ("19890", a report/document id, not a date) is used as the date for *every single bullet* — all 13 history/imaging/status/reason bullets are dated "19890". The differential-diagnosis list also degenerates into a repetition loop: `1. Atrezie de cai biliare / 2. Cistos / 3. Cistos / 4. Cistos / 5. Cistos`. Worst `pre_exam` output of any model tested across either survey round. | 168.9s | 4.9 |

Romanian-language rerun: same diagnosis/content, same "19890"-as-date
artifact recurs on `pre_exam` (fewer instances, still present); `report`
and `lab` stayed clean, no new fabrications.

## RoQwen3-VL-2B-Instruct

| Kind | Result | warm total | tok/s |
|---|---|---|---|
| `imaging` | ✅ correct, includes the Kasai procedure detail unprompted — fast, 94-79 tok/s both languages | 0.9s | 93.6 |
| `lab` | ✅ plausible impression, no fabrication spotted, both languages | 7.3s | 10.1 |
| `report` | ❌ **format violation + repetition**: ignores the "2-3 sentence executive summary, plain prose" instruction entirely on the English run, instead dumping a structured histopathology breakdown with the *same boilerplate sentence* ("Noduli regenerativi cu hepatocite colestazice...") repeated verbatim for 3 different findings — a copy/repetition artifact, not real per-finding detail. **Romanian run is clean** — correct prose executive summary, right format, though anchors the discharge date on the stray header date (15/07/2026, today's-date-in-source, not a real event date) rather than the actual November 2025 course — the recurring current-date-anchor pattern flagged for other models in the 07-31 survey. | 23.0s (EN) / 12.3s (RO) | 9.0 |
| `pre_exam` | ⚠️ mostly correct and well-structured (correct diagnosis, correct 04.11.2025 ultrasound finding verbatim, no dilation-status inversion) but **still misuses "19890" as a date once** ("Chirurgie: 19890"), and states the patient "is currently undergoing surgery" (`în curs de intervenție chirurgicală`) — a status inversion, since the Kasai procedure already happened and the patient was postoperative/discharged by the time of this record. Romanian run is cleaner still: no date-fabrication, no status inversion, correctly narrates the ultrasound history in full. | 64.6s (EN) / 49.5s (RO) | 7.4 (EN) / 8.4 (RO) |

Clearly the stronger of the two RoQwen candidates — no repetition-loop
degeneration, no pervasive "19890"-as-date epidemic, and Romanian-run
quality is consistently better than the (unwanted, ignored-directive)
English run.

## Speed

Both are fast relative to the 07-31 survey's field — expected, given
smaller base models (2–3B) than most 07-31 contenders (4B):

| Model | Σt (4 kinds, EN) | Σt (4 kinds, RO) |
|---|---|---|
| `RoQwen3-VL-2B-Instruct` | 95.8s | 73.7s |
| `RoQwen2.5-VL-3B-Instruct` | 223.1s | 156.8s |

For reference, 07-31's fastest Tier A/B model was `qwen/qwen3-vl-4b` at
118s (EN) — `RoQwen3-VL-2B-Instruct` beats every viable (non-Tier-D/F)
model in that survey on raw speed while staying in the same size class as
the smaller Tier B/C entries.

## Phase 2: `RoQwen3-VL-2B-Instruct` on the 9-case battery (Romanian only)

Chosen as the follow-up candidate (user decision) despite the primary-
fixture caveats above, and extended to the same 9 independent real
fixtures (Cases A–I) used to validate `qwen/qwen3-4b` and the other 07-31
leaders — `report` on all 9, `pre_exam` on 8 (Case A excluded, same as
prior rounds — too short to stress the format). Romanian only, given Key
finding 1 (English requests are ignored regardless). Judged against source
text, same standard as every other Phase 2 round in this survey.

### `report` (9 cases)

| Case | Result |
|---|---|
| A (ortho) | ✅ correct, faithful |
| B (cardio) | ✅ correct, faithful (though overly literal — near-verbatim restatement rather than a real 2–3 sentence summary, truncated mid-sentence at the 340-token budget) |
| C (no clinical content) | ❌ **severe**: fabricates "Pacientul a fost diagnosticat cu COVID-19" (patient was diagnosed with COVID-19) — invented; the source only mentions routine COVID vaccination per national policy, not a diagnosis. Then **self-contradicts** in the next sentence: "Înregistrarea nu conține informații despre tratament sau diagnostic specific" (the record contains no treatment/diagnosis information) — directly negating its own prior claim. Also opens by narrating the task instructions instead of answering. Same failure class as `qwen/qwen3-4b`/`medgemma-4b-it` on this exact case in the 07-31 survey. |
| D (oncology) | ❌ **source conflation**: attributes the CT scan's finding and measurements (84/103/101mm hepatic mass, 15.07.2024, Dr. Petrisor) to the prior day's ultrasound exam (14.07.2024, Dr. Coman) instead of that ultrasound's actual finding (a 100/80mm suprarenal-region mass) — mixes two different studies into one. Also truncated mid-sentence at 340 tokens on this dense case. |
| E (hepatology) | ✅ correct, faithful |
| F (ENT) | ✅ correct, faithful, appropriately stops before dumping the discharge-instructions boilerplate |
| G (febrile infant) | ❌ **diagnosis conflation**: states "A fost diagnosticat cu pneumonie iarna 2023" (diagnosed with pneumonia, winter 2023) — that's past medical history (`APP`), a resolved, unrelated prior episode — while omitting the actual current admission diagnosis entirely (fever + productive cough + abnormal chest X-ray this admission, Nov 2024). |
| H (cardio/Holter) | ❌ **timeline conflation + severe under-coverage**: places the paroxysmal loss-of-consciousness episodes "în perioada 20.08-22.08.2024" — that date range is the *first* admission's dates; the episodes actually occurred about a week *after* that discharge. One sentence total, entirely missing the actual reason for the current visit (Holter EKG follow-up). |
| I (infant resp., pertussis) | ⚠️ **misses the pertussis finding** (confirmed positive Bordetella pertussis PCR, the single most decisive finding in the case) — runs out of the 340-token budget before reaching it. Same "report budget too tight for dense cases" artifact documented for the original 4 models in 07-31 (where `ministral` was the one exception); not unique to this model. |

**Score: 4 clean / 4 hard fail / 1 budget-miss** — worse than every model
in the 07-31 Phase 2 extended `report` tally except `medgemma-4b-it`
(2 clean/5 fail/2 minor). Two of the four hard fails (C, D) are severe:
an invented diagnosis with a same-output self-contradiction, and a
cross-exam fact conflation.

### `pre_exam` (8 cases, B–I)

| Case | Result |
|---|---|
| B (cardio) | ✅ correct in substance — no explicit diagnosis exists in the source and the model correctly writes `[Not available]` rather than inventing one, faithfully transcribes the ECG/echo findings. Minor format slip: the `Summary` line uses a random exam-finding sentence instead of a diagnosis/specialty line (defensible here since there's genuinely no diagnosis to state) |
| C (no clinical content) | ✅ **correct** — unlike its own `report`-kind run on the same case, here it correctly declines every section (`[nu sunt furnizate]`/`[nu este menționată]`), no fabrication. Minor format slip: the `Summary` line echoes the instruction template text instead of stating "not available" |
| D (oncology) | ✅ correct: "Diagnoză principală: hepatoblastom... Specialitatea: oncologie pediatrică" |
| E (hepatology) | ✅ correct: "Infecție VHB cu transmitere materno-fetala..." |
| F (ENT) | ❌ **severe format collapse**: the entire output is the raw prompt template echoed back verbatim — literal placeholder text like `[Modul] - [Rezultat] în exacte cuvinte (translatate)` and the instruction's own field-description sentences (e.g. "3-5 entități posibile, cea mai probabilă fiind prima...") — not filled in with real content at all, despite Case F having clear, extractable clinical content (chronic nasopharyngeal obstruction, adenoidectomy). Worse than Case C's decline, because here there *was* something to summarize and the model produced nothing usable. |
| G (febrile infant) | ✅ plausible: "Pneumonie interstitială" — consistent with the radiology finding ("interstitiu pulmonar accentuat") |
| H (cardio/Holter) | ✅ correct: "Diagnoză principală: Sincopa... Specialitate implicată: Cardiologie" — matches the source's stated diagnoses |
| I (infant resp., pertussis) | ❌ **wrong headline diagnosis, right detail buried below it**: `Summary` states "Diagnoză principală: Bronșit acută" (acute bronchitis) — a term that appears nowhere in the source — while the `History` section further down *does* correctly transcribe "PCR pentru Bordetella pertussis - pozitiv" verbatim. A clinician skimming just the one-line summary (the whole point of that field) would be misled into the wrong diagnosis despite the correct answer being present two sections later. |

**Score: 6 clean / 2 hard fail** — one severe format collapse (F) and one
headline/detail inconsistency with real clinical-safety relevance (I).
Markedly better than the `report` kind on the same cases, consistent with
the "kind-dependent reliability" pattern documented throughout this
survey.

## Recommendation

**Not ready to replace or join `qwen/qwen3-4b`/`qwen3.5-4b`.** The Phase 2
battery moves `RoQwen3-VL-2B-Instruct` from "worth a closer look" to a
documented **Tier D-equivalent** on `report` (4/9 hard fail, two severe:
an invented diagnosis with same-output self-contradiction on Case C, a
cross-exam source conflation on Case D) and **Tier C-equivalent** on
`pre_exam` (6/8 clean, but one full-format collapse on real content, and
one headline-diagnosis error with the correct answer sitting unused two
sections later on the pertussis case — a genuine clinical-safety-relevant
failure mode, not just an omission). `RoQwen2.5-VL-3B-Instruct`'s single
worse `pre_exam` result on the primary fixture (pervasive date fabrication
+ repetition loop) was never extended to Phase 2 and isn't worth pursuing
given `RoQwen3-VL-2B-Instruct`'s Phase 2 results already came back
unfavorable.

**Net verdict on the Romanian-tuning angle**: Romanian continual
pretraining measurably helped raw language fluency (no leaks, natural
phrasing throughout) but didn't transfer the base Qwen3 family's
Phase-2-grade reliability — `qwen/qwen3-4b` itself scored 11 clean/2 fail/
4 minor across the same-shaped 17-cell battery in the 07-31 survey; this
2B Romanian-tuned sibling scores roughly 10 clean/6 fail/1 miss on a
smaller, easier subset of that same test. Model *size* (2B vs. 4B) is a
plausible confound here, not just the fine-tuning — a like-for-like
comparison against a Romanian-tuned 4B (i.e. a working `RoGemma3-4B-
Instruct`, or a hypothetical `RoQwen3-4B`) would be needed to separate the
two variables before drawing a firm conclusion about the fine-tuning
approach itself.

**Not currently recommended for promotion or a production trial.**
`RoGemma3-4B-Instruct` remains untested pending either an LM Studio server
update or further investigation into the `gemma3.rope.freq_base_swa`/load
incompatibility — worth revisiting given the size confound above.

## Evidence

Raw JSON/markdown dumps: `_testing_/r39_roqwen25vl3b_{en,ro}_*`,
`_testing_/r39_roqwen3vl2b_{en,ro}_*` (primary-fixture Phase 1 runs),
`_testing_/r40_case{A-I}_{report,pre_exam}.*` (Phase 2 case battery,
`RoQwen3-VL-2B-Instruct` only) (gitignored, retained locally).
GGUFs (text Q4_K_M + mmproj F16 for both RoQwen models; text-only for
RoGemma3) and conversion notes on Hugging Face:
`costinstroie/RoQwen2.5-VL-3B-Instruct-GGUF`,
`costinstroie/RoQwen3-VL-2B-Instruct-GGUF`,
`costinstroie/RoGemma3-4B-Instruct-GGUF` (final version-matched b8733
build; still doesn't load on this LM Studio server, see above). Also
registered in `/opt/LLM/llama-cpu/models.ini` for local CPU testing.
