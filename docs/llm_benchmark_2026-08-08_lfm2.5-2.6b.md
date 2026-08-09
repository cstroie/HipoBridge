# On-device LLM benchmark — `lfm2.5-2.6b` (2026-08-08)

New candidate requested for evaluation: LiquidAI's `lfm2.5-2.6b` (Q5_K_M,
2.7B params, 1.94 GB on disk — already present on the LM Studio server,
no download needed). Same method as the `llm_benchmark_2026-07-31.md`
round: `benchmark_llm.py` against the app's real production message
assembly (`_build_messages()`), same per-kind system prompt and
`max_tokens`, the same real primary fixture (the de-identified
biliary-atresia case used throughout that round, reconstructed verbatim
from `_testing_/r31_report.md`'s Source section since the original fetch
used a live report id that wasn't recorded), 2 warm iterations per kind
(1 for `pre_exam`, see below), cold-load timing reported separately.
`lms.py swap lfm2.5-2.6b --keep medgemma-4b-it` used to load it in
isolation, matching the standing VRAM-contention practice on these two
4 GB cards.

## Result: Tier F — unsuppressable reasoning leak, ruled out

`lfm2.5-2.6b` reproduces the same failure class already documented for
`lfm2.5-1.2b-thinking`, `lfm2.5-8b-a1b`, `phi-4-mini-reasoning`, and the
`qwen3.5-*-claude-4.6-opus-reasoning-distilled` finetunes in the prior
round: it never emits a real `content` field. The entire `max_tokens`
budget is spent on `reasoning_content` — raw chain-of-thought planning —
and the stream ends (`finish_reason: "length"`) before any final answer
is produced. Confirmed on **all 4 kinds**, both languages tested, with
**5 independent suppression attempts, all ineffective**:

1. `chat_template_kwargs: {"enable_thinking": false}` (sent by
   `benchmark_llm.py` on every request already — Qwen3's real switch, a
   no-op here)
2. `reasoning: {"effort": "none"}` / `reasoning_effort: "none"` (also
   sent by default)
3. `/no_think` appended to the input text (the Qwen3 text-token
   workaround)
4. `reasoning: {"budget": 0}` / `reasoning_budget: 0` (guessed, based on
   the `reasoning_budget_message` field visible in this model's
   `lms.py list --json` load config)
5. `thinking: {"type": "disabled"}` (guessed, OpenAI-style)

Verified directly against the server outside the benchmark tool too
(`curl` against `/v1/chat/completions`): `usage.completion_tokens_details.
reasoning_tokens` consistently accounts for ~all of `completion_tokens`,
`message.content` is `""`, and `message.reasoning_content` holds the
narration. `benchmark_llm.py`'s existing "accept `content` or
`reasoning_content`" fallback (needed for other servers that stream
visible text under the wrong field) is what makes the leak show up as
"output" at all here — this model has no working suppression path found
in this round.

## Per-kind results (English, primary fixture)

| Kind | max_tokens | Result | warm total | tok/s |
|---|---|---|---|---|
| `imaging` | 60 | ❌ leak: "The user wants me to extract a one-line triage label..." — never reaches an answer | 22.4s | 3.2 |
| `lab` | 600 | ❌ leak: "The user wants me to interpret abnormal laboratory results..." | 160.5s | 3.8 |
| `report` | 340 | ❌ leak: narrates the full extraction plan, gets partway through drafting an actual summary inside the reasoning trace, but truncates before emitting real `content` — and even mid-reasoning fabricates "hepatocellular carcinoma-like changes" (not in the source; the actual histopathology finding is regenerative nodules with cholestasis, no malignancy) and a nonsensical discharge date "15/11/2026" | 89.9s | 3.9 |
| `pre_exam` | 1300 | ❌ leak: reasons its way through a fully-structured draft (correct diagnosis, correct Kasai-procedure timeline) inside the trace, but also **inverts the 04.11.2025 ultrasound's bile-duct-dilation finding** ("dilated intrahepatic bile ducts" — the source explicitly says "nedilatate/nevizualizate", non-dilated/not visualized) — the same bile-duct fact-inversion pattern already flagged for `qwen/qwen3-vl-4b` and `qwen3-4b-instruct-2507` in the prior round. Never emits final `content` either. | 350.5s | 3.7 |
| `imaging` (Romanian) | 60 | ❌ same leak, same English-language reasoning text regardless of requested output language — the leak happens upstream of the language directive entirely | 16.6s | 4.1 |

Σt (4 English kinds, warm totals): **623.4s** — by a wide margin the
slowest model in either survey round. The prior slowest, `medgemma-1.5-
4b-it`, needed 246s for the same 4-kind battery; this model needs 2.5x
that just to produce nothing.

Raw JSON/markdown dumps: `_testing_/r38_lfm25_en_{imaging,lab,report,
pre_exam}.md`/`.json`, `_testing_/r38_lfm25_ro_imaging.md`/`.json`
(gitignored, retained locally, not committed).

## Why Romanian and Phase 2 weren't run further

Once 4/4 English kinds plus a Romanian spot-check all reproduced the
identical unsuppressable-leak signature — with 5 independent suppression
mechanisms tried and failing exactly as they failed for every other
Tier F reasoning model in the prior round — running the full Romanian
rerun and the 9-case/8-case Phase 2 extended battery (as was done for the
5 serious contenders in the `07-31` final report) would only re-confirm
an already-conclusive architectural verdict at real GPU-time cost on
2 shared 4 GB cards. This matches how `phi-4-mini-reasoning` and the
`opus-reasoning-distilled` variants were handled: Tier F rules a model
out before Phase 2 relevance, not after exhausting the full battery.

One byproduct is worth flagging on its own, independent of the Tier F
call: even inside its unusable reasoning trace, this model reproduces
the survey's recurring bile-duct-dilation fact-inversion on `pre_exam`
and invents a cancer-adjacent finding on `report` — so a hypothetical
future fix that got the leak suppressed would still need scrutiny on
accuracy, not just format.

## Recommendation

**Rule out.** No change to the `07-31` final report's recommendation
(`qwen/qwen3-4b` promotion, `qwen3.5-4b` as second candidate). Do not
carry `lfm2.5-2.6b` forward without a fixed, working reasoning-suppression
mechanism from LiquidAI/LM Studio — none was found in this round, matching
every other reasoning-leak model already ruled out in `llm_benchmark_
2026-07-31_final_report.md`'s Tier F table, which this model now joins.
