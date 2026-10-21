"""Provider adapters without network: request shape and error classification."""

import base64
import json
from types import SimpleNamespace

import anthropic
import httpx
import httpx2
import pytest

from app.ai.providers import ImagePart, ProviderCall, ProviderError, TextPart
from app.ai.providers import anthropic as anthropic_provider
from app.ai.providers import groq as groq_provider
from app.ai.schemas import SuggestOut, TaggingOut

CALL = ProviderCall(
    system="SYSTEM PROMPT", parts=[TextPart("Catalogue this item."), ImagePart(b"\xff\xd8img")],
    schema_name="tagging", json_schema=TaggingOut.tool_schema(), max_output_tokens=400, timeout_s=12,
    temperature=0.1, options={"effort": "low", "thinking_headroom": 1000},
)


class StubClient:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.params, self.timeout = result, error, None, None
        self.messages = self

    def with_options(self, timeout):
        self.timeout = timeout
        return self

    def create(self, **params):
        self.params = params
        if self.error:
            raise self.error
        return self.result


def _message(content, stop_reason="tool_use"):
    usage = SimpleNamespace(input_tokens=900, output_tokens=60, cache_read_input_tokens=1200,
                            cache_creation_input_tokens=0)
    return SimpleNamespace(content=content, stop_reason=stop_reason, usage=usage)


def _tool_use(name="submit_tagging", data=None):
    return SimpleNamespace(type="tool_use", name=name, input=data or {"category": "top"})


@pytest.fixture
def claude(monkeypatch):
    def use(stub):
        monkeypatch.setattr(anthropic_provider, "_client", lambda key: stub)
        return stub
    return use


def test_anthropic_request_shape(claude):
    stub = claude(StubClient(_message([SimpleNamespace(type="thinking"), _tool_use()])))
    result = anthropic_provider.AnthropicProvider().complete_json(CALL, "claude-x")

    assert result.data == {"category": "top"}
    assert (result.input_tokens, result.output_tokens, result.cache_read_tokens) == (900, 60, 1200)
    p = stub.params
    assert stub.timeout == 12 and p["model"] == "claude-x" and p["max_tokens"] == 1400
    assert p["system"] == [{"type": "text", "text": "SYSTEM PROMPT", "cache_control": {"type": "ephemeral"}}]
    assert p["tool_choice"] == {"type": "auto"} and p["output_config"] == {"effort": "low"}
    tool = p["tools"][0]
    assert (tool["name"], tool["strict"], tool["input_schema"]["additionalProperties"]) == ("submit_tagging", True, False)
    assert "temperature" not in p  # current Claude models reject non-default sampling
    image, text, instruction = p["messages"][0]["content"][1], p["messages"][0]["content"][0], p["messages"][0]["content"][2]
    assert text == {"type": "text", "text": "Catalogue this item."}
    assert image["source"] == {"type": "base64", "media_type": "image/jpeg",
                               "data": base64.standard_b64encode(b"\xff\xd8img").decode()}
    assert "submit_tagging" in instruction["text"]


def test_anthropic_no_tool_call_is_bad_output_with_tokens(claude):
    claude(StubClient(_message([SimpleNamespace(type="text", text="hi")], stop_reason="end_turn")))
    with pytest.raises(ProviderError) as e:
        anthropic_provider.AnthropicProvider().complete_json(CALL, "claude-x")
    assert e.value.kind == "bad_output" and e.value.input_tokens == 900 and e.value.cache_read_tokens == 1200


def test_anthropic_refusal_moves_on(claude):
    claude(StubClient(_message([], stop_reason="refusal")))
    with pytest.raises(ProviderError) as e:
        anthropic_provider.AnthropicProvider().complete_json(CALL, "claude-x")
    assert (e.value.kind, e.value.message) == ("error", "refusal")


def _status_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("boom", response=httpx2.Response(status, request=request), body=None)


@pytest.mark.parametrize("error, kind", [
    (lambda: anthropic.APITimeoutError(request=httpx2.Request("POST", "https://x")), "timeout"),
    (lambda: anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x")), "unavailable"),
    (lambda: _status_error(anthropic.RateLimitError, 429), "rate_limited"),
    (lambda: _status_error(anthropic.OverloadedError, 529), "rate_limited"),
    (lambda: _status_error(anthropic.AuthenticationError, 401), "auth"),
    (lambda: _status_error(anthropic.NotFoundError, 404), "config"),
    (lambda: _status_error(anthropic.BadRequestError, 400), "config"),
    (lambda: _status_error(anthropic.InternalServerError, 500), "unavailable"),
])
def test_anthropic_error_classification(claude, error, kind):
    claude(StubClient(error=error()))
    with pytest.raises(ProviderError) as e:
        anthropic_provider.AnthropicProvider().complete_json(CALL, "claude-x")
    assert e.value.kind == kind


def _groq(monkeypatch, status=200, payload=None, exc=None):
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(url=url, json=json, timeout=timeout)
        if exc:
            raise exc
        return httpx.Response(status, json=payload if payload is not None else {}, request=httpx.Request("POST", url))

    monkeypatch.setattr(groq_provider.httpx, "post", post)
    return sent


def test_groq_request_shape_and_tokens(monkeypatch):
    sent = _groq(monkeypatch, payload={
        "choices": [{"message": {"content": "```json\n{\"category\": \"top\"}\n```"}}],
        "usage": {"prompt_tokens": 800, "completion_tokens": 40},
    })
    result = groq_provider.GroqProvider().complete_json(CALL, "qwen-x")
    assert result.data == {"category": "top"} and (result.input_tokens, result.output_tokens) == (800, 40)
    body = sent["json"]
    assert body["model"] == "qwen-x" and body["temperature"] == 0.1 and body["max_completion_tokens"] == 400
    assert body["response_format"] == {"type": "json_object"} and sent["timeout"] == 12
    assert body["messages"][0] == {"role": "system", "content": "SYSTEM PROMPT"}
    user = body["messages"][1]["content"]
    assert user[0] == {"type": "text", "text": "Catalogue this item."}
    assert user[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_groq_text_only_is_a_plain_string(monkeypatch):
    sent = _groq(monkeypatch, payload={"choices": [{"message": {"content": "{\"outfits\": []}"}}]})
    call = ProviderCall(system="S", parts=[TextPart("a"), TextPart("b")], schema_name="suggest",
                        json_schema=SuggestOut.tool_schema(), max_output_tokens=10, timeout_s=5,
                        repair_note="fix it")
    groq_provider.GroqProvider().complete_json(call, "gpt-x")
    assert sent["json"]["messages"][1]["content"] == "a\nb\nfix it" and "temperature" not in sent["json"]


@pytest.mark.parametrize("status, kind", [(429, "rate_limited"), (401, "auth"), (400, "config"), (503, "unavailable")])
def test_groq_status_classification(monkeypatch, status, kind):
    _groq(monkeypatch, status=status)
    with pytest.raises(ProviderError) as e:
        groq_provider.GroqProvider().complete_json(CALL, "m")
    assert e.value.kind == kind


def test_groq_timeout_and_unparseable_reply(monkeypatch):
    _groq(monkeypatch, exc=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderError) as e:
        groq_provider.GroqProvider().complete_json(CALL, "m")
    assert e.value.kind == "timeout"

    _groq(monkeypatch, payload={"choices": [{"message": {"content": "no json"}}], "usage": {"prompt_tokens": 5}})
    with pytest.raises(ProviderError) as e:
        groq_provider.GroqProvider().complete_json(CALL, "m")
    assert e.value.kind == "bad_output" and e.value.input_tokens == 5


def test_tool_schemas_are_strict():
    def walk(schema):
        if schema.get("type") == "object":
            assert schema["additionalProperties"] is False
            assert set(schema["required"]) == set(schema["properties"])
            for sub in schema["properties"].values():
                walk(sub)
        if schema.get("type") == "array":
            walk(schema["items"])

    for model in (TaggingOut, SuggestOut):
        walk(model.tool_schema())
        json.dumps(model.tool_schema())


def test_tagging_schema_coerces_into_vocabularies():
    out = TaggingOut.model_validate({"category": "DRESS", "colors": ["burgundy", "neon", "black", "red", "blue"],
                                     "warmth": 9, "seasons": ["monsoon"], "pattern": "zigzag"})
    assert (out.category, out.colors, out.warmth, out.pattern) == ("dress", ["burgundy", "black", "red"], 5, "solid")
    assert out.seasons == ["spring", "summer", "autumn", "winter"] and out.is_clothing is True
    assert out.confidence is None and out.uncertain == []  # a v1-shaped answer still validates
    out = TaggingOut.model_validate({"category": "top", "confidence": "1.7", "uncertain": ["colors", "price", "warmth", "colors"]})
    assert out.confidence == 1.0 and out.uncertain == ["colors", "warmth"]
    assert TaggingOut.model_validate({"category": "top", "confidence": "high"}).confidence is None


def test_anthropic_error_detail_is_the_api_message(claude):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": "invalid_request_error", "message": "tools.0.input_schema: bad"}}
    claude(StubClient(error=anthropic.BadRequestError("Error code: 400 - {...}",
                                                      response=httpx2.Response(400, request=request), body=body)))
    with pytest.raises(ProviderError) as e:
        anthropic_provider.AnthropicProvider().complete_json(CALL, "claude-x")
    assert (e.value.kind, e.value.message) == ("config", "400 invalid_request_error: tools.0.input_schema: bad")


def test_groq_error_detail_is_the_api_message(monkeypatch):
    _groq(monkeypatch, status=429, payload={"error": {"message": "Rate limit reached for model qwen", "type": "tokens"}})
    with pytest.raises(ProviderError) as e:
        groq_provider.GroqProvider().complete_json(CALL, "m")
    assert e.value.message == "429 tokens: Rate limit reached for model qwen"


def test_suggest_titles_and_reasons_are_trimmed():
    out = SuggestOut.model_validate({"outfits": [{"title": "  Şık ofis \n", "items": [1], "reason": "Serin gün.\n\n"}]})
    assert (out.outfits[0].title, out.outfits[0].reason) == ("Şık ofis", "Serin gün.")
