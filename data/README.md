# Data

## Patient profiles

`dummy_patients/P00{1..5}.json` are 5 synthetic patient profiles used to
validate the pipeline. They were authored by hand to exercise diverse
clinical scenarios and noise profiles:

| Patient | Scenario                                            | Noise profile                                                    |
|---------|-----------------------------------------------------|------------------------------------------------------------------|
| P001    | 58 M, acute chest pain, known CAD                   | health_literacy=2, anxious, rambling, moderate slang, coop=4     |
| P002    | 24 F, asthma exacerbation                           | health_literacy=4, calm, terse, no slang, coop=5                 |
| P003    | 82 F, confusion + multiple comorbidities            | health_literacy=1, confused, rambling, no slang, coop=3          |
| P004    | 46 M, severe upper abdominal pain, PUD/GERD history | health_literacy=2, frustrated, normal, heavy slang, coop=3       |
| P005    | 27 M, depression + GAD                              | health_literacy=3, frustrated, terse, moderate slang, coop=2     |

Each file follows the schema in [`../docs/data_schema.md`](../docs/data_schema.md).

## Sources and licensing

- **CUIs**: every concept reference uses a UMLS Concept Unique Identifier
  (CUI). UMLS itself is released under the
  [UMLS Metathesaurus License](https://www.nlm.nih.gov/research/umls/knowledge_sources/metathesaurus/index.html);
  the CUIs themselves are non-proprietary identifiers but downloading atoms
  via the REST API requires a free UMLS license.
- **Patient data**: the 5 profiles in this directory are entirely
  **synthetic**, hand-authored for testing. They contain no real-patient
  information and are not derived from any clinical dataset.
- **No real PHI** is ever ingested by the pipeline.

## Adding your own patients

Drop additional `P*.json` files into `dummy_patients/` and update
`pipeline/main.py` to enumerate them. The patient-atom-injection step
(`VectorDB.add_patient_atoms`) is in-memory only — your patient atoms are
never written to disk and the on-disk FAISS index is never modified.
