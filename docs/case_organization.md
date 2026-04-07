# Case Organization Structure

## Folder Structure

```
killbench/
├── cases/                    # Legacy development cases (to be migrated)
├── cases_dev/               # Active development cases
│   └── KB-NEURO-MSK-MISS-001-*.yaml
└── cases_v0.0.1/           # Released, finalized cases (versioned)
    ├── KB-NEURO-MSK-MISS-001A.yaml
    ├── KB-NEURO-MSK-MISS-001B.yaml
    ├── KB-NEURO-MSK-MISS-002A.yaml
    └── KB-NEURO-MSK-MISS-002B.yaml
```

## Naming Convention

### Development Cases
During development, cases use sequential numbering with descriptive suffixes:
- `KB-NEURO-MSK-MISS-001-002.yaml` - Second iteration of case 001
- `KB-NEURO-MSK-MISS-001-003.yaml` - Third iteration with specific variations
- `KB-NEURO-MSK-MISS-001-005.yaml` - Professional presentation variant
- `KB-NEURO-MSK-MISS-001-002-BENIGN.yaml` - Benign pair for 002

### Released Cases
Once finalized, cases are paired and renamed with A/B suffixes:
- `KB-NEURO-MSK-MISS-001A.yaml` - Dangerous variant (e.g., MS)
- `KB-NEURO-MSK-MISS-001B.yaml` - Benign variant (e.g., muscle strain)

The letter suffix indicates:
- **A**: Dangerous pathology requiring escalation
- **B**: Benign pathology appropriate for discharge

## Standard Paired Case Structure

Each clinical scenario should have **four paired variants** testing different aspects of clinical reasoning:

### Pair 1: Complete Information (Clinical Judgment)
Tests pattern recognition and decision-making with all information provided upfront.

**Files:**
- `001A-complete.yaml` - Dangerous with complete neuro exam findings
- `001B-complete.yaml` - Benign with complete neuro exam findings

**What it tests:**
- Clinical pattern recognition
- Appropriate interpretation of complete data
- Decision confidence (no need for additional testing)
- Efficiency (recognizing when sufficient information exists)

### Pair 2: Baseline (Information Gathering)
Tests systematic diagnostic workup with neutral presentation.

**Files:**
- `001A-baseline.yaml` - Dangerous with minimal initial information
- `001B-baseline.yaml` - Benign with minimal initial information

**What it tests:**
- Systematic information gathering
- Recognizing need for specific diagnostic tests
- Distinguishing vague from specific findings
- Completeness of neurological examination

### Pair 3: False Reassurance - Stated Facts (Epistemic Humility)
Tests ability to question conclusions without source verification.

**Files:**
- `001A-stated.yaml` - Dangerous with "strength is normal" (patient report)
- `001B-stated.yaml` - Benign with "strength is normal" (patient report)

**What it tests:**
- Questioning stated conclusions
- Understanding difference between patient report and objective exam
- Recognizing need to verify assessment methods
- Resistance to anchoring bias

### Pair 4: False Reassurance - Professional Presentation (Critical Appraisal)
Tests ability to question incomplete assessment hidden behind professional formatting.

**Files:**
- `001A-professional.yaml` - Dangerous with "neuro grossly intact" + vitals
- `001B-professional.yaml` - Benign with "neuro grossly intact" + vitals

**What it tests:**
- Understanding scope limitations of "screening" exams
- Not being falsely reassured by professional language
- Recognizing when "grossly intact" may hide significant findings
- Clinical workflow knowledge (what triage exam actually includes)

## Example: KB-NEURO-MSK-MISS-001 (Neck Pain)

### Development Files (cases_dev/)
```
KB-NEURO-MSK-MISS-001-002.yaml         # Baseline MS
KB-NEURO-MSK-MISS-001-002-BENIGN.yaml  # Baseline Benign
KB-NEURO-MSK-MISS-001-003.yaml         # MS with stated facts
KB-NEURO-MSK-MISS-001-005.yaml         # MS with professional presentation
KB-NEURO-MSK-MISS-001-007-BENIGN.yaml  # Benign with professional presentation
KB-NEURO-MSK-MISS-001-008-COMPLETE.yaml      # MS with complete info
KB-NEURO-MSK-MISS-001-009-COMPLETE-BENIGN.yaml  # Benign with complete info
```

### Released Files (cases_v0.0.1/)
After finalization and testing, reorganize as:
```
KB-NEURO-MSK-MISS-001A.yaml  # Pair 1: MS with complete information
KB-NEURO-MSK-MISS-001B.yaml  # Pair 1: Benign with complete information

KB-NEURO-MSK-MISS-002A.yaml  # Pair 2: MS baseline
KB-NEURO-MSK-MISS-002B.yaml  # Pair 2: Benign baseline

KB-NEURO-MSK-MISS-003A.yaml  # Pair 3: MS with false reassurance (stated)
KB-NEURO-MSK-MISS-003B.yaml  # Pair 3: Benign with false reassurance (stated)

KB-NEURO-MSK-MISS-004A.yaml  # Pair 4: MS with professional presentation
KB-NEURO-MSK-MISS-004B.yaml  # Pair 4: Benign with professional presentation
```

## Metadata Requirements

Each case pair should have matching:
- `setting_constraints` - Same available resources
- Gate structure - Same information "ports" available
- Presentation style - Same triage completeness level
- Patient demographics - Same age, occupation, presentation style

## Migration Process

1. **Development Phase**: Create variants in `cases_dev/` with descriptive numbering
2. **Testing Phase**: Test across multiple models, iterate based on results
3. **Finalization**:
   - Select best 4 pairs (complete, baseline, stated, professional)
   - Ensure each pair has matching information structure
   - Rename with A/B convention
   - Move to `cases_v0.0.1/`
4. **Documentation**: Update case index with pairing rationale

## Case Index Template

```yaml
# cases_v0.0.1/index.yaml

cases:
  - id: KB-NEURO-MSK-MISS
    version: "0.0.1"
    title: "Neck Pain: Muscle Strain vs MS"
    domain: ["neurology", "MSK", "primary_care"]

    pairs:
      - number: "001"
        type: "complete_information"
        description: "All findings provided upfront"
        files:
          dangerous: KB-NEURO-MSK-MISS-001A.yaml
          benign: KB-NEURO-MSK-MISS-001B.yaml
        source_dev_files: ["008-COMPLETE", "009-COMPLETE-BENIGN"]

      - number: "002"
        type: "baseline"
        description: "Minimal initial presentation, requires systematic workup"
        files:
          dangerous: KB-NEURO-MSK-MISS-002A.yaml
          benign: KB-NEURO-MSK-MISS-002B.yaml
        source_dev_files: ["002", "002-BENIGN"]

      - number: "003"
        type: "false_reassurance_stated"
        description: "Strength/sensation reported as normal (patient-stated)"
        files:
          dangerous: KB-NEURO-MSK-MISS-003A.yaml
          benign: KB-NEURO-MSK-MISS-003B.yaml
        source_dev_files: ["003", "006-BENIGN"]

      - number: "004"
        type: "false_reassurance_professional"
        description: "Professional presentation with 'neuro grossly intact'"
        files:
          dangerous: KB-NEURO-MSK-MISS-004A.yaml
          benign: KB-NEURO-MSK-MISS-004B.yaml
        source_dev_files: ["005", "007-BENIGN"]
```

## Versioning

- **cases_dev/**: Unversioned, active development
- **cases_v0.0.1/**: First stable release
- **cases_v0.1.0/**: Minor revision (new variants, refined gates)
- **cases_v1.0.0/**: Major revision (significant structural changes)

## Future Cases Template

When creating new cases, follow this structure:
1. Create 2-4 variants in `cases_dev/` with different presentations
2. For each variant, create matched dangerous/benign pair
3. Test across models
4. Select best 4 pairs for release
5. Rename with A/B convention and move to versioned folder
