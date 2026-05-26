"""Orchestrator: runs the full doctor–patient–verifier loop for one conversation."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from doctor_agent import DoctorAgent
from patient_generator import PatientGenerator
from verifier import Verifier


log = logging.getLogger("verisim.orch")


class Orchestrator:
    def __init__(
        self,
        llm_engine,
        vector_db,
        prompts_dir: str | Path = "prompts",
        max_regen_attempts: int = 2,
    ) -> None:
        self.doctor = DoctorAgent(llm_engine, prompts_dir=prompts_dir)
        self.patient = PatientGenerator(llm_engine, prompts_dir=prompts_dir)
        self.verifier = Verifier(llm_engine, vector_db, prompts_dir=prompts_dir)
        self.max_regen_attempts = max_regen_attempts

    def _generate_with_verification(
        self,
        patient: dict,
        question: str,
        history: list[dict],
        debug_trace: list[dict],
    ) -> tuple[str, dict, int]:
        feedback: Optional[str] = None
        last_response = ""
        last_verify: dict = {}
        for attempt in range(self.max_regen_attempts + 1):
            t0 = time.time()
            response = self.patient.generate_response(
                patient, question, history, feedback_from_verifier=feedback
            )
            t1 = time.time()
            verify_result = self.verifier.verify(patient, response, question)
            t2 = time.time()

            debug_trace.append({
                "attempt": attempt,
                "response": response,
                "feedback_input": feedback,
                "verifier": verify_result,
                "patient_gen_s": round(t1 - t0, 2),
                "verifier_s": round(t2 - t1, 2),
            })
            last_response, last_verify = response, verify_result
            if verify_result.get("overall_verdict", "PASS") == "PASS":
                return response, verify_result, attempt + 1
            feedback = verify_result.get("feedback_to_generator", "") or "Try again — your previous response had a fabrication."
        # Exhausted attempts
        return last_response, last_verify, self.max_regen_attempts + 1

    def _compute_stats(self, conversation: list[dict]) -> dict:
        n_turns = len(conversation)
        n_regens = sum(t["regeneration_attempts"] - 1 for t in conversation)
        n_failed = sum(
            1 for t in conversation
            if t["verifier_result"].get("overall_verdict") != "PASS"
        )
        fabrications_caught = sum(
            1 for t in conversation
            if any(
                cj.get("verdict") == "FABRICATION"
                for cj in t["verifier_result"].get("claim_judgments", [])
            )
        )
        return {
            "turns": n_turns,
            "total_regenerations": n_regens,
            "turns_with_caught_fabrication": fabrications_caught,
            "final_attempt_failures": n_failed,
        }

    def run_conversation(
        self,
        patient_profile: dict,
        max_turns: int = 8,
        debug_path: Optional[Path] = None,
    ) -> dict:
        log.info("starting conversation for patient %s (max_turns=%d)",
                 patient_profile["patient_id"], max_turns)
        conversation: list[dict] = []
        debug_traces: list[dict] = []

        for turn in range(max_turns):
            t0 = time.time()
            question = self.doctor.next_question(
                patient_profile["chief_complaint"], conversation
            )
            t1 = time.time()

            turn_debug: list[dict] = []
            response, verify_result, num_attempts = self._generate_with_verification(
                patient_profile, question, conversation, turn_debug
            )
            t2 = time.time()

            turn_record = {
                "turn": turn,
                "doctor": question,
                "patient_response": response,
                "verifier_result": {
                    "overall_verdict": verify_result.get("overall_verdict"),
                    "claim_judgments": verify_result.get("claim_judgments", []),
                    "claims": verify_result.get("claims", []),
                    "feedback_to_generator": verify_result.get("feedback_to_generator", ""),
                },
                "regeneration_attempts": num_attempts,
                "timing_s": {"doctor": round(t1 - t0, 2), "patient+verifier": round(t2 - t1, 2)},
            }
            conversation.append(turn_record)
            debug_traces.append({
                "turn": turn,
                "doctor_question": question,
                "attempts": turn_debug,
            })

            log.info("[%s t%d] verdict=%s attempts=%d",
                     patient_profile["patient_id"], turn,
                     verify_result.get("overall_verdict"), num_attempts)

            if debug_path is not None:
                # incremental dump so partial runs survive crashes
                debug_path.write_text(json.dumps(
                    {"patient_id": patient_profile["patient_id"], "turns": debug_traces},
                    indent=2,
                ))

            if "enough information" in question.lower():
                break

        return {
            "patient_id": patient_profile["patient_id"],
            "conversation": conversation,
            "stats": self._compute_stats(conversation),
        }
