# On-device LLM benchmark — SmolLM2-1.7B-Instruct (2026-08-11)

Follow-up to `llm_benchmark_2026-08-11_rogemma3-4b-v2.md` (same session).
New candidate: `lmstudio-community/SmolLM2-1.7B-Instruct-GGUF` (Q4_K_M),
downloaded and benchmarked fresh. Download itself needed a retry — the
first attempt (`--retries 5`) died mid-transfer at 30.4% and exhausted all
5 auto-resumes without completing (the flaky-HF-link behavior documented
in prior rounds); a second attempt with `--retries 10` completed cleanly.

## Loading

Unlike RoGemma3-4B-v2, no crash at any context length tried. Loaded
directly at `context_length=6144` (same value used for the RoGemma round,
for a fair speed comparison) via `lms.py load smollm2-1.7b-instruct
--context-length 6144`; a trivial `"hi"` chat call returned cleanly before
the full run. XRayVision was stopped and all other models unloaded first,
same standing practice as every round in this session.

## Method

Identical to the RoGemma3-4B-v2 round: `benchmark_llm.py` against the same
primary fixture (biliary-atresia case, `_testing_/r31_report.md`'s Source
section), 2 warm iterations per kind, all 4 kinds (`imaging`/`lab`/
`report`/`pre_exam`), both English and Romanian requested-language runs.

## Speed

Fastest model benchmarked in this session — smaller (1.7B vs. 4B) and it
shows:

| Kind | tok/s (EN) | tok/s (RO) | warm total (EN) | warm total (RO) |
|---|---|---|---|---|
| `imaging` | 25.3 | 25.4 | 3.30s | 3.30s |
| `lab` | 18.5 | 18.8 | 32.91s | 21.84s |
| `report` | 18.7 | 18.7 | 19.18s | 19.19s |
| `pre_exam` | 17.3 | 17.3 | 76.35s | 76.35s |

Roughly 2x RoGemma3-4B-v2's throughput (~9 tok/s) at every kind, as
expected from the size difference. Speed is not the problem with this
model — quality is.

## Quality — worse than RoGemma3-4B-v2, in a different way

RoGemma echoed *fragments* of the source or the instruction template.
SmolLM2 does something more actively wrong: on 3 of 4 kinds it opens with
the raw source **from the very first line**, including internal record
metadata never meant for a clinician (`19890`, `True`, `stationar`) — but
then, rather than just truncating verbatim, it **silently blends content
from different dated entries into one fabricated composite paragraph**,
and alters real facts (a ward name, a date) along the way.

| Kind | Result |
|---|---|
| `imaging` (EN + RO) | ❌ **complete task failure, both languages, byte-identical**: output is exactly `15/07/2026\nCHIRURGIE I\n19890\nTrue\n17/12/2025 12:00\nstationar` — the raw record header, verbatim, truncated at the 60-token budget before reaching any actual clinical content. Not an impression in any sense. |
| `report` (EN) | ❌ **complete task failure**: raw source header verbatim, no summarization, no translation (stays in Romanian despite `--language English`), truncated mid-sentence at 340 tokens before reaching anything past the record header + admission note. |
| `report` (RO) | ❌ **complete task failure + fabricated fact alteration + timeline conflation**: opens with the same raw header, but with `CHIRURGIE II` where the source says `CHIRURGIE I` (fabricated ward-name change) and a pediatric consult redated to `05/12/2025` where the source says `04.11.2025`/`05.11.2025` (fabricated date). Also silently blends the *admission* note's wording with findings from the *13.11.2025 readmission* note (`"Abdomen destins cu circulatie colaterala. Pansamente curate."`) into what reads as a single "Starea la internare" paragraph — a real cross-entry conflation, not just truncated copying. |
| `pre_exam` (EN + RO) | ❌ **complete task failure, both languages, near-identical**: same raw-header opening, same silent conflation pattern — inserts `"pe SUV"` (via urinary catheter) into the admission note's diuresis line, a phrase that in the source only appears in the *later* 13.11.2025 readmission note, not the original admission. No template structure (`### Summary`/`### History`/etc.) attempted at all — worse in that specific respect than RoGemma3-4B-v2, which at least produced the right section structure (just with no content filled in). |
| `lab` (EN) | ❌ **severe fabrication, worse than RoGemma's**: invents an entire 23-item lab abnormality list — Lymphopenia, Anemia, Azotaemia (×2), Hyperglycaemia, Hyperbilirubinaemia, Hyperkalaemia, Hyperphosphataemia, Hypercalcaemia, Hypokalaemia, Hypomagnesaemia, Hypophosphataemia — **none of which appear anywhere in the source**, which contains no lab panel at all. Degenerates into a repetition loop re-cycling the same ~6 findings 3 times before hitting the token budget, and is internally self-contradictory (asserts both **Hyperkalaemia** and **Hypokalaemia** — high *and* low potassium — as separate findings in the same list). The single most fabricated, most self-contradictory output across both benchmark rounds this session. |
| `lab` (RO) | ⚠️ no numeric fabrication, grounded in real narrative content (correctly identifies biliary atresia, Kasai procedure, ICU transfer) — but doesn't extract or reference a single actual lab value either (same omission failure as RoGemma's Romanian `lab` run), and ends with a grammatically broken, semantically incoherent sentence (`"Recomandă: Adăugă unul din medicinii specializate în hepatologia să-l intelească mai mult decât pacienților..."`) that doesn't parse as a real clinical recommendation. |

## Recommendation

**Not usable — worse than RoGemma3-4B-v2, not better.** Faster (2x
throughput, as expected from the smaller size), and doesn't share
RoGemma's load/generation-crash problem, but the actual output quality is
worse on both ends of the failure spectrum documented this session:
`imaging`/`report`/`pre_exam` fail completely (verbatim-echo-with-silent-
conflation, actively altering real facts rather than just failing to
produce new content), and `lab` produces the single most severe
fabrication seen in either round — a wholesale invented, internally
self-contradictory 23-item lab panel with zero grounding in the source.
1.7B is very likely simply too small to follow this project's structured
system prompts at all; no further testing recommended for this model or
smaller.

## Evidence

Raw JSON/markdown dumps (source + full untruncated output, one file per
kind × language): `_testing_/smollm2_bench/{imaging,lab,report,pre_exam}_
{English,Romanian}.{json,md}`.
