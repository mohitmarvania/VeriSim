"""Vector DB wrapper for the VeriSim verifier.

Wraps the FAISS index + parallel metadata.jsonl + BioLORD encoder built by
the `verisim_vectordb` pipeline. Supports in-memory injection of
patient-specific ground-truth atoms at runtime (tagged is_in_history=true).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


log = logging.getLogger("verisim.vdb")


class VectorDB:
    def __init__(
        self,
        faiss_path: str | Path,
        metadata_path: str | Path,
        biolord_model: str = "FremyCompany/BioLORD-2023",
        device: str = "cuda",
    ) -> None:
        log.info("loading FAISS index from %s", faiss_path)
        self.index = faiss.read_index(str(faiss_path))
        self.dim = self.index.d

        log.info("loading metadata from %s", metadata_path)
        self.metadata: list[dict] = []
        with open(metadata_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    self.metadata.append(json.loads(line))
        if len(self.metadata) != self.index.ntotal:
            raise RuntimeError(
                f"metadata count {len(self.metadata)} != index ntotal {self.index.ntotal}"
            )

        log.info("loading BioLORD encoder %s on %s", biolord_model, device)
        self.encoder = SentenceTransformer(biolord_model, device=device)

        log.info("VectorDB ready: %d vectors, dim=%d", self.index.ntotal, self.dim)

    def _embed(self, texts: list[str]) -> np.ndarray:
        emb = self.encoder.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return emb.astype(np.float32)

    def retrieve(
        self,
        query: str,
        k: int = 5,
        filter_patient_id: Optional[str] = None,
    ) -> list[dict]:
        """Top-k matches for `query`. If `filter_patient_id`, results are
        unfiltered (all vectors searched), but a `is_history_match` flag is
        added per result indicating whether the match belongs to the patient."""
        emb = self._embed([query])
        # Over-retrieve so we can include both general and patient-specific
        # hits if filter_patient_id is set.
        k_search = max(k, k * 4) if filter_patient_id else k
        D, I = self.index.search(emb, min(k_search, self.index.ntotal))
        hits: list[dict] = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            rec = dict(self.metadata[idx])
            rec["similarity"] = float(score)
            rec["index_id"] = int(idx)
            if filter_patient_id is not None:
                rec["is_history_match"] = (
                    rec.get("is_in_history", False)
                    and rec.get("patient_id") == filter_patient_id
                )
            hits.append(rec)
        return hits[:k]

    def add_patient_atoms(self, patient_id: str, atoms: list[dict]) -> int:
        """Encode and append patient ground-truth atoms to the index.

        Each atom dict needs at least a `text` field; we fill in
        `is_in_history=true`, `patient_id`, and a fresh `atom_id`.
        Returns the count actually added (dedup against same patient).
        """
        existing_texts = {
            (m.get("patient_id"), m["text"].lower().strip())
            for m in self.metadata
            if m.get("is_in_history") and m.get("patient_id") == patient_id
        }
        new_atoms: list[dict] = []
        new_texts: list[str] = []
        next_id = self.index.ntotal
        for a in atoms:
            text = (a.get("text") or "").strip()
            if not text:
                continue
            key = (patient_id, text.lower())
            if key in existing_texts:
                continue
            existing_texts.add(key)
            rec = dict(a)
            rec["text"] = text
            rec["patient_id"] = patient_id
            rec["is_in_history"] = True
            rec["atom_id"] = next_id
            next_id += 1
            new_atoms.append(rec)
            new_texts.append(text)
        if not new_atoms:
            return 0
        embeddings = self._embed(new_texts)
        self.index.add(embeddings)
        self.metadata.extend(new_atoms)
        log.info("added %d patient atoms for %s (total now %d)",
                 len(new_atoms), patient_id, self.index.ntotal)
        return len(new_atoms)
