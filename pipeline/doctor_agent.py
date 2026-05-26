"""Doctor agent — asks the next clinically-relevant question."""

from __future__ import annotations

from pathlib import Path


class DoctorAgent:
    def __init__(self, llm_engine, prompts_dir: str | Path = "prompts") -> None:
        self.llm = llm_engine
        self.system_prompt = (Path(prompts_dir) / "doctor_system.txt").read_text()

    def next_question(
        self,
        patient_chief_complaint: str,
        conversation_history: list[dict],
        temperature: float = 0.7,
    ) -> str:
        # Render the conversation so far as a short transcript
        if conversation_history:
            transcript_lines = []
            for turn in conversation_history:
                transcript_lines.append(f"Doctor: {turn['doctor']}")
                transcript_lines.append(f"Patient: {turn['patient_response']}")
            transcript = "\n".join(transcript_lines)
        else:
            transcript = "(no prior turns — this is your first question)"

        user_msg = (
            f"Chief complaint: {patient_chief_complaint}\n\n"
            f"Conversation so far:\n{transcript}\n\n"
            f"Ask your next question."
        )

        return self.llm.generate(
            system=self.system_prompt,
            user=user_msg,
            max_tokens=200,
            temperature=temperature,
        )
