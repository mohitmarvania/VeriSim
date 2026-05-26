"""VeriSim full-pipeline driver: loads vector DB + Llama-3.1-70B,
populates patient ground-truth atoms, runs 5 conversations, writes reports."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from llm_engine import LlamaEngine
from orchestrator import Orchestrator
from vector_db import VectorDB
from umls_client import UMLSClient


ROOT = Path("/path/to/working_dir/verisim_pipeline")
PROMPTS = ROOT / "pipeline_code" / "prompts"
DUMMY_PATIENTS = ROOT / "dummy_patients.json"
CONVERSATIONS = ROOT / "conversations"
OUTPUT = ROOT / "output"
LOGS = ROOT / "logs"
VECTOR_DB_PATH = Path("/path/to/working_dir/verisim_vectordb/output")
UMLS_CACHE = Path("/path/to/working_dir/verisim_vectordb/cache")

CONVERSATIONS.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)


def setup_logging() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger("verisim.main")


def fetch_atoms_for_patient(
    umls: UMLSClient, patient: dict, log: logging.Logger
) -> list[dict]:
    """Fetch ground-truth atoms from UMLS for every CUI in the patient's profile."""
    atoms: list[dict] = []
    sections = [
        ("symptom", patient.get("symptoms", [])),
        ("medication", patient.get("medications", [])),
        ("condition", patient.get("conditions", [])),
        ("procedure", patient.get("procedures", [])),
        ("allergy", patient.get("allergies", [])),
    ]
    for category, items in sections:
        for it in items:
            cui = it.get("cui")
            if not cui:
                continue
            # Synthetic atom from the patient profile text itself (always include)
            atoms.append({
                "text": it["text"],
                "parent_cui": cui,
                "source_vocab": "PATIENT_PROFILE",
                "tty": "PROFILE",
                "category": category,
                "source_meta": {k: v for k, v in it.items() if k != "cui"},
            })
            # Plus all UMLS atoms for this CUI (cross-vocab synonyms)
            try:
                umls_atoms = umls.get_atoms(
                    cui,
                    sabs=["SNOMEDCT_US", "RXNORM", "ICD10CM", "CPT",
                          "HCPCS", "MDR", "MSH", "NCI", "LNC"],
                    page_size=100,
                    max_pages=3,
                )
            except Exception as e:
                log.warning("UMLS atoms fetch failed for %s: %s", cui, e)
                continue
            for a in umls_atoms:
                if str(a.get("suppressible", "")).lower() == "true":
                    continue
                if str(a.get("obsolete", "")).lower() == "true":
                    continue
                text = (a.get("name") or "").strip()
                if not text:
                    continue
                atoms.append({
                    "text": text,
                    "parent_cui": cui,
                    "source_aui": a.get("ui"),
                    "source_code": (a.get("code") or "").split("/")[-1],
                    "source_vocab": a.get("rootSource") or "",
                    "tty": a.get("termType") or "",
                    "category": category,
                })
    log.info("[%s] fetched %d ground-truth atoms", patient["patient_id"], len(atoms))
    return atoms


def write_test_report(all_results: list[dict], out_path: Path) -> None:
    total_turns = sum(r["stats"]["turns"] for r in all_results)
    total_regens = sum(r["stats"]["total_regenerations"] for r in all_results)
    total_caught = sum(r["stats"]["turns_with_caught_fabrication"] for r in all_results)
    total_failed = sum(r["stats"]["final_attempt_failures"] for r in all_results)
    avg_attempts = (total_turns + total_regens) / max(total_turns, 1)

    lines = ["# VeriSim Pipeline Test Results\n"]
    lines.append("## Summary")
    lines.append(f"- Total conversations: {len(all_results)}")
    lines.append(f"- Total turns: {total_turns}")
    lines.append(f"- Total patient utterances (incl. regens): {total_turns + total_regens}")
    lines.append(f"- Turns with caught fabrications: {total_caught}")
    lines.append(f"- Regenerations triggered: {total_regens}")
    lines.append(f"- Avg attempts per turn: {avg_attempts:.2f}")
    lines.append(f"- Final-attempt failures (still flagged after max regens): {total_failed}")
    lines.append("")

    lines.append("## Per-Patient Results")
    for r in all_results:
        pid = r["patient_id"]
        s = r["stats"]
        lines.append(f"### {pid}")
        lines.append(f"- Turns: {s['turns']}")
        lines.append(f"- Regenerations: {s['total_regenerations']}")
        lines.append(f"- Caught fabrications: {s['turns_with_caught_fabrication']}")
        # First exchange with caught fabrication, if any
        for turn in r["conversation"]:
            judgments = turn["verifier_result"].get("claim_judgments", [])
            if any(cj.get("verdict") == "FABRICATION" for cj in judgments):
                lines.append("- Sample turn with fabrication detection:")
                lines.append(f"  - **Doctor:** {turn['doctor']}")
                lines.append(f"  - **Patient (final):** {turn['patient_response']}")
                lines.append(f"  - **Verifier verdict:** "
                             f"{turn['verifier_result']['overall_verdict']}")
                for cj in judgments[:3]:
                    lines.append(
                        f"    - claim={cj.get('claim')!r} → {cj.get('verdict')}"
                    )
                if turn["verifier_result"].get("feedback_to_generator"):
                    lines.append(
                        f"  - **Feedback:** {turn['verifier_result']['feedback_to_generator']}"
                    )
                break
        lines.append("")

    lines.append("## Sample full conversation — first patient")
    if all_results:
        r0 = all_results[0]
        lines.append(f"Patient {r0['patient_id']}:\n")
        for t in r0["conversation"]:
            lines.append(f"**Turn {t['turn']}**")
            lines.append(f"- Doctor: {t['doctor']}")
            lines.append(f"- Patient: {t['patient_response']}")
            v = t["verifier_result"]
            lines.append(
                f"- Verifier: {v['overall_verdict']} "
                f"(attempts={t['regeneration_attempts']}, "
                f"claims={len(v.get('claims', []))})"
            )
            lines.append("")

    lines.append("## Failure Modes Observed")
    # Heuristic scan
    notes = []
    if total_failed > 0:
        notes.append(f"- {total_failed} turn(s) remained flagged after max regenerations — "
                     "indicates either persistent generator hallucination or verifier false-positive.")
    if total_regens == 0:
        notes.append("- Zero regenerations triggered — either generator was perfect or verifier "
                     "is too lenient.")
    parse_errors = sum(
        1 for r in all_results for t in r["conversation"]
        if t["verifier_result"].get("parse_error")
    )
    if parse_errors:
        notes.append(f"- {parse_errors} verifier JSON parse failures.")
    if not notes:
        notes.append("- No obvious failure modes detected in this run.")
    lines.extend(notes)
    lines.append("")

    out_path.write_text("\n".join(lines))


def main() -> int:
    log = setup_logging()
    log.info("=" * 70)
    log.info("VeriSim pipeline run starting")
    log.info("=" * 70)

    # Vector DB
    vdb = VectorDB(
        faiss_path=VECTOR_DB_PATH / "umls_atoms.faiss",
        metadata_path=VECTOR_DB_PATH / "umls_metadata.jsonl",
        biolord_model="FremyCompany/BioLORD-2023",
        device="cuda",
    )
    log.info("vector DB ready: %d vectors", vdb.index.ntotal)

    # Patient ground truth fetch
    umls = UMLSClient(cache_dir=str(UMLS_CACHE))
    log.info("UMLS client ready (cache hits will be reused from prior build)")

    patients = json.loads(DUMMY_PATIENTS.read_text())
    log.info("loaded %d dummy patients", len(patients))

    t0 = time.time()
    for p in patients:
        atoms = fetch_atoms_for_patient(umls, p, log)
        n = vdb.add_patient_atoms(p["patient_id"], atoms)
        log.info("[%s] added %d patient atoms to vector DB", p["patient_id"], n)
    log.info("patient ingest done in %.1fs (vdb now %d vectors)",
             time.time() - t0, vdb.index.ntotal)

    # LLM engine — share across all agents.
    # vLLM 0.21 needs libcudart.so.13; some HPC clusters have CUDA 12.6 driver,
    # so we go transformers + bitsandbytes 4-bit. Slower per token than vLLM but
    # reliable on this driver/wheel combo.
    llm = LlamaEngine(
        model_name="meta-llama/Llama-3.1-70B-Instruct",
        backend="transformers",
        quantization="bitsandbytes",
    )

    # Orchestrate
    orch = Orchestrator(llm, vdb, prompts_dir=PROMPTS, max_regen_attempts=2)
    all_results: list[dict] = []
    for p in patients:
        out_path = CONVERSATIONS / f"{p['patient_id']}.json"
        debug_path = CONVERSATIONS / f"{p['patient_id']}_debug.json"
        if out_path.exists():
            log.info("skipping %s (already done)", p["patient_id"])
            all_results.append(json.loads(out_path.read_text()))
            continue
        try:
            result = orch.run_conversation(p, max_turns=8, debug_path=debug_path)
        except Exception as e:
            log.exception("conversation failed for %s: %s", p["patient_id"], e)
            continue
        out_path.write_text(json.dumps(result, indent=2))
        all_results.append(result)
        log.info("[%s] saved → %s", p["patient_id"], out_path)

    write_test_report(all_results, OUTPUT / "test_results.md")
    log.info("=" * 70)
    log.info("PIPELINE DONE — %d conversations completed", len(all_results))
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
