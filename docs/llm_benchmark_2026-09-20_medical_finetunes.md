# On-device LLM benchmark — costinstroie/lfm-medical-1.2b vs. costinstroie/qwen2.5-1.5b-medical-sft vs. production (2026-09-20)

Two new medical-domain fine-tunes, downloaded via `lms.py download` and
benchmarked with `benchmark_llm.py` against the same primary fixture used
throughout this project's benchmark history (the biliary-atresia case,
`_testing_/ciobotaru_report_trim.txt`), compared to `qwen3.5-4b`, the
current production `default`/`medical` model (`llm.cfg`). 2 warm iterations
per kind, 4 kinds (`report`/`imaging`/`lab`/`pre_exam_brief`), Romanian
(production's configured `[llm] language`). `lfm-medical-1.2b` was also
probed separately with a larger token budget, lower temperature, and a
repetition penalty, in both Romanian and English, to rule out a simple
budget-starvation explanation for its failures (see below) — this
required adding `--temperature`, `--repetition-penalty`, and
`--max-tokens` flags to `benchmark_llm.py`, which didn't previously expose
any of the three.

## Speed

| Kind | `lfm-medical-1.2b` tok/s / total | `qwen2.5-1.5b-medical-sft` tok/s / total | `qwen3.5-4b` tok/s / total |
|---|---|---|---|
| `report` | 33.0 / 10.68s | 19.1 / 18.16s | 7.3 / 20.26s |
| `imaging` | 38.2 / 1.93s | 60.8 / 0.60s | 31.3 / 1.22s |
| `lab` | 32.0 / 19.13s | 19.7 / 19.27s | 7.9 / 15.24s |
| `pre_exam_brief` | 32.6 / 14.13s | 19.2 / 12.35s | 7.0 / 60.16s |

Both smaller models are faster per-token than production, as expected
(1.2B/1.5B vs. 4B). But raw throughput is irrelevant here: **every
`lfm-medical-1.2b` row above hit its kind's max-token ceiling** —
`toks` in the raw benchmark output equals `max_tokens` exactly on all 4
kinds (340/60/600/450) — meaning the tok/s number reflects a full runaway
generation, not a completed, budget-respecting answer. Total wall time is
consistently *worse* than it looks because none of it produced usable
output (see Quality).

## Quality — `lfm-medical-1.2b`: unsuppressable reasoning leak, confirmed not a budget problem

On **all 4 kinds**, `lfm-medical-1.2b` fills its entire token budget with
first-person English planning monologue ("Okay, let's tackle this...",
"Wait, let me check again...") and never reaches the actual answer. This
is despite `benchmark_llm.py` sending the same three reasoning-suppression
signals used against every other reasoning model in this project's
history (`reasoning: {effort: none}`, `reasoning_effort: none`,
`chat_template_kwargs: {enable_thinking: false}`) — this model ignores all
three, matching the `lfm2.5-*-thinking`/`lfm2.5-8b-a1b` pattern already
documented as Tier F in `llm_benchmark_2026-07-31_final_report.md`.

**Per the user's instruction not to dismiss this as a budget artifact**,
`lfm-medical-1.2b` was re-tested alone with `--max-tokens 1500
--temperature 0.1 --repetition-penalty 1.15`, in both Romanian and
English:

| Language | Tokens used | Outcome |
|---|---|---|
| Romanian | 1310 / 1500 | Reaches an answer after ~1250 tokens of English reasoning — but the answer **fabricates a diagnosis**: invents "hydronephrosis," "ascites," "pyelonephritis" (none in the source; the real diagnosis is biliary atresia/Kasai procedure, a hepatobiliary condition, not renal). Final Romanian is also grammatically broken, with an English word substituted mid-sentence ("Aceasta este in **state** de hydronephrosis..."). |
| English | 1130 / 1500 | Reaches an answer, but **hallucinates the procedure entirely**: calls it a "laparoscopic cholecystectomy for biliary obstruction" — the source describes a Kasai portoenterostomy for biliary atresia (congenital absence of bile ducts), a fundamentally different diagnosis and operation from a cholecystectomy for obstruction. |

This confirms the user's expectation going in (LFM was not trained on
Romanian and appears to substitute other Romance-language vocabulary/
grammar patterns) but goes further: even given generous budget, low
temperature, and a repetition penalty — and in its stronger language,
English — the model's eventual answer is a genuine clinical fabrication,
not just a language artifact. This is a harder failure than the
budget-truncation case: extending the budget doesn't fix it, it just
gives the model enough rope to also hallucinate.

**Verdict: not usable in either language, any kind, any generation
setting tried.** Same disposition as the project's existing Tier F
reasoning-leak entries — no further testing recommended without an
upstream fix to make the reasoning suppression actually take effect.

## Quality — `qwen2.5-1.5b-medical-sft`: mixed, one severe SFT-leakage failure

| Kind | Result |
|---|---|
| `report` | ⚠️ Opens correctly grounded and in Romanian, but degenerates into a **repetition loop**: restates near-identical "Ecografie abdominală... arată că pacientul are dimensiuni crescute ale cai biliare intrahepatice..." for 3 different dates, truncated mid-loop at the 340-token budget. |
| `imaging` | ✅ Correct: "Atrezie de cai biliare" — identical to `qwen3.5-4b`, minimal tokens (10), correct language. |
| `lab` | ⚠️ Grounded in real facts (biliary atresia, Kasai, prednisone) but generic/thin, doesn't extract or interpret any specific finding the way `qwen3.5-4b` does, and opens with a malformed word ("**Impressionă:**" — not real Romanian, should be "Impresie"). No fabrication, but weaker than production. |
| `pre_exam_brief` | ❌ **Severe fabrication — SFT training-data leakage**: instead of a Romanian pre-exam briefing, produces a verbatim-style USMLE/medical-board multiple-choice question, in English — fabricated vitals ("temperature is 37°C... pulse is 125/min..."), fabricated birth history ("born at term via spontaneous vaginal delivery... delivered by his mother in her home"), and a lettered answer list (`{'A': 'Choledochal cyst', 'B': 'Hepatoblastoma', ...}`). None of this is grounded in the source at all — this looks like the model regurgitating its own fine-tuning data format rather than following the system prompt. |

**Verdict: not production-ready.** Two of 4 kinds are clean/strong
(`imaging` matches production exactly; `lab` is weak but not fabricated),
but the `pre_exam_brief` failure is categorically worse than anything in
this project's benchmark history — a wholesale off-task training-data
leak, not a clinical-content error. The `report`-kind repetition loop is
also a real, recurring failure pattern (same shape as `qwen3.5-2b`'s and
`SmolLM2`'s documented repetition-loop failures in earlier rounds).

## Quality — `qwen3.5-4b` (production, reference)

Clean, accurate, correct language, and grounded in the source on all 4
kinds tested this round — consistent with its existing Tier A standing in
`llm_benchmark_2026-07-31_final_report.md`. Notably the only model whose
`lab` output correctly synthesizes an "Impresie" line with an actual
differential read of the case (colestază neonatală severă) rather than a
generic restatement.

## Recommendation

Neither new model displaces `qwen3.5-4b` in production:

- **`lfm-medical-1.2b`**: unusable. Confirmed (not just suspected) reasoning-
  leak architecture, and even when given room to finish thinking, its
  actual clinical content is fabricated. No configuration tried (default,
  nor `temperature=0.1` + `repetition_penalty=1.15` + 1500-token budget,
  in either language) produced a trustworthy answer.
- **`qwen2.5-1.5b-medical-sft`**: not ready. `imaging` is a genuine win
  (matches production, much faster), but the `pre_exam_brief`
  training-data leak is disqualifying on its own, and the `report`
  repetition loop is a second independent failure mode. Worth revisiting
  only if a future fine-tune iteration fixes the SFT-leakage and
  repetition issues — `imaging`-only deployment could be considered
  separately given that kind's clean, fast result, but that's a narrower
  claim than "replaces production."

## Evidence

Raw JSON/markdown dumps, one file per kind (+ the two LFM high-budget
probes): `_testing_/med_ft_bench/{report,imaging,lab,pre_exam_brief}_
Romanian.{json,md}`, `_testing_/med_ft_bench/lfm_report_{Romanian,
English}_hibudget.{json,md}`.

## Tooling change

`tools/benchmark_llm.py` gained `--temperature`, `--repetition-penalty`,
and `--max-tokens` CLI flags (previously temperature was hardcoded to
0.2, no repetition penalty was ever sent, and max_tokens was always the
kind's production value with no override) — needed to run the LFM
high-budget probe above. Defaults unchanged, so every prior invocation in
this project's benchmark history still reproduces identically.
