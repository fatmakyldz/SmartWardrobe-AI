"""Groq (OpenAI-compatible chat completions, JSON mode) over httpx."""

import base64
import json

import httpx

from ...config import get_settings
from .base import ImagePart, ProviderCall, ProviderError, ProviderResult, TextPart


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


def _user_content(call: ProviderCall) -> str | list[dict]:
    texts = [p.text for p in call.parts if isinstance(p, TextPart)]
    images = [p for p in call.parts if isinstance(p, ImagePart)]
    if call.repair_note:
        texts.append(call.repair_note)
    if not images:
        return "\n".join(texts)
    content: list[dict] = [{"type": "text", "text": t} for t in texts]
    for img in images:
        url = f"data:{img.media_type};base64," + base64.b64encode(img.data).decode()
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content


class GroqProvider:
    name = "groq"

    def configured(self) -> bool:
        return bool(get_settings().groq_api_key)

    def complete_json(self, call: ProviderCall, model: str) -> ProviderResult:
        s = get_settings()
        body = {
            "model": model,
            "messages": [{"role": "system", "content": call.system}, {"role": "user", "content": _user_content(call)}],
            "max_completion_tokens": call.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        if call.temperature is not None:
            body["temperature"] = call.temperature
        try:
            resp = httpx.post(
                f"{s.groq_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                json=body,
                timeout=call.timeout_s,
            )
        except httpx.TimeoutException as e:
            raise ProviderError("timeout", str(e))
        except httpx.HTTPError as e:
            raise ProviderError("unavailable", str(e))

        if resp.status_code == 429:
            raise ProviderError("rate_limited", resp.text)
        if resp.status_code in (401, 403):
            raise ProviderError("auth", resp.text)
        if resp.status_code >= 500:
            raise ProviderError("unavailable", resp.text)
        if resp.status_code >= 400:
            raise ProviderError("config", resp.text)

        try:
            payload = resp.json()
        except ValueError as e:
            raise ProviderError("bad_output", str(e))
        usage = payload.get("usage") or {}
        tokens = dict(input_tokens=int(usage.get("prompt_tokens") or 0),
                      output_tokens=int(usage.get("completion_tokens") or 0))
        try:
            return ProviderResult(data=_extract_json(payload["choices"][0]["message"]["content"]), **tokens)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            raise ProviderError("bad_output", str(e), **tokens)
