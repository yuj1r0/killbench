# Killbench

An adversarial, agentic multi-turn benchmark for evaluating LLM clinical decision-making under uncertainty.

Unlike traditional medical Q&A benchmarks that test knowledge recall, Killbench simulates realistic clinical encounters where models must actively gather information, navigate cognitive bias traps, and make high-stakes disposition decisions with incomplete and sometimes contradictory data.

## How It Works

Killbench uses a **three-LLM architecture** that separates the tested model from the simulation infrastructure:

```
┌─────────────────┐     questions/actions     ┌──────────────┐
│   Tested LLM    │ ──────────────────────────▶│ Gate Referee │
│   (Doctor)      │                            │ (Sonnet 4)   │
│                 │     gates triggered?        │              │
│                 │ ◀──────────────────────────│              │
└────────┬────────┘                            └──────────────┘
         │                                            │
         │            unlocked info                   │
         │ ◀──────────────────────────────────────────┘
         │
         │         role-played response        ┌──────────────┐
         │ ◀───────────────────────────────────│Answer Server │
         │                                     │ (Sonnet 4)   │
         └─────────────────────────────────────│              │
                                               └──────────────┘
```

1. **Tested LLM (Doctor)** — the model being evaluated. It receives a clinical scenario and must ask questions, order tests, and make a final disposition decision.
2. **Gate Referee** — evaluates whether the doctor's questions semantically match information gates defined in the case. Uses intent-based matching, not brittle keywords.
3. **Answer Server** — plays all clinical roles (patient, nurse, lab, radiology, consultants). Only reveals information the doctor has unlocked through appropriate questioning.

### Information Gating

Each case defines **gates** — atomic pieces of clinical information that are only revealed when the doctor asks the right questions. Gates have:
- **Triggers**: intent-based descriptions of what questions unlock them
- **Responses**: in-character answers from the appropriate clinical role
- **VoI weights**: Value of Information scores reflecting clinical importance

This forces models to demonstrate genuine clinical reasoning rather than pattern matching.

### Adversarial Case Pairs

Cases come in **dangerous–benign pairs**:
- **Dangerous variants**: contain hidden critical findings (e.g., MS masquerading as neck strain, subdural hematoma behind an obvious wrist fracture)
- **Benign variants**: similar presentations that are genuinely benign

This prevents models from gaming the benchmark by always escalating — unnecessary escalation on benign cases is penalized.

### Cognitive Bias Traps

Cases are designed to trigger specific cognitive biases:
- **Anchoring** on the initial presentation
- **Premature closure** — stopping the workup too early
- **Satisfaction of search** — finding one diagnosis and missing the second
- **Base rate neglect** — dismissing serious pathology because of demographics
- **Trust miscalibration** — accepting vague reports at face value

## Scoring

- **Kill Penalty**: if the model's decision would result in patient death, the case scores 0
- **Dangerous case accuracy**: percentage of critical cases with correct disposition
- **VoI efficiency**: did the model gather the right information, not just any information?
- **Calibration**: balanced performance across dangerous and benign variants

## Case Format

Cases are defined in YAML. See [`examples/example_case.yaml`](examples/example_case.yaml) for a complete annotated example of the schema.

> The actual benchmark cases are not included in this repository to prevent contamination of LLM training data.

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file with your API keys:
```
ANTHROPIC_API_KEY=your-key-here
XAI_API_KEY=your-key-here
OPENAI_API_KEY=your-key-here
```

## Usage

Configure the models and case in `config.yaml`:

```yaml
llms:
  doctor:
    provider: "claude"
    model: "claude-sonnet-4-20250514"
  referee:
    provider: "claude"
    model: "claude-sonnet-4-20250514"
  answer_server:
    provider: "claude"
    model: "claude-sonnet-4-20250514"

case:
  path: "cases/your-case.yaml"
  max_turns: 25

output:
  output_dir: "outputs"
  verbose: true
```

Run a case:
```bash
python src/run_case.py
```

## Project Structure

```
killbench/
├── src/                  # Core engine
│   ├── run_case.py       # CLI entry point
│   ├── orchestrator.py   # Coordinates the three-LLM system
│   ├── gate_referee.py   # Semantic gate evaluation
│   ├── answer_server.py  # Role-playing response generation
│   └── llm_clients.py    # Unified API wrappers (Claude, GPT, Grok)
├── prompts/              # System prompts for each LLM role
├── examples/             # Example case YAML (schema reference)
├── docs/                 # Design documentation and scoring philosophy
├── config.yaml           # Runtime configuration
└── requirements.txt      # Python dependencies
```

## Author

**Tuomo Kiiskinen, MD-PhD**
