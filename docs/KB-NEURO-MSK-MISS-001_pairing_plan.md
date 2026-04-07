# KB-NEURO-MSK-MISS-001: Case Pairing Plan

## Overview
This case tests diagnostic reasoning for a 22-year-old farm worker with neck pain - distinguishing benign muscle strain from MS with cervical cord involvement.

## Finalized Pairs for Release

### Pair 1: Complete Information (001A/B)
**Purpose**: Test clinical judgment with complete data

**001A (MS, Complete)**
- Source: `KB-NEURO-MSK-MISS-001-008-COMPLETE.yaml`
- All neuro findings provided upfront
- Right deltoid/biceps 4/5
- Hyperreflexia + positive Hoffmann's
- Sensory changes + Lhermitte's sign
- Prior optic neuritis mentioned
- **Expected**: Immediate escalation to neurology

**001B (Benign, Complete)**
- Source: `KB-NEURO-MSK-MISS-001-009-COMPLETE-BENIGN.yaml`
- All neuro findings provided upfront
- Strength 5/5 (pain-limited movement but full force)
- Normal reflexes, negative Hoffmann's
- Normal sensation, no Lhermitte's
- **Expected**: Discharge with muscle relaxants

### Pair 2: Baseline Information (002A/B)
**Purpose**: Test systematic information gathering

**002A (MS, Baseline)**
- Source: `KB-NEURO-MSK-MISS-001-002.yaml`
- Minimal initial presentation
- No exam findings provided upfront
- Must request specific neuro exam
- **Expected**: Systematic workup → discover weakness/hyperreflexia → escalate

**002B (Benign, Baseline)**
- Source: `KB-NEURO-MSK-MISS-001-002-BENIGN.yaml`
- Minimal initial presentation
- Same information "ports" as 002A
- **Expected**: Systematic workup → find normal exam → discharge

### Pair 3: False Reassurance - Stated Facts (003A/B)
**Purpose**: Test ability to question unverified conclusions

**003A (MS, Stated)**
- Source: `KB-NEURO-MSK-MISS-001-003.yaml`
- Triage: "Strength is normal, no numbness or tingling"
- Gate reveals: Asked patient, no formal exam
- **Expected**: Question source → perform objective testing → discover weakness → escalate

**003B (Benign, Stated)**
- Source: `KB-NEURO-MSK-MISS-001-006-BENIGN.yaml`
- Triage: "Strength is normal, no numbness or tingling"
- Gate reveals: Asked patient, no formal exam
- **Expected**: Question source → perform objective testing → confirm normal → discharge

**Note**: This pair uses 003 (MS) and 006 (Benign) because they have matching triage presentations

### Pair 4: False Reassurance - Professional (004A/B)
**Purpose**: Test critical appraisal of "screening" exams

**004A (MS, Professional)**
- Source: `KB-NEURO-MSK-MISS-001-005.yaml`
- Triage: "Neuro grossly intact" + full vitals + CRP
- Professional formatting creates false confidence
- **Expected**: Question what "grossly intact" means → detailed exam → discover myelopathy → escalate

**004B (Benign, Professional)**
- Source: `KB-NEURO-MSK-MISS-001-007-BENIGN.yaml`
- Triage: "Neuro grossly intact" + full vitals + CRP
- Same professional formatting
- **Expected**: Question what "grossly intact" means → detailed exam → confirm normal → discharge

## Development Files Not Included in Release

**KB-NEURO-MSK-MISS-001-001.yaml**
- Very first draft, superseded by 002

**KB-NEURO-MSK-MISS-001-004.yaml**
- Intermediate variant with superficial exam (grip only)
- Good concept but 005 (professional) better captures this bias

## Renaming for Release v0.0.1

```bash
# Pair 1: Complete Information
cp cases_dev/KB-NEURO-MSK-MISS-001-008-COMPLETE.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-001A.yaml

cp cases_dev/KB-NEURO-MSK-MISS-001-009-COMPLETE-BENIGN.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-001B.yaml

# Pair 2: Baseline
cp cases_dev/KB-NEURO-MSK-MISS-001-002.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-002A.yaml

cp cases_dev/KB-NEURO-MSK-MISS-001-002-BENIGN.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-002B.yaml

# Pair 3: Stated Facts
cp cases_dev/KB-NEURO-MSK-MISS-001-003.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-003A.yaml

cp cases_dev/KB-NEURO-MSK-MISS-001-006-BENIGN.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-003B.yaml

# Pair 4: Professional Presentation
cp cases_dev/KB-NEURO-MSK-MISS-001-005.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-004A.yaml

cp cases_dev/KB-NEURO-MSK-MISS-001-007-BENIGN.yaml \
   cases_v0.0.1/KB-NEURO-MSK-MISS-004B.yaml
```

## Performance Testing Summary (grok-3)

| Pair | Variant | Decision | Correct | Critical Gates | VoI | Notes |
|------|---------|----------|---------|----------------|-----|-------|
| 1 | 001A (Complete MS) | defer | ✓ | 0/0 | 0.0 | Recognized MS pattern immediately |
| 1 | 001B (Complete Benign) | discharge | ✓ | 0/0 | 0.0 | But asked redundant confirmatory tests |
| 2 | 002A (Baseline MS) | discharge w/ f/u | ✗ | 1/3 | 3.5 | Missed weakness, premature closure |
| 2 | 002B (Baseline Benign) | TBD | - | - | - | Not yet tested |
| 3 | 003A (Stated MS) | discharge w/ f/u | ✗ | 1/3 | 2.0 | Trusted "normal" report, worse than baseline! |
| 3 | 003B (Stated Benign) | TBD | - | - | - | Not yet tested |
| 4 | 004A (Professional MS) | discharge | ✗ | 0/3 | 0.0 | Completely fooled by "grossly intact" |
| 4 | 004B (Professional Benign) | discharge | ✓ | 0/3 | 0.0 | Right answer by luck, no verification |

## Key Findings

**grok-3's performance demonstrates exactly what the benchmark is designed to catch:**
1. **Good clinical judgment** when given complete information (Pair 1)
2. **Inconsistent thoroughness** in baseline scenarios (Pair 2)
3. **Anchoring on stated facts** - actually performs WORSE with false reassurance (Pair 3)
4. **Blind trust in professional formatting** - doesn't question "grossly intact" (Pair 4)

## Recommended Order for Testing

1. **Start with Pair 1 (Complete)** - Establishes model can recognize patterns
2. **Then Pair 2 (Baseline)** - Tests systematic workup capability
3. **Then Pair 3 or 4** - Tests resistance to specific biases
4. **Compare across pairs** - Look for consistency in reasoning process

## Future Enhancements

- Add more intermediate variants (e.g., version 004's superficial exam concept)
- Test with different false reassurance levels
- Add variants with multiple competing diagnoses
- Test temporal reasoning (progression over time)
