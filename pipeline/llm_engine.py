"""Llama-3.1-70B inference wrapper. Prefers vLLM; falls back to transformers+bitsandbytes 4-bit."""

from __future__ import annotations

import logging
import os
from typing import Optional


log = logging.getLogger("verisim.llm")


class LlamaEngine:
    """Thin wrapper around either vLLM or transformers. Single global engine
    shared by all agents — Llama-3.1-70B is too big to load multiple times."""

    def __init__(
        self,
        model_name: str = "meta-llama/Llama-3.1-70B-Instruct",
        backend: str = "auto",  # "vllm" | "transformers" | "auto"
        tensor_parallel_size: int = 2,
        max_model_len: int = 8192,
        gpu_memory_utilization: float = 0.9,
        quantization: Optional[str] = None,  # "awq" | "gptq" | "bitsandbytes" | None
    ) -> None:
        self.model_name = model_name
        self.backend = backend
        self._vllm = None
        self._tokenizer = None
        self._hf_model = None

        if backend in ("vllm", "auto"):
            try:
                from vllm import LLM, SamplingParams
                self._SamplingParams = SamplingParams
                log.info(
                    "loading vLLM model=%s tp=%d max_len=%d util=%.2f quant=%s",
                    model_name, tensor_parallel_size, max_model_len,
                    gpu_memory_utilization, quantization,
                )
                kwargs = dict(
                    model=model_name,
                    tensor_parallel_size=tensor_parallel_size,
                    max_model_len=max_model_len,
                    gpu_memory_utilization=gpu_memory_utilization,
                    enforce_eager=False,
                    dtype="auto",
                    trust_remote_code=False,
                )
                if quantization:
                    kwargs["quantization"] = quantization
                self._vllm = LLM(**kwargs)
                self.backend = "vllm"
                log.info("vLLM loaded successfully")
            except Exception as e:
                log.warning("vLLM load failed (%s); trying transformers fallback", e)
                if backend == "vllm":
                    raise
                self.backend = "transformers"

        if self.backend != "vllm":
            self._init_transformers(quantization or "bitsandbytes")

    def _init_transformers(self, quantization: str) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        log.info("loading transformers model=%s quant=%s", self.model_name, quantization)
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name, trust_remote_code=False
        )
        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

        kwargs: dict = {"trust_remote_code": False, "device_map": "auto"}
        if quantization == "bitsandbytes":
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
        else:
            kwargs["torch_dtype"] = torch.bfloat16

        self._hf_model = AutoModelForCausalLM.from_pretrained(self.model_name, **kwargs)
        self._hf_model.eval()

    # ------------------------------------------------------------------
    # generation API
    # ------------------------------------------------------------------

    def _build_prompt(self, system: str, user: str) -> str:
        """Apply Llama-3.1 chat template."""
        # Llama-3.1 instruct format
        return (
            "<|begin_of_text|>"
            f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
            f"<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>"
            f"<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

    def generate(
        self,
        system: str,
        user: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[list[str]] = None,
    ) -> str:
        prompt = self._build_prompt(system, user)
        if self.backend == "vllm":
            params = self._SamplingParams(
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop or ["<|eot_id|>", "<|end_of_text|>"],
            )
            outputs = self._vllm.generate([prompt], params, use_tqdm=False)
            return outputs[0].outputs[0].text.strip()
        else:
            import torch
            ids = self._tokenizer(prompt, return_tensors="pt").to(self._hf_model.device)
            with torch.inference_mode():
                gen = self._hf_model.generate(
                    **ids,
                    max_new_tokens=max_tokens,
                    do_sample=temperature > 0,
                    temperature=temperature if temperature > 0 else 1.0,
                    top_p=top_p,
                    pad_token_id=self._tokenizer.pad_token_id,
                    eos_token_id=self._tokenizer.eos_token_id,
                )
            new_tokens = gen[0, ids["input_ids"].shape[1]:]
            text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
            return text.strip()

    def generate_batch(
        self,
        prompts: list[tuple[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[list[str]] = None,
    ) -> list[str]:
        """Batch generate from (system, user) pairs."""
        if self.backend != "vllm":
            return [self.generate(s, u, max_tokens, temperature, top_p, stop)
                    for s, u in prompts]
        prompts_built = [self._build_prompt(s, u) for s, u in prompts]
        params = self._SamplingParams(
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop or ["<|eot_id|>", "<|end_of_text|>"],
        )
        outputs = self._vllm.generate(prompts_built, params, use_tqdm=False)
        return [o.outputs[0].text.strip() for o in outputs]
