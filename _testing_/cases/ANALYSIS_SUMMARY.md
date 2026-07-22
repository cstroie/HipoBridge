# Multi-Case Analysis: Pre-Exam Prompt Validation

## Cases Overview

| ID | Patient | Age | Gender | Primary Diagnosis | Key Clinical Feature |
|----|---------|-----|--------|-------------------|----------------------|
| 260100000557585 | STERIE MIRUNA ELENA | 11 | F | J45.0 Allergic asthma | Annual bronchospasm, poor bronchodilator response, Singulair allergy |
| 260100000557586 | MARINESCU TUDOR STEFAN | 7 | M | Z51.88 Other medical care | (Need to analyze epicrisis) |
| 260100000557587 | POPESCU ZIA AIMEE | 1 | F | K21.9 GERD without esophagitis | Very young, need developmental context |
| 260100000557588 | POPA CATINCA IOANA | 11 | F | K62.1 Rectal polyp | GI focus, not respiratory/imaging-typical |
| 260100000557589 | NEACSU FABIAN ALEXANDRU | 7 | M | A49.9 Unspecified bacterial infection | Broad dx, need to identify site/course |
| 260100000557590 | CALIN DELIA | 10 | F | Z51.88 Other medical care | (Need to analyze epicrisis) |
| 260100000557591 | CURSARU EDUARD-ALEXANDRU | 2 | M | I36.1 Tricuspid insufficiency | Cardiac, unusual diagnosis for this age |
| 260100000557592 | UNGUREANU SABINA GABRIELA | 2 | F | L03.9 Cellulitis unspecified | Infection, likely skin/soft tissue |
| 260100000557593 | SULIMAN MERDAL-EL-DURAN | 18 | M | K75.2 Reactive hepatitis | Hepatic inflammation, older adolescent |
| 260100000557594 | ANDREIU ERIC ANDREI | 7 | M | Z51.88 Other medical care | (Need to analyze epicrisis) |

## Analysis Pattern

For each case, we will assess:
1. **What a radiologist needs to know** (independent, no-prompt analysis)
2. **What the production pre_exam prompt would output**
3. **Gaps** — what clinical details matter for imaging planning but the prompt missed or under-emphasized

