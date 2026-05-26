"""Two-call verifier: (1) extract claims, (2) judge against retrieved evidence."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path


log = logging.getLogger("verisim.verifier")


def _parse_json_response(text: str, default):
    """Parse JSON from a model response, tolerating fences and extra prose."""
    # strip code fences
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # if there's preamble, try to find the first '{' or '[' and last '}' or ']'
    if not (text.startswith("{") or text.startswith("[")):
        m = re.search(r"[\[{]", text)
        if m:
            text = text[m.start():]
    if text.endswith("```"):
        text = text[:-3]
    # truncate trailing prose after the matching bracket
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # find last } or ]
        last = max(text.rfind("}"), text.rfind("]"))
        if last > 0:
            try:
                return json.loads(text[: last + 1])
            except json.JSONDecodeError:
                pass
    log.warning("JSON parse failed; using default. text=%r", text[:300])
    return default


def _format_evidence(evidence: list[dict]) -> str:
    """Render claims + retrieved matches as readable text for the judge LLM."""
    blocks: list[str] = []
    for i, e in enumerate(evidence, 1):
        block = [f"Claim {i}: {e['claim']!r}"]
        block.append(f"Top {len(e['matches'])} retrieved matches:")
        for j, m in enumerate(e["matches"], 1):
            history_flag = ""
            if m.get("is_in_history"):
                pid = m.get("patient_id") or ""
                history_flag = f" [is_in_history=True, patient_id={pid}]"
            meta = m.get("umls_metadata") or {}
            keep = {k: v for k, v in meta.items()
                    if v and k in {"ingredient", "treats_conditions",
                                    "drug_class", "procedure_site",
                                    "finding_site", "is_brand", "mechanism"}}
            extra = ""
            if keep:
                meta_parts = []
                for k, v in keep.items():
                    if isinstance(v, list):
                        meta_parts.append(f"{k}={','.join(v[:3])}")
                    else:
                        meta_parts.append(f"{k}={v}")
                extra = f"  ({'; '.join(meta_parts)})" if meta_parts else ""
            block.append(
                f"  [{j}] {m['text']!r}  sim={m['similarity']:.3f}  "
                f"category={m.get('category')}{history_flag}{extra}"
            )
        blocks.append("\n".join(block))
    return "\n\n".join(blocks) if blocks else "(no medical claims extracted)"


def _items_text(items: list[dict]) -> str:
    if not items:
        return "(none)"
    return "; ".join(it.get("text", "?") for it in items)


class Verifier:
    def __init__(self, llm_engine, vector_db, prompts_dir: str | Path = "prompts",
                 retrieval_k: int = 5, similarity_threshold: float = 0.55) -> None:
        self.llm = llm_engine
        self.vdb = vector_db
        self.extract_prompt_tmpl = (Path(prompts_dir) / "verifier_extract.txt").read_text()
        self.judge_prompt_tmpl = (Path(prompts_dir) / "verifier_judge.txt").read_text()
        self.k = retrieval_k
        # Below this similarity, claims are treated as underspecified and default
        # to PASS (no verifiable medical content).
        self.similarity_threshold = similarity_threshold

    def _extract_claims(self, doctor_question: str, patient_utterance: str) -> list[str]:
        prompt = self.extract_prompt_tmpl.format(
            doctor_question=doctor_question,
            patient_utterance=patient_utterance,
        )
        raw = self.llm.generate(
            system="You output only valid JSON. No preamble, no markdown.",
            user=prompt,
            max_tokens=400,
            temperature=0.1,
        )
        parsed = _parse_json_response(raw, default=[])
        if not isinstance(parsed, list):
            return []
        return [str(c).strip() for c in parsed if str(c).strip()]

    def _judge(self, patient_profile: dict, doctor_question: str,
               patient_utterance: str, evidence: list[dict]) -> dict:
        prompt = self.judge_prompt_tmpl.format(
            patient_id=patient_profile["patient_id"],
            demographics=patient_profile.get("demographics", {}),
            symptoms_text_list=_items_text(patient_profile.get("symptoms", [])),
            medications_text_list=_items_text(patient_profile.get("medications", [])),
            conditions_text_list=_items_text(patient_profile.get("conditions", [])),
            procedures_text_list=_items_text(patient_profile.get("procedures", [])),
            allergies_text_list=_items_text(patient_profile.get("allergies", [])),
            doctor_question=doctor_question,
            patient_utterance=patient_utterance,
            claims_with_evidence=_format_evidence(evidence),
        )
        raw = self.llm.generate(
            system="You output only valid JSON. No preamble, no markdown.",
            user=prompt,
            max_tokens=900,
            temperature=0.15,
        )
        default = {
            "claim_judgments": [],
            "overall_verdict": "PASS",
            "feedback_to_generator": "",
            "parse_error": True,
            "raw": raw[:500],
        }
        parsed = _parse_json_response(raw, default=default)
        if not isinstance(parsed, dict):
            return default
        parsed.setdefault("overall_verdict", "PASS")
        parsed.setdefault("feedback_to_generator", "")
        parsed.setdefault("claim_judgments", [])
        return parsed

    def verify(self, patient_profile: dict, patient_utterance: str,
               doctor_question: str) -> dict:
        # Step 1 — claim extraction
        claims = self._extract_claims(doctor_question, patient_utterance)

        # Step 2 — retrieval per claim
        evidence: list[dict] = []
        for c in claims:
            matches = self.vdb.retrieve(
                c, k=self.k, filter_patient_id=patient_profile["patient_id"]
            )
            evidence.append({"claim": c, "matches": matches})

        # Step 3 — judgment
        if not claims:
            judgment = {
                "claim_judgments": [],
                "overall_verdict": "PASS",
                "feedback_to_generator": "",
                "reason": "no medical claims to verify",
            }
        else:
            judgment = self._judge(
                patient_profile, doctor_question, patient_utterance, evidence
            )
        judgment["claims"] = claims
        judgment["evidence"] = evidence
        return judgment
