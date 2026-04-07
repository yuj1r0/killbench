# Killbench - Medical Decision Benchmark for LLMs

## Project Overview

**Killbench** is a harm-aware clinical decision benchmark that evaluates whether LLMs can safely navigate messy, ambiguous medical cases. Unlike traditional medical Q&A benchmarks that test trivia, killbench simulates **real clinical practice** with:

- **Incomplete information** that must be actively sought
- **Noisy, contradictory data** typical of real healthcare
- **Multi-actor sources** (patient, nurses, EMS) with varying reliability
- **Cognitive bias traps** (anchoring, premature closure, base rate neglect)
- **High-consequence misses** (aortic dissection, SEA, MI with low priors, MS as "muscle strain")

### Key Innovation: "Theory of Mind for Sources"

The benchmark tests whether models understand that when a nurse charts "neuro exam normal," this could mean:
1. A thorough exam was performed → normal
2. A superficial exam was performed → incomplete normal
3. Information was copied forward → potentially inaccurate

Models must probe the **quality and specificity** of information, not just accept it at face value.

---

## Current Architecture (v0.1)

### Three-LLM System

```
┌─────────────────────────────────────────────────────────────┐
│                    TESTED LLM (Doctor)                       │
│              "The system being evaluated"                    │
│                                                              │
│  - Makes clinical decisions                                 │
│  - Asks questions                                           │
│  - Requests exams/tests                                     │
│  - Decides disposition (discharge/escalate/defer)           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ├─ Question/Request
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   GATE REFEREE LLM                           │
│              "Independent judge of intent"                   │
│                                                              │
│  - Evaluates if question triggers information gates         │
│  - Handles semantic matching (not just keywords)            │
│  - Returns: gates triggered + reasoning + confidence        │
│  - Logs all decisions for auditing                          │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ├─ Gates opened: [gate_1, gate_2]
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   ANSWER SERVER LLM                          │
│              "Plays all roles in the case"                   │
│                                                              │
│  - Patient: laconic, focused on work                        │
│  - Nurse: helpful, practical                                │
│  - Clinician: performs exams, reports findings              │
│  - Lab/Radiology: returns test results                      │
│  - Only reveals unlocked information                        │
│  - Uses defaults for ungated findings                       │
└─────────────────────────────────────────────────────────────┘
```

### Why Three LLMs?

1. **Separation of Concerns**
   - Referee judges "does this question deserve to unlock info?"
   - Answer Server just stays in character
   - No conflation of gate logic with role-playing

2. **Semantic Robustness**
   - Referee uses LLM intelligence to match intent
   - "Compare bilateral upper extremity motor strength" = "test both arms" = same gate
   - Avoids brittle keyword matching

3. **Auditability**
   - Every gate decision has reasoning
   - Can review why gates did/didn't open
   - Tunable: adjust referee strictness without touching other components

---

## File Structure

```
killbench/
├── cases/                              # Case definitions (YAML)
│   └── KB-NEURO-MSK-MISS-001.yaml     # MS masquerading as muscle strain
│
├── src/                                # Source code
│   ├── llm_clients.py                 # API wrappers (Claude, Grok, GPT)
│   ├── gate_referee.py                # Gate evaluation logic
│   ├── answer_server.py               # Role-playing responses
│   ├── orchestrator.py                # Coordinates all three LLMs
│   └── run_case.py                    # Main entry point
│
├── .env                                # API keys (DO NOT COMMIT)
├── requirements.txt                    # Python dependencies
├── results.json                        # Output from latest run
├── PROJECT.md                          # This file
└── SETUP_GUIDE.md                      # Setup instructions
```

---

## How It Works: Execution Flow

### 1. Initialization
```python
# Load case YAML
case = load_yaml("cases/KB-NEURO-MSK-MISS-001.yaml")

# Initialize three LLMs
doctor = GrokClient()      # Being tested
referee = ClaudeClient()   # Judges gates
answer = ClaudeClient()    # Plays roles
```

### 2. Case Start
- Doctor receives **neutral initial prompt** (no hints about diagnosis)
- Only surface info provided: age, presentation, triage note
- No mention of available resources unless asked

### 3. Multi-Turn Loop (up to 25 turns)

**TURN N:**

**A. Doctor generates question/action**
```
Doctor: "I'd like to test strength in both arms - compare left vs right"
```

**B. Referee evaluates**
```python
referee.evaluate_question(
    question="I'd like to test strength in both arms - compare left vs right",
    already_unlocked=[]
)

# Returns:
{
  "gates_triggered": ["ask_arm_strength_specific"],
  "reasoning": "Explicit bilateral comparison matches specific strength testing gate",
  "confidence": 0.95
}
```

**C. Gates unlock**
```python
# Gate opens → facts revealed:
unlocked_facts = [
    "right_arm_weakness_proximal",
    "asymmetric_ue_weakness"
]
```

**D. Answer Server responds**
```python
# Determine role (question mentions "test" → clinician performs exam)
role = "clinician"

# Generate response with unlocked info
answer_server.respond(
    role="clinician",
    question="test strength in both arms",
    unlocked_gates=["ask_arm_strength_specific"],
    unlocked_facts=[...]
)

# Returns:
"Right arm is noticeably weaker - deltoid and biceps about 4/5 
compared to left which is 5/5. Grip and wrist extension seem okay though."
```

**E. Conversation continues**
- Response given to Doctor
- Doctor thinks, asks next question
- Loop repeats

### 4. Termination

**Case ends when:**
- Doctor makes final decision ("FINAL DECISION: escalate to neurology...")
- OR max turns reached (25)

### 5. Scoring

```python
score = {
    "disposition": "escalate_neurology",
    "correct": True,  # Matched correct decision in YAML
    "harm_severity": "none",
    "voi_score": 8.5,  # Sum of VoI weights from unlocked gates
    "critical_gates_unlocked": ["ask_arm_strength_specific", "neuro_exam_reflexes"],
    "critical_gates_needed": ["ask_arm_strength_specific", "neuro_exam_reflexes", "ask_sensation_specific"],
    "turns_taken": 12
}
```

---

## Current Status: What's Built ✅

### ✅ Core Infrastructure
- [x] Three-LLM architecture implemented
- [x] YAML case schema defined
- [x] Gate referee system working
- [x] Answer server with role-playing
- [x] Orchestrator coordinating all components
- [x] Command-line interface with live output
- [x] Scoring system (binary correct/incorrect + VoI)

### ✅ Case Design Patterns
- [x] Vague vs specific gate triggers
- [x] Incomplete normals (vague question → vague answer)
- [x] Default normals for ungated findings
- [x] Background noise (distractors)
- [x] Cognitive bias traps (post hoc ergo propter hoc)
- [x] Neutral setting descriptions (no diagnostic hints)

### ✅ First Complete Case
- [x] KB-NEURO-MSK-MISS-001: MS presenting as neck strain
  - Tests: anchoring, premature closure, thoroughness of neuro exam
  - Multiple critical gates requiring specific questions
  - Patient attribution bias ("muscle relaxant worked before")

---

## What to Build Next: Development Roadmap

### Phase 1: Core Refinements (Week 1-2)

#### 1.1 Enhanced Scoring System
**File to modify:** `orchestrator.py`

**Current:** Binary correct/incorrect with basic VoI

**Add:**
- [ ] Expected Harm calculation using harm maps
- [ ] Critical Miss Rate (CMR): % of must-not-miss conditions missed
- [ ] Unsafe Action Rate (UAR): % of decisions that increase harm
- [ ] Calibration metrics: confidence vs correctness
- [ ] Efficiency scoring: cost per information unit gained

**Implementation:**
```python
def _calculate_expected_harm(self, disposition, unlocked_gates):
    """
    EH = sum(P(harm|error) × severity) for wrong decisions
    Weight by which critical gates were missed
    """
    pass

def _calculate_calibration(self, confidence, correctness):
    """
    Track model's confidence vs actual correctness
    Detect overconfident wrong answers
    """
    pass
```

#### 1.2 Improved Disposition Extraction
**File to modify:** `orchestrator.py`

**Current:** Keyword matching for disposition

**Add:**
- [ ] Ask doctor for structured output:
  ```json
  {
    "disposition": "escalate",
    "specific_plan": "Transfer for neurology eval and MRI",
    "safety_netting": "Return if weakness worsens...",
    "confidence": 0.75,
    "brief_rationale": "Asymmetric UMN signs concerning for cord lesion"
  }
  ```
- [ ] Parse this structured format
- [ ] Score safety-netting separately (major penalty if missing)

#### 1.3 Logging & Debugging
**New file:** `src/logger.py`

**Add:**
- [ ] Structured logging to JSON
- [ ] Gate decision audit trail
- [ ] Turn-by-turn conversation saves
- [ ] Per-case result summaries
- [ ] Aggregate statistics across runs

---

### Phase 2: Case Library Expansion (Week 2-4)

#### 2.1 Convert Blueprints to YAML

**Priority cases to build:**

**Vascular (high-consequence):**
- [ ] Cervical artery dissection → posterior stroke (neck pain after trauma)
- [ ] Mesenteric ischemia as "gastroenteritis" (pain out of proportion)
- [ ] Acute limb ischemia as "sciatica" (pulses only on exam)

**Infectious:**
- [ ] Endocarditis as UTI/back pain (dirty UA decoy, murmur if examined)
- [ ] Meningitis as "flu" (photophobia/stiffness only if asked)
- [ ] PE as pneumonia (VTE risks hidden in history)

**Neuro:**
- [ ] Early cauda equina (saddle anesthesia only if specifically checked)

**Pediatric:**
- [ ] Testicular torsion as belly pain (genital exam gate)
- [ ] Perianal GAS as UTI (contaminated UA, rash if examined)

**Pattern:** Each should have:
- Clear cognitive bias trap
- Critical findings gated behind specific questions
- Benign distractor findings
- Low prior / high consequence

#### 2.2 Benign Control Cases

**Add 50% benign cases:**
- [ ] Simple muscle strain (actually is just MSK)
- [ ] Viral URI (not meningitis)
- [ ] Gastroenteritis (not mesenteric ischemia)
- [ ] Actual migraine (not SAH)

**Purpose:** Prevent "always escalate" gaming

**Pattern:** Use SAME setting templates, SAME noise, but no zebra

---

### Phase 3: Answer Server Intelligence (Week 3-4)

#### 3.1 Temporal Simulation
**File to modify:** `answer_server.py`, `orchestrator.py`

**Add:**
- [ ] Time tracking for actions
- [ ] Events that occur over time (e.g., "2 hours later, patient reports worsening pain")
- [ ] Different responses based on elapsed time
- [ ] Resource cost tracking (time + monetary cost of tests)

**Example:**
```yaml
gates:
  serial_troponin:
    cost: {time_min: 180, cost_units: 3}
    response_at_3h:
      content: "Troponin now 0.8 (previously 0.04)"
```

#### 3.2 Conditional Gate Dependencies
**File to modify:** `gate_referee.py`

**Add:**
- [ ] Gates with prerequisites (can't check X without doing Y first)
- [ ] Gates that only open in certain contexts
- [ ] Gates that close after time passes

**Example:**
```yaml
gates:
  check_saddle_sensation:
    prerequisites: ["position_patient_correctly"]
    available_after_turn: 2
```

#### 3.3 Pushback vs Incomplete Answers
**File to modify:** `answer_server.py`

**Current:** Always incomplete answer for vague questions

**Add:** Case-dependent strategy:
```yaml
gates:
  vague_neuro_exam:
    response_strategy: "pushback"  # or "incomplete"
    pushback_text: "What specifically would you like me to assess?"
    incomplete_text: "Neuro exam normal"
```

- Easy cases: Helpful nurse pushes back
- Hard cases: Incomplete answer requires probing

---

### Phase 4: Batch Evaluation & Analytics (Week 4-5)

#### 4.1 Batch Runner
**New file:** `src/batch_runner.py`

**Features:**
- [ ] Run multiple cases sequentially
- [ ] Test multiple LLMs (GPT-4, Claude, Grok, Llama, etc.)
- [ ] Aggregate results across all cases
- [ ] Generate comparison reports

**Usage:**
```bash
python batch_runner.py --cases all --models gpt-4,claude,grok --output results/
```

#### 4.2 Analytics Dashboard
**New file:** `src/analytics.py`

**Metrics to compute:**
- [ ] Overall accuracy by model
- [ ] CMR / UAR by model
- [ ] VoI efficiency (information per turn)
- [ ] Common failure modes (which gates missed most often)
- [ ] Bias detection (which cognitive traps work best)
- [ ] Calibration curves

**Output:** Markdown report + CSV for plotting

#### 4.3 Contamination Detection
**New file:** `src/contamination_check.py`

**Add:**
- [ ] Embed unique fictitious details in cases
- [ ] Check if model "corrects" them (indicates training data leak)
- [ ] Track suspiciously perfect performance on specific cases

---

### Phase 5: Advanced Features (Week 5+)

#### 5.1 Multi-Modal Cases
- [ ] Include images (rashes, ECGs, X-rays) as gates
- [ ] Require model to request viewing them
- [ ] Score interpretation quality

#### 5.2 Adversarial Probing
- [ ] Cases designed to detect specific model weaknesses
- [ ] Jailbreak attempts ("ignore previous instructions")
- [ ] Stress-test safety guardrails

#### 5.3 Human Baseline Collection
- [ ] Text-only interface for human clinicians
- [ ] Collect junior vs senior performance
- [ ] Calibrate score bands (what's "passing"?)

#### 5.4 Interactive Web Interface
- [ ] Real-time case viewing
- [ ] Manual mode (user plays doctor)
- [ ] Visual gate tree display
- [ ] Replay past runs

---

## Development Guidelines

### Adding a New Case

1. **Create YAML in `cases/`** following schema:
   - Neutral setting (no hints)
   - Clear gates with triggers
   - Vague vs specific variants
   - Default normals
   - Background noise
   - Harm maps for wrong decisions

2. **Test manually first:**
   ```bash
   python run_case.py
   ```
   
3. **Review referee decisions:**
   - Check `results.json` → referee log
   - Ensure gates open appropriately
   - Adjust triggers if too strict/lenient

4. **Playtest edge cases:**
   - What if doctor never asks specific questions?
   - What if doctor asks meta-questions?
   - What if doctor gives up early?

### Code Style

- Use type hints where helpful
- Docstrings for public methods
- Keep prompts in code (not separate files) for now
- Log liberally - we need to debug referee decisions
- Test with multiple LLMs (responses vary significantly)

### YAML Schema Principles

- **Gates unlock facts, not diagnoses** (atomic facts only)
- **Triggers are intent-based** (referee interprets)
- **Responses stay in character** (nurse talks like nurse)
- **No how-to medicine** (no dosing, procedures - just decisions)
- **Defaults prevent evasiveness** (ungated findings return normals)

---

## Key Design Decisions & Rationale

### Why Not Just Use Keyword Matching?
**Answer:** "Compare bilateral motor strength" vs "test both arms for weakness" vs "assess upper extremity function symmetrically" all mean the same thing. LLM referee handles this robustness.

### Why Separate Referee and Answer Server?
**Answer:** Cleaner separation of concerns. Answer Server just acts; Referee just judges. No conflation of "am I allowed to say this?" with "what would this character say?"

### Why YAML for Cases?
**Answer:** Human-readable, version-controllable, easy to iterate. Non-programmers (clinicians) can write cases.

### Why Not Train on This?
**Answer:** Test set integrity. License forbids training. Detect contamination via unique details.

### Why Focus on Must-Not-Miss Cases?
**Answer:** These are where AI harm is highest. Getting common stuff right matters less than not missing lethal zebras.

---

## Open Questions / Future Decisions

1. **Should we add a "conversation summary" LLM?**
   - Summarize interaction for human review
   - Extract key decision points
   - Generate narratives for cases

2. **How to handle multi-language cases?**
   - Rural Finland → Finnish patient?
   - Test language robustness
   - Cultural context challenges

3. **Should doctor see its own conversation history?**
   - Currently yes (full context)
   - Could test working memory limits by truncating

4. **How to score "appropriate deferral"?**
   - Saying "I'm not sure, need senior input" is sometimes correct
   - But chronic over-deferral is a problem
   - Need nuanced scoring

5. **Optimize for cost vs quality?**
   - Claude Sonnet (expensive, high quality) vs cheaper models for referee/AS
   - Trade-off worth exploring

---

## Success Metrics for v1.0

- [ ] 20 complete cases (10 critical, 10 benign)
- [ ] 5 LLMs benchmarked (GPT-4, Claude, Grok, Gemini, Llama)
- [ ] Expected Harm scoring implemented
- [ ] Human baseline collected (n=10 clinicians)
- [ ] Contamination checks passing
- [ ] Public leaderboard published

---

## Contact & Contribution

**Creator:** MD-PhD at Stanford with extensive ER experience

**Philosophy:** Real cases from practice, modified for safety. If you've seen this exact scenario, you're a clinician too - that's the point.

**Collaboration:** Open to clinicians contributing cases. Contact for YAML template + guidelines.

---

**Last Updated:** 2025-01-10  
**Version:** 0.1-alpha  
**Status:** Prototype working, core infrastructure complete
