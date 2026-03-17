from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

try:
    from litellm import completion
except Exception:  # pragma: no cover - optional until dependencies are installed
    completion = None


logger = logging.getLogger(__name__)


class LiteLLMJSONClient:
    def generate_json(self, *, model: str | None, system_prompt: str, user_prompt: str) -> dict[str, Any] | None:
        if not model:
            return None
        if completion is None:
            logger.warning("LiteLLM is unavailable; falling back to stub agent behavior.")
            return None

        settings = get_settings()
        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if settings.llm_api_base:
            request["api_base"] = settings.llm_api_base
        if settings.llm_api_key:
            request["api_key"] = settings.llm_api_key

        try:
            response = completion(**request)
            content = self._extract_content(response)
            return self._parse_json_content(content)
        except Exception as exc:  # pragma: no cover - network/provider-dependent
            logger.warning("LiteLLM request failed for model %s: %s", model, exc)
            return None

    def _extract_content(self, response: Any) -> str:
        message = response["choices"][0]["message"]
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LiteLLM returned an empty completion payload")
        return content

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        normalized = content.strip()
        if normalized.startswith("```"):
            normalized = normalized.strip("`")
            if normalized.startswith("json"):
                normalized = normalized[4:].strip()
        try:
            payload = json.loads(normalized)
        except json.JSONDecodeError:
            start = normalized.find("{")
            end = normalized.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            payload = json.loads(normalized[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("LiteLLM response must decode into a JSON object")
        return payload
