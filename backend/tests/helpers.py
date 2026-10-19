"""Pick item numbers from the context the fake model received, instead of hard-coding them:
the §6 pre-filter and ordering decide which number each piece gets."""

import re

_LINE = re.compile(r"^(\d+): (\w+)/")


def wardrobe(call) -> dict[str, list[int]]:
    """category → item numbers, in context order."""
    text = "\n".join(p.text for p in call.parts if hasattr(p, "text"))
    out: dict[str, list[int]] = {}
    for line in text.split("WARDROBE", 1)[-1].splitlines():
        if m := _LINE.match(line):
            out.setdefault(m.group(2), []).append(int(m.group(1)))
    return out


def outfit(call, *categories: str) -> list[int]:
    """The first item of each category; default: a top and a bottom."""
    w = wardrobe(call)
    return [w[c][0] for c in categories or ("top", "bottom")]


def answer(*categories: str):
    """A fake-provider responder giving one outfit made of the first item of each category."""
    return lambda call, model: {"outfits": [{"title": "t", "items": outfit(call, *categories), "reason": "r"}]}
