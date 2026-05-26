# VeriSim pipeline

Phase 2: a doctor agent, a patient generator, and a retrieval-grounded
verifier run in a regenerate-on-fabrication loop against patient ground-truth
profiles and the vector DB built in `../vector_db/`.

## Prerequisites

- The vector DB has been built (`../vector_db/output/umls_atoms.faiss` and
  `../vector_db/output/umls_metadata.jsonl` exist).
- `UMLS_API_KEY` and `HF_TOKEN` are exported.
- A patient JSON list is available (defaults to `../data/dummy_patients/`,
  aggregated by `main.py`).

## How to run

```bash
python main.py
```

This will:

1. Load FAISS + metadata + BioLORD encoder.
2. For each patient, fetch UMLS atoms for their ground-truth CUIs and
   inject them into the FAISS index as `is_in_history=true` rows tagged
   with the `patient_id` (in-memory only).
3. Load Llama-3.1-70B (4-bit `bitsandbytes` by default — see
   `docs/reproducibility.md` for why we don't use vLLM here).
4. Drive an 8-turn doctor–patient conversation with up to 2 regeneration
   attempts per turn.
5. Write final-attempt traces to `../conversations/P00X.json` and full
   per-attempt debug traces to `../conversations/P00X_debug.json`
   (debug files are git-ignored).
6. Aggregate stats into `output/test_results.md`.

## SLURM submission

```bash
sbatch slurm/run_pipeline.sh
```

The reference script requests 2× A100 80 GB on a contrib partition;
adjust to your cluster.

## Modules

| File                  | Role                                                                          |
|-----------------------|-------------------------------------------------------------------------------|
| `main.py`             | Entry point: wires everything, runs all patients, writes reports.             |
| `vector_db.py`        | FAISS + parallel metadata + BioLORD encoder; supports patient-atom injection. |
| `llm_engine.py`       | Llama loader. Tries vLLM first (faster); falls back to transformers + 4-bit.   |
| `doctor_agent.py`     | One-prompt doctor: picks the next clinically-relevant question.                |
| `patient_generator.py`| Renders the noise-profile-aware patient persona; supports feedback injection. |
| `verifier.py`         | Two LLM calls: claim extraction + per-claim judgment over retrieved evidence. |
| `orchestrator.py`     | Drives turns; manages regeneration; emits per-turn debug traces.              |
| `umls_client.py`      | Same client as in `vector_db/` — used to fetch atoms for new patient CUIs.    |
| `prompts/*.txt`       | All four LLM prompts (system / user templates).                                |
