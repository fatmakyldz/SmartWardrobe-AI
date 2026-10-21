"""Experiment (v1.1 candidate, not a feature): can one photo of several garments be split into pieces?

The roadmap's "zero-effort wardrobe" idea — lay 6–8 pieces on the bed, take one photo, get them all — stands or
falls on how well a vision model finds and boxes each garment. Before building anything in the app, this script
measures that on your own photos:

    python scripts/experiments/multi_garment.py photos/ --out /tmp/mg            # detect + crop + contact sheet
    python scripts/experiments/multi_garment.py photos/ --out /tmp/mg --tag      # also run tagging v2 on each crop
    python scripts/experiments/multi_garment.py photos/ --out /tmp/mg --provider fake  # plumbing check, no API

Input: a folder of JPEG/PNG/HEIC photos, each showing one or more garments (flat-lays, a rail, a pile). Put the
number of garments you see in the file name if you want precision/recall, e.g. `bed-6.jpg` → 6 expected.
Output per photo: the boxes drawn on the picture, one crop per box, and `results.json`; `index.html` is a contact
sheet to judge by eye. The summary prints detected vs expected counts, median confidence, cost and latency.

It talks to the provider directly (the same AnthropicProvider the gateway uses, same strict-tool pattern) and
touches nothing in the app: no route, no prompt file under app/ai/prompts, no DB. ANTHROPIC_API_KEY from
backend/.env. Costs: ~1 vision call per photo (+1 tagging call per crop with --tag), Haiku-class.
"""

import argparse
import base64
import html
import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageDraw  # noqa: E402

from app.ai.providers import PROVIDERS, ImagePart, ProviderCall, TextPart  # noqa: E402
from app.ai.providers.fake import FAKE  # noqa: E402
from app.ai.schemas.tagging import TaggingOut  # noqa: E402
from app.vocab import CATEGORIES, COLORS, PATTERNS, SEASONS  # noqa: E402

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

DETECT_MODEL = "claude-haiku-5-5"  # the vision tier the app's tagging route uses (routes.default.json)
TAG_MODEL = "claude-haiku-5-5"
SIDE = 1024  # detection needs more pixels than tagging's 640 thumbnail: small items on a bed

DETECT_SYSTEM = """You find clothing in photos for a wardrobe app. The photo may show several garments or accessories
laid out, hanging on a rail, or in a pile. Return every distinct wearable item you can see, each with a tight
bounding box. Coordinates are fractions of the image width/height (0–1): x and y are the top-left corner, w and h
the box size. One box per item; do not box the same garment twice; ignore people, furniture, hangers and backgrounds.
If a garment is only partly visible, box the visible part and lower its confidence."""

DETECT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},  # short English noun, e.g. "navy blazer"
                    "category": {"type": "string", "enum": CATEGORIES},
                    "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": ["label", "category", "x", "y", "w", "h", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

TAG_SYSTEM_PATH = Path(__file__).resolve().parents[2] / "app/ai/prompts/tagging/v2.md"


@dataclass
class Box:
    label: str
    category: str
    x: float
    y: float
    w: float
    h: float
    confidence: float
    tags: dict | None = None


@dataclass
class PhotoResult:
    file: str
    expected: int | None
    detected: int
    boxes: list[Box]
    latency_ms: int
    input_tokens: int
    output_tokens: int
    error: str | None = None


def jpeg(img: Image.Image, side: int) -> bytes:
    im = img.convert("RGB")
    im.thumbnail((side, side))
    buf = BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def expected_count(path: Path) -> int | None:
    tail = path.stem.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None


def detect(provider, model: str, photo: bytes) -> tuple[list[Box], int, int, int]:
    call = ProviderCall(system=DETECT_SYSTEM, parts=[TextPart("Find every garment in this photo."), ImagePart(photo, "image/jpeg")],
                        schema_name="detect_garments", json_schema=DETECT_SCHEMA, max_output_tokens=1500, timeout_s=60, temperature=0.0)
    t0 = time.time()
    res = provider.complete_json(call, model)
    boxes = []
    for it in res.data.get("items", []):
        try:
            x, y, w, h = (max(0.0, min(1.0, float(it[k]))) for k in ("x", "y", "w", "h"))
            if w <= 0.01 or h <= 0.01:
                continue
            boxes.append(Box(str(it.get("label", ""))[:60], str(it.get("category", "")), x, y, min(w, 1 - x), min(h, 1 - y),
                             max(0.0, min(1.0, float(it.get("confidence", 0))))))
        except (KeyError, TypeError, ValueError):
            continue
    return boxes, int((time.time() - t0) * 1000), res.input_tokens, res.output_tokens


def tag(provider, model: str, crop: bytes) -> dict:
    system = TAG_SYSTEM_PATH.read_text().format(categories=CATEGORIES, colors=COLORS, patterns=PATTERNS, seasons=SEASONS, language="English")
    call = ProviderCall(system=system, parts=[TextPart("Catalogue this item."), ImagePart(crop, "image/jpeg")],
                        schema_name="tagging", json_schema=TaggingOut.tool_schema(), max_output_tokens=400, timeout_s=30, temperature=0.1)
    return provider.complete_json(call, model).data


def fake_respond(call, model):
    if call.schema_name == "detect_garments":
        return {"items": [{"label": "left piece", "category": "top", "x": 0.05, "y": 0.1, "w": 0.4, "h": 0.5, "confidence": 0.8},
                          {"label": "right piece", "category": "bottom", "x": 0.55, "y": 0.1, "w": 0.4, "h": 0.7, "confidence": 0.7}]}
    return {"is_clothing": True, "category": "top", "subcategory": "t-shirt", "name": "Fake tee", "colors": ["white"], "pattern": "solid",
            "warmth": 2, "formality": 2, "seasons": ["summer"], "confidence": 0.9, "uncertain": []}


def run(folder: Path, out: Path, provider_name: str, do_tag: bool) -> list[PhotoResult]:
    if provider_name == "fake":
        FAKE.respond = fake_respond
    provider = PROVIDERS[provider_name]
    if not provider.configured():
        sys.exit(f"provider {provider_name} is not configured (ANTHROPIC_API_KEY in backend/.env)")
    out.mkdir(parents=True, exist_ok=True)
    results: list[PhotoResult] = []
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic", ".webp"))
    if not photos:
        sys.exit(f"no photos in {folder}")
    for path in photos:
        img = Image.open(path)
        img = img.convert("RGB")
        try:
            boxes, ms, tin, tout = detect(provider, DETECT_MODEL, jpeg(img, SIDE))
        except Exception as e:  # noqa: BLE001 — an experiment: record and move on
            results.append(PhotoResult(path.name, expected_count(path), 0, [], 0, 0, 0, error=f"{type(e).__name__}: {str(e)[:120]}"))
            print(f"{path.name}: ERROR {results[-1].error}")
            continue
        W, H = img.size
        drawn = img.copy()
        d = ImageDraw.Draw(drawn)
        for n, b in enumerate(boxes):
            px = (int(b.x * W), int(b.y * H), int((b.x + b.w) * W), int((b.y + b.h) * H))
            d.rectangle(px, outline="#E3B23C", width=max(3, W // 300))
            d.text((px[0] + 6, px[1] + 6), f"{n + 1} {b.label} {b.confidence:.2f}", fill="#E3B23C")
            crop = img.crop(px)
            crop.save(out / f"{path.stem}-{n + 1}.jpg", quality=90)
            if do_tag:
                try:
                    b.tags = tag(provider, TAG_MODEL, jpeg(crop, 640))
                except Exception as e:  # noqa: BLE001
                    b.tags = {"error": f"{type(e).__name__}: {str(e)[:80]}"}
        drawn.thumbnail((1400, 1400))
        drawn.save(out / f"{path.stem}-boxes.jpg", quality=85)
        r = PhotoResult(path.name, expected_count(path), len(boxes), boxes, ms, tin, tout)
        results.append(r)
        exp = f"/{r.expected}" if r.expected is not None else ""
        print(f"{path.name}: {r.detected}{exp} items, {ms} ms, {tin}+{tout} tokens")
    (out / "results.json").write_text(json.dumps([asdict(r) for r in results], indent=2))
    write_index(out, results, do_tag)
    return results


def write_index(out: Path, results: list[PhotoResult], do_tag: bool) -> None:
    rows = []
    for r in results:
        crops = "".join(
            f'<figure><img src="{html.escape(r.file.rsplit(".", 1)[0])}-{n + 1}.jpg"><figcaption>{n + 1}. {html.escape(b.label)} '
            f'<small>{b.category} · {b.confidence:.2f}</small>'
            + (f'<br><small>{html.escape(json.dumps({k: b.tags.get(k) for k in ("name", "category", "colors", "confidence")}, ensure_ascii=False))}</small>' if do_tag and b.tags else "")
            + "</figcaption></figure>"
            for n, b in enumerate(r.boxes))
        exp = f" / expected {r.expected}" if r.expected is not None else ""
        rows.append(f'<section><h2>{html.escape(r.file)} — {r.detected} detected{exp} · {r.latency_ms} ms'
                    f'{" · <b>" + html.escape(r.error) + "</b>" if r.error else ""}</h2>'
                    f'<img class="full" src="{html.escape(r.file.rsplit(".", 1)[0])}-boxes.jpg"><div class="crops">{crops}</div></section>')
    (out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>multi-garment experiment</title><style>body{font:14px system-ui;margin:24px;background:#ECE8E3;color:#2A1B26}"
        ".full{max-width:100%;max-height:70vh;display:block;margin:8px 0}.crops{display:flex;flex-wrap:wrap;gap:12px}figure{margin:0;width:160px}"
        "figure img{width:160px;height:160px;object-fit:contain;background:#fff;border-radius:8px}figcaption{font-size:12px}section{margin-bottom:40px}</style>"
        + "".join(rows))


def summary(results: list[PhotoResult]) -> None:
    ok = [r for r in results if not r.error]
    with_expected = [r for r in ok if r.expected is not None]
    print(f"\nphotos {len(results)}, errors {len(results) - len(ok)}, items detected {sum(r.detected for r in ok)}")
    if with_expected:
        exact = sum(r.detected == r.expected for r in with_expected)
        under = sum(r.detected < r.expected for r in with_expected)
        over = sum(r.detected > r.expected for r in with_expected)
        print(f"count accuracy on {len(with_expected)} labelled photos: exact {exact}, under {under}, over {over}")
    confs = [b.confidence for r in ok for b in r.boxes]
    if confs:
        print(f"box confidence median {statistics.median(confs):.2f}, min {min(confs):.2f}")
    if ok:
        print(f"latency median {statistics.median(r.latency_ms for r in ok)} ms; tokens in {sum(r.input_tokens for r in ok)}, out {sum(r.output_tokens for r in ok)}")
    print("judge the boxes by eye in index.html: a box that cuts a garment or merges two counts as a miss.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--provider", choices=["anthropic", "fake"], default="anthropic")
    ap.add_argument("--tag", action="store_true", help="also run tagging v2 on every crop")
    args = ap.parse_args()
    summary(run(args.folder, args.out, args.provider, args.tag))


if __name__ == "__main__":
    main()
