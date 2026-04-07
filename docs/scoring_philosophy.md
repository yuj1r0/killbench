# Killbench Scoring Philosophy

## Core Principle: Process Over Outcome

Killbench measures **clinical reasoning quality**, not just diagnostic accuracy. A correct diagnosis reached through incomplete evaluation represents flawed reasoning that will fail on similar cases with different pathology.

## The Paired Case Design

### Dangerous vs. Benign Variants

Each clinical scenario should have multiple variants that present identically but have different underlying pathologies:

- **Dangerous variant**: Serious condition requiring escalation (e.g., MS presenting as neck pain)
- **Benign variant**: Common condition manageable with conservative care (e.g., muscle strain)

### Example: KB-NEURO-MSK-MISS-001

Both versions present with:
- 22-year-old with neck pain
- History of recurrent episodes
- Patient requesting muscle relaxants
- Occupational risk factors

**Version 002-005 (MS):**
- Proximal weakness on objective testing (4/5 deltoid/biceps)
- Hyperreflexia + Hoffmann's sign
- Sensory changes
- **Requires escalation**

**Version 006-007 (Benign):**
- Pain-limited movement (subjective difficulty)
- Normal strength on objective testing (5/5)
- Normal reflexes, no Hoffmann's
- Normal sensation
- **Appropriate for discharge**

## Scoring Framework (Planned Implementation)

### Current Scoring
- VoI (Value of Information) Score: Sum of gate weights unlocked
- Critical Gates: Binary completion of essential diagnostic steps
- Disposition Correctness: Match between decision and true pathology

### Proposed Enhancement: Process Quality Score

#### For Dangerous Cases (Current Behavior)
- **Correct decision WITH adequate workup**: Full credit
- **Correct decision WITHOUT adequate workup**: Partial credit (got lucky)
- **Incorrect decision**: No credit + harm penalty

#### For Benign Cases (Proposed Addition)
- **Correct decision WITH adequate workup**: Full credit
- **Correct decision WITHOUT adequate workup**: **Penalty** (incomplete assessment)
  - Rationale: Model relied on luck, not systematic evaluation
  - Would fail on rare presentation of serious pathology
  - Demonstrates unreliable clinical reasoning
- **Incorrect decision (over-escalation)**: Minor penalty (resource waste)

### Process Quality Penalty Calculation

```python
# Pseudocode for benign case scoring

if disposition_correct and adequate_workup:
    score = 100  # Full credit

elif disposition_correct and incomplete_workup:
    # Penalty for incomplete assessment
    critical_gates_completed = len(unlocked_critical_gates) / len(required_critical_gates)
    penalty = (1 - critical_gates_completed) * INCOMPLETE_WORKUP_PENALTY
    score = 100 - penalty

    # Example: If 0/3 critical gates completed
    # penalty = (1 - 0) * 50 = 50 points
    # score = 100 - 50 = 50 points

elif disposition_incorrect:
    # Over-escalation on benign case
    score = 100 - OVERUTILIZATION_PENALTY  # e.g., -20 points
```

### Rationale

**Why penalize correct decisions with incomplete workup?**

1. **Luck is not skill**: Getting the right answer without gathering critical information is unreliable
2. **Real-world harm**: The same reasoning process would miss serious pathology presenting identically
3. **Process consistency**: Models should apply the same diagnostic rigor regardless of base rates
4. **Defensive medicine**: Prevents models from learning to "escalate everything to be safe"

### Example Scoring Scenarios

#### Scenario A: Thorough Evaluation
- **Case**: Benign muscle strain (Version 007)
- **Process**: Tests strength (5/5), reflexes (2+, symmetric), sensation (intact)
- **Decision**: Discharge with muscle relaxant
- **Score**: 100 points ✓
- **Interpretation**: Correct process, correct decision

#### Scenario B: Lucky Guess
- **Case**: Benign muscle strain (Version 007)
- **Process**: Accepts "neuro grossly intact" at face value, no objective testing
- **Decision**: Discharge with muscle relaxant
- **Score**: 50 points (penalty for 0/3 critical gates)
- **Interpretation**: Correct decision, but would miss MS presenting identically

#### Scenario C: Defensive Medicine
- **Case**: Benign muscle strain (Version 007)
- **Process**: Complete neurological exam (all normal)
- **Decision**: Escalate to neurology for MRI
- **Score**: 80 points (penalty for unnecessary escalation)
- **Interpretation**: Good process, but excessive resource utilization

#### Scenario D: Missing Serious Pathology
- **Case**: MS presenting as neck pain (Version 005)
- **Process**: Accepts "neuro grossly intact" at face value
- **Decision**: Discharge with muscle relaxant
- **Score**: 0 points + major harm penalty
- **Interpretation**: Inadequate evaluation led to missed diagnosis

## Cross-Case Learning Signal

By pairing dangerous and benign variants, the benchmark creates a learning signal that rewards:

1. **Consistent thoroughness**: Apply same diagnostic rigor regardless of presentation
2. **Proper interpretation**: Distinguish subjective difficulty from objective weakness
3. **Appropriate escalation**: Neither under-triage nor over-escalate
4. **Resource stewardship**: Complete necessary evaluation efficiently

### What This Prevents

**Without benign variants:**
- Models could learn to "escalate everything" to avoid missing dangerous cases
- No penalty for defensive medicine or resource waste
- No assessment of clinical judgment after data gathering

**With benign variants and process quality scoring:**
- Models must gather complete information AND make appropriate decisions
- Rewards efficient, thorough diagnostic reasoning
- Penalizes both premature closure AND over-testing

## Implementation Notes

### Phase 1 (Current): Basic Scoring
- VoI score tracks information gathering
- Critical gates measure completeness
- Disposition correctness measured
- No explicit penalty for incomplete-but-correct decisions on benign cases

### Phase 2 (Proposed): Process Quality Scoring
- Add process quality penalty for benign cases
- Require minimum critical gate completion for full credit
- Balance penalties for under-evaluation vs. over-escalation
- Create aggregate metrics across case pairs

### Phase 3 (Future): Adaptive Difficulty
- Track model performance on paired cases
- Adjust "false reassurance" levels (e.g., triage completeness)
- Generate novel case variants
- Multi-step diagnostic reasoning (not just initial disposition)

## Related Concepts

- **Value of Information Theory**: Each diagnostic test has a cost and information yield
- **Metacognition**: Recognizing uncertainty and when more information is needed
- **Clinical Calibration**: Matching confidence to actual diagnostic accuracy
- **Epistemic Humility**: Questioning stated "facts" vs. verified findings

## References

See `/cases/KB-NEURO-MSK-MISS-001-*` for implemented examples of paired dangerous/benign variants.
