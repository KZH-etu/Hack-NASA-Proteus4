"""OpenAI-compatible client for LM Studio (Phi-3.5 metadata & Qwen3 embeddings)."""

from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

_METADATA_SYSTEM_PROMPT = (
    "You are a scientific document metadata extractor. "
    "Read the excerpt from a NASA scientific report and return ONLY a valid JSON object "
    "with exact keys: "
    '"mission_program" (string, e.g. "Apollo", "Skylab", "ISS", "Shuttle", or "Unknown"), '
    '"experiment_year" (integer or null), '
    '"authors" (string, comma-separated names, or "Unknown"). '
    "Do not include any explanation or markdown outside the JSON object."
)


class DocumentMetadata(BaseModel):
    """Validated metadata extracted from the beginning of a Markdown report."""

    mission_program: str = Field(default="Unknown")
    experiment_year: int | None = Field(default=None)
    authors: str = Field(default="Unknown")

    @field_validator("mission_program", mode="before")
    @classmethod
    def _clean_program(cls, value: Any) -> str:
        if value is None or str(value).strip() == "":
            return "Unknown"
        return str(value).strip()

    @field_validator("experiment_year", mode="before")
    @classmethod
    def _parse_year(cls, value: Any) -> int | None:
        if value is None or str(value).strip() == "":
            return None
        return int(value)

    @field_validator("authors", mode="before")
    @classmethod
    def _normalize_authors(cls, value: Any) -> str:
        if value is None:
            return "Unknown"
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return ", ".join(cleaned) if cleaned else "Unknown"
        text = str(value).strip()
        return text if text else "Unknown"


class LMStudioClient:
    """Wrapper around LM Studio's local OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        metadata_model: str = "phi-3.5-mini-instruct",
        embedding_model: str = "text-embedding-qwen3-embedding-0.6b",
        embedding_batch_size: int = 32,
        client: Any | None = None,
    ) -> None:
        self.base_url = base_url
        self.metadata_model = metadata_model
        self.embedding_model = embedding_model
        self.embedding_batch_size = embedding_batch_size
        self.client = client if client is not None else OpenAI(base_url=base_url, api_key=api_key)

    def check_connection(self) -> None:
        """Verify that LM Studio is reachable before starting a batch stage."""
        try:
            self.client.models.list()
        except Exception as exc:
            raise ConnectionError(
                f"Cannot reach LM Studio at {self.base_url}. "
                "Ensure LM Studio is running with the local server enabled."
            ) from exc

    def extract_metadata_json(self, text_excerpt: str) -> DocumentMetadata:
        """Call Phi-3.5-mini to extract structured JSON metadata from an excerpt."""
        response = self.client.chat.completions.create(
            model=self.metadata_model,
            temperature=0.0,
            messages=[
                {"role": "system", "content": _METADATA_SYSTEM_PROMPT},
                {"role": "user", "content": text_excerpt},
            ],
        )
        raw_content = response.choices[0].message.content or ""
        parsed = _extract_json_object(raw_content)
        return DocumentMetadata.model_validate(parsed)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate dense embeddings in batches via Qwen3-Embedding 0.6B."""
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for start in range(0, len(texts), self.embedding_batch_size):
            batch = texts[start : start + self.embedding_batch_size]
            response = self.client.embeddings.create(
                model=self.embedding_model,
                input=batch,
            )
            sorted_items = sorted(response.data, key=lambda item: item.index)
            all_vectors.extend(list(item.embedding) for item in sorted_items)
        return all_vectors


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    """Strip markdown fences / surrounding prose and parse the first JSON object."""
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if brace_match:
            cleaned = brace_match.group(0)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM did not return valid JSON: {raw_text!r}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
    return data
