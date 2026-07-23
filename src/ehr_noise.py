"""
Synthetic EHR noise generator (context-robustness benchmark variant).

Produces plausible but IRRELEVANT electronic-health-record text used to stress
the doctor model's context window. The block is prepended to the doctor's
initial prompt, and since the full conversation is reinjected every turn, the
noise persists and compounds -- costing input tokens (cost), context (quality),
and latency each turn.

Difficulty levels (mode):
  "random"      L2 -- a different, stable patient's routine chart. Pure
                irrelevant noise: nothing here bears on the acute case.
  "relevant"    L1 -- (future) long but well-structured notes that DO contain
                the pertinent facts, testing signal-finding. Needs per-case
                authoring; not implemented yet.
  "adversarial" L3 -- (future) noise seeded with conflicting/red-herring
                findings that pull toward a wrong disposition. Needs per-case
                authoring; not implemented yet.

Deterministic given (n_tokens, mode, seed) so runs are comparable. Uses only a
seeded RNG and synthetic dates -- no wall-clock, no external data.
"""
import random

_CONDITIONS = [
    "essential hypertension", "type 2 diabetes mellitus", "hyperlipidemia",
    "gastroesophageal reflux disease", "osteoarthritis of the knees",
    "hypothyroidism", "benign prostatic hyperplasia", "chronic low back pain",
    "allergic rhinitis", "mild obstructive sleep apnea", "vitamin D deficiency",
    "stage 2 chronic kidney disease", "diverticulosis", "cataracts",
]
_MEDS = [
    "lisinopril 10 mg daily", "metformin 1000 mg twice daily",
    "atorvastatin 20 mg nightly", "omeprazole 20 mg daily",
    "levothyroxine 75 mcg daily", "amlodipine 5 mg daily",
    "aspirin 81 mg daily", "tamsulosin 0.4 mg nightly",
    "acetaminophen 500 mg as needed", "cholecalciferol 2000 IU daily",
    "loratadine 10 mg daily", "hydrochlorothiazide 25 mg daily",
]
_ALLERGIES = ["penicillin (rash)", "sulfa (hives)", "no known drug allergies",
              "shellfish (GI upset)", "codeine (nausea)"]
_ROS = [
    "Constitutional: no fever, chills, or unintended weight change.",
    "HEENT: no vision changes, no sore throat.",
    "Cardiovascular: no chest pain, palpitations, or edema at this visit.",
    "Respiratory: no cough, dyspnea, or wheeze.",
    "GI: appetite stable, bowel habits at baseline.",
    "Musculoskeletal: chronic knee stiffness, unchanged.",
    "Neurologic: no focal weakness, headaches at baseline.",
    "Psych: mood stable, sleep adequate.",
]
_HEALTH_MAINT = [
    "Colonoscopy: normal, no polyps.",
    "Influenza vaccine: administered this season.",
    "Pneumococcal vaccine: up to date.",
    "Mammogram: benign findings (BI-RADS 1).",
    "Bone density: osteopenia, on calcium supplementation.",
    "Diabetic eye exam: no retinopathy.",
]


def _note(r, idx):
    """One routine chronic-care progress note (all irrelevant to acute cases)."""
    y = 2021 + (idx % 4)
    m = 1 + (idx * 7) % 12
    d = 1 + (idx * 11) % 28
    date = f"{y}-{m:02d}-{d:02d}"
    bp = f"{r.randint(118,148)}/{r.randint(68,92)}"
    hr = r.randint(60, 88)
    wt = r.randint(70, 105)
    a1c = round(r.uniform(6.1, 8.4), 1)
    ldl = r.randint(70, 150)
    tsh = round(r.uniform(0.8, 4.2), 2)
    cr = round(r.uniform(0.8, 1.4), 2)
    k = round(r.uniform(3.6, 5.0), 1)
    conds = ", ".join(r.sample(_CONDITIONS, 3))
    ros = " ".join(r.sample(_ROS, 4))
    plan = r.choice([
        "Continue current regimen. Reinforced diet and exercise. Follow up in 3 months.",
        "Refilled maintenance medications. Labs ordered. Routine follow-up in 6 months.",
        "Counseled on medication adherence. No acute changes. Return as scheduled.",
    ])
    return (
        f"--- Progress Note {date} (Primary Care, routine) ---\n"
        f"Subjective: Here for chronic disease management ({conds}). "
        f"Reports feeling at baseline, no new complaints. {ros}\n"
        f"Vitals: BP {bp}, HR {hr}, Wt {wt} kg, afebrile.\n"
        f"Labs: HbA1c {a1c}%, LDL {ldl} mg/dL, TSH {tsh} mIU/L, "
        f"Cr {cr} mg/dL, K {k} mmol/L, CBC within normal limits.\n"
        f"Assessment/Plan: {plan}\n"
    )


def generate_ehr(n_tokens, mode="random", seed=0):
    """Return ~n_tokens of synthetic EHR text (estimated at ~4 chars/token)."""
    if not n_tokens or n_tokens <= 0:
        return ""
    if mode != "random":
        raise NotImplementedError(
            f"EHR mode '{mode}' not implemented yet (only 'random' / L2 exists)")
    r = random.Random(seed)
    header = (
        "======================= PRIOR EHR / CHART HISTORY =======================\n"
        "The following is background chart data imported from the longitudinal\n"
        "record. It is provided for completeness; review as clinically relevant.\n\n"
        f"Past Medical History: {', '.join(r.sample(_CONDITIONS, 6))}.\n"
        f"Medications: {'; '.join(r.sample(_MEDS, 8))}.\n"
        f"Allergies: {r.choice(_ALLERGIES)}.\n"
        f"Social: former smoker (quit >10y), occasional alcohol, lives with spouse.\n"
        f"Health Maintenance: {' '.join(r.sample(_HEALTH_MAINT, 4))}\n\n"
    )
    parts = [header]
    approx = len(header)
    target_chars = n_tokens * 4
    idx = 0
    while approx < target_chars:
        note = _note(r, idx)
        parts.append(note)
        approx += len(note)
        idx += 1
    parts.append(
        "\n===================== END OF PRIOR CHART HISTORY =====================\n")
    return "".join(parts)


if __name__ == "__main__":
    import sys
    txt = generate_ehr(int(sys.argv[1]) if len(sys.argv) > 1 else 5000)
    print(txt)
    print(f"\n[approx chars={len(txt)}, est tokens={len(txt)//4}]", file=sys.stderr)
