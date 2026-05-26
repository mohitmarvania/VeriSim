# Reproducibility

## Hardware requirements

| Component                  | Minimum                                    | Notes                                                                 |
|---------------------------|--------------------------------------------|----------------------------------------------------------------------|
| Vector DB build           | 1× A100 80 GB (or 1× any 24 GB GPU)        | GPU is needed only for the BioLORD encoder; FAISS index is CPU.       |
| Pipeline (Llama-3.1-70B)  | 1× A100 80 GB (4-bit) or 2× A100 80 GB (fp16) | 4-bit `bitsandbytes` fits the 70B model on a single 80 GB card.       |
| Pipeline (Llama-3.1-8B)   | 1× A100 40 GB                              | If you want a faster validation pass, swap the model name.            |
| Disk                      | ~250 GB                                    | 132 GB for the 70B weights + ~30 GB for HF/UMLS cache + outputs.      |
| CUDA driver               | ≥ 12.6                                     | See **Known issues** below.                                            |

## Estimated wall-clock times (1× A100 80 GB)

| Step                                          | Time (observed)       |
|-----------------------------------------------|-----------------------|
| Vector DB build (Phases B–F, all phases)      | ~1 h 09 min           |
| ↳ Phase B (seed resolve + expansion)          | ~2 min                |
| ↳ Phase C (atoms+relations, ~18.7K CUIs)      | ~66 min               |
| ↳ Phase D–F (embed + FAISS + verify)          | ~1 min                |
| Llama-3.1-70B-Instruct weight download (HF)   | ~4 min                |
| Llama-3.1-70B load in 4-bit (transformers)    | ~3 min                |
| One conversation (8 turns)                    | ~8–11 min             |
| Full validation (5 patients × 8 turns)        | ~50 min               |

## Step-by-step

### 1. Install requirements

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu126
```

Verify CUDA is visible:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### 2. Register UMLS + set API key

Register at https://uts.nlm.nih.gov/uts/ and obtain an API key. Then:

```bash
cp .env.example .env
# edit .env to add UMLS_API_KEY and HF_TOKEN
source .env
export UMLS_API_KEY HF_TOKEN HF_HOME
```

### 3. Build the vector DB (~1 h on 1× A100)

```bash
cd vector_db/
python build_vector_db.py --phase all
```

On a SLURM cluster, submit instead via `sbatch slurm/run_build.sh` (the
script assumes `--account=<SLURM_ACCOUNT>` and `--qos=gpu`; edit to match
your scheduler).

Outputs land in `vector_db/output/`:

- `umls_atoms.faiss`     (~236 MB, IndexFlatIP, 768-d)
- `umls_metadata.jsonl`  (parallel metadata, one record per FAISS row)
- `umls_atoms.jsonl`     (raw extracted atoms, pre-dedup)
- `embeddings.npy`       (the float32 matrix that built the index)
- `build_report.md`

### 4. Prepare patient JSONs

The repo ships 5 sample profiles in `data/dummy_patients/`. Each is a single
JSON with five medical-entity sections (symptoms, medications, conditions,
procedures, allergies) and a `noise_profile` object. See
[`data_schema.md`](data_schema.md) for the schema. To add your own patients,
drop additional `P*.json` files into `data/dummy_patients/` and modify
`pipeline/main.py` to enumerate them (or aggregate into one list file).

### 5. Run the pipeline (~10 min per patient on 1× A100)

```bash
cd pipeline/
python main.py
```

On SLURM: `sbatch slurm/run_pipeline.sh`.

Outputs:

- `pipeline/output/test_results.md`  — aggregate stats + sample exchanges
- `pipeline/../conversations/P00X.json` — final per-patient trace
- `pipeline/../conversations/P00X_debug.json` — every regeneration attempt with full verifier output

## Known issues

1. **CUDA-13 wheel trap.** The default `pip install torch` and
   `pip install vllm` pull CUDA-13 wheels which fail with
   `RuntimeError: The NVIDIA driver on your system is too old (found
   version 12060)` on hosts with the 12.6 driver. The requirements file pins
   `torch==2.6.0+cu126`; install with the
   `--extra-index-url https://download.pytorch.org/whl/cu126` flag as shown
   above.

2. **vLLM 0.21 incompatibility on CUDA-12.6.** Even with `torch+cu126`,
   vLLM 0.21 fails on import with `libcudart.so.13: cannot open shared
   object file` because it bundles CUDA-13 native libs. Downgrading vLLM
   below 0.10 to support CUDA-12 requires building xformers from source and
   currently fails because torch isn't visible at xformers' build step.
   The pipeline therefore defaults to `transformers + bitsandbytes` 4-bit
   inference (`backend="transformers"`); the vLLM code path is preserved in
   `pipeline/llm_engine.py` and works once a compatible CUDA driver is
   available.

3. **`accelerate` is a hard dep of `transformers` for `device_map="auto"`.**
   The first run-through missed this — `accelerate==1.13.0` is now in
   `requirements.txt`.

4. **Stat counter bug in `Orchestrator._compute_stats` — fixed.** The
   original implementation only inspected the *final* `verifier_result` per
   turn, so any FABRICATION that was caught on attempt 0 and then PASSed
   on attempt 1 was reported as 0 caught. The fix scans every attempt in the
   per-turn debug trace; see the relevant code in
   `pipeline/orchestrator.py`. The 5-patient validation run actually caught
   3 fabrications + 1 underspecified-claim regeneration (legacy VAGUE
   verdict from the pilot's three-way scheme; under the current binary scheme
   such underspecified claims default to PASS) -> all corrected on the
   regen pass.
