from .anthropic import AnthropicProvider
from .base import ImagePart, Part, Provider, ProviderCall, ProviderError, ProviderResult, TextPart
from .fake import FAKE
from .groq import GroqProvider

PROVIDERS: dict[str, Provider] = {"anthropic": AnthropicProvider(), "groq": GroqProvider(), "fake": FAKE}

__all__ = ["PROVIDERS", "FAKE", "ImagePart", "Part", "Provider", "ProviderCall", "ProviderError", "ProviderResult",
           "TextPart"]
