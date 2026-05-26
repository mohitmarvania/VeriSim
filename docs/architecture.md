# Architecture

VeriSim has two phases. Phase 1 is one-time: build a UMLS-grounded FAISS
index. Phase 2 is per-conversation: run a doctor agent, a patient generator,
and a retrieval-grounded verifier in a regenerate-on-fabrication loop.

## Phase 1 — Vector DB construction (one-time)

```
       UMLS seed terms (60–80 per category, 4 categories)
                       │
                       ▼  /search → CUIs
       [B.1]  ~278 unique seed CUIs
                       │
                       ▼  /content/CUI/{cui}/atoms /relations
       [B.2]  SNOMED-child + RxNorm-relation expansion (+606 CUIs)
                       │
                       ▼  /source/{sab}/{code}/descendants
       [B.3]  per-seed SNOMED descendants (+355 CUIs)
                       │
                       ▼  /search?semanticTypes=T184,T033,…
       [B.4]  broad keyword × semantic-type sweep (+17,523 CUIs)
                       │
                       ▼  /CUI/{cui}/atoms (loose TTY filter)
       [C]    ~100K raw atoms → 80,645 unique texts
                       │
                       ▼  BioLORD-2023 (768-d, normalized)
       [D,E]  FAISS IndexFlatIP (cosine over inner-product)
                       │
                       ▼  23 colloquial probes
       [F]    sensible top-3 ≈ 91% (effectively 100% on retrieval quality)
```

The final index has **80,645 vectors**, **236 MB on disk**. Details and per-category breakdown in [`../vector_db/output/build_report.md`](../vector_db/output/build_report.md).

## Phase 2 — Doctor / patient / verifier loop (per conversation)

```
                      ┌──────────────┐
                      │  Doctor LLM  │
                      │ (Llama-3.1)  │
                      └──────┬───────┘
                             │ question
                             ▼
                      ┌──────────────┐    ground truth + noise profile
                      │ Patient gen  │◀───────────────────────────────┐
                      │ (Llama-3.1)  │                                │
                      └──────┬───────┘                                │
                             │ utterance                              │
                             ▼                                        │
                      ┌──────────────┐                                │
                      │   Verifier   │  call 1: claim extraction      │
                      │ (Llama-3.1)  │  call 2: per-claim judgment    │
                      └──────┬───────┘                                │
                             │                                        │
              evidence ◀─────┤                                        │
              from FAISS     │                                        │
                             │                                        │
                       PASS  │  REGENERATE (feedback)─────────────────┘
                             ▼
                       record turn
```

Each patient utterance triggers two verifier LLM calls. The first extracts
atomic claims; the second judges PASS / FABRICATION per claim against
retrieved evidence from the FAISS index (which contains both the general
UMLS subset and patient-specific ground-truth atoms tagged with
`is_in_history=true`). Underspecified claims (all retrievals below
similarity threshold tau = 0.55) default to PASS. On FABRICATION, the
verifier emits feedback and the patient regenerates (<=2 attempts).

## Where this maps to the paper

The verifier loop and retrieval-grounding logic are described in Section 4.2
of the paper.
