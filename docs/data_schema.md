# Data schemas

All inputs and outputs are JSON. Schemas below are written informally
(JSON-Schema–ish) — fields marked optional may be omitted.

---

## 1. Patient profile (`data/dummy_patients/P*.json`)

```jsonc
{
  "patient_id":        "string, e.g. \"P001\"",
  "demographics":      { "age": "int", "sex": "\"M\" | \"F\"" },
  "chief_complaint":   "string",

  "symptoms":     [ {
    "text":     "string",                                   // lay-friendly name
    "cui":      "string, UMLS CUI (e.g. \"C0008031\")",
    "severity": "\"mild\" | \"moderate\" | \"severe\"",     // optional
    "onset":    "string, free-text (e.g. \"2 hours ago\")", // optional
    "duration": "string, free-text"                          // optional
  } ],

  "medications":  [ {
    "text":      "string",
    "cui":       "string",
    "dose":      "string",                                  // optional
    "frequency": "string (e.g. \"BID\", \"daily\")"          // optional
  } ],

  "conditions":   [ {
    "text":            "string",
    "cui":             "string",
    "diagnosed_year":  "int"                                // optional
  } ],

  "procedures":   [ {
    "text":        "string",
    "cui":         "string",
    "year":        "int",                                   // optional
    "indication":  "string"                                  // optional
  } ],

  "allergies":    [ {
    "text":     "string",
    "cui":      "string",
    "reaction": "string"                                    // optional
  } ],

  "noise_profile": [
    // Each patient is assigned exactly two of the six noise dimensions
    // defined in the paper (per the main quantitative evaluation protocol).
    // Severity levels are drawn from L1-L3; L0 (ideal) and L4 (extreme)
    // are reserved for ablation studies and qualitative stress-test examples.
    {
      "type":  "\"memory_recall\" | \"health_literacy\" | \"emotional_state\" | \"communication_style\" | \"cognitive_processing\" | \"social_cultural\"",
      "level": "int 0-4  (0 = no impairment, 4 = extreme)"
    },
    { "type": "...", "level": "..." }
  ]
}
```

---

## 2. Conversation trace (`examples/conversations/P*.json`)

```jsonc
{
  "patient_id": "string",
  "conversation": [
    {
      "turn":               "int (0-indexed)",
      "doctor":             "string — doctor's question",
      "patient_response":   "string — final-attempt utterance after any regenerations",
      "verifier_result": {
        "overall_verdict":      "\"PASS\" | \"REGENERATE\"",
        "claims":               [ "string", ... ],          // atomic claims extracted
        "claim_judgments":      [ {
          "claim":     "string",
          "verdict":   "\"PASS\" | \"FABRICATION\"",
          "reasoning": "string"
        } ],
        "feedback_to_generator": "string (empty when PASS)"
      },
      "regeneration_attempts": "int — total attempts including the successful one",
      "timing_s": { "doctor": "float", "patient+verifier": "float" }
    }
  ],
  "stats": {
    "turns":                          "int",
    "total_regenerations":            "int",
    "turns_with_caught_fabrication":  "int",
    "final_attempt_failures":         "int"
  }
}
```

The corresponding `*_debug.json` files (not shipped — see `.gitignore`)
contain every attempt with its full verifier output, retrieved evidence,
and per-call timings.

---

## 3. Verifier intermediate JSON (LLM call outputs)

### Call 1 — claim extraction

```jsonc
// model output (strict JSON, list of strings)
[
  "patient has chest pain",
  "patient takes a beta blocker"
]
```

### Call 2 — judgment

```jsonc
{
  "claim_judgments": [
    {
      "claim":     "string",
      "verdict":   "\"PASS\" | \"FABRICATION\",
      "reasoning": "string"
    }
  ],
  "overall_verdict":       "\"PASS\" | \"REGENERATE\"",
  "feedback_to_generator": "string (empty when PASS)"
}
```

The verifier uses similarity threshold **tau = 0.55**: claims whose
retrievals all fall below this threshold are treated as underspecified
(e.g., "I feel weird") and default to **PASS**, since they assert no
verifiable medical content. Atoms in the index carry an `is_in_history`
flag and a `patient_id` so that the judge can distinguish general UMLS
evidence from patient-specific ground truth.

---

## 4. Vector-DB atom record (`umls_metadata.jsonl`)

One JSON object per line, parallel to FAISS rows by index.

```jsonc
{
  "atom_id":         "int (= FAISS row id)",
  "text":            "string (the surface form that was embedded)",
  "parent_cui":      "string (UMLS CUI this atom belongs to)",
  "parent_label":    "string (preferred name of the CUI)",
  "source_aui":      "string (UMLS atom UI)",
  "source_code":     "string (source-vocab code)",
  "source_vocab":    "\"SNOMEDCT_US\" | \"RXNORM\" | \"ICD10CM\" | \"CPT\" | \"HCPCS\" | \"MDR\" | \"MSH\" | \"NCI\" | \"LNC\" | \"PATIENT_PROFILE\"",
  "tty":             "string (UMLS term type, e.g. \"PT\", \"SY\", \"FN\")",
  "category":        "\"symptom\" | \"medication\" | \"procedure\" | \"condition\" | \"allergy\"",
  "is_in_history":   "bool",
  "patient_id":      "string | null  (set iff is_in_history is true)",
  "from_expansion":  "bool",
  "umls_metadata":   { "finding_site": ["..."], "ingredient": ["..."], "...": "..." },
  "duplicate_count": "int (how many raw atoms collapsed onto this surface form)"
}
```
