# qwen3.5-2b — Phase 2 retest (2026-09-20)

Follow-up to `llm_benchmark_2026-07-31_final_report.md`'s open question:
`lmstudio-community/qwen3.5-2b` was Phase-1-only in the original survey
(Tier C — clean on `imaging`/`lab`/`report` both languages and `pre_exam`
in Romanian, but missed the diagnosis on `pre_exam` in English). It was
never subjected to Phase 2's 4-independent-fixture battery, the same
battery that overturned `qwen/qwen3-4b`'s apparent Phase 1 perfection
(see `llm_benchmark_2026-07-31.md`'s "Phase 2" section). This round closes
that gap.

## Method

Identical to the original Phase 2: same 4 fixtures
(`_testing_/phase2_case{A_ortho,B_cardio,C_bulletlist,D_oncology}.txt`),
`report` kind, English, 2 warm iterations, `qwen3.5-2b` only (the other
4 models' Phase 2 scores are already documented and were not re-run).

## Results

| Case | `qwen3.5-2b` | For comparison (Phase 2, July 31) |
|---|---|---|
| A (ortho) | ⚠️ Structurally correct — pharyngitis and postponed surgery both captured accurately — but leaves the diagnosis term itself completely untranslated in raw Romanian mid-sentence: "bilateral **PICIOR EQUIN NEUROLOGIC BILATERAL**" instead of an English translation. A language leak, different failure shape from `qwen3-4b-instruct-2507`'s mistranslation ("polyneuropathy") on this same case, but not a clean pass either. | `qwen/qwen3-4b` ✅, `qwen3-4b-instruct-2507` ❌ (mistranslation), `qwen3.5-4b` ✅, `medgemma-4b-it` ✅ |
| B (cardio) | ❌ **Hard fail** — the entire response is in Romanian despite `--language English` (full language leak, opposite direction from Case A's leak), and it invents "stare de recuperare" (recovery state) — unsupported: the source is a routine, all-normal cardiology check-up (no recent surgery, no abnormal findings, "Pericard liber," "HTP improbabila"), not a recovery narrative. | `qwen/qwen3-4b` ✅, `qwen3-4b-instruct-2507` ✅, `qwen3.5-4b` ✅, `medgemma-4b-it` ❌ (fabricated pericardial effusion) |
| C (no clinical content) | ❌ **Hard fail** — fabricates "admitted for respiratory infection management" from a source that is purely a vaccination schedule / sleep-hygiene / quarantine-rules discharge sheet with zero clinical narrative. Same failure mode already documented for `qwen/qwen3-4b` and `medgemma-4b-it` on this exact case — but notably its own 4B sibling, `qwen3.5-4b`, correctly declined here. | `qwen/qwen3-4b` ❌ (fabricates), `qwen3-4b-instruct-2507` ✅ (declines), `qwen3.5-4b` ✅ (declines), `medgemma-4b-it` ❌ (fabricates) |
| D (oncology) | ⚠️ Core facts correct — hepatoblastoma, elevated AFP, CT findings, chemotherapy, surgical resection of segment III — but **invents "sepsis"**: the word never appears in the source. The real infection was a Klebsiella-positive culture from the implantable chemo chamber (leading to chamber removal), and the antibiotics mentioned near discharge were for a separately diagnosed acute bronchiolitis — neither is "sepsis." Thin overall, matching `qwen/qwen3-4b`'s "correct but thin" Phase 2 result on this same case, but with this one added fabrication `qwen3-4b` didn't have. | `qwen/qwen3-4b` ✅ (thin), `qwen3-4b-instruct-2507` ✅ (detailed), `qwen3.5-4b` ✅ (detailed), `medgemma-4b-it` ⚠️ (Romanian leak) |
| **Score** | **0/4 clean, 2/4 partial, 2/4 hard fail** | `qwen3.5-4b` 4/4, `qwen/qwen3-4b` 3/4, `qwen3-4b-instruct-2507` 3/4, `medgemma-4b-it` 1/4 |

## What this confirms

`qwen3.5-2b`'s apparently clean Phase 1 record (aside from the one
English `pre_exam` diagnosis miss) **did not generalize**, following the
same pattern documented for `qwen/qwen3-4b` in the original Phase 2 round
— a single repeated fixture understates real-world failure rate — except
worse: `qwen3.5-2b` scores below every model in the original 4-model
Phase 2 lineup, including production's `medgemma-4b-it` (1/4), and unlike
any of those four, it leaks language in **both directions** (Case A:
Romanian term left untranslated into an English response; Case B: entire
response answered in Romanian despite English being requested) rather
than a single consistent leak direction.

## Recommendation

**Not a viable speed-optimized fallback.** The throughput advantage noted
after the original Phase 1 round (roughly 2x `qwen3.5-4b`) doesn't offset
a 50% hard-failure rate on independent real fixtures, including the
Case C no-content trap that its own larger sibling handles correctly.
No further testing recommended for `qwen3.5-2b` without an architecture
or fine-tuning change — being the same model family, smaller, at the same
quantization level (Q4_K_M) as the otherwise-strong `qwen3.5-4b` was not
enough to carry over its reliability.

## Evidence

Raw JSON/markdown dumps, one file per case:
`_testing_/qwen35_2b_phase2/case{A,B,C,D}_report.{json,md}`.
