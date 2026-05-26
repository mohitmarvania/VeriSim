# Examples

`conversations/P00{1..5}.json` are the **final-attempt** doctor–patient
transcripts from the 5-patient validation run (Llama-3.1-70B-Instruct,
8 turns each, 2 max regeneration attempts per turn).

For each turn we keep:

- `doctor` — the LLM-generated question
- `patient_response` — the *successful* patient utterance (after any regen)
- `verifier_result` — the verifier's verdict (PASS), the atomic claims it extracted, and the per-claim judgments
- `regeneration_attempts` — total attempts for that turn (1 = clean first pass)
- `timing_s` — wall-clock times for doctor + patient + verifier calls

We deliberately **do not include** the `*_debug.json` files (one per
patient) — those record every regeneration attempt with full retrieval
evidence and are large (~200 KB each). They are produced by `pipeline/main.py`
into `../conversations/` at runtime and are git-ignored.

## Headline numbers from this run

| Metric                          | Value          |
|---------------------------------|----------------|
| Total conversations             | 5              |
| Total turns                     | 40             |
| Patient utterances (incl. regens) | 44             |
| Regenerations triggered         | 4              |
| Fabrications caught             | 3 (P001 t6, P002 t1, P004 t6) |
| Underspecified-utterance regens (legacy) | 1 (P005 t5) |
| False positives                 | 0              |
| Final-attempt failures          | 0              |

Note on verdicts: the pilot traces were generated with an earlier three-way
verdict scheme {PASS, FABRICATION, VAGUE}. The paper and current pipeline
use the binary scheme {PASS, FABRICATION}, with underspecified claims
(retrievals below similarity threshold tau = 0.55) defaulting to PASS.

The three caught fabrications were each a specific claim outside the
patient's ground truth — alcohol use (P001), inhaler dosing specifics not
in profile (P002), and a "quit smoking 10 years ago" history that the
profile never contained (P004). In all three cases the patient regenerator,
on receiving the verifier's feedback, produced a profile-consistent answer
on the second attempt.
