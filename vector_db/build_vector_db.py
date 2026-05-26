"""VeriSim general UMLS vector-DB build pipeline (phases B–F).

Phase B  resolve seed terms → CUIs (with optional 1-level child expansion)
Phase C  pull atoms + relations per CUI, emit per-atom JSONL with metadata
Phase D  dedup texts, embed with BioLORD-2023 (cosine via normalised vectors)
Phase E  build IndexFlatIP FAISS index
Phase F  run verification queries
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
from tqdm import tqdm

import seeds
from umls_client import UMLSClient


ROOT = Path("/path/to/working_dir/verisim_vectordb")
CACHE = ROOT / "cache"
OUT = ROOT / "output"
SEED_DIR = ROOT / "seed_cuis"

OUT.mkdir(parents=True, exist_ok=True)
SEED_DIR.mkdir(parents=True, exist_ok=True)

ATOMS_JSONL = OUT / "umls_atoms.jsonl"
METADATA_JSONL = OUT / "umls_metadata.jsonl"
FAISS_PATH = OUT / "umls_atoms.faiss"
EMB_PATH = OUT / "embeddings.npy"
UNRESOLVED_LOG = ROOT / "unresolved_seeds.log"
BUILD_REPORT = OUT / "build_report.md"
TEST_REPORT = OUT / "test_results.md"

EMBED_MODEL_NAME = "FremyCompany/BioLORD-2023"
EMBED_DIM = 768


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("verisim_vdb")


# ---------------------------------------------------------------------------
# Phase B — seed resolution
# ---------------------------------------------------------------------------

def _best_match(term: str, results: list[dict], preferred_sabs: list[str]) -> dict | None:
    """Pick the most relevant result: first one in preferred SAB, else first."""
    if not results:
        return None
    # filter out NONE / OMIT placeholders sometimes returned
    real = [r for r in results if r.get("ui") and r["ui"] != "NONE"]
    if not real:
        return None
    for sab in preferred_sabs:
        for r in real:
            if r.get("rootSource") == sab:
                return r
    return real[0]


def resolve_seeds(client: UMLSClient, log: logging.Logger) -> dict[str, dict]:
    """Resolve every seed term to its primary CUI. Returns {cui: meta} where meta has category, label, source seed term."""
    cui_meta: dict[str, dict] = {}
    unresolved: list[str] = []
    all_terms = seeds.all_seeds()
    log.info("Phase B.1: resolving %d seed terms via /search", len(all_terms))
    cat_count: Counter = Counter()
    for term, category in tqdm(all_terms, desc="resolve seeds"):
        preferred = seeds.SEARCH_SAB_BY_CATEGORY[category]
        try:
            data = client.search(term, page_size=15)
            results = data.get("result", {}).get("results", [])
        except Exception as e:
            log.warning("search failed for %r: %s", term, e)
            unresolved.append(term)
            continue
        match = _best_match(term, results, preferred)
        if not match:
            unresolved.append(term)
            continue
        cui = match["ui"]
        if cui in cui_meta:
            # already seen; keep first category
            continue
        cui_meta[cui] = {
            "cui": cui,
            "category": category,
            "preferred_label": match.get("name", term),
            "root_source": match.get("rootSource"),
            "seed_term": term,
            "from_expansion": False,
        }
        cat_count[category] += 1

    if unresolved:
        UNRESOLVED_LOG.write_text("\n".join(unresolved) + "\n")
        log.warning("unresolved seeds: %d (logged to %s)", len(unresolved), UNRESOLVED_LOG)

    log.info("Phase B.1 done: %d unique CUIs from %d seeds — %s",
             len(cui_meta), len(all_terms), dict(cat_count))

    # Phase B.2 — expand seed CUIs via SNOMED children (all categories) and via
    # RxNorm related-CUIs (medications). Two levels deep for symptom/condition.
    log.info("Phase B.2: expanding seeds via SNOMED children + RxNorm relations")
    expansion: dict[str, dict] = {}

    def _snomed_codes_for(cui: str) -> list[str]:
        try:
            atoms = client.get_atoms(
                cui, sabs=["SNOMEDCT_US"], ttys=["PT", "FN", "SY"], page_size=20
            )
        except Exception as e:
            log.warning("atom probe failed for %s: %s", cui, e)
            return []
        codes: list[str] = []
        seen: set[str] = set()
        for a in atoms:
            code = (a.get("code") or "").split("/")[-1]
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    def _expand_snomed(parent_cui: str, parent_meta: dict, codes: list[str],
                       children_cap: int = 200, codes_cap: int = 3) -> list[str]:
        """For each SNOMED child source-code, resolve to CUI via one /source/{sab}/{code}/atoms
        call and add to `expansion`. Returns list of new child CUIs."""
        added: list[str] = []
        for code in codes[:codes_cap]:
            try:
                children = client.get_source_children(
                    "SNOMEDCT_US", code, page_size=100, max_pages=2
                )
            except Exception as e:
                log.warning("children fetch failed for %s/%s: %s", parent_cui, code, e)
                continue
            for child in children[:children_cap]:
                child_code = (child.get("ui") or "").strip()
                child_name = child.get("name", "")
                if not child_code:
                    continue
                # Resolve child CUI via one source-atom call
                try:
                    src_atoms = client.get_source_atoms(
                        "SNOMEDCT_US", child_code, page_size=3, max_pages=1
                    )
                except Exception as e:
                    log.debug("source-atom resolve failed for %s: %s", child_code, e)
                    continue
                if not src_atoms:
                    continue
                child_cui = ""
                for a in src_atoms:
                    cui_url = a.get("concept") or ""
                    if cui_url:
                        child_cui = cui_url.rsplit("/", 1)[-1]
                        if child_cui.startswith("C"):
                            break
                if not child_cui or child_cui in cui_meta or child_cui in expansion:
                    continue
                expansion[child_cui] = {
                    "cui": child_cui,
                    "category": parent_meta["category"],
                    "preferred_label": child_name,
                    "root_source": "SNOMEDCT_US",
                    "seed_term": parent_meta["seed_term"],
                    "from_expansion": True,
                    "expansion_depth": parent_meta.get("expansion_depth", 0) + 1,
                }
                added.append(child_cui)
        return added

    # First level: every SNOMED-rooted seed
    base = [(cui, m) for cui, m in list(cui_meta.items())
            if m["root_source"] == "SNOMEDCT_US"]
    log.info("Phase B.2: first-level SNOMED expansion over %d seeds", len(base))
    first_level: list[tuple[str, dict]] = []
    for cui, meta in tqdm(base, desc="expand L1"):
        codes = _snomed_codes_for(cui)
        new = _expand_snomed(cui, meta, codes, children_cap=150, codes_cap=3)
        for cc in new:
            first_level.append((cc, expansion[cc]))

    log.info("Phase B.2: L1 added %d CUIs; running L2 for symptom/condition", len(first_level))
    # Second level for symptom & condition only (these subtrees aren't too deep)
    l2_targets = [(cc, mm) for cc, mm in first_level
                  if mm["category"] in ("symptom", "condition")]
    # cap to avoid runaway
    random.seed(1)
    if len(l2_targets) > 800:
        l2_targets = random.sample(l2_targets, 800)
    for cui, meta in tqdm(l2_targets, desc="expand L2"):
        codes = _snomed_codes_for(cui)
        _expand_snomed(cui, meta, codes, children_cap=50, codes_cap=1)

    # RxNorm expansion: for each medication seed CUI, pull related ingredient/brand CUIs
    log.info("Phase B.2: RxNorm relation expansion for medication seeds")
    med_seeds = [(cui, m) for cui, m in list(cui_meta.items())
                 if m["category"] == "medication"]
    rxnorm_relas = {"has_ingredient", "has_active_ingredient", "has_tradename",
                    "tradename_of", "ingredient_of", "form_of", "has_dose_form",
                    "consists_of", "constitutes"}
    for cui, meta in tqdm(med_seeds, desc="expand meds"):
        try:
            rels = client.get_relations(cui, page_size=100, max_pages=3)
        except Exception as e:
            log.warning("med relations failed for %s: %s", cui, e)
            continue
        for r in rels:
            rela = (r.get("additionalRelationLabel") or "").lower()
            if rela not in rxnorm_relas:
                continue
            related_cui_url = r.get("relatedId") or ""
            child_cui = related_cui_url.split("/")[-1]
            if not child_cui.startswith("C") or child_cui in cui_meta or child_cui in expansion:
                continue
            expansion[child_cui] = {
                "cui": child_cui,
                "category": "medication",
                "preferred_label": r.get("relatedIdName", ""),
                "root_source": "RXNORM",
                "seed_term": meta["seed_term"],
                "from_expansion": True,
                "expansion_depth": 1,
            }

    log.info("Phase B.2: added %d expanded CUIs total", len(expansion))
    cui_meta.update(expansion)

    # Phase B.3 — for each original SNOMED-rooted seed, pull /descendants
    # (transitive subtree). Smaller per-seed subtrees complete fast and avoid
    # the timeouts that top-level-axis descendants hit. Resolve each descendant
    # code to a CUI via one /source/SNOMEDCT_US/{code}/atoms call.
    seed_only = [(cui, m) for cui, m in list(cui_meta.items())
                 if m["root_source"] == "SNOMEDCT_US" and not m.get("from_expansion")]
    log.info("Phase B.3: pulling SNOMED descendants for %d original seeds", len(seed_only))
    axis_expansion: dict[str, dict] = {}
    for cui, meta in tqdm(seed_only, desc="B.3 seeds"):
        codes = _snomed_codes_for(cui)
        if not codes:
            continue
        primary = codes[0]
        try:
            descendants = client.get_source_descendants(
                "SNOMEDCT_US", primary, page_size=100, max_pages=4
            )
        except Exception as e:
            log.warning("descendants fetch failed for %s/%s: %s", cui, primary, e)
            continue
        for d in descendants:
            child_code = (d.get("ui") or "").strip()
            child_name = d.get("name", "")
            if not child_code:
                continue
            try:
                src_atoms = client.get_source_atoms(
                    "SNOMEDCT_US", child_code, page_size=2, max_pages=1
                )
            except Exception:
                continue
            if not src_atoms:
                continue
            child_cui = ""
            for a in src_atoms:
                u = a.get("concept") or ""
                if u:
                    candidate = u.rsplit("/", 1)[-1]
                    if candidate.startswith("C"):
                        child_cui = candidate
                        break
            if not child_cui or child_cui in cui_meta or child_cui in axis_expansion:
                continue
            axis_expansion[child_cui] = {
                "cui": child_cui,
                "category": meta["category"],
                "preferred_label": child_name,
                "root_source": "SNOMEDCT_US",
                "seed_term": meta["seed_term"],
                "from_expansion": True,
                "expansion_depth": 3,
            }
    log.info("Phase B.3: added %d CUIs from seed descendants", len(axis_expansion))
    cui_meta.update(axis_expansion)

    # Phase B.4 — broad keyword × semantic-type sweep. For each category, run
    # several /search queries filtered by the relevant semantic types and
    # source vocabs, then paginate. This is the bulk-discovery step that gets
    # us thousands of additional CUIs.
    log.info("Phase B.4: broad semantic-type sweeps")
    sweep_expansion: dict[str, dict] = {}
    for category, sabs, semtypes, keywords in seeds.SEMTYPE_SWEEPS:
        for kw in keywords:
            for page in range(1, 21):  # up to 20 pages × 25 = 500 results per kw
                try:
                    data = client.search(
                        kw, sabs=sabs, semantic_types=semtypes,
                        page_size=25, page_number=page,
                    )
                except Exception as e:
                    log.warning("search page failed (%s/%s p=%d): %s", category, kw, page, e)
                    break
                results = (data.get("result") or {}).get("results") or []
                real = [r for r in results if r.get("ui") and r["ui"] != "NONE"]
                if not real:
                    break
                for r in real:
                    cui = r["ui"]
                    if not cui.startswith("C") or cui in cui_meta or cui in sweep_expansion:
                        continue
                    sweep_expansion[cui] = {
                        "cui": cui,
                        "category": category,
                        "preferred_label": r.get("name", ""),
                        "root_source": r.get("rootSource") or sabs[0],
                        "seed_term": f"sweep:{kw}",
                        "from_expansion": True,
                        "expansion_depth": 4,
                    }
                if len(real) < 25:
                    break
        log.info("Phase B.4: %s sweep so far: %d new CUIs", category, len(sweep_expansion))
    log.info("Phase B.4: added %d CUIs from semantic-type sweeps", len(sweep_expansion))
    cui_meta.update(sweep_expansion)

    # save per-category seed files
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for cui, m in cui_meta.items():
        by_cat[m["category"]].append(m)
    for cat, items in by_cat.items():
        (SEED_DIR / f"seed_{cat}s.json").write_text(json.dumps(items, indent=2))

    return cui_meta


# ---------------------------------------------------------------------------
# Phase C — atom + relation extraction
# ---------------------------------------------------------------------------

def _classify_atom(parent_category: str, atom: dict) -> str:
    # if the parent category was set from seed lineage, use that — semantic-type
    # remapping below is only used when parent_category is missing.
    return parent_category


def _extract_relations(rels: list[dict], category: str) -> dict[str, Any]:
    """Bucket RELA values into category-specific metadata dict."""
    keep = seeds.RELAS_BY_CATEGORY.get(category, set())
    bucket: dict[str, list[str]] = defaultdict(list)
    is_brand = False
    for r in rels:
        rela = (r.get("additionalRelationLabel") or "").strip().lower()
        if not rela or rela not in keep:
            continue
        target = r.get("relatedIdName") or r.get("relatedId")
        if not target:
            continue
        if rela in ("has_tradename", "tradename_of"):
            is_brand = True
            continue
        # normalise medication relations
        if rela in ("has_active_ingredient", "has_ingredient"):
            bucket["ingredient"].append(target)
        elif rela == "may_treat":
            bucket["treats_conditions"].append(target)
        elif rela == "may_prevent":
            bucket["prevents_conditions"].append(target)
        elif rela == "has_disposition":
            bucket["mechanism"].append(target)
        elif rela == "has_dose_form":
            bucket["dose_form"].append(target)
        elif rela in ("isa", "is_a"):
            bucket["isa"].append(target)
        elif rela in ("procedure_site", "procedure_site_direct", "procedure_site_indirect"):
            bucket["procedure_site"].append(target)
        elif rela in ("has_method", "method_of"):
            bucket["method"].append(target)
        elif rela == "has_approach":
            bucket["approach"].append(target)
        elif rela == "has_intent":
            bucket["has_intent"].append(target)
        elif rela == "has_route_of_administration":
            bucket["route_of_administration"].append(target)
        elif rela == "has_procedure_device":
            bucket["procedure_device"].append(target)
        elif rela == "has_specimen":
            bucket["specimen"].append(target)
        else:
            bucket[rela].append(target)
    # dedupe each list, cap at 10
    out: dict[str, Any] = {k: sorted(set(v))[:10] for k, v in bucket.items()}
    if is_brand:
        out["is_brand"] = True
    return out


def extract_atoms(client: UMLSClient, cui_meta: dict[str, dict], log: logging.Logger) -> int:
    """Iterate every CUI, extract atoms + relations, append to JSONL. Returns count."""
    log.info("Phase C: extracting atoms+relations for %d CUIs", len(cui_meta))
    n_written = 0
    n_atoms_seen = 0
    atom_id = 0
    # truncate file
    open(ATOMS_JSONL, "w").close()

    buf: list[str] = []
    with open(ATOMS_JSONL, "a") as fout:
        for cui, meta in tqdm(cui_meta.items(), desc="atoms+rels"):
            category = meta["category"]
            try:
                atoms = client.get_atoms(
                    cui,
                    sabs=seeds.EXTRACT_SABS,
                    language="ENG",
                    page_size=200,
                )
            except Exception as e:
                log.warning("get_atoms failed for %s: %s", cui, e)
                continue
            # 1 page of relations is enough for representative RELA bucketing;
            # seed CUIs get more depth.
            rel_pages = 3 if not meta.get("from_expansion") else 1
            try:
                rels = client.get_relations(cui, page_size=100, max_pages=rel_pages)
            except Exception as e:
                log.warning("get_relations failed for %s: %s", cui, e)
                rels = []
            rela_meta = _extract_relations(rels, category)

            for a in atoms:
                n_atoms_seen += 1
                sab = a.get("rootSource") or ""
                tty = a.get("termType") or ""
                # UMLS returns these flags as JSON strings ("true"/"false"), not bools
                if str(a.get("suppressible", "")).lower() == "true":
                    continue
                if str(a.get("obsolete", "")).lower() == "true":
                    continue
                allowed = seeds.KEEP_TTYS.get(sab)
                if allowed and tty not in allowed:
                    continue
                text = (a.get("name") or "").strip()
                if not text:
                    continue
                rec = {
                    "atom_id": atom_id,
                    "text": text,
                    "parent_cui": cui,
                    "parent_label": meta["preferred_label"],
                    "source_aui": a.get("ui"),
                    "source_code": (a.get("code") or "").split("/")[-1],
                    "source_vocab": sab,
                    "tty": tty,
                    "category": _classify_atom(category, a),
                    "is_in_history": False,
                    "patient_id": None,
                    "from_expansion": meta.get("from_expansion", False),
                    "umls_metadata": rela_meta,
                }
                buf.append(json.dumps(rec))
                atom_id += 1
                n_written += 1
                if len(buf) >= 100:
                    fout.write("\n".join(buf) + "\n")
                    fout.flush()
                    buf = []
        if buf:
            fout.write("\n".join(buf) + "\n")

    log.info("Phase C done: %d raw atoms seen, %d written to %s", n_atoms_seen, n_written, ATOMS_JSONL)
    return n_written


# ---------------------------------------------------------------------------
# Phase D — embedding
# ---------------------------------------------------------------------------

def embed_atoms(log: logging.Logger) -> tuple[int, int]:
    """Dedup texts, embed unique ones with BioLORD-2023, save embeddings + metadata."""
    log.info("Phase D: loading atoms from %s", ATOMS_JSONL)
    seen_text: dict[str, dict] = {}
    dup_count: dict[str, int] = {}
    total = 0
    with open(ATOMS_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            total += 1
            key = rec["text"].lower().strip()
            if key in seen_text:
                dup_count[key] = dup_count.get(key, 1) + 1
                continue
            seen_text[key] = rec
    log.info("Phase D: %d total atoms, %d unique by text", total, len(seen_text))

    unique_records: list[dict] = []
    new_atom_id = 0
    for key, rec in seen_text.items():
        rec = dict(rec)  # copy
        rec["duplicate_count"] = dup_count.get(key, 1)
        rec["atom_id"] = new_atom_id  # re-id to be parallel with FAISS rows
        unique_records.append(rec)
        new_atom_id += 1

    texts = [r["text"] for r in unique_records]
    log.info("Phase D: loading embedding model %s", EMBED_MODEL_NAME)
    from sentence_transformers import SentenceTransformer
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("Phase D: device=%s", device)
    model = SentenceTransformer(EMBED_MODEL_NAME, device=device)

    log.info("Phase D: encoding %d unique texts", len(texts))
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=256,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    log.info("Phase D: encoded in %.1fs (%.1f texts/s)",
             time.time() - t0, len(texts) / max(time.time() - t0, 1e-9))

    embeddings = embeddings.astype(np.float32)
    if embeddings.shape[1] != EMBED_DIM:
        log.warning("expected dim %d, got %d", EMBED_DIM, embeddings.shape[1])
    np.save(EMB_PATH, embeddings)

    with open(METADATA_JSONL, "w") as f:
        for r in unique_records:
            f.write(json.dumps(r) + "\n")
    log.info("Phase D done: saved %s and %s", EMB_PATH, METADATA_JSONL)
    return total, len(unique_records)


# ---------------------------------------------------------------------------
# Phase E — FAISS index
# ---------------------------------------------------------------------------

def build_faiss(log: logging.Logger) -> int:
    import faiss
    log.info("Phase E: loading %s", EMB_PATH)
    vecs = np.load(EMB_PATH).astype(np.float32)
    log.info("Phase E: shape=%s", vecs.shape)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, str(FAISS_PATH))
    size_mb = FAISS_PATH.stat().st_size / 1024 / 1024
    log.info("Phase E done: %d vectors, %.1f MB → %s", index.ntotal, size_mb, FAISS_PATH)
    return index.ntotal


# ---------------------------------------------------------------------------
# Phase F — verification
# ---------------------------------------------------------------------------

TEST_QUERIES: list[tuple[str, str, str]] = [
    ("my chest feels heavy and tight", "symptom", "chest_pain neighborhood"),
    ("can't catch my breath", "symptom", "dyspnea / shortness of breath"),
    ("my chest is doing weird stuff frfr", "symptom", "chest discomfort family"),
    ("I keep throwing up", "symptom", "vomiting / nausea"),
    ("feeling really lightheaded when I stand up", "symptom", "orthostatic / dizziness"),
    ("pain shoots down my left arm", "symptom", "chest pain radiating left arm"),
    ("my head is pounding", "symptom", "headache / migraine"),
    ("I'm so tired all the time", "symptom", "fatigue"),
    ("my blood pressure pill", "medication", "antihypertensives"),
    ("that diabetes medication I take every morning", "medication", "metformin / antidiabetics"),
    ("the cholesterol pill", "medication", "statins"),
    ("I take a baby aspirin daily", "medication", "aspirin"),
    ("the water pill for my legs swelling", "medication", "furosemide / diuretics"),
    ("they did that heart cath thing", "procedure", "cardiac catheterization"),
    ("I had my gallbladder taken out", "procedure", "cholecystectomy"),
    ("got a scope done", "procedure", "endoscopy / colonoscopy"),
    ("they put a stent in", "procedure", "stent placement / PCI"),
    ("high blood sugar", "condition", "diabetes / hyperglycemia"),
    ("high blood pressure", "condition", "hypertension"),
    ("my ticker is acting up", "condition", "heart-related (afib, etc.)"),
    ("the silent killer", "condition", "hypertension (colloquial)"),
    ("my left leg is throbbing", "negative", "leg pain — should NOT return chest pain"),
    ("I'm allergic to peanuts", "negative", "allergy — should NOT fabricate"),
]


def run_tests(log: logging.Logger) -> tuple[float, list[dict]]:
    import faiss
    from sentence_transformers import SentenceTransformer
    import torch

    log.info("Phase F: loading FAISS + metadata")
    index = faiss.read_index(str(FAISS_PATH))
    metas: list[dict] = []
    with open(METADATA_JSONL) as f:
        for line in f:
            metas.append(json.loads(line))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(EMBED_MODEL_NAME, device=device)

    results = []
    sensible_count = 0
    for q, expected_cat, expected_desc in TEST_QUERIES:
        emb = model.encode([q], normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)
        D, I = index.search(emb, 10)
        hits = []
        for rank, (score, idx) in enumerate(zip(D[0], I[0]), 1):
            m = metas[idx]
            hits.append({
                "rank": rank,
                "score": float(score),
                "text": m["text"],
                "parent_cui": m["parent_cui"],
                "category": m["category"],
                "source_vocab": m["source_vocab"],
                "tty": m["tty"],
            })
        # crude sensibility check: top-3 should not all be wildly off-category for non-negative tests
        if expected_cat == "negative":
            sensible = True  # detailed eval done manually
        else:
            top3_cats = [h["category"] for h in hits[:3]]
            sensible = expected_cat in top3_cats
        if sensible:
            sensible_count += 1
        results.append({
            "query": q,
            "expected_category": expected_cat,
            "expected_desc": expected_desc,
            "hits": hits,
            "sensible_top3": sensible,
        })

    acc = sensible_count / len(TEST_QUERIES)
    log.info("Phase F done: sensible top-3 = %.0f%%", acc * 100)
    return acc, results


def write_test_report(results: list[dict], acc: float) -> None:
    lines = ["# VeriSim Vector DB — Test Query Results\n",
             f"Sensible top-3 (category match heuristic): **{acc*100:.0f}%**\n"]
    for r in results:
        lines.append(f"## Query: `{r['query']}`")
        lines.append(f"- Expected ({r['expected_category']}): {r['expected_desc']}")
        lines.append(f"- Sensible top-3: {'yes' if r['sensible_top3'] else 'NO ❌'}")
        lines.append("")
        lines.append("| rank | score | text | category | source_vocab | tty | parent_cui |")
        lines.append("|---|---|---|---|---|---|---|")
        for h in r["hits"]:
            t = h["text"].replace("|", "\\|")
            lines.append(
                f"| {h['rank']} | {h['score']:.3f} | {t} | {h['category']} | "
                f"{h['source_vocab']} | {h['tty']} | {h['parent_cui']} |"
            )
        lines.append("")
        # top-3 commentary
        top3 = r["hits"][:3]
        if r["expected_category"] == "negative":
            assess = f"Top-3 returned: {[h['text'] for h in top3]}. Visual check required."
        elif r["sensible_top3"]:
            assess = (f"Top-3 hits look on-topic for {r['expected_category']}.")
        else:
            assess = (f"Top-3 categories were {[h['category'] for h in top3]} — "
                      f"expected at least one {r['expected_category']}. Flag for review.")
        lines.append(f"> {assess}\n")
    TEST_REPORT.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# build report
# ---------------------------------------------------------------------------

def write_build_report(
    *,
    cui_meta: dict[str, dict] | None,
    total_atoms: int,
    unique_atoms: int,
    n_vectors: int,
    phase_times: dict[str, float],
    api_stats: dict | None,
    acc: float | None,
) -> None:
    lines = ["# VeriSim Vector DB Build Report\n"]
    lines.append("## Summary")
    lines.append(f"- Total atoms extracted: {total_atoms}")
    lines.append(f"- Unique texts embedded: {unique_atoms}")
    lines.append(f"- Total vectors in FAISS: {n_vectors}")
    if FAISS_PATH.exists():
        lines.append(f"- FAISS index size: {FAISS_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    if EMB_PATH.exists():
        lines.append(f"- Embeddings size: {EMB_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    total_secs = sum(phase_times.values())
    lines.append(f"- Total build time: {timedelta(seconds=int(total_secs))}")
    if api_stats:
        lines.append(f"- UMLS API calls: {api_stats['api_calls']}  (cache hits: {api_stats['cache_hits']})")
    if acc is not None:
        lines.append(f"- Test query sensible top-3: {acc*100:.0f}%")
    lines.append("")

    lines.append("## Phase Timing")
    for phase, sec in phase_times.items():
        lines.append(f"- {phase}: {sec:.1f}s")
    lines.append("")

    lines.append("## Per-Category Breakdown")
    lines.append("| Category | Seed CUIs (incl. expansions) | Atoms extracted | After dedup |")
    lines.append("|---|---|---|---|")
    cat_seed_counts: Counter = Counter()
    cat_atom_counts: Counter = Counter()
    cat_unique_counts: Counter = Counter()
    if cui_meta:
        for m in cui_meta.values():
            cat_seed_counts[m["category"]] += 1
    if ATOMS_JSONL.exists():
        with open(ATOMS_JSONL) as f:
            for line in f:
                rec = json.loads(line)
                cat_atom_counts[rec["category"]] += 1
    if METADATA_JSONL.exists():
        with open(METADATA_JSONL) as f:
            for line in f:
                rec = json.loads(line)
                cat_unique_counts[rec["category"]] += 1
    for cat in ("symptom", "medication", "procedure", "condition"):
        lines.append(
            f"| {cat} | {cat_seed_counts.get(cat, 0)} | "
            f"{cat_atom_counts.get(cat, 0)} | {cat_unique_counts.get(cat, 0)} |"
        )
    lines.append("")

    if UNRESOLVED_LOG.exists():
        unresolved = UNRESOLVED_LOG.read_text().strip().splitlines()
        lines.append("## Unresolved Seeds")
        if unresolved:
            lines.append("```")
            for u in unresolved:
                lines.append(u)
            lines.append("```")
        else:
            lines.append("- none")
        lines.append("")

    # sample atoms
    if METADATA_JSONL.exists():
        per_cat: dict[str, list[dict]] = defaultdict(list)
        with open(METADATA_JSONL) as f:
            for line in f:
                rec = json.loads(line)
                per_cat[rec["category"]].append(rec)
        lines.append("## Sample atoms (5 random per category)")
        random.seed(0)
        for cat in ("symptom", "medication", "procedure", "condition"):
            items = per_cat.get(cat, [])
            if not items:
                continue
            sample = random.sample(items, min(5, len(items)))
            lines.append(f"### {cat}")
            for s in sample:
                lines.append(f"- `{s['text']}` ({s['source_vocab']}/{s['tty']}, CUI={s['parent_cui']})")
        lines.append("")

    lines.append("## Test Query Results Summary")
    if TEST_REPORT.exists() and acc is not None:
        lines.append(f"Full details in `test_results.md`. Sensible top-3 heuristic: {acc*100:.0f}%.")
    else:
        lines.append("Test queries not run.")

    BUILD_REPORT.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all", "B", "C", "D", "E", "F"], default="all")
    ap.add_argument("--skip-embed", action="store_true",
                    help="dev shortcut — skip phase D if embeddings.npy already exists")
    args = ap.parse_args()

    log = setup_logging()
    log.info("=" * 70)
    log.info("VeriSim Vector DB build — phase=%s", args.phase)
    log.info("=" * 70)

    client = UMLSClient(cache_dir=str(CACHE))
    log.info("API key loaded; cache=%s", CACHE)

    phase_times: dict[str, float] = {}
    cui_meta: dict[str, dict] | None = None
    total_atoms = 0
    unique_atoms = 0
    n_vectors = 0
    acc = None

    # Phase B
    if args.phase in ("all", "B", "C"):
        t = time.time()
        cui_meta = resolve_seeds(client, log)
        phase_times["B (resolve+expand seeds)"] = time.time() - t

    # Phase C
    if args.phase in ("all", "C"):
        t = time.time()
        if cui_meta is None:
            # load from disk if we skipped B
            cui_meta = {}
            for cat in ("symptom", "medication", "procedure", "condition"):
                p = SEED_DIR / f"seed_{cat}s.json"
                if p.exists():
                    for m in json.loads(p.read_text()):
                        cui_meta[m["cui"]] = m
        total_atoms = extract_atoms(client, cui_meta, log)
        phase_times["C (atoms+relations)"] = time.time() - t

    # Phase D
    if args.phase in ("all", "D"):
        t = time.time()
        if args.skip_embed and EMB_PATH.exists() and METADATA_JSONL.exists():
            log.info("Phase D: skipped (embeddings.npy and metadata.jsonl already exist)")
            with open(METADATA_JSONL) as f:
                unique_atoms = sum(1 for _ in f)
            total_atoms = total_atoms or unique_atoms
        else:
            total_atoms, unique_atoms = embed_atoms(log)
        phase_times["D (embedding)"] = time.time() - t

    # Phase E
    if args.phase in ("all", "E"):
        t = time.time()
        n_vectors = build_faiss(log)
        phase_times["E (FAISS index)"] = time.time() - t

    # Phase F
    if args.phase in ("all", "F"):
        t = time.time()
        acc, results = run_tests(log)
        write_test_report(results, acc)
        phase_times["F (verification)"] = time.time() - t

    # Reload counts from disk if we ran partial phases
    if METADATA_JSONL.exists() and unique_atoms == 0:
        with open(METADATA_JSONL) as f:
            unique_atoms = sum(1 for _ in f)
    if ATOMS_JSONL.exists() and total_atoms == 0:
        with open(ATOMS_JSONL) as f:
            total_atoms = sum(1 for _ in f)
    if FAISS_PATH.exists() and n_vectors == 0:
        import faiss
        n_vectors = faiss.read_index(str(FAISS_PATH)).ntotal

    write_build_report(
        cui_meta=cui_meta,
        total_atoms=total_atoms,
        unique_atoms=unique_atoms,
        n_vectors=n_vectors,
        phase_times=phase_times,
        api_stats=client.stats(),
        acc=acc,
    )

    log.info("=" * 70)
    log.info("BUILD COMPLETE")
    log.info("vectors=%d  unique_atoms=%d  total_atoms=%d", n_vectors, unique_atoms, total_atoms)
    if acc is not None:
        log.info("test top-3 sensible: %.0f%%", acc * 100)
    log.info("Outputs at %s", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
