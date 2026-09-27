"""LLM provider abstraction.

Extraction/analysis code calls `get_llm().complete(...)` and never touches
a provider SDK directly. Swap providers via LLM_PROVIDER in .env.
"""

import time
from typing import Protocol

from app.config import settings


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> str: ...


class _RetryMixin:
    retries: int = 3
    backoff: float = 2.0

    def _with_retry(self, fn):
        for attempt in range(self.retries):
            try:
                return fn()
            except Exception:
                if attempt == self.retries - 1:
                    raise
                time.sleep(self.backoff * (attempt + 1))


class GroqProvider(_RetryMixin):
    name = "groq"

    def __init__(self, model: str | None = None):
        from groq import Groq

        self.client = Groq(api_key=settings.groq_api_key)
        self.model = model or settings.groq_model

    def complete(self, messages, json_mode=False, temperature=0.0, max_tokens=4096):
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        return self._with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            .choices[0]
            .message.content
        )


class OpenAIProvider(_RetryMixin):
    name = "openai"

    def __init__(self, model: str | None = None):
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = model or settings.openai_model

    def complete(self, messages, json_mode=False, temperature=0.0, max_tokens=4096):
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        return self._with_retry(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            .choices[0]
            .message.content
        )


class GeminiProvider(_RetryMixin):
    name = "gemini"

    def __init__(self, model: str | None = None):
        import google.generativeai as genai

        genai.configure(api_key=settings.gemini_api_key)
        self.model = model or settings.gemini_model
        self.client = genai.GenerativeModel(self.model)

    def complete(self, messages, json_mode=False, temperature=0.0, max_tokens=4096):
        # Gemini uses a single prompt string; flatten chat messages.
        prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        cfg = {"temperature": temperature, "max_output_tokens": max_tokens}
        if json_mode:
            cfg["response_mime_type"] = "application/json"
        return self._with_retry(
            lambda: self.client.generate_content(
                prompt, generation_config=cfg
            ).text
        )


class MockProvider:
    """Deterministic offline provider for tests and demos.

    Inspects the prompt: if it contains the check catalog (planning) it
    selects all check ids; if it contains evidence chunks it emits one
    finding per check quoting the first chunk verbatim — which means its
    output always passes evidence verification."""

    name = "mock"
    model = "mock"

    def complete(self, messages, json_mode=False, temperature=0.0, max_tokens=4096):
        import json
        import re

        prompt = "\n".join(m["content"] for m in messages)

        if "AVAILABLE CHECKS" in prompt:
            ids = re.findall(r"- id=([\w_]+)", prompt)
            return json.dumps({"check_ids": ids})

        chunks = re.findall(
            r"\[chunk_id=([\w\-]+) \| file=([^|\]]+)\| pages=(\d+)-(\d+)\]\n(.*?)(?=\n\n---|\Z)",
            prompt, re.DOTALL,
        )
        if chunks:
            cid, fname, p1, p2, text = chunks[0]
            quote = text.strip().split(". ")[0][:200]
            return json.dumps(
                {
                    "findings": [
                        {
                            "title": "Mock finding",
                            "finding": "Mock extraction for offline testing.",
                            "severity": "MEDIUM",
                            "confidence": 0.9,
                            "reason": "mock provider",
                            "evidence": [{"chunk_id": cid, "quote": quote}],
                        }
                    ]
                }
            )

        return json.dumps({"answer": "mock", "citations": [], "confidence": 0.5})


_PROVIDERS = {
    "groq": GroqProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "mock": MockProvider,
}


def get_llm(provider: str | None = None, model: str | None = None) -> LLMProvider:
    name = provider or settings.llm_provider
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{name}'. Options: {list(_PROVIDERS)}")
    return _PROVIDERS[name](model=model)
