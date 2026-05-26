# Prompt Templates

This directory contains the exact prompt templates used by the VeriSim
pipeline. Each file maps to a figure in the paper's appendix.

## File-to-Paper Mapping

| File                  | Component           | Paper Figure (Appendix A) | Used by                |
|-----------------------|---------------------|---------------------------|------------------------|
| `patient_system.txt`  | Patient Generator   | Figure A1                 | `patient_generator.py` |
| `verifier_extract.txt`| Verifier Call 1     | Figure A2                 | `verifier.py`          |
| `verifier_judge.txt`  | Verifier Call 2     | Figure A3                 | `verifier.py`          |
| `doctor_system.txt`   | Doctor LLM          | Figure A4                 | `doctor_agent.py`      |
| `llm_as_judge.txt`    | LLM-as-Judge        | Figure A5                 | evaluation scripts     |

## Variable substitution

All prompts use Python's `str.format()` substitution. Variables are
double-braced (`{{...}}`) when literal braces are needed in the output
(e.g., the JSON schema in `verifier_judge.txt`).

The variable names used in each prompt are listed in the prompt itself in
its `=== INPUT ===` or `=== EVALUATION DATA ===` block.

## Verdict scheme (Verifier Call 2)

The verifier produces a binary per-claim verdict `{PASS, FABRICATION}` and
an overall verdict `{PASS, REGENERATE}`. Underspecified claims (all
retrievals below cosine-similarity threshold `tau = 0.55`) default to
PASS, since they assert no verifiable medical fact.

## Noise dimensions (Patient Generator)

The Patient Generator's noise profile uses six dimensions, each ranging
from level 0 (no impairment) to level 4 (extreme):

  1. memory_recall
  2. health_literacy
  3. emotional_state
  4. communication_style
  5. cognitive_processing
  6. social_cultural

Per the paper protocol, each patient profile assigns non-zero levels
to exactly two of these six dimensions, with severity levels drawn from
L1-L3 for the main quantitative evaluation. Levels L0 (ideal) and L4
(extreme) are reserved for ablation studies and qualitative
stress-test examples.

## Modifying the prompts

To experiment with prompt variations, edit the corresponding `.txt` file.
The pipeline reloads prompts from disk at startup (no rebuild required).
For reproducibility of paper results, use the prompts as shipped.