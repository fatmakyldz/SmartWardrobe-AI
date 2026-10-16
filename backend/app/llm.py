"""Thin Groq client (OpenAI-compatible chat completions, JSON mode)."""

import json
import logging

import httpx
from fastapi import HTTPException

from .config import get_settings

log = logging.getLogger("llm")


class LLMError(HTTPException):
    def __init__(self, code: str = "ai_unavailable", status: int = 502):
        super().__init__(status, detail={"code": code})


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def chat_json(messages: list[dict], model: str, temperature: float = 0.4, max_tokens: int = 1500) -> dict:
    s = get_settings()
    if not s.groq_api_key:
        raise LLMError("ai_not_configured", 503)

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = httpx.post(
            f"{s.groq_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {s.groq_api_key}"},
            json=body,
            timeout=60,
        )
    except httpx.HTTPError as e:
        log.warning("Groq request failed: %s", e)
        raise LLMError()

    if resp.status_code == 429:
        raise LLMError("ai_busy", 503)
    if resp.status_code >= 400:
        log.warning("Groq error %s: %s", resp.status_code, resp.text[:500])
        raise LLMError()

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)
    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.warning("Groq reply not parseable: %s", e)
        raise LLMError("ai_bad_reply")
