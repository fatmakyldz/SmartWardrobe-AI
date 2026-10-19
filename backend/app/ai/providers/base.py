"""What every provider speaks: parts in, a JSON object (plus token counts) out."""

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes  # raw image bytes; providers encode them their own way
    media_type: str = "image/jpeg"


Part = TextPart | ImagePart


@dataclass(frozen=True)
class ProviderCall:
    system: str
    parts: list[Part]
    schema_name: str  # e.g. "tagging"
    json_schema: dict  # strict JSON schema of the expected object
    max_output_tokens: int
    timeout_s: float
    temperature: float | None = None  # honoured where the model accepts it (Groq)
    options: dict = field(default_factory=dict)  # per-model options from the routes config
    repair_note: str | None = None  # set on the retry after a bad_output


@dataclass(frozen=True)
class ProviderResult:
    data: dict
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


# timeout / rate_limited: retried on the same model; bad_output: retried once with a repair note;
# auth / config: the model is skipped; unavailable / error: next model.
FailureKind = Literal["timeout", "rate_limited", "bad_output", "auth", "config", "unavailable", "error"]


class ProviderError(Exception):
    def __init__(self, kind: FailureKind, message: str = "", *, input_tokens: int = 0, output_tokens: int = 0,
                 cache_read_tokens: int = 0, cache_write_tokens: int = 0):
        super().__init__(f"{kind}: {message[:200]}")
        self.kind = kind
        self.message = message[:200]  # provider error bodies are capped, never logged in full
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens


class Provider(Protocol):
    name: str

    def configured(self) -> bool: ...

    def complete_json(self, call: ProviderCall, model: str) -> ProviderResult: ...
