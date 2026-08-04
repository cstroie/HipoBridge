# Taming reasoning-token overrun in LFM2.5-1.2B-Thinking

## Vendor background (Liquid AI blog post)

Per Liquid AI's announcement post for this model (https://www.liquid.ai/blog/lfm2-5-1-2b-thinking-on-device-reasoning-under-1gb), relevant to the behavior observed below:

- **Training**: midtraining establishes a "reason first, then answer" pattern using reasoning traces; SFT on synthetic reasoning traces; then preference alignment/RLVR using a critic-free GRPO-style policy-gradient method with an n-gram-based repetition penalty applied during training specifically to discourage "doom looping." Liquid reports this reduced their doom-loop rate from **15.74%** (mid-training checkpoint) to **0.36%** (final RLVR checkpoint) on their internal representative prompts — i.e., they knew about and specifically targeted the repeated-phrase looping behavior we independently observed in test D, but did not eliminate it.
- **No documented reasoning-budget/length-control mechanism** — the blog only claims the model "requires fewer output tokens... versus competitors" in aggregate, with no guidance on constraining reasoning or answer length at inference time. `--reasoning-budget` is a `llama-server`/`llama-cli` feature, not something Liquid designed the model around.
- **Scope**: Liquid recommends this model for **"agentic and reasoning-heavy tasks (tool use, math, programming)"** and explicitly says **it is not recommended for creative writing or chat** — for those, they point to the separate `LFM2.5-1.2B-Instruct` checkpoint instead.
- Liquid's own evaluations use `temperature=0.6` for this thinking model (vs. greedy for their instruct model) — closer to the server's 0.8 default than the 0.1–0.3 values tested in this report.
- No specifics given on quantization's effect on reasoning quality; only memory footprints per format (fits in ~900 MB on-device; GGUF Q4_0, MLX 8-bit, ONNX INT8 variants listed). We're testing the community `Q4_K_M` GGUF quantization, not one Liquid directly evaluated.

**Implication for the quality-evaluation findings below**: the two clearest total failures — P9 (haiku) and P10 (bicycle-vs-blue, an open-ended/creative comparison) — fall squarely in the domain Liquid says this checkpoint isn't meant for; that failure mode may simply be *expected* misuse rather than a defect. The more concerning results are P8 (code) and P3/P5/P7 (math/counting/multi-step arithmetic), since those are exactly the "programming" and "math" tasks Liquid positions this model for, and it still failed to complete them within a 400-token answer budget.

## Materials

- **Model**: `LFM2.5-1.2B-Thinking-Q4_K_M.gguf`
- **Server**: `llama-server` (router-managed, OpenAI-compatible), reached at `http://127.0.0.1:8080/v1`, model id `LFM2.5-1.2b-Thinking`
- **Launch config** (fixed, not changed during testing): `--ctx-size 16384 --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on --parallel 2 --jinja` — no `--reasoning-budget` or `--reasoning` flag set, so the server defaults to unrestricted (`-1`) reasoning.
- **Server sampler defaults** (from `/props`): `temperature 0.8, top_k 40, top_p 0.95, min_p 0.05, repeat_penalty 1.0`. Effective context per slot: 8192 tokens (16384 / 2 parallel slots).
- **Chat template**: no `no_think` control token exists; generation always starts at `<|im_start|>assistant\n` and the model decides on its own whether to emit `<think>...</think>`.
- **Test prompts** (fixed set, increasing difficulty):
  - P1 trivial: "What is 2+2?"
  - P2 factual: "What is the capital of France?"
  - P3 moderate: "A train travels 60 km in 1.5 hours. What is its average speed?"
  - P4 open-ended: "Explain briefly why the sky is blue."

All HTTP-endpoint requests were driven with `curl` against the live shared endpoint (no server restarts). A separate `llama-cli` binary (`/opt/LLM/llama-cpu/llama-cli`), loading the same `.gguf` directly and independent of the shared server, was also tested — since it's a self-contained process we spin up ourselves, `--reasoning-budget` could be exercised freely there.

## Method

Four experiments, all client-side (no server-flag changes):

- **A — Sampler sweep**: `temperature` (0.3/0.7/0.8/1.0 via `default`), `top_k`, `top_p`, `repeat_penalty`, and greedy (`temperature 0`), each x 4 prompts, `max_tokens: 300`, via `/v1/chat/completions`.
- **B — Prompt engineering**: since a system-prompt instruction to limit reasoning was ignored in preliminary probing, instructions were instead embedded in the *user* message: `inline_brief` ("think for at most one sentence"), `format_request` (explicit "Reasoning: ... / Answer: ..." template), `fewshot` (two short worked examples), vs. `baseline` (no instruction). Fixed sampler = user's example config (`temp 0.3, top_k 20, top_p 0.85, repeat_penalty 1.15`), `max_tokens: 300`.
- **C — Two-pass forced cutoff**: emulate the server's `--reasoning-budget` without restarting it. Render the raw prompt via `/apply-template`, call `/completion` with `max_tokens: 60` and `stop: ["</think>"]`. If the model hits the token limit before closing `</think>` (it always did), truncate the partial reasoning, append `"\n[Reasoning budget reached, answering now.]\n</think>\n"`, and issue a second `/completion` call (`max_tokens: 120`) to force the final answer.
- **D — Repetition/looping check**: one longer run (`max_tokens: 500`, `temperature 0.7`) on P3/P4 at `repeat_penalty` 1.0/1.15/1.3, scanning the reasoning text for any 4-word phrase repeated ≥3 times.
- **E — `llama-cli` with `--reasoning-budget`**: the user's original command form, run directly against `llama-cli -m LFM2.5-1.2B-Thinking-Q4_K_M.gguf -st -n 300 --temp 0.3 --top-k 20 --top-p 0.85 --repeat-penalty 1.15 -p "<prompt>"`, at `--reasoning-budget` ∈ {none (baseline, -1 default), 0, 30, 60, 100}, across all 4 prompts. (`-st` = single-turn, needed since `--no-conversation` from the user's original example doesn't exist in this build; llama-cli suggested `llama-completion` for that, but `-st` gives an equivalent one-shot run.)

## Results

### A — Sampler sweep (`max_tokens: 300`)

| Config | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| default (0.8/40/0.95/1.0) | length, 0 content words | **stop**, 57 words | length, 0 words | **stop**, 36 words |
| user_example (0.3/20/0.85/1.15) | **stop**, 9 words | **stop**, 35 words | length, 0 words | length, 42 words (truncated) |
| low_temp_only (0.3) | length, 0 words | **stop**, 39 words | length, 0 words | length, 33 words (truncated) |
| high_repeat_penalty (0.3/1.3) | length, 0 words | **stop**, 52 words | length, 0 words | **stop**, 28 words |
| greedy (temp 0) | **stop**, 17 words | **stop**, 54 words | length, 0 words | length, 0 words |

Reasoning consumed 130–240 words (roughly 170–300 tokens) in every single run, regardless of sampler settings. No config reliably answered all 4 prompts within a 300-token budget; P3 (the arithmetic word problem) failed under *every* sampler configuration. Sampler tuning shifts which prompts happen to finish in time but does not shorten the reasoning itself — it's essentially noise around a ~200-word reasoning floor.

### B — Prompt engineering (fixed sampler: user_example, `max_tokens: 300`)

| Variant | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| baseline (no instruction) | **stop**, 29 words | **stop**, 55 words | length, 0 words | **stop**, 22 words |
| inline_brief ("think ≤1 sentence") | length, 0 words | length, 6 words (truncated) | length, 0 words | length, 0 words |
| format_request (Reasoning:/Answer: template) | length, 0 words | length, 0 words | length, 0 words | length, 0 words |
| fewshot (2 short examples) | length, 0 words | length, 0 words | length, 0 words | length, 0 words |

**All three prompting strategies made things strictly worse than doing nothing.** Every instructed variant produced 190–240 words of reasoning and 0 content words on every prompt (3/4 succeeded with `baseline`; 0/4 with any instructed variant). The model spends its reasoning budget deliberating about *how to satisfy the instruction* rather than shortening the reasoning — telling it to "think briefly" or follow an output format is itself something it reasons about at length.

### C — Two-pass forced cutoff (60-token reasoning cap + forced close, `/completion`)

| Prompt | Pass-1 stopped naturally? | Reasoning tokens | Answer words | Wall time |
|---|---|---|---|---|
| P1 | No (hit 60-token cap) | 60 | 89 | 6.95s |
| P2 | No (hit 60-token cap) | 60 | 49 | 5.11s |
| P3 | No (hit 60-token cap) | 60 | 94 | 6.91s |
| P4 | No (hit 60-token cap) | 60 | 32 | 4.01s |

This is the only method that reliably produced *some* answer content for every prompt, and total tokens/wall time dropped sharply (~5–7s vs. 9–12s+ for A/B, often without ever reaching an answer there). However, quality is mixed: forcibly closing `</think>` doesn't fully switch the model into "answer mode" — for P1 and P3 it kept narrating in a reasoning voice after the forced tag close (e.g., P1's answer opened with "Okay, let's tackle this question..." and only stated "4" ~60 words in, past our preview window). P2 and P4 produced clean, direct answers. The forced-budget message ("[Reasoning budget reached, answering now.]") is not a strong enough cue on its own to fully suppress the model's reasoning register.

### D — Repetition/looping (`max_tokens: 500`, temp 0.7)

| repeat_penalty | P3 repeated phrases | P4 repeated phrases |
|---|---|---|
| 1.0 | 2 (e.g. "60 divided by 1.5." x3, "1.5 times 40 is" x3) | 2 |
| 1.15 | 1 | 0 |
| 1.3 | 1 | 0 |

Confirms the "runs endlessly" complaint: at `repeat_penalty 1.0` the model does fall into short repeated-phrase loops during arithmetic reasoning (re-deriving the same division step 3 times). `repeat_penalty 1.15` and `1.3` reduce but do not eliminate this — P3 still repeated a phrase 3x even at 1.3. Reasoning length itself (~280–350 words) was not meaningfully reduced by higher repeat_penalty; it mainly reduces *loops*, not overall verbosity.

### E — `llama-cli` with `--reasoning-budget` (`-n 300`, `temp 0.3/top-k 20/top-p 0.85/repeat-penalty 1.15`)

| Config | P1 | P2 | P3 | P4 |
|---|---|---|---|---|
| baseline (no budget flag, -1 default) | 180w reasoning → 17w answer | 146w → 28w | 218w reasoning, **never closed `</think>` within 300 tokens, 0-word answer** | 225w → 25w |
| `--reasoning-budget 0` | 88w → 21w | 130w → 34w | 203w reasoning, **never closed, 0-word answer** | 46w → 38w |
| `--reasoning-budget 30` | 23w → 188w | 31w → 143w | 38w → 174w | 33w → 217w |
| `--reasoning-budget 60` | 45w → 78w | 55w → 120w | 61w → 145w | 58w → 99w |
| `--reasoning-budget 100` | 76w → 100w | 83w → 114w | 93w → 112w | 90w → 155w |

`--reasoning-budget 30/60/100` all scored **4/4** — every prompt got a real answer, reasoning length tracked the requested budget almost linearly (e.g. budget 30 → 23–38 words actually used), and answers were substantially longer/more complete than anything the HTTP endpoint produced in tests A–C. This is a clean, reliable fix and — unlike every client-side approach tried — required no prompt trickery, no multi-pass calls, and no guessing.

**Surprise finding**: `--reasoning-budget 0` is documented ("0 for immediate end") to force the model to stop thinking essentially immediately, but it did not — P3 reasoned for 203 words and never closed `</think>` within the 300-token cap, the exact same failure mode as running with no budget flag at all. `0` behaved like "unrestricted," not "immediate end," in this build (`b8808-408225bb1`). Anyone relying on `--reasoning-budget 0` to fully disable thinking should verify against their own build — it does not appear safe to assume here.

## Discussion

- Per-request reasoning controls (`reasoning_budget`, `reasoning: "off"`, system-prompt instructions) are all silently ignored by this server build — confirmed again here since instructed prompting (B) had no positive effect and in fact backfired.
- The model has a strong, fairly fixed tendency to reason for ~150–350 words regardless of prompt difficulty — P1 ("2+2") reasons about as much as P3 (a word problem). This looks like a property of this Q4_K_M checkpoint's `Thinking` behavior, not something samplers or prompting can talk it out of.
- The only lever that reliably bounds output within a small token budget is a **hard, externally-imposed cutoff**: `--reasoning-budget N` (tested directly and confirmed working via `llama-cli` in test E — not exercised on the shared `llama-server`, since per-request `reasoning_budget` is ignored there and the server wasn't restarted), or the client-side two-pass truncate-and-force-close workaround (C) when only an HTTP endpoint without that flag is available.
- `--reasoning-budget` on `llama-cli` clearly outperforms the C workaround: it produced longer, more complete, better-formed answers (e.g. budget 30 → 143–217-word answers vs. C's 32–94-word ones) because the server injects its own budget-cutoff message and lets the *same* generation continue coherently, rather than us splicing two separate completions together. If a real `--reasoning-budget`-capable server is available for a given deployment, prefer it over the two-pass HTTP hack.
- The two-pass HTTP workaround's "force the model to answer" cue is imperfect — the model sometimes resumes a reasoning-style monologue after the forced `</think>`, so answers need a bit more headroom (120 tokens was sometimes tight) and ideally a stronger post-cutoff cue than the one tested.
- `--reasoning-budget 0` ("immediate end" per `llama-cli --help`) did not behave as documented in this build — it let P3 reason for 200+ words and never close `</think>`, identical to the no-budget baseline. Any positive integer budget (30/60/100) worked as expected; only `0` was unreliable. This looks like a build-specific edge-case bug rather than a documented behavior to design around.

## Conclusions

1. Sampler tuning (temperature/top_k/top_p/repeat_penalty) does not fix excessive reasoning; it only marginally affects which specific prompts happen to finish before hitting `max_tokens`.
2. Prompt-based instructions to reason briefly or follow an output format actively make the problem worse for this model — avoid them.
3. Higher `repeat_penalty` (1.15–1.3) measurably reduces (but doesn't eliminate) repetitive looping within the reasoning trace.
4. A hard external cutoff — either `--reasoning-budget` at the server/CLI level or a client-side truncate-and-force-close two-pass call — is the only approach tested that reliably yields an answer within a small token budget.
5. `--reasoning-budget N` (N ≥ 30 tested) works exactly as intended on `llama-cli` and is clearly the best of everything tested: 4/4 prompts answered at every budget value tried, with full-length, coherent answers. `--reasoning-budget 0` specifically is unreliable in this build (`b8808-408225bb1`) — it does not force an immediate stop as documented.
6. Per Liquid AI's own blog post, this checkpoint is trained and positioned for reasoning-heavy/agentic tasks (math, programming, tool use) and explicitly **not** for creative writing or open-ended chat (their `LFM2.5-1.2B-Instruct` is recommended for that instead). Two of our worst quality-eval failures (haiku, an open-ended comparison question) are arguably out-of-scope usage rather than defects — but the model still failed to reliably complete code and math/counting tasks, which are within its stated domain.
7. The "doom looping" / repetitive-reasoning behavior we observed (test D) is a known, documented issue Liquid specifically targeted during RLVR training, reducing it from 15.74% to a reported 0.36% — it was reduced, not eliminated, which matches our small-sample results still catching instances of it.

## Recommendations

- **Best fix, confirmed working**: run with `--reasoning-budget N`, N in the 30–100 range (e.g. 60 is a good default — short reasoning, plenty of answer room). Tested directly on `llama-cli` with 4/4 success at every N ≥ 30 and clean, coherent, full-length answers — clearly the best result of anything tried in this report. **Avoid `--reasoning-budget 0`** — despite being documented as "immediate end," it behaved identically to unrestricted (-1) in this build and let reasoning run away on the harder prompt. If this needs to run against the shared `llama-server` rather than a standalone `llama-cli`, it requires adding `--reasoning-budget` to that server's launch flags (not done here, since the user chose to leave that shared service untouched) — per-request equivalents are silently ignored by the server.
- **Best client-side workaround when no `--reasoning-budget` is available** (e.g. calling a shared endpoint you can't relaunch): the two-pass `/completion` approach from test C — cap the reasoning pass at ~60–100 tokens with `stop: ["</think>"]`, then force-close with an explicit instruction and continue with a modest `max_tokens` (≥150 recommended, higher than the 120 tested here, since the model sometimes needs extra tokens to fully drop the reasoning register). Consider strengthening the forced-close message, e.g. explicitly prefixing the continuation with `"Final answer: "` rather than just closing the think tag, to more forcefully switch the model's voice. Expect noticeably shorter/rougher answers than native `--reasoning-budget` gives.
- Set `repeat_penalty` to 1.15–1.3 regardless of which fix is used — it reduces (though doesn't eliminate) repetitive reasoning loops at no cost to answer quality.
- Do not rely on system-prompt or user-prompt instructions to shorten reasoning for this model — they are net negative.
- If stuck with `/v1/chat/completions` convenience and no reasoning-budget control at all, `max_tokens` should be raised well above 300 (e.g. 500+) to give the model room to both reason (~200–350 words) and answer.
- Match the task to the model: per Liquid's own guidance, don't route creative-writing or open-ended chat prompts to this Thinking checkpoint — use `LFM2.5-1.2B-Instruct` for those. Reserve this model for math/programming/agentic tasks, which is what it's positioned and trained for — though even there, our tests show it still needs a generous `max_tokens` (or the client-side truncation strategy above) to reliably land the deliverable rather than re-litigate it.

## Quality evaluation (reasoning-budget 60, live deployment)

Follow-up pass after the user set `reasoning-budget = 60` in `models.ini` for `LFM2.5-1.2b-Thinking` and the router reloaded that model with it live. This evaluates *response quality*, not just whether reasoning gets cut off. 10 prompts, one call each (no repeats, per token-conservation instruction), `max_tokens: 400`, server defaults (temp 0.8/top_k 40/top_p 0.95/repeat_penalty 1.0, no overrides), against the live `http://127.0.0.1:8080/v1/chat/completions`.

| # | Prompt | finish | reasoning w | answer w | Correct | Clean | Complete |
|---|---|---|---|---|---|---|---|
| P1 | "What is 2+2?" | length | 44 | 211 | unresolved (never states final answer before cutoff) | No — pure hedging/second-guessing | **No** |
| P2 | Capital of France | stop | 44 | 105 | Yes (Paris) | Partial — answer duplicated, a stray literal `</think>` leaks into the content field | Yes |
| P3 | Train average speed | length | 43 | 205 | Yes, computed 40 km/h — but buried mid-ramble, never a clean closing statement | No | **No** |
| P4 | Sky is blue | stop | 46 | 51 | Yes | **Yes — clean, direct, correct** | Yes |
| P5 | Alice's apples (multi-step) | length | 43 | 225 | No — gets stuck oscillating over whether half-apples are allowed, never concludes | No | **No** |
| P6 | 3 benefits of exercise (list) | stop | 49 | 152 | Yes, correct numbered list | Partial — same duplicate-draft-then-final-answer pattern as P2 | Yes |
| P7 | Count R's in "strawberry" | length | 42 | 162 | No — recounts letters twice, cut off mid-count, never states the final tally | No | **No** |
| P8 | Prime-check Python function | length | 49 | 226 | **No — no code was ever produced**, 400 tokens spent entirely on prose planning | No | **No** |
| P9 | Haiku about autumn | length | 43 | 190 | **No haiku produced** — spent the whole budget deliberating about syllable counts | No | **No** |
| P10 | Bicycle vs. the color blue (ambiguous) | length | 45 | 248 | N/A (open-ended) | No — never reaches a stance | **No** |

**3 of 10 fully clean+complete (P2, P4, P6); 6 of 10 ran out of the 400-token budget without ever delivering the requested artifact (no code, no haiku, no final tally, no concluded answer); 1 (P3) reached the right number but never states it cleanly.**

### Discussion

- `reasoning-budget 60` works exactly as designed on the `<think>` block itself — reasoning length is tightly and consistently 42–49 words across all 10 prompts, regardless of topic. That part of the original problem is solved.
- **It does not bound the *answer*.** The budget only forces the model out of the `<think>...</think>` span; nothing stops the *content* that follows from continuing in the same rambling, self-correcting "thinking voice" (visible verbatim in P1/P3/P5/P7/P8/P9/P10 — phrases like "Wait, let me check again," "Hmm, maybe I miscounted," "Let me think through this step by step" appear in `content`, not just `reasoning_content`). For prompts whose deliverable is a concrete artifact (code, a poem, an exact count) rather than a short factual/explanatory sentence, this reliably burns through `max_tokens` before the artifact ever appears.
- Two responses (P2, P6) show a distinct artifact: the model produces a full internal draft-and-answer cycle *inside the content field itself*, including a second, literal `</think>` tag that the server's reasoning-parser doesn't intercept (because it already closed the first one at the budget cutoff). The final answer is still correct in both cases, but the visible response is doubled and mentions internal deliberation markup.
- This contradicts the earlier optimistic 4-prompt spot-check (immediately after applying the config) — that check used `max_tokens: 300` and happened to sample cleaner completions on all 4 short-factual-style prompts. With `temperature 0.8` (server default, unchanged), answer verbosity/rambling is highly stochastic — the same prompt can land a clean 50-word answer or a 250-word non-conclusion purely by sampling luck. The 10-prompt set here, run once each, is more representative and shows the failure mode is common (6/10), not rare.
- The short, purely-factual/explanatory prompts (P2, P4, P6) worked best. The prompts that failed to complete all required the model to *produce* something (code, a poem, a specific count, a multi-step numeric conclusion) rather than *recall or explain* something — the "thinking voice" leaking into content is especially costly there because the model treats the deliverable itself as something to keep deliberating about.

### Additional recommendations from this pass

- `reasoning-budget` alone is not sufficient for tasks that require a generated artifact (code, creative writing, precise counts/multi-step arithmetic conclusions) — expect it to still ramble through much of `max_tokens` before/without delivering. For those task types, either: raise `max_tokens` substantially (600–800+) to give the rambling room to eventually reach the artifact, or lower `temperature` for such requests (untested here, but the rambling/hedging pattern is consistent with high-temperature sampling exploring many hedges before committing).
- Consider setting a lower `temperature` (e.g. 0.3–0.5, as in the user's original example) as the default for this model rather than the server's default 0.8 — none of the quality-pass prompts used a lowered temperature, and the earlier sampler-sweep (test A) suggested lower temperature correlates with fewer wasted reasoning tokens; it likely helps content-rambling too, though this wasn't directly re-tested under the new reasoning-budget config.
- The literal `</think>` leaking into `content` (P2, P6) is a minor but real display bug worth knowing about if this endpoint's raw `content` field is ever shown to end users unfiltered — a client should strip stray `<think>`/`</think>` tags defensively rather than assume the server's `reasoning_content` split is exhaustive.

### Follow-up: does `temperature 0.1` fix the answer-side rambling?

Re-ran the identical 10-prompt set, one call each, `max_tokens: 400`, `reasoning-budget 60` (unchanged, live), only difference: `"temperature": 0.1` per-request (no server/config change needed — unlike `reasoning_budget`, `temperature` is honored per-request by this server).

| # | Prompt | finish (temp 0.8) | finish (temp 0.1) | Notes at temp 0.1 |
|---|---|---|---|---|
| P1 | 2+2 | length | **stop** | Reaches clean `\boxed{4}` at the end, but still preceded by the same "maybe it's a trick / let me check binary" hedging pattern |
| P2 | Capital of France | stop | stop | Same duplicate-draft-plus-stray-`</think>` artifact as before, plus a malformed `\boxedParis}` typo |
| P3 | Train speed | length | length | Same outcome — computes 40 km/h mid-ramble, cut off before a clean closing statement |
| P4 | Sky is blue | stop | stop | Clean correct answer both times, reasoning-voice still bleeds in beforehand |
| P5 | Alice's apples | length | length | Same oscillation over splitting apples, never concludes |
| P6 | Exercise list | length | length | **Improvement**: the 3-item list is now delivered immediately at the top of `content` (unlike temp 0.8's buried-after-fake-`</think>` version) — but then the model re-litigates its own list choice for 150+ more words and still hits the token limit |
| P7 | Strawberry R's | length | length | Same — recounts letters twice, cut off before stating a final tally |
| P8 | Prime-check code | length | length | **Slight improvement**: actually starts writing real Python (`def is_prime(n): ...`) instead of pure prose planning, but the loop body is cut off mid-line before completion |
| P9 | Haiku | length | length | Still no haiku — spends the whole budget on syllable-counting false starts |
| P10 | Bicycle vs. blue | length | length | Still never reaches a stance, same open-ended rambling structure |

**Verdict: lowering temperature to 0.1 does not meaningfully fix this.** Completion rate is unchanged (3/10 clean `stop` at both temperatures — the same three "recall/explain" prompts, P2/P4, plus P1 swapping in for P6). Reasoning length is unaffected either way (41–49 words, since it's governed by the hard `reasoning-budget` cutoff, not sampling temperature). The self-checking, hedging narrative style ("wait, let me check again," "maybe I'm misinterpreting") persists nearly verbatim at low temperature — it's a stylistic/behavioral trait of this checkpoint's answer generation, not a temperature-driven exploration artifact. The only real differences observed were two isolated cases (P6, P8) where the answer/deliverable happened to surface earlier in the response — not a systematic effect confirmed across the set.

**Updated recommendation**: don't rely on `temperature` to control answer-side rambling for this model. If artifact-producing prompts (code, creative writing, precise counts, multi-step arithmetic) matter for the intended use case, the more promising levers remain (a) a substantially larger `max_tokens` (600–800+) to let the rambling run its course before the deliverable appears, or (b) a stop-sequence/two-pass strategy on the client side that detects when the model has produced the deliverable and truncates the trailing self-review, since the model reliably re-litigates a correct-looking answer instead of stopping once it has one.

### Follow-up: applying the vendor guidance — larger `max_tokens` for in-scope tasks, route creative prompts to `LFM2.5-1.2b-Instruct`

Based on Liquid's own scoping (math/programming/agentic tasks are what this Thinking checkpoint is for; creative writing/chat should go to `LFM2.5-1.2b-Instruct`), reran two changes together, one call each, `reasoning-budget 60` unchanged:

- **P3, P5, P7, P8** (the in-scope math/counting/code prompts that failed to complete at `max_tokens: 400`) rerun on `LFM2.5-1.2b-Thinking` with `max_tokens: 800`.
- **P9, P10** (the out-of-scope creative/open-ended prompts) rerun on `LFM2.5-1.2b-Instruct` instead, `max_tokens: 400` (no reasoning-budget applies — Instruct doesn't emit `<think>` at all).

| # | Prompt | Model | max_tokens | finish | Result |
|---|---|---|---|---|---|
| P3 | Train speed | Thinking | 800 | **stop** | **Fixed** — reaches a clean closing statement: `Average speed = 60/1.5 = 40 km/h`, `\boxed{40}` |
| P5 | Alice's apples | Thinking | 800 | length | **Still incomplete** — 474 words, still oscillating between "is 1.5 apples valid?" framings, cut off mid-fraction-arithmetic without ever stating a final number |
| P7 | Strawberry R's | Thinking | 800 | length | **Still incomplete** — 374 words, re-spells and re-indexes the word repeatedly, cut off before stating the final count (correct answer is 3, never reached) |
| P8 | Prime-check code | Thinking | 800 | length | **Still incomplete** — 417 words entirely spent re-deriving the `range(2, int(sqrt(n))+1)` boundary condition over and over; no complete function ever emitted |
| P9 | Haiku | **Instruct** | 400 | stop | **Fixed** — clean haiku in 10 words, no hedging, sub-1-second response |
| P10 | Bicycle vs. blue | **Instruct** | 400 | stop | **Fixed** — direct, well-structured comparative answer, reaches an actual stance, no rambling |

**Key finding: doubling the budget does not reliably fix the in-scope failures.** Only P3 (a single-step, unambiguous calculation) converged with more room. P5, P7, and P8 — all involving either ambiguity (can apples be split?), repeated verification of a discrete count, or an off-by-one boundary check in code — kept re-deriving the same intermediate result rather than converging, and were still mid-ramble at 800 tokens. This suggests the "doom-looping" behavior Liquid's RLVR training targeted (reducing it from 15.74% to 0.36%, per the vendor blog) is specifically triggered by tasks requiring iterative self-verification of a discrete/exact result — not by prompt difficulty or budget size — and more `max_tokens` alone doesn't reliably escape it once it starts.

**Routing creative/open-ended prompts to the Instruct model, on the other hand, completely resolved those two cases** — exactly as Liquid's usage guidance predicts, since that model doesn't reason/hedge at all.

**Revised recommendation**: 
- Route by task type as Liquid recommends — creative writing and open-ended/subjective questions to `LFM2.5-1.2b-Instruct`, not the Thinking variant.
- For in-scope math/code/counting tasks on the Thinking model, a larger `max_tokens` helps *some* prompts (simple, unambiguous single-step calculations) but is not a reliable fix for prompts prone to iterative self-verification loops (multi-step arithmetic with ambiguity, exact character/discrete counts, boundary-condition code). For those, a client-side detector that stops generation once a correct-looking deliverable first appears (rather than waiting for the model to stop on its own) is likely necessary — token budget increases alone can't be assumed to converge.
