"""Patient generator — simulates noisy patient responses constrained to ground truth.

The patient profile's `noise_profile` field is a list of {type, level} entries
selecting a subset of the six paper-defined noise dimensions:
  memory_recall, health_literacy, emotional_state, communication_style,
  cognitive_processing, social_cultural

Per the paper's protocol, each patient is assigned exactly two dimensions
with levels drawn from L1-L3 for the main quantitative evaluation. Dimensions
not listed default to level 0 (no impairment).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


# Canonical list of the six paper-defined noise dimensions.
NOISE_DIMENSIONS = [
    "memory_recall",
    "health_literacy",
    "emotional_state",
    "communication_style",
    "cognitive_processing",
    "social_cultural",
]


def _format_items(items: list[dict], fields: list[str]) -> str:
    if not items:
        return "(none)"
    lines = []
    for it in items:
        parts = []
        for f in fields:
            v = it.get(f)
            if v:
                parts.append(f"{f}={v}")
        lines.append("- " + ", ".join(parts) if parts else "- (unspecified)")
    return "\n".join(lines)


def _noise_levels(noise_profile) -> dict:
    """Convert noise_profile (list of {type, level} dicts) into a level-per-dim dict.

    Dimensions not present in the patient's profile default to level 0.
    Backwards-compatible with the legacy dict-style noise_profile where keys
    are dimension names — those will be passed through as integer levels.
    """
    levels = {dim: 0 for dim in NOISE_DIMENSIONS}
    if isinstance(noise_profile, list):
        for entry in noise_profile:
            t = entry.get("type")
            lvl = entry.get("level", 0)
            if t in levels:
                levels[t] = int(lvl)
    elif isinstance(noise_profile, dict):
        # legacy compatibility — treat known keys as levels
        for k, v in noise_profile.items():
            if k in levels and isinstance(v, (int, float)):
                levels[k] = int(v)
    return levels


class PatientGenerator:
    def __init__(self, llm_engine, prompts_dir: str | Path = "prompts") -> None:
        self.llm = llm_engine
        self.system_template = (Path(prompts_dir) / "patient_system.txt").read_text()

    def _render_system(self, patient: dict, feedback: Optional[str]) -> str:
        levels = _noise_levels(patient.get("noise_profile", []))
        feedback_section = (
            "=== FEEDBACK FROM PREVIOUS ATTEMPT ===\n"
            f"Your previous response had this issue: {feedback}\n"
            "Please regenerate your response, addressing this issue while still "
            "being a realistic patient with the same noise profile."
            if feedback
            else ""
        )
        return self.system_template.format(
            demographics=patient["demographics"],
            chief_complaint=patient["chief_complaint"],
            symptoms_list=_format_items(
                patient.get("symptoms", []), ["text", "severity", "onset", "duration"]
            ),
            medications_list=_format_items(
                patient.get("medications", []), ["text", "dose", "frequency"]
            ),
            conditions_list=_format_items(
                patient.get("conditions", []), ["text", "diagnosed_year"]
            ),
            procedures_list=_format_items(
                patient.get("procedures", []), ["text", "year", "indication"]
            ),
            allergies_list=_format_items(
                patient.get("allergies", []), ["text", "reaction"]
            ),
            memory_recall=levels["memory_recall"],
            health_literacy=levels["health_literacy"],
            emotional_state=levels["emotional_state"],
            communication_style=levels["communication_style"],
            cognitive_processing=levels["cognitive_processing"],
            social_cultural=levels["social_cultural"],
            feedback_section=feedback_section,
        )

    def generate_response(
        self,
        patient_profile: dict,
        doctor_question: str,
        conversation_history: list[dict],
        feedback_from_verifier: Optional[str] = None,
        temperature: float = 0.85,
    ) -> str:
        system = self._render_system(patient_profile, feedback_from_verifier)

        if conversation_history:
            recent = conversation_history[-3:]  # last 3 turns for context, keep prompt short
            transcript = "\n".join(
                f"Doctor: {t['doctor']}\nPatient: {t['patient_response']}"
                for t in recent
            )
        else:
            transcript = "(this is the first exchange)"

        user_msg = (
            f"Recent conversation:\n{transcript}\n\n"
            f"Doctor just asked: {doctor_question}\n\n"
            f"Respond as the patient."
        )

        return self.llm.generate(
            system=system,
            user=user_msg,
            max_tokens=300,
            temperature=temperature,
        )