# Prompts Directory

This directory contains all system prompts and templates used in the Killbench evaluation system.

## Files

### `doctor_system.txt`
System prompt for the tested LLM (doctor being evaluated). This defines the doctor's role, objectives, and output format.

**Variables:** None (static system prompt)

**Key aspects:**
- Clarifies the doctor is requesting information, not directly interviewing
- Lists available information sources (patient questions, exams, tests, staff)
- Encourages thoroughness without being too prescriptive

### `initial_case.txt`
Template for the initial case presentation given to the doctor.

**Variables:**
- `{age}`: Patient's age (from case YAML)
- `{sex}`: Patient's sex (from case YAML)
- `{triage_nurse}`: Triage nurse's initial presentation (from case YAML `roles.triage_nurse`)

## Usage

The orchestrator loads these prompts at runtime and interpolates variables from the case YAML.

## Editing Guidelines

- Keep prompts neutral - avoid hints about diagnosis
- For doctor_system.txt: Balance thoroughness with efficiency, don't make information-gathering too obvious as "the answer"
- For initial_case.txt: Maintain minimal information (only what's immediately visible)
- Test changes by running cases with different LLMs to ensure robustness
