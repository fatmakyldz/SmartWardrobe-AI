"""Test provider: scripted answers and injected failures, no network."""

from collections import defaultdict, deque
from collections.abc import Callable

from .base import ProviderCall, ProviderError, ProviderResult

Script = dict | ProviderError | ProviderResult


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.queues: dict[str, deque[Script]] = defaultdict(deque)
        self.respond: Callable[[ProviderCall, str], Script] | None = None  # fallback when a queue is empty
        self.calls: list[tuple[str, ProviderCall]] = []
        self.enabled = True

    def script(self, model: str, *answers: Script) -> None:
        self.queues[model].extend(answers)

    def configured(self) -> bool:
        return self.enabled

    def complete_json(self, call: ProviderCall, model: str) -> ProviderResult:
        self.calls.append((model, call))
        if self.queues[model]:
            answer = self.queues[model].popleft()
        elif self.respond is not None:
            answer = self.respond(call, model)
        else:
            raise ProviderError("unavailable", f"fake: nothing scripted for {model}")
        if isinstance(answer, ProviderError):
            raise answer
        if isinstance(answer, ProviderResult):
            return answer
        return ProviderResult(data=answer, input_tokens=100, output_tokens=50)


FAKE = FakeProvider()
