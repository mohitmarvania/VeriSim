# Vector DB build

Phase 1 of VeriSim: build a UMLS-grounded FAISS index that the runtime
verifier searches against.

## What it does

1. **Phase B.1** — resolve ~278 curated ED-presenting seed terms to UMLS CUIs via `/search`.
2. **Phase B.2** — expand each seed by pulling immediate SNOMED children and RxNorm relations (ingredients, brand names, etc.).
3. **Phase B.3** — for each original SNOMED-rooted seed, pull its transitive `/descendants`.
4. **Phase B.4** — broad keyword × semantic-type sweep over the SNOMED+RxNorm vocabularies (this is the high-yield step — adds ~17K CUIs).
5. **Phase C** — for every CUI, pull cross-vocab atoms (SNOMED, RxNorm, ICD-10-CM, CPT, HCPCS, MDR, MSH, NCI, LNC) and relations, filter by `suppressible/obsolete`, apply a permissive TTY allowlist.
6. **Phase D** — embed unique atom texts with [BioLORD-2023](https://huggingface.co/FremyCompany/BioLORD-2023) (768-d, L2-normalized for cosine-as-inner-product).
7. **Phase E** — build a FAISS `IndexFlatIP`.
8. **Phase F** — run 23 colloquial probe queries and produce `test_results.md`.

Our reference build (see `output/build_report.md`) yields **80,645 unique
vectors** (236 MB on disk) across 18,762 unique CUIs.

## How to run

```bash
export UMLS_API_KEY="<your-umls-api-key>"
python build_vector_db.py --phase all                # full pipeline
# or run a single phase against existing cache:
python build_vector_db.py --phase C
```

The script caches every UMLS REST response on disk in `cache/` (hashed by
URL), so re-runs are essentially free for the API portion.

## SLURM submission

```bash
sbatch slurm/run_build.sh
```

Edit `slurm/run_build.sh` to set `--account=<SLURM_ACCOUNT>` and the
appropriate `--partition` / `--gres` lines for your cluster.

## Files in this directory

| Path                                 | Purpose                                                                  |
|--------------------------------------|--------------------------------------------------------------------------|
| `build_vector_db.py`                 | Main pipeline (`--phase all|B|C|D|E|F`).                                  |
| `umls_client.py`                     | UMLS REST API client (cache, tenacity retries, defensive pagination).    |
| `seeds.py`                           | Curated ED-presenting seed lists (Phase B.1).                            |
| `seed_concepts/`                     | The expanded CUI sets per category from our reference run.               |
| `slurm/run_build.sh`                 | SLURM submission script (A100 80 GB, 4 hours).                            |
| `output/build_report.md`             | Per-category breakdown, timings, and sample atoms from our run.          |
