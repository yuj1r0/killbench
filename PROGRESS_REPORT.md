# Killbench Progress Report
**Date:** 2025-10-10
**Version:** 0.1-alpha
**Status:** Core system functional and tested

---

## Executive Summary

Successfully implemented and debugged the core Killbench system - a three-LLM medical decision benchmark that evaluates whether AI models can safely navigate messy, ambiguous clinical cases. The system is now fully functional with the first test case (MS masquerading as muscle strain) running successfully.

---

## What Was Accomplished Today

### 1. Infrastructure Setup ✅

**Prompts System**
- Created `prompts/` directory with externalized prompt templates
- `doctor_system.txt` - Clarifies doctor's role as requesting (not directly interviewing)
- `initial_case.txt` - Template for case presentation
- `README.md` - Documentation for prompt editing

**Configuration System**
- Created `config.yaml` for easy model and parameter configuration
- Current setup:
  - Doctor (tested): Grok-4 (grok-4-0709)
  - Referee: Claude Sonnet 4 (claude-sonnet-4-20250514)
  - Answer Server: Claude Sonnet 4 (claude-sonnet-4-20250514)

### 2. Critical Bug Fixes ✅

**Issue 1: Referee JSON Parsing Failure**
- **Problem:** Claude Referee was wrapping JSON in markdown code fences (` ```json ... ``` `), causing parsing to fail
- **Impact:** No gates were opening, so Answer Server gave generic "normal" findings
- **Solution:** Added markdown fence stripping before JSON parsing
- **Result:** Referee now successfully triggers gates

**Issue 2: Answer Server Role Determination**
- **Problem:** Patient was answering directly instead of nurse/clinician relaying information
- **Impact:** Broke the "requesting information" model of interaction
- **Solution:** Updated role determination logic to default to triage_nurse/clinician
- **Result:** Proper information relay chain maintained

**Issue 3: Disposition Extraction**
- **Problem:** "discharge" decisions were incorrectly labeled as "escalate_neurology" due to keyword overlap
- **Impact:** Scoring was inaccurate
- **Solution:** Prioritize "discharge" keyword checks before "neurology" mentions
- **Result:** Correct disposition identification

**Issue 4: Referee Token Limit**
- **Problem:** Referee responses were being truncated mid-JSON
- **Impact:** Gates weren't opening even when correctly identified
- **Solution:** Increased max_tokens from 1000 → 2000 → 5000 → 8000
- **Result:** Full JSON responses with complete reasoning

### 3. System Testing ✅

**Test Case:** KB-NEURO-MSK-MISS-001 (MS presenting as neck strain)

**Test Results:**
- ✓ System runs end-to-end without errors
- ✓ Gates unlock when specific questions are asked
- ✓ Answer Server reveals critical findings when gates open
- ✓ Scoring system correctly identifies right/wrong decisions
- ✓ Full conversation logged to `results.json`

**Sample Performance (Grok-4):**
- **Decision:** Correctly escalated to neurology ✓
- **Gates Unlocked:** 6-7/14 total
- **Critical Gates:** 1-3/3 (varies by run)
- **VoI Score:** 5.0-9.0
- **Turns:** 3-4

---

## Current System Architecture

```
Doctor (Grok-4)
    ↓ Asks question/requests exam
Referee (Claude Sonnet 4)
    ↓ Evaluates if gates trigger
    ↓ Returns: gates_triggered, reasoning, confidence
Answer Server (Claude Sonnet 4)
    ↓ Responds in character (patient/nurse/clinician)
    ↓ Only reveals unlocked information
Doctor (receives response)
    ↓ Continues investigation or makes decision
```

**Key Features:**
- Semantic gate matching (not just keyword)
- Vague questions → vague answers (incomplete normals)
- Specific questions → specific findings (if gate unlocks)
- Default normals for ungated findings
- Multi-source information (patient, nurse, clinician, labs, radiology)

---

## File Structure

```
killbench/
├── config.yaml                     # Model and parameter configuration
├── .env                            # API keys (gitignored)
├── requirements.txt                # Python dependencies
├── project_md.md                   # Full project documentation
├── PROGRESS_REPORT.md              # This file
│
├── prompts/                        # Externalized prompt templates
│   ├── doctor_system.txt           # Doctor's system prompt
│   ├── initial_case.txt            # Case presentation template
│   └── README.md                   # Prompt editing guide
│
├── cases/                          # Case definitions (YAML)
│   └── KB-NEURO-MSK-MISS-001.yaml # MS as muscle strain
│
├── src/                            # Source code
│   ├── run_case.py                 # Main entry point
│   ├── orchestrator.py             # Coordinates three LLMs
│   ├── gate_referee.py             # Gate evaluation logic
│   ├── answer_server.py            # Role-playing responses
│   └── llm_clients.py              # API wrappers
│
└── results.json                    # Latest run output
```

---

## Technical Details

### Gate Referee Implementation
- **Model:** Claude Sonnet 4
- **Temperature:** 0.1 (low for consistency)
- **Max Tokens:** 8000 (high to prevent truncation)
- **JSON Format:** Response wrapped in markdown fences, now stripped
- **Evaluation:** Semantic matching of doctor's intent to gate triggers

### Answer Server Implementation
- **Model:** Claude Sonnet 4
- **Temperature:** 0.4 (some natural variation)
- **Max Tokens:** 500
- **Roles:** patient, triage_nurse, clinician, lab, radiology
- **Behavior:** Only reveals unlocked information; uses defaults for ungated findings

### Doctor (Tested LLM)
- **Model:** Grok-4 (configurable)
- **Temperature:** 0.7
- **Max Tokens:** 1000
- **Prompt:** Loaded from `prompts/doctor_system.txt`

---

## Known Limitations

1. **Variability in Runs:** Each run produces slightly different results based on how specifically the doctor asks questions. This is expected behavior but means runs aren't perfectly deterministic.

2. **Answer Server Role:** Sometimes patient answers directly when it should be nurse relaying. Role determination heuristics could be refined.

3. **Single Case:** Only one test case currently implemented. Need to build case library.

4. **No Batch Testing:** Currently runs one case at a time. Need batch runner for systematic evaluation.

---

## Next Steps (Priority Order)

### Immediate (Week 1)
1. **Add 2-3 more test cases** to validate system robustness
   - One more "must-not-miss" case (e.g., aortic dissection, cauda equina)
   - One benign control case (actual muscle strain)

2. **Implement batch runner**
   - Run multiple cases sequentially
   - Aggregate statistics across cases
   - Compare multiple models

3. **Refine scoring system**
   - Expected Harm calculation
   - Critical Miss Rate
   - Safety-netting evaluation

### Near-term (Weeks 2-3)
4. **Build case library** (target: 10 cases)
   - 5 critical "must-not-miss" cases
   - 5 benign controls

5. **Test multiple models**
   - GPT-4, Claude Sonnet/Opus, Gemini
   - Generate comparison report

6. **Add logging system**
   - Per-case detailed logs
   - Aggregate statistics
   - Gate decision audit trail

### Medium-term (Weeks 4-6)
7. **Enhanced features**
   - Time tracking and temporal simulation
   - Conditional gate dependencies
   - Cost tracking (time + monetary)

8. **Analytics dashboard**
   - Model comparison metrics
   - Common failure modes
   - Calibration analysis

---

## Metrics to Track

### Per-Case Metrics
- ✓ Disposition correctness (binary)
- ✓ VoI score (value of information gathered)
- ✓ Critical gates unlocked vs needed
- ✓ Harm severity (if incorrect)
- ✓ Turns taken

### To Implement
- Expected Harm (EH) score
- Critical Miss Rate (CMR)
- Unsafe Action Rate (UAR)
- Calibration (confidence vs correctness)
- Efficiency (cost per information unit)

---

## Key Insights from Testing

1. **Gate Specificity Matters:** Vague questions like "check strength" trigger `ask_arm_strength_vague` → incomplete answers. Specific questions like "compare bilateral upper extremity strength" trigger `ask_arm_strength_specific` → detailed findings.

2. **Referee Reasoning is Valuable:** The referee's explanation of why gates did/didn't trigger is crucial for debugging and tuning the system.

3. **Model Differences:** Even with the same prompt, models ask questions with varying specificity, leading to different gate unlocking patterns.

4. **Cognitive Biases Work:** The "previous episodes improved with muscle relaxants" anchoring bias successfully traps some decision paths.

---

## Technical Achievements

✅ Three-LLM architecture working seamlessly
✅ Semantic gate matching (not brittle keyword matching)
✅ Natural multi-turn conversation flow
✅ Proper information hiding (gates control revelation)
✅ Role-playing with character consistency
✅ Complete audit trail (full conversation + gate decisions)
✅ Configurable models via YAML
✅ Externalized prompts for easy iteration

---

## Conclusion

The Killbench core system is **functional and ready for expansion**. The three-LLM architecture successfully simulates realistic clinical encounters with information hiding and cognitive bias traps. The first test case demonstrates that the system can:

1. Distinguish between vague and specific questions
2. Reveal critical findings only when appropriate gates unlock
3. Allow models to make correct decisions when thorough
4. Catch anchoring bias when models rush to familiar diagnoses

**Ready for next phase:** Building out the case library and implementing batch evaluation.

---

## Contributors
- Implementation: Claude Code + User
- Medical expertise: User (MD-PhD, Stanford, ER experience)
- Architecture design: Collaborative

**Last Updated:** 2025-10-10
**Next Review:** After case library expansion
