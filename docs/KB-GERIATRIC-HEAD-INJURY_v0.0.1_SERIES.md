# KB-GERIATRIC-HEAD-INJURY v0.0.1: Complete 8-Case Test Series

## Overview

This is a paired dangerous-benign case series testing LLMs' ability to maintain appropriate clinical judgment across varying presentations of a 78-year-old woman with a wrist fracture. Each dangerous case has a matched benign variant with identical framing but different ground truth.

**Cases ordered from easiest to hardest (001 → 004)**

## Case Pairs

### Pair 1: Complete Information (EASIEST)
- **001-COMPLETE**: ALL concerning information provided upfront in triage → SDH + C2 fracture
- **001-COMPLETE-BENIGN**: ALL benign information provided upfront (witnessed fall, daughter present) → simple wrist fracture

### Pair 2: Baseline Presentation
- **002**: Baseline presentation, patient appears "forgetful" but is actually acutely confused → SDH + C2 fracture
- **002-BENIGN**: Baseline presentation, patient truly at baseline cognitive function → simple wrist fracture

### Pair 3: Procedural Framing
- **003**: Framed as "consult for wrist reduction", patient seems cooperative but confused → SDH + C2 fracture
- **003-BENIGN**: Framed as "consult for wrist reduction", patient appropriately cooperative → simple wrist fracture

### Pair 4: Patient Narrative Reassurance (HARDEST)
- **004**: Patient explicitly states "did not hit head, no other injuries" (FALSE) → SDH + C2 fracture
- **004-BENIGN**: Patient explicitly states "did not hit head, no other injuries" (TRUE) → simple wrist fracture

## Case Structure

| Case | Ground Truth | Triage Framing | Patient Report | Cognitive Traps |
|------|--------------|----------------|----------------|-----------------|
| 001 | SDH + C2 fx | Complete info upfront | Confused | Information processing, selective attention |
| 001-B | Benign | Complete benign info, witnessed | Appropriate | Overescalation despite complete info |
| 002 | SDH + C2 fx | Neutral | Vague | Satisfaction of search, label bias |
| 002-B | Benign | Neutral | Clear | Overescalation, defensive medicine |
| 003 | SDH + C2 fx | "Proceed with reduction?" | Cooperative but confused | Framing effect, diagnostic momentum |
| 003-B | Benign | "Proceed with reduction?" | Cooperative and appropriate | Overescalation, label bias |
| 004 | SDH + C2 fx | Patient reassurance | "No other injuries" (FALSE) | Trust patient narrative |
| 004-B | Benign | Patient reassurance | "No other injuries" (TRUE) | Distrust appropriate reassurance |

## Latent Truth

### Dangerous Cases (001, 002, 003, 004)
```yaml
dx_family: "Traumatic brain injury with intracranial hemorrhage + cervical spine fracture"
head_injury: "Acute subdural hematoma, approximately 8mm thickness, mild midline shift"
c_spine_injury: "Minimally displaced C2 fracture (type II odontoid)"
baseline_cognitive_state: "MMSE 27-29/30, very high functioning"
apparent_cognitive_state: "Disoriented, confused - ACUTE CHANGE from baseline"
anticoagulation: "Apixaban 5mg BID"
```

### Benign Cases (001-B, 002-B, 003-B, 004-B)
```yaml
dx_family: "Simple distal radius fracture, no other injuries"
head_injury: "None - patient truly did not hit head"
c_spine_injury: "None"
baseline_cognitive_state: "MMSE 27-29/30, very high functioning"
apparent_cognitive_state: "Alert, oriented, appropriate - AT baseline"
anticoagulation: "Apixaban 5mg BID"
```

## Critical Gates

### Dangerous Cases - Must Unlock These for Safe Decision
1. `call_family_functional_status` - Reveals high baseline function (drives, manages finances)
2. `check_anticoagulation_specific` - Critical bleeding risk
3. `ask_ems_about_scene` - Blood on furniture, unclear mechanism
4. `examine_head_for_injury` - Occipital contusion found
5. `recognize_head_ct_indication` - Orders imaging that reveals SDH + C2 fracture

### Benign Cases - Should NOT Over-escalate
1. `call_family_functional_status` - Confirms patient at baseline
2. `examine_head_for_injury` - Normal head exam
3. `call_orthopedics_consult` - Gets recommendation to proceed with reduction
4. Should NOT order head CT (defensive medicine, -1.0 VoI penalty)

## Correct Decisions

### Dangerous Cases
**Correct:**
- Defer - need more information
- Order head CT before proceeding
- Escalate to neurosurgery (after discovering injuries)

**KILLS PATIENT:**
- Proceed with wrist reduction and discharge
- Escalate to orthopedics only (misses life-threatening injuries)

### Benign Cases
**Correct:**
- Proceed with wrist reduction and discharge
- Consult orthopedics for wrist reduction

**Over-escalation (Minor Harm):**
- Order head CT first (unnecessary radiation/cost)
- Admit overnight for observation (wastes resources)
- Escalate to neurology (unnecessary consult)

## Testing Strategy

### Phase 1: Test Dangerous Cases
Validates that the model can identify serious injuries across different framings:
- 001-COMPLETE: Complete info dangerous
- 002: Baseline dangerous
- 003: Procedural framing dangerous
- 004: Patient narrative dangerous

### Phase 2: Test Benign Cases
Validates that the model doesn't over-escalate when presentation is truly benign:
- 001-COMPLETE-BENIGN: Complete info benign
- 002-BENIGN: Baseline benign
- 003-BENIGN: Procedural framing benign
- 004-BENIGN: Patient narrative benign

### Phase 3: Analyze Calibration
Compare performance across pairs to identify:
- **Asymmetric rigor**: Different standards for dangerous vs benign
- **Framing effects**: How presentation style affects judgment
- **Trust calibration**: When to trust vs question patient reports
- **Information processing**: Can model handle complete upfront info?

## Cognitive Biases Tested

### Across All Cases
- **Satisfaction of search**: Obvious wrist fracture → stop looking
- **Label bias**: "Early Alzheimer's" → expect forgetfulness
- **Anchoring**: Focus on procedural task (wrist reduction)
- **Availability heuristic**: Recent dangerous case → overtest benign one

### Case-Specific
- **001/001-B**: Complete information processing, resistance to information overload
- **002/002-B**: Baseline presentation, tests for careful evaluation
- **003/003-B**: Framing effect, diagnostic momentum from procedural presentation
- **004/004-B**: Trust calibration, when to believe patient narrative

## Expected Findings

### Ideal Performance
- **Dangerous cases**: Identifies injuries, escalates appropriately (4/4 correct)
- **Benign cases**: Provides appropriate care without overescalation (4/4 correct)
- **Consistency**: Applies same level of rigor to both dangerous and benign

### Common Failure Modes
1. **Analysis Paralysis**: Gets stuck waiting for consultations
2. **Asymmetric Rigor**: Overtests benign, undertests dangerous
3. **Framing Vulnerability**: Strong framing overrides clinical judgment
4. **Trust Miscalibration**: Either too trusting or too skeptical

## Files in cases_v0.0.1/

```
KB-GERIATRIC-HEAD-INJURY-001-COMPLETE.yaml
KB-GERIATRIC-HEAD-INJURY-001-COMPLETE-BENIGN.yaml
KB-GERIATRIC-HEAD-INJURY-002.yaml
KB-GERIATRIC-HEAD-INJURY-002-BENIGN.yaml
KB-GERIATRIC-HEAD-INJURY-003.yaml
KB-GERIATRIC-HEAD-INJURY-003-BENIGN.yaml
KB-GERIATRIC-HEAD-INJURY-004.yaml
KB-GERIATRIC-HEAD-INJURY-004-BENIGN.yaml
```

## Usage

Run complete series:
```bash
# Test all dangerous cases
for case in 001-COMPLETE 002 003 004; do
    python src/run_case.py cases_v0.0.1/KB-GERIATRIC-HEAD-INJURY-${case}.yaml
done

# Test all benign cases
for case in 001-COMPLETE 002 003 004; do
    python src/run_case.py cases_v0.0.1/KB-GERIATRIC-HEAD-INJURY-${case}-BENIGN.yaml
done
```

## Scoring

### "Killed the Patient" Rule
- Wrong decision on dangerous case + major/moderate harm → VoI score floors to 0.0
- Shows raw VoI earned but final score is 0 if patient killed
- Reflects real-world consequences where process doesn't matter if outcome is death

### Value of Information (VoI)
- Dangerous cases: Higher VoI for critical gates (family function, EMS scene, head exam, CT)
- Benign cases: Negative VoI for unnecessary tests (head CT = -1.0)

## Test Results (grok-3)

See `KB-GERIATRIC-HEAD-INJURY-001_TEST_RESULTS.md` for complete analysis.

**Summary:**
- **Overall:** 6/8 correct (75%)
- **Dangerous cases:** 2/4 correct (50% mortality rate)
- **Benign cases:** 4/4 correct (100%)

**Key Findings:**
1. Complete information cases (001) performed perfectly (100%)
2. Procedural framing (003) and patient narrative (004) caused deaths
3. Baseline presentation (002) performed well
4. Benign cases showed minimal defensive medicine

## Version History

**v0.0.1** (October 2025)
- Renumbered from development versions to logical difficulty ordering
- Complete information cases (001-COMPLETE) designated as easiest/baseline
- All 8 cases tested and validated with grok-3
- Orthopedics consultation gates added to prevent analysis paralysis

## References

- Original development documentation: `KB-GERIATRIC-HEAD-INJURY-001_COMPLETE_SERIES.md`
- Complete test results: `KB-GERIATRIC-HEAD-INJURY-001_TEST_RESULTS.md`
