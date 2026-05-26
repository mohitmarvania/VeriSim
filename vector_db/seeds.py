"""Seed term lists per category for the VeriSim general UMLS subset."""

SYMPTOMS = [
    "chest pain", "shortness of breath", "abdominal pain", "headache", "nausea",
    "vomiting", "dizziness", "fatigue", "fever", "cough", "sore throat",
    "back pain", "dyspnea", "palpitations", "syncope", "weakness", "numbness",
    "tingling", "rash", "swelling", "sweating", "chills", "diaphoresis",
    "anxiety", "confusion", "blurred vision", "ringing in ears", "joint pain",
    "muscle pain", "leg pain", "arm pain", "neck pain", "jaw pain",
    "chest tightness", "chest pressure", "lightheadedness", "heart palpitations",
    "irregular heartbeat", "bloating", "constipation", "diarrhea", "heartburn",
    "indigestion", "loss of appetite", "weight loss", "weight gain", "insomnia",
    "depression", "hot flashes", "night sweats", "bruising", "bleeding",
    "dehydration", "dry mouth", "frequent urination", "painful urination",
    "itching", "hives", "hair loss", "memory loss", "difficulty swallowing",
    "hoarseness",
]

MEDICATIONS = [
    "acetaminophen", "ibuprofen", "aspirin", "metformin", "lisinopril",
    "amlodipine", "metoprolol", "atorvastatin", "simvastatin", "omeprazole",
    "pantoprazole", "levothyroxine", "albuterol", "hydrochlorothiazide",
    "losartan", "gabapentin", "sertraline", "fluoxetine", "citalopram",
    "trazodone", "alprazolam", "lorazepam", "clonazepam", "oxycodone",
    "hydrocodone", "tramadol", "morphine", "prednisone", "amoxicillin",
    "azithromycin", "ciprofloxacin", "doxycycline", "warfarin", "clopidogrel",
    "apixaban", "rivaroxaban", "insulin glargine", "insulin lispro",
    "metformin hydrochloride", "glipizide", "glimepiride", "sitagliptin",
    "empagliflozin", "furosemide", "spironolactone", "carvedilol",
    "propranolol", "diltiazem", "verapamil", "nitroglycerin", "isosorbide",
    "atenolol", "ramipril", "valsartan", "montelukast", "fluticasone",
    "tiotropium", "salbutamol", "prednisolone", "methylprednisolone",
    "ondansetron", "loperamide", "famotidine", "ranitidine", "escitalopram",
    "duloxetine", "venlafaxine", "bupropion", "mirtazapine", "quetiapine",
    "olanzapine", "risperidone", "aripiprazole", "lithium", "valproate",
    "lamotrigine", "levetiracetam", "topiramate", "phenytoin", "carbamazepine",
    "allopurinol", "colchicine", "methotrexate", "hydroxychloroquine",
]

PROCEDURES = [
    "cardiac catheterization", "coronary angiography",
    "percutaneous coronary intervention", "appendectomy", "cholecystectomy",
    "hysterectomy", "hip replacement", "knee replacement", "cesarean section",
    "colonoscopy", "endoscopy", "ECG", "echocardiogram", "CT scan", "MRI",
    "X-ray", "ultrasound", "biopsy", "intubation", "blood transfusion",
    "dialysis", "bone marrow biopsy", "lumbar puncture", "thoracentesis",
    "paracentesis", "cardioversion", "pacemaker insertion",
    "defibrillator insertion", "cataract surgery", "tonsillectomy",
    "mastectomy", "lumpectomy", "prostatectomy", "vasectomy", "tubal ligation",
    "liposuction", "gastric bypass", "sleeve gastrectomy", "hernia repair",
    "bypass surgery", "CABG", "angioplasty", "stent placement", "vaccination",
    "blood draw", "IV insertion", "catheter insertion", "wound debridement",
    "skin graft", "amputation", "laparoscopy",
]

CONDITIONS = [
    "type 2 diabetes", "type 1 diabetes", "hypertension", "hyperlipidemia",
    "coronary artery disease", "myocardial infarction", "heart failure",
    "atrial fibrillation", "COPD", "asthma", "pneumonia", "bronchitis",
    "gastritis", "GERD", "peptic ulcer disease", "irritable bowel syndrome",
    "inflammatory bowel disease", "Crohn's disease", "ulcerative colitis",
    "hepatitis", "cirrhosis", "chronic kidney disease", "acute kidney injury",
    "urinary tract infection", "pyelonephritis", "kidney stones",
    "benign prostatic hyperplasia", "hypothyroidism", "hyperthyroidism",
    "anemia", "iron deficiency anemia", "vitamin B12 deficiency",
    "osteoporosis", "osteoarthritis", "rheumatoid arthritis", "gout",
    "fibromyalgia", "migraine", "tension headache", "epilepsy", "stroke",
    "transient ischemic attack", "Parkinson disease", "Alzheimer disease",
    "dementia", "depression", "anxiety disorder", "bipolar disorder",
    "schizophrenia", "PTSD", "OCD", "ADHD", "autism spectrum disorder",
    "pregnancy", "breast cancer", "lung cancer", "colon cancer",
    "prostate cancer", "skin cancer", "melanoma", "lymphoma", "leukemia",
    "eczema", "psoriasis", "allergic rhinitis", "sinusitis", "otitis media",
    "conjunctivitis", "glaucoma", "cataracts", "macular degeneration",
    "deep vein thrombosis", "pulmonary embolism", "sepsis", "septic shock",
    "anaphylaxis", "cellulitis", "abscess", "MRSA infection", "influenza",
    "COVID-19", "RSV infection",
]


# UMLS source vocabularies we pull atoms from
EXTRACT_SABS = [
    "SNOMEDCT_US", "RXNORM", "ICD10CM", "CPT", "HCPCS", "MDR",
    "MSH", "NCI", "LNC",
]

# Acceptable TTYs per source vocab. Loose: keep lay/clinical synonyms broadly,
# only drop highly-technical or obvious non-synonym TTYs. Empty = keep all.
KEEP_TTYS = {
    "SNOMEDCT_US": {"FN", "PT", "SY", "PTGB", "SB"},
    "RXNORM": {"IN", "BN", "SCD", "SBD", "PIN", "SY", "TMSY",
               "SCDC", "SCDF", "SBDF", "SBDC", "SBDG", "MIN", "PSN"},
    "CPT": {"PT", "SY", "ETCF", "ETCLIN", "GLP"},
    "HCPCS": {"PT", "SY", "OAM", "OAS"},
    "ICD10CM": {"PT", "HT", "ET", "AB"},
    "MDR": {"PT", "LLT", "HT", "OS", "SMQ"},
    "MSH": {"MH", "ET", "PEP", "NM", "PM", "HT"},
    "NCI": {"PT", "SY", "DN", "AB", "AD", "FBD", "HD"},
    "LNC": {"LN", "LC", "LO", "LPN", "OSN", "CN"},
}

# Semantic type → category mapping for fallback classification
SEMTYPE_CATEGORY = {
    "T184": "symptom",   # Sign or Symptom
    "T033": "symptom",   # Finding
    "T046": "symptom",   # Pathologic Function
    "T200": "medication",  # Clinical Drug
    "T121": "medication",  # Pharmacologic Substance
    "T109": "medication",  # Organic Chemical
    "T060": "procedure",  # Diagnostic Procedure
    "T061": "procedure",  # Therapeutic or Preventive Procedure
    "T047": "condition",  # Disease or Syndrome
    "T191": "condition",  # Neoplastic Process
    "T019": "condition",  # Congenital Abnormality
    "T037": "condition",  # Injury or Poisoning
    "T048": "condition",  # Mental or Behavioral Dysfunction
}

# RELA labels we extract per category
SYMPTOM_RELAS = {
    "finding_site", "associated_morphology", "causative_agent", "severity",
    "due_to", "interprets", "pathological_process",
}
MEDICATION_RELAS = {
    "has_active_ingredient", "has_ingredient", "has_dose_form", "tradename_of",
    "has_tradename", "may_treat", "may_prevent", "has_disposition",
    "isa", "is_a",
}
PROCEDURE_RELAS = {
    "procedure_site", "procedure_site_direct", "procedure_site_indirect",
    "has_method", "method_of", "has_approach", "has_intent",
    "has_route_of_administration", "has_procedure_device", "has_specimen",
}
CONDITION_RELAS = SYMPTOM_RELAS | {"finding_site"}

RELAS_BY_CATEGORY = {
    "symptom": SYMPTOM_RELAS,
    "medication": MEDICATION_RELAS,
    "procedure": PROCEDURE_RELAS,
    "condition": CONDITION_RELAS,
}


def all_seeds() -> list[tuple[str, str]]:
    """Return [(term, category), ...] for every seed."""
    out: list[tuple[str, str]] = []
    for t in SYMPTOMS:
        out.append((t, "symptom"))
    for t in MEDICATIONS:
        out.append((t, "medication"))
    for t in PROCEDURES:
        out.append((t, "procedure"))
    for t in CONDITIONS:
        out.append((t, "condition"))
    return out


# preferred source per category for the initial /search resolution
SEARCH_SAB_BY_CATEGORY = {
    "symptom": ["SNOMEDCT_US"],
    "medication": ["RXNORM"],
    "procedure": ["SNOMEDCT_US", "CPT"],
    "condition": ["SNOMEDCT_US", "ICD10CM"],
}


# Phase B.4: broad keyword + semantic-type sweeps. Each tuple is
# (category, sabs, semantic_types, keywords). The /search endpoint requires
# a `string`; we use these high-coverage clinical keywords to pull thousands
# of CUIs filtered by semantic type.
SEMTYPE_SWEEPS = [
    ("symptom", ["SNOMEDCT_US", "MDR"], ["T184", "T033", "T046"], [
        "pain", "ache", "discomfort", "weakness", "numbness", "tingling",
        "fatigue", "swelling", "bleeding", "fever", "nausea", "dizziness",
        "rash", "itch", "cough", "feeling",
    ]),
    ("condition", ["SNOMEDCT_US", "ICD10CM"], ["T047", "T191", "T019", "T037", "T048"], [
        "disease", "disorder", "syndrome", "infection", "cancer", "tumor",
        "failure", "deficiency", "inflammation", "injury", "fracture",
        "ulcer", "abnormality", "neoplasm",
    ]),
    ("procedure", ["SNOMEDCT_US", "CPT"], ["T060", "T061"], [
        "surgery", "procedure", "biopsy", "imaging", "therapy", "treatment",
        "repair", "removal", "replacement", "examination", "scan", "test",
        "operation", "insertion",
    ]),
    ("medication", ["RXNORM", "SNOMEDCT_US"], ["T200", "T121", "T109", "T197"], [
        "tablet", "capsule", "injection", "inhibitor", "antibody",
        "antagonist", "agonist", "vaccine", "supplement", "antibiotic",
        "steroid", "antiviral", "analgesic",
    ]),
]
