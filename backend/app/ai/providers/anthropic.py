"""Claude Messages API via the official SDK. The answer is forced into shape with one strict tool."""

import base64
from functools import lru_cache

import anthropic

from ...config import get_settings
from .base import ImagePart, ProviderCall, ProviderError, ProviderResult, TextPart

DEFAULT_THINKING_HEADROOM = 4096  # adaptive thinking counts towards max_tokens


def _detail(e: Exception) -> str:
    """The API's own error message (e.g. what was wrong with the request), not the SDK's wrapper text."""
    body = getattr(e, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict) and body["error"].get("message"):
        status = getattr(e, "status_code", "")
        return f"{status} {body['error'].get('type', '')}: {body['error']['message']}".strip()
    return str(e)


@lru_cache
def _client(api_key: str) -> anthropic.Anthropic:
    # Retries belong to the gateway, which counts every attempt's tokens.
    return anthropic.Anthropic(api_key=api_key, max_retries=0)


class AnthropicProvider:
    name = "anthropic"

    def configured(self) -> bool:
        return bool(get_settings().anthropic_api_key)

    def complete_json(self, call: ProviderCall, model: str) -> ProviderResult:
        tool_name = f"submit_{call.schema_name}"
        content: list[dict] = []
        for part in call.parts:
            if isinstance(part, ImagePart):
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": part.media_type,
                               "data": base64.standard_b64encode(part.data).decode()},
                })
            elif isinstance(part, TextPart):
                content.append({"type": "text", "text": part.text})
        content.append({"type": "text", "text": f"Give your answer by calling the {tool_name} tool."})
        if call.repair_note:
            content.append({"type": "text", "text": call.repair_note})

        params: dict = {
            "model": model,
            "max_tokens": call.max_output_tokens + int(call.options.get("thinking_headroom", DEFAULT_THINKING_HEADROOM)),
            # The system prompt is fixed per prompt version and language, so it is cacheable.
            "system": [{"type": "text", "text": call.system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            # Forced tool_choice is rejected by current models; auto + strict + the instruction above.
            "tools": [{
                "name": tool_name,
                "description": f"Submit the {call.schema_name} result.",
                "input_schema": call.json_schema,
                "strict": True,
            }],
            "tool_choice": {"type": "auto"},
        }
        if call.options.get("effort"):
            params["output_config"] = {"effort": call.options["effort"]}

        client = _client(get_settings().anthropic_api_key)
        try:
            resp = client.with_options(timeout=call.timeout_s).messages.create(**params)
        except anthropic.APITimeoutError as e:
            raise ProviderError("timeout", str(e))
        except anthropic.APIConnectionError as e:
            raise ProviderError("unavailable", str(e))
        except anthropic.RateLimitError as e:
            raise ProviderError("rate_limited", _detail(e))
        except anthropic.OverloadedError as e:
            raise ProviderError("rate_limited", _detail(e))
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise ProviderError("auth", _detail(e))
        except (anthropic.NotFoundError, anthropic.BadRequestError, anthropic.UnprocessableEntityError) as e:
            raise ProviderError("config", _detail(e))
        except anthropic.APIStatusError as e:
            raise ProviderError("unavailable" if e.status_code >= 500 else "error", _detail(e))

        u = resp.usage
        tokens = dict(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=u.cache_read_input_tokens or 0,
            cache_write_tokens=u.cache_creation_input_tokens or 0,
        )
        if resp.stop_reason == "refusal":
            raise ProviderError("error", "refusal", **tokens)
        for block in resp.content:
            if block.type == "tool_use" and block.name == tool_name and isinstance(block.input, dict):
                return ProviderResult(data=block.input, **tokens)
        raise ProviderError("bad_output", f"no {tool_name} call (stop_reason={resp.stop_reason})", **tokens)
