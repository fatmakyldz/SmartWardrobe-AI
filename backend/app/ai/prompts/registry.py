"""Prompt templates live in prompts/<feature>/<version>.md. Placeholders are {name}; other braces are literal."""

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..errors import AIError

ROOT = Path(__file__).parent
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class PromptTemplate:
    feature: str
    version: str
    text: str

    def render(self, variables: dict) -> str:
        def sub(m: re.Match) -> str:
            if m.group(1) not in variables:
                raise KeyError(f"prompt {self.feature}/{self.version} needs {{{m.group(1)}}}")
            return str(variables[m.group(1)])

        return _PLACEHOLDER.sub(sub, self.text)


@lru_cache
def get(feature: str, version: str) -> PromptTemplate:
    path = ROOT / feature / f"{version}.md"
    if not re.fullmatch(r"[a-z_]+", feature) or not re.fullmatch(r"v\d+", version) or not path.is_file():
        raise AIError("prompt_not_found")
    return PromptTemplate(feature, version, path.read_text(encoding="utf-8").rstrip("\n"))


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
