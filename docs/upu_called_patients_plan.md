# UPU ultrasound: patients called in by a hospital physician

Plan agreed 2026-11-02. Tool: `tools/upu_called.py` (built on `tools/upu_us_stats.py`).

## Questions

1. Was this UPU ultrasound patient **called in by a hospital physician** (a control done
   through the emergency department) rather than a spontaneous emergency?
2. How many UPU patients a day are **non-urgent controls called from home**?

Why: they load the radiologist on call with routine work that belongs to the day-care
cabinet.

## Two axes, not one

- **A. Arranged**: the visit was set up by a hospital physician.
- **B. Non-urgent**: discharged home, low triage, nothing done but the ultrasound.

Report the 2 x 2. "Arranged and urgent" (a post-op complication the surgeon rightly sends)
is legitimate; the target is "arranged and non-urgent".

## Signals (strongest first)

1. A specialist consult in the visit, early (within minutes of arrival), or before the
   ultrasound request; the request ordered by someone other than the UPU physician.
2. A recent discharge (last 90 days) from a ward whose physician (`medic_out`) is the one
   consulting now, or from the consulting specialty's ward.
3. Reason for visit / diagnosis: "control", "reevaluare", "la recomandarea", "chemat",
   "programat", "post-operator"; ICD-10 Z09, Z48 and similar.
4. Imaging-only visit: no labs, no X-ray, sent home.
5. Triage level (non-urgent / routine codes).
6. Arrival at working-type hours on the consulting physician's on-call afternoon.
7. Repeats: the same patient through UPU at intervals, same specialist.

On-call schedule: derived from who consults in UPU after 14:00; the owner's on-call
tables only validate it.

## Ground truth

- Retrospective: ~200 random UPU ultrasounds labelled blind by a radiologist; rule
  sensitivity/specificity and a corrected daily rate with CI.
- Prospective (preferred): 2-4 weeks with one tick per UPU ultrasound ("sent by a
  physician? which specialty?").

## Privacy

Flags, counts and salted hashes only. Reason and diagnosis text are turned into flags in
memory and never written. Physicians are reported by specialty, never by name.

## Steps

1. Feasibility: for October 2026, how often each field is filled.
2. Features per request -> `called.csv`; score A and B by rules.
3. Report: daily count, 2 x 2, by specialty, by hour and weekday, on-call vs routine.
4. Validation set for the owner to label.
