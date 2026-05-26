# VeriSim Vector DB Build Report

## Summary
- Total atoms extracted: 100135
- Unique texts embedded: 80645
- Total vectors in FAISS: 80645
- FAISS index size: 236.3 MB
- Embeddings size: 236.3 MB
- Total build time: 1:08:44
- UMLS API calls: 53285  (cache hits: 8217)
- Test query sensible top-3: 91%

## Phase Timing
- B (resolve+expand seeds): 105.4s
- C (atoms+relations): 3966.5s
- D (embedding): 49.3s
- E (FAISS index): 1.1s
- F (verification): 2.1s

## Per-Category Breakdown
| Category | Seed CUIs (incl. expansions) | Atoms extracted | After dedup |
|---|---|---|---|
| symptom | 2380 | 9438 | 7624 |
| medication | 2358 | 7068 | 6286 |
| procedure | 6921 | 23452 | 20962 |
| condition | 7103 | 60177 | 45773 |

## Sample atoms (5 random per category)
### symptom
- `Acute cough (finding)` (SNOMEDCT_US/FN, CUI=C0742857)
- `Number of pads used (observable entity)` (SNOMEDCT_US/FN, CUI=C0425950)
- `Spiking temperature` (MDR/LLT, CUI=C0424781)
- `Feeling of suffocation` (SNOMEDCT_US/SY, CUI=C0546947)
- `Central muscle fatigue (finding)` (SNOMEDCT_US/FN, CUI=C0231523)
### medication
- `Alprazolam 250 microgram oral tablet` (SNOMEDCT_US/PT, CUI=C0974159)
- `Phosphodiesterase V Inhibitor` (NCI/SY, CUI=C1318700)
- `Adrenergic beta-1 Receptor Blockers` (MSH/ET, CUI=C0304516)
- `Interleukin 23 receptor antagonist-containing product` (SNOMEDCT_US/PT, CUI=C4722042)
- `Entry Inhibitors, HIV` (MSH/PM, CUI=C1449715)
### procedure
- `Microsurgical repair vein (procedure)` (SNOMEDCT_US/FN, CUI=C0398167)
- `Echography of abdomen, B-scan, limited (procedure)` (SNOMEDCT_US/FN, CUI=C0203465)
- `Removal of vein segment` (CPT/ETCF, CUI=C5693898)
- `Operative procedure on hip joint` (SNOMEDCT_US/SY, CUI=C0186081)
- `Aversion therapy - behavior correction (regime/therapy)` (SNOMEDCT_US/FN, CUI=C0004415)
### condition
- `Inflammation of vulva (disorder)` (SNOMEDCT_US/FN, CUI=C0042996)
- `Iron Storage Disorders` (MSH/PM, CUI=C0018995)
- `Cerebellar deficiency syndrome (disorder)` (SNOMEDCT_US/FN, CUI=C5979809)
- `Disease of female genital system` (SNOMEDCT_US/SY, CUI=C0017411)
- `Glycogen Storage Disease 1 (GSD I)` (MSH/ET, CUI=C0017920)

## Test Query Results Summary
Full details in `test_results.md`. Sensible top-3 heuristic: 91%.