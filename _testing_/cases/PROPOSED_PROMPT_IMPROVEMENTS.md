# Proposed Improvements to `pre_exam.md`
## Based on Multi-Case Analysis (10 Real Pediatric Cases)

---

## Priority 1: Clarify "Reason for Current Exam" Section
**Issue**: Many cases are follow-up imaging, not initial workup. The prompt doesn't distinguish, leaving radiologist unclear on clinical context.

**Current text** in pre_exam.md:
```
### Reason for current exam
The clinical question this new study should answer, if stated.
```

**Proposed revision**:
```
### Reason for current exam
Is this an initial imaging workup or a follow-up study? If follow-up, what was the prior finding or diagnosis? 
What is the specific clinical question this study should answer (if stated)?
```

**Rationale**: Cases 260100000557586, 260100000557590, 260100000557594 are all follow-up studies. The radiologist needs to know this to interpret appropriately (e.g., assess for interval change, progression, complications).

---

## Priority 2: Add Medication Allergies & Adverse Reactions
**Issue**: Medication allergies affect post-imaging treatment planning and are critical safety information.

**Current coverage**: Not explicitly prompted.

**Proposed addition** (add to "Current clinical status" section):
```
Medication allergies or documented adverse drug reactions (if any, state which agent and reaction type).
```

**Rationale**: Case 260100000557585 has Singulair allergy — critical for future management. This should not be buried in the narrative; it should be surfaced explicitly.

**Impact**: 1/10 cases in this sample; estimated 10-15% of cases overall have relevant drug allergies.

---

## Priority 3: Add Disease Control & Medication Adherence for Chronic Conditions
**Issue**: Patients with chronic disease may be undertreated or non-adherent, changing risk assessment and imaging interpretation.

**Current coverage**: Not explicitly prompted.

**Proposed addition** (add to "Current clinical status" section):
```
For chronic conditions: is the patient on recommended therapy? Have there been gaps in treatment? What is the current disease activity/control status?
```

**Rationale**: Case 260100000557593 (HBV infection) was off Entecavir for extended period, now has reactive hepatitis. Imaging interpretation needs to account for this unstable disease state. Without this information, radiologist might miss urgency or severity.

**Impact**: ~20% of cases involve chronic disease; this addition would benefit those cases.

---

## Priority 4: Add Immunosuppression & Concurrent Infection Status
**Issue**: Immunocompromised patients need different imaging protocols (infection control, timing, interpretation).

**Current coverage**: Not explicitly prompted.

**Proposed addition** (add to "Current clinical status" section):
```
Immunosuppression status (e.g., chemotherapy, HIV, primary immunodeficiency, chronic corticosteroid use) and any concurrent infections (e.g., VRE colonization, active C. difficile) that affect imaging protocols or infection control.
```

**Rationale**: Case 260100000557592 is a 14-month-old with acute leukemia, C. difficile enterocolitis, and VRE colonization. Imaging team needs to know this for:
- Sterile technique requirements
- Timing of imaging (before vs. after treatment)
- Risk of infection transmission

**Impact**: ~10% of cases involve significant immunosuppression; critical safety issue when present.

---

## Priority 5: Add Relevant Family History with Clinical Implications
**Issue**: Family history can significantly change imaging approach and risk stratification.

**Current coverage**: Prompt asks for family history in general, but doesn't prompt for disease-specific or cancer-risk relevance.

**Proposed addition** (add to "History" section OR new subsection):
```
Family history of malignancy (especially relevant to current diagnosis), hereditary syndromes (e.g., FAP, Lynch), or genetic risk factors that affect imaging interpretation or urgency.
```

**Rationale**: Case 260100000557588 has grandfather with colon cancer + elevated fecal calprotectin → likely IBD, not just a polyp. This family history + lab changes the imaging protocol significantly.

**Impact**: ~20% of cases; can escalate imaging urgency/scope when present.

---

## Priority 6: Add Incidental Findings That Affect Imaging
**Issue**: Structural findings (hemangiomas, masses, anatomic variants) may affect patient positioning, imaging protocols, or interpretation expectations.

**Current coverage**: Not prompted.

**Proposed addition** (add to "Current clinical status" section):
```
Incidental or known structural findings (e.g., benign hemangiomas, congenital variants, incidental lesions) that may affect imaging feasibility, patient positioning, or interpretation.
```

**Rationale**: Case 260100000557587 has lumbosacral infantile hemangiomas that might affect supine positioning or be mistaken for other lesions if not known beforehand.

**Impact**: ~20% of pediatric cases; mostly benign, but important for radiologist to know.

---

## Summary Table

| Priority | Issue | Affected Cases in Sample | Estimated Prevalence | Impact Level |
|----------|-------|------------------------|----------------------|--------------|
| 1 | Clarify initial vs. follow-up imaging | 3/10 (30%) | High | Clinical urgency |
| 2 | Medication allergies | 1/10 (10%) | Medium | Safety |
| 3 | Disease control & adherence | 1/10 (10%) | Medium | Risk assessment |
| 4 | Immunosuppression & infections | 1/10 (10%) | Medium | Safety & protocols |
| 5 | Relevant family history | 2/10 (20%) | Medium | Risk stratification |
| 6 | Incidental findings | 2/10 (20%) | Low | Interpretation |

---

## Implementation Notes

1. **All proposed additions are GENERIC** — they apply to any clinical record, not just these 10 pediatric cases. No case-specific wording.

2. **None of the proposed changes alter the core structure** of pre_exam (no new main sections, just additions to existing sections).

3. **Token impact**: Adding these clauses will increase prompt length by ~100-150 tokens. At ~900-token max_tokens budget for pre_exam output, this is acceptable (leaves ~750-800 for actual output).

4. **All proposed additions maintain the "STRICT RULES"** about grounding, no fabrication, etc.

---

## Recommended Order of Implementation

1. **High-impact, low-risk**: Clarify "Reason for current exam" (Priority 1)
2. **Safety-critical**: Add medication allergies (Priority 2) and immunosuppression (Priority 4)
3. **Risk stratification**: Add disease control & relevant family history (Priorities 3 & 5)
4. **Nice-to-have**: Add incidental findings (Priority 6)

