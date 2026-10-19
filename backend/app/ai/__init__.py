"""AI package: features call the gateway; the gateway calls providers. See docs/AI-00-foundation.md §3–§5."""

from .errors import AIError
from .gateway import AIRequest, AIResponse, complete

__all__ = ["AIError", "AIRequest", "AIResponse", "complete"]
