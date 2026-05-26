# VeriSim

VeriSim is a patient simulation framework with retrieval-augmented truth
verification, designed for stress-testing medical AI under controllable
patient communication noise.

A Patient Generator (an instruction-tuned LLM, e.g., Llama-3.1-70B-Instruct)
produces multi-turn responses to a Doctor LLM under a noise profile spanning
six clinically grounded dimensions (memory recall, health literacy, emotional
state, communication style, cognitive processing, social-cultural). A two-call
Verifier extracts atomic medical claims from each candidate patient response,
retrieves supporting evidence from a UMLS-grounded FAISS vector database
(BioLORD-2023 embeddings over ~80,000 atoms with structured clinical
metadata), and decides per-claim PASS / FABRICATION. On FABRICATION, the
verifier emits feedback that triggers regeneration of the patient turn
(up to two attempts). The pipeline produces noisy but ground-truth-adherent
synthetic doctor-patient transcripts.

## Anonymity statement
This repository is anonymized for double-blind review.

## Quick start

```bash
# 1. Install pinned dependencies into a fresh venv
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Register for a UMLS license (https://uts.nlm.nih.gov/uts/) and export the key
export UMLS_API_KEY="<your-umls-api-key>"

# 3. Build the vector DB (~1 hour on 1xA100 80GB), then run the pipeline on dummy patients
python vector_db/build_vector_db.py --phase all
python pipeline/main.py
```

See [docs/reproducibility.md](docs/reproducibility.md) for the detailed walkthrough.

## Repository structure

```
VeriSim/
├── README.md                       # This file
├── LICENSE                         # MIT (anonymous copyright)
├── requirements.txt                # Pinned dependencies (combined)
├── .gitignore                      # Standard exclusions
├── .env.example                    # Sample env vars
│
├── docs/
│   ├── architecture.md             # Two-phase architecture overview
│   ├── reproducibility.md          # End-to-end reproduction recipe
│   └── data_schema.md              # JSON schemas for patient + traces
│
├── vector_db/                      # Phase 1: build UMLS-grounded FAISS index
│   ├── README.md
│   ├── build_vector_db.py
│   ├── umls_client.py              # UMLS REST API wrapper (cache + retries)
│   ├── seeds.py                    # In-code seed term lists (Phase B.1)
│   ├── seed_concepts/              # Post-expansion CUI sets per category
│   │   ├── symptoms.json
│   │   ├── medications.json
│   │   ├── procedures.json
│   │   └── conditions.json
│   ├── slurm/run_build.sh
│   └── output/build_report.md      # Stats from our build run
│
├── pipeline/                       # Phase 2: doctor + patient + verifier loop
│   ├── README.md
│   ├── main.py
│   ├── vector_db.py                # FAISS + metadata + BioLORD wrapper
│   ├── llm_engine.py               # vLLM / transformers Llama loader
│   ├── doctor_agent.py
│   ├── patient_generator.py
│   ├── verifier.py                 # Two-call extract+judge verifier
│   ├── orchestrator.py
│   ├── umls_client.py              # Same client used in vector_db/
│   ├── prompts/
│   │   ├── doctor_system.txt
│   │   ├── patient_system.txt
│   │   ├── verifier_extract.txt
│   │   └── verifier_judge.txt
│   ├── slurm/run_pipeline.sh
│   └── output/test_results.md      # 5-patient validation results
│
├── data/
│   ├── README.md
│   └── dummy_patients/             # 5 synthetic profiles
│       ├── P001.json … P005.json
│
└── examples/
    ├── README.md
    └── conversations/              # Final-attempt traces from the validation run
        ├── P001.json … P005.json
```

## Prompt-to-paper mapping

All LLM prompts used by the pipeline are stored as text files in
[pipeline/prompts/](pipeline/prompts/). Each file corresponds to a figure in
the paper's Appendix A. See
[pipeline/prompts/README.md](pipeline/prompts/README.md) for the mapping.

## Reproducibility

The full step-by-step reproduction recipe is in
[docs/reproducibility.md](docs/reproducibility.md). The verifier's behavior
and the vector-DB construction protocol are described in Section 4.2 of the
paper.

## Citation

Citation information will be added after review.

## License

MIT License — see [LICENSE](LICENSE). (c) Anonymous authors, 2026.