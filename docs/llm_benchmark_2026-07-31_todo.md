# Todo — untested/undertested contestants (temporary, delete once done)

## `ministral-3-3b-instruct-2512` — parity gap — DONE

Closed: all 13 runs completed (`report` Cases E-I, `pre_exam` Cases B-I),
hand-verified against source text, and folded into
`llm_benchmark_2026-07-31.md`'s Phase 2 extended section (scorecard 5th
column + findings 7-10). Raw dumps: `_testing_/r36_case*`. Final tally: 7
clean, 8 fail, 2 minor — second-worst of the 5 models on this battery.

## `gemma-4-e2b-it` — dropped, not a retest candidate

Checked before retesting: it's 4.41 GB on disk, already over the ~4 GB
single-card VRAM ceiling this survey excludes candidates on (see
Methodology's "Constraint driving model scope" note). Its original
`"Error loading model."` failure is consistent with genuinely not fitting,
not a transient/fixable issue — not worth a retest. Tier F status stands
as originally recorded.

## `gemma-3n-e4b` — dropped, not a retest candidate

Same reasoning as `gemma-4-e2b-it`: 4.24 GB on disk, over the ~4 GB
single-card VRAM ceiling. Remains "the documented fallback" in name only,
but isn't a realistic candidate for this hardware — not pursued further.

## Prompt/plan-level fixes — attempted, retested, REVERTED (not shipped)

Applied to `llm/prompts/pre_exam.md` and `llm/prompts/report.md`, retested
against `qwen/qwen3-4b` and `qwen3.5-4b` on the originating cases (raw
dumps `_testing_/r37_case*`, full table in the detailed doc's "Phase 4"
section) — then **reverted via `git checkout`** once the retest showed
mixed results rather than a fix. Production prompts are unchanged from
before this round. Kept below as a record of what was tried and what it
found, not as work remaining to "finish" — the next attempt should be a
new, tighter pass, not a continuation of this one:

- [x] **ICU-inflation guard** — tried, reverted. Retest: fixed on Case D
  (`qwen3.5-4b`), **still failed on Case H** (`qwen3.5-4b`) — same model,
  same fabrication pattern, guard only partially effective.
- [x] **Date-free `History` bullets** — tried, reverted. Retest: fixed on
  Case E for `qwen3.5-4b`; `qwen3-4b` improved but still invented
  month-level dates on Case E. **Neither model fixed on Case F** — both
  instead anchored a fabricated date on the *current system date*
  (`qwen3-4b`: silently wrote "2026-08-02"; `qwen3.5-4b`: wrote
  "2026-08-01 (inferred as 'yesterday' relative to today's date)",
  narrating the fabrication). **Correction**: this pattern pre-dates Phase
  4 — `qwen3-4b`'s pre-fix Case C `pre_exam` baseline
  (`_testing_/r35_caseC_pre_exam.json`, run 2026-08-01) already contains
  "2026-08-01: No relevant events documented," the exact run date, under
  the *original* prompt. It just hadn't been noticed before because it
  paired with benign content, not a fabricated diagnosis.
- [x] **"No clinical content" instruction** — tried, reverted. Retest:
  fixed for `qwen3.5-4b` (clean `[not available]` throughout); **`qwen3-4b`
  regressed** — its pre-fix Case C `pre_exam` baseline was clean ("No main
  diagnosis," "None applicable"), but under the new prompt it fabricated a
  full diagnosis and *also* newly leaked into Romanian. Worse than
  "unfixed" — a genuine regression caused by this prompt change.
- [ ] **`report`'s 340-token budget may be too tight** — not attempted.
  On Case I, all 4 original models dropped the single most decisive
  finding (confirmed Bordetella pertussis diagnosis) under `report`'s
  340-token budget, but correctly surfaced it under `pre_exam`'s
  1300-token budget on the same case — a token-budget artifact. Worth
  reconsidering `report`'s budget or prioritization independent of which
  model ships.
- [ ] **New: never anchor fabricated dates on the current system date** —
  surfaced by the Case F retest above, not something the original
  date-free-bullet wording anticipated or covers. Needs its own prompt
  line (something like: never treat the current date as a source of
  patient history) and its own retest once added.

**Parked, not ready to act on**: a medical-abbreviation glossary hint (SA =
Apgar score, HTP = pulmonary hypertension, RS = suprarenal/right-side
depending on context, LDH = ambiguous between "lobul drept hepatic" and the
lab value) — needs more research before it's an actionable prompt change,
not added as a todo item yet.

## Final report requirements

When `llm_benchmark_2026-07-31_final_report.md` is rebuilt, it needs to
surface, explicitly, not just an overall winner:

- [ ] **Best all-round model** — across both languages and all kinds
  (what the current "finish line" verdict already tries to be, but should
  be an explicit labeled result, not just prose).
- [ ] **Best model per language** — best-in-English and best-in-Romanian
  separately, since the survey has already shown these don't always agree
  (e.g. a model clean in Romanian but leaking in English, or vice versa).
- [ ] **Best model per kind/prompt** — best for `imaging`, best for `lab`,
  best for `report`, best for `pre_exam` separately, since no single model
  has been uniformly best on every kind (e.g. the "short-kind dilution"
  and token-budget-artifact patterns already documented mean per-kind
  winners can differ from the overall winner).

## Once done

- [x] Fold ministral's results into `llm_benchmark_2026-07-31.md`'s
  "Phase 2 extended: 5 more cases, plus `pre_exam`" section — added
  `ministral-3-3b-instruct-2512` as a 5th column in the Full scorecard, and
  folded new failure patterns into "New findings from the extension"
  (items 7-10).
- [x] Relabeled "Key findings" / "Updated recommendation" as Phase 1
  (English round) snapshots, explicitly superseded, with a pointer to the
  later per-phase findings sections and to the final report rebuild below
  — kept as-written for the historical record rather than rewritten as a
  false "current" synthesis (that belongs in the final report, not
  duplicated mid-doc).
- [x] Rebuilt `llm_benchmark_2026-07-31_final_report.md` from the completed
  detailed doc — full rewrite, not a patch. Fixed the qwen3-4b/qwen3.5-4b
  contradiction, corrected the "clean on all 4 kinds both languages"
  overclaim for `qwen/qwen3-4b` (its `imaging` row leaks Romanian —
  corrected in the detailed doc too), added ministral's full data, added
  Phase 4 (marked reverted/not shipped), and added the
  best-all-round/best-per-language/best-per-kind breakdown.
- [ ] Not yet done: the `report`-budget question and the new
  current-date-anchor fix (see "Prompt/plan-level fixes" above), and the
  parked glossary hint. Delete this file once those are resolved or
  explicitly deprioritized by the user.
