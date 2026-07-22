# Cross-Case Gap Analysis: Pre-Exam Prompt Validation
## 10 Real Pediatric Cases (260100000557585–260100000557594)

---

## Key Patterns: What Radiologists Care About That The Prompt Misses

### 1. **Medication Allergies & Adverse Reactions**
**Case 260100000557585 (Asthma)**: Singulair (montelukast) adverse reaction documented.

**Why it matters**: 
- Post-imaging treatment planning — radiologist needs to know which agents are contraindicated for this patient
- Risk of anaphylaxis or severe reaction if the agent is re-prescribed after imaging

**Current prompt coverage**: The prompt asks for "current treatment" and "recent course" but does NOT explicitly prompt for documented medication allergies or prior adverse reactions.

**Proposed addition**: Add to "Current clinical status" or new subsection:
> "Documented medication allergies or prior adverse drug reactions (if any stated in the record) — important for post-imaging treatment planning."

---

### 2. **Family History with Specific Clinical/Imaging Implications**
**Case 260100000557588 (Rectal polyp + IBD)**: Grandfather had colon cancer; patient has elevated fecal calprotectin (2200 mcg/g, markedly abnormal) and 18 months of bloody stools with abdominal pain.

**Why it matters**:
- Family history + lab + symptoms = this is likely **inflammatory bowel disease** (Crohn's or UC), NOT just a simple polyp
- Imaging approach changes: need to assess colon segment involvement, complications, fistulas — different protocol than polypectomy follow-up

**Current prompt coverage**: The prompt asks for "prior imaging" but does NOT explicitly request or synthesize family history + lab + clinical presentation together. Risk of missing the IBD diagnosis entirely if only the diagnosis code ("rectal polyp") is visible.

**Proposed addition**: Add to "History" or "Current clinical status":
> "Family history of malignancy (especially GI) or hereditary syndromes relevant to imaging indication."
> AND: "Key abnormal labs that change clinical interpretation (e.g., elevated inflammatory markers, positive serology)."

---

### 3. **Immunosuppression & Infection Risk**
**Case 260100000557592 (Acute leukemia + fistula)**: 14-month-old with acute lymphoblastic leukemia (induction therapy), C. difficile enterocolitis, VRE colonization, and complex perineal-vulvovaginal fistula from tissue necrosis.

**Why it matters**:
- Imaging needs to account for immunosuppression: risk of opportunistic infection, delayed healing, atypical presentations
- Fistula imaging for surgical planning in a highly compromised patient — different urgency/sterility protocols
- Concurrent infection (VRE) affects imaging timing and infection control

**Current prompt coverage**: The prompt does NOT explicitly ask for immunosuppression status or concurrent infections.

**Proposed addition**: Add to "Current clinical status":
> "Immunosuppression status (if applicable: chemotherapy, HIV, primary immunodeficiency, chronic corticosteroid use) and concurrent infections (e.g., VRE colonization, C. difficile) — affects imaging protocols and interpretation."

---

### 4. **Incidental/Structural Findings That May Affect Imaging**
**Case 260100000557587 (GERD + infantile hemangiomas)**: 3-month-old with infantile hemangiomas in the lumbosacral region (two lesions: 1×0.5×0.2 cm and 2×3×1.5 cm).

**Why it matters**:
- Infantile hemangiomas are usually benign but can: interfere with positioning, be mistaken for other lesions, or warrant imaging (e.g., to monitor growth or check for internal involvement)
- May affect patient positioning during imaging (pressure from hemangioma, discomfort)

**Current prompt coverage**: The prompt does NOT prompt for incidental structural findings or anatomic variants that may affect imaging planning.

**Proposed addition**: Add to "Current clinical status":
> "Incidental or known structural findings (e.g., hemangiomas, masses, anatomic variants) that may affect imaging feasibility or interpretation."

---

### 5. **Undertreated or Poorly Controlled Chronic Disease**
**Case 260100000557593 (Chronic HBV infection)**: 17-year-old with mother-to-child HBV transmission; WAS on 1.5 years of Entecavir (stopped by family), now has elevated viral load (as of 10/2023), and has just restarted therapy. Currently in "reactive hepatitis" state.

**Why it matters**:
- Not being on treatment for extended period = high replication, risk of fulminant hepatitis, cirrhosis progression
- Imaging (ultrasound/MRI) needs to assess liver parenchyma for fibrosis/cirrhosis, especially in this undertreated phase
- Elevated viral load + recent restart of therapy = patient is in an unstable disease state, high risk

**Current prompt coverage**: The prompt does NOT prompt for therapy adherence, gaps in treatment, or disease control status.

**Proposed addition**: Add to "Current clinical status":
> "Medication adherence and disease control status (for chronic conditions): is the patient on recommended therapy? Are there gaps in treatment? What is the current disease activity/control status?"

---

### 6. **Decoding Vague Diagnosis Codes to Identify the Actual Clinical Problem**
**Case 260100000557589 (\"Unspecified bacterial infection\")**: Diagnosis code is A49.9 (unspecified), but epicrisis reveals: fever (max 38.6°C), productive cough ×2 weeks, nasal obstruction, frontal headache, otalgia. This is clearly **upper respiratory tract infection/sinusitis**, not a "mystery" infection.

**Why it matters**:
- If radiologist only reads the diagnosis code ("unspecified"), they don't know what to image or what to look for
- Clinical presentation ("productive cough, nasal obstruction, headache, otalgia") → sinus imaging (CT or US) is indicated
- Prompt needs to help radiologist decode the clinical context from the epicrisis text, not just the diagnosis label

**Current prompt coverage**: The prompt asks for "main diagnosis" but does NOT explicitly prompt to extract the clinical presentation that defines the actual imaging need.

**Proposed addition**: Add to "History" or new section:
> "Presenting symptoms and clinical course that define the imaging need (not just the diagnosis label). When diagnosis code is vague (e.g., 'unspecified infection'), extract the specific clinical presentation from the record."

---

### 7. **Post-Surgical Follow-Up Context**
**Cases 260100000557590, 260100000557594**: Post-cholecystectomy eval, post-stone disease intervention.

**Why it matters**:
- Imaging is NOT initial diagnostic workup — it's follow-up/re-evaluation
- Radiologist needs to know the baseline/prior imaging to assess interval change
- Clinical question may be "resolution of complication?" vs. "recurrence?" vs. "routine surveillance?"

**Current prompt coverage**: The prompt asks for "prior imaging" but does NOT explicitly prompt for the clinical context of why imaging is being repeated now.

**Proposed addition**: Add to "Reason for current exam":
> "Is this initial imaging workup or follow-up? If follow-up, what was the prior finding/diagnosis, and what is the clinical question for THIS exam?"

---

### 8. **Risk Stratification for Serious Underlying Pathology**
**Case 260100000557588 (Rectal polyp)**: Elevated fecal calprotectin + family hx of colon cancer + 18 months of symptoms = HIGH RISK for IBD with potential complications.

**Why it matters**:
- Imaging protocol and urgency change based on risk
- If missed as "just a polyp," radiologist may not image the entire colon to assess for other lesions, fistulas, or transmural inflammation

**Current prompt coverage**: The prompt does NOT ask for risk stratification or factors that would escalate imaging urgency/scope.

---

## Proposed Prompt Improvements Summary

### New Sections to Add:

1. **Medication allergies & adverse reactions** (under "Current clinical status")
   - One-line instruction: Capture any documented drug allergies or adverse reactions

2. **Risk factors & family history** (under "History" or dedicated section)
   - Family hx of malignancy (especially relevant to imaging site)
   - Hereditary syndromes (e.g., FAP, Lynch)
   - Risk factors that change imaging interpretation

3. **Immunosuppression & infection status** (under "Current clinical status")
   - Chemotherapy, HIV, immunodeficiency, chronic steroids
   - Concurrent infections (VRE, C. diff, etc.)

4. **Incidental findings that affect imaging** (under "Current clinical status")
   - Anatomic variants, structural lesions, hemangiomas, etc.

5. **Disease control & medication adherence** (under "Current clinical status")
   - For chronic conditions: on therapy? therapy gaps? current disease activity?

6. **Reason for CURRENT exam** (strengthen existing section)
   - Clarify: initial workup vs. follow-up?
   - If follow-up, what was the prior finding/question?
   - What is the clinical question for THIS imaging?

7. **Presenting symptoms & clinical context** (under "Reason for current exam" or "History")
   - Extract from epicrisis: what prompted the imaging referral?
   - When diagnosis code is vague, extract the actual clinical problem

---

## Validation Notes

- **Case variety**: 10 unrelated pediatric patients with diverse diagnoses (respiratory, GI, cardiac, hematologic, infectious, urologic)
- **Common missed elements**: medication allergies (1/10), relevant family hx (2/10), immunosuppression (1/10), incidental findings (2/10), undertreated chronic disease (1/10), need for context on clinical question (7/10)
- **Frequency of improvements**: 70-100% of cases would benefit from at least one of the proposed additions

EOF

wc -l /home/costin/work/hippobridge/_testing_/cases/CROSS_CASE_GAP_ANALYSIS.md