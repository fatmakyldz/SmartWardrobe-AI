"""Dev-only: draws the flat illustrations used by the demo wardrobe.

Run:  python scripts/make_demo_assets.py   (needs `pip install cairosvg`)
Writes PNGs to app/demo_assets/. The PNGs are committed, so production never runs this.
"""

from pathlib import Path

import cairosvg

OUT = Path(__file__).resolve().parents[1] / "app" / "demo_assets"
BG = "#F2EEE8"


def shade(hex_color: str, f: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    if f < 1:
        r, g, b = (int(c * f) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * (f - 1)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def svg(body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="600" height="600">'
        f'<rect width="200" height="200" fill="{BG}"/>'
        '<ellipse cx="100" cy="182" rx="62" ry="6" fill="#000" opacity=".06"/>'
        f"{body}</svg>"
    )


def tshirt(c, stripes=None):
    d = shade(c, 0.78)
    s = ""
    if stripes:
        s = "".join(
            f'<rect x="58" y="{y}" width="84" height="5" fill="{stripes}" clip-path="url(#b)"/>' for y in range(62, 170, 14)
        )
    return svg(
        '<defs><clipPath id="b"><path d="M58 52 L142 52 L142 168 L58 168 Z"/></clipPath></defs>'
        f'<path d="M78 36 Q100 48 122 36 L162 56 L150 84 L142 80 L142 168 L58 168 L58 80 L50 84 L38 56 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>{s}'
        f'<path d="M80 37 Q100 56 120 37" fill="none" stroke="{d}" stroke-width="3"/>'
    )


def shirt(c):
    d = shade(c, 0.75)
    buttons = "".join(f'<circle cx="100" cy="{y}" r="2.2" fill="{d}"/>' for y in (66, 88, 110, 132, 154))
    return svg(
        f'<path d="M80 34 L120 34 L160 54 L168 150 L150 152 L142 92 L142 170 L58 170 L58 92 L50 152 L32 150 L40 54 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M80 34 L100 58 L120 34 L112 30 L100 44 L88 30 Z" fill="{shade(c, 1.15)}" stroke="{d}" stroke-width="2"/>'
        f'<line x1="100" y1="58" x2="100" y2="170" stroke="{d}" stroke-width="2"/>{buttons}'
        f'<rect x="114" y="74" width="16" height="14" rx="2" fill="none" stroke="{d}" stroke-width="1.8"/>'
    )


def sweater(c):
    d = shade(c, 0.8)
    ribs = "".join(f'<line x1="{x}" y1="158" x2="{x}" y2="170" stroke="{d}" stroke-width="1.6"/>' for x in range(62, 140, 6))
    knit = "".join(
        f'<path d="M{x} 70 l4 6 l4 -6 M{x} 90 l4 6 l4 -6 M{x} 110 l4 6 l4 -6 M{x} 130 l4 6 l4 -6" '
        f'fill="none" stroke="{d}" stroke-width="1.2" opacity=".55"/>'
        for x in range(72, 124, 14)
    )
    return svg(
        f'<path d="M78 36 Q100 50 122 36 L158 56 L170 150 L150 154 L142 96 L142 170 L58 170 L58 96 L50 154 L30 150 L42 56 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>{knit}{ribs}'
        f'<path d="M78 36 Q100 54 122 36" fill="none" stroke="{d}" stroke-width="5"/>'
        f'<rect x="30" y="146" width="20" height="8" fill="{d}" opacity=".5"/><rect x="150" y="146" width="20" height="8" fill="{d}" opacity=".5"/>'
    )


def trousers(c, denim=False):
    d = shade(c, 0.72)
    seams = (
        f'<path d="M66 44 L60 176 M134 44 L140 176" stroke="{shade(c, 1.35)}" stroke-width="1.6" stroke-dasharray="3 3" fill="none"/>'
        if denim
        else f'<path d="M84 50 L80 176 M116 50 L120 176" stroke="{d}" stroke-width="1.4" fill="none" opacity=".6"/>'
    )
    return svg(
        f'<path d="M64 30 L136 30 L146 178 L108 178 L100 82 L92 178 L54 178 Z" fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<rect x="64" y="30" width="72" height="12" fill="{shade(c, 0.88)}" stroke="{d}" stroke-width="2"/>'
        f'<circle cx="100" cy="36" r="2.4" fill="{d}"/>'
        f'<path d="M70 44 Q80 60 92 46 M130 44 Q120 60 108 46" fill="none" stroke="{d}" stroke-width="1.8"/>{seams}'
    )


def skirt(c):
    d = shade(c, 0.75)
    pleats = "".join(f'<line x1="{100 + (x - 100) * 0.55}" y1="48" x2="{x}" y2="168" stroke="{d}" stroke-width="1.4" opacity=".6"/>' for x in range(56, 150, 16))
    return svg(
        f'<path d="M70 36 L130 36 L156 168 L44 168 Z" fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<rect x="70" y="36" width="60" height="12" fill="{shade(c, 0.88)}" stroke="{d}" stroke-width="2"/>{pleats}'
    )


def dress(c):
    d = shade(c, 0.75)
    return svg(
        f'<path d="M82 24 L90 24 Q100 40 110 24 L118 24 L124 70 Q120 82 126 92 L156 172 L44 172 L74 92 Q80 82 76 70 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M76 84 Q100 92 124 84" fill="none" stroke="{d}" stroke-width="3"/>'
        f'<path d="M100 92 L96 172 M100 92 L120 172 M100 92 L78 172" stroke="{d}" stroke-width="1.2" opacity=".45"/>'
    )


def blazer(c):
    d = shade(c, 0.7)
    return svg(
        f'<path d="M78 30 L122 30 L160 50 L170 156 L148 158 L144 100 L146 174 L54 174 L56 100 L52 158 L30 156 L40 50 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M78 30 L100 110 L122 30 L112 30 L100 72 L88 30 Z" fill="{BG}"/>'
        f'<path d="M78 30 L92 78 L84 84 L100 110 M122 30 L108 78 L116 84 L100 110" fill="{shade(c, 0.85)}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
        f'<circle cx="104" cy="126" r="2.6" fill="{d}"/><circle cx="104" cy="144" r="2.6" fill="{d}"/>'
        f'<line x1="64" y1="134" x2="84" y2="134" stroke="{d}" stroke-width="2"/><line x1="116" y1="134" x2="136" y2="134" stroke="{d}" stroke-width="2"/>'
        f'<line x1="118" y1="82" x2="132" y2="82" stroke="{d}" stroke-width="2"/>'
    )


def coat(c):
    d = shade(c, 0.72)
    return svg(
        f'<path d="M76 22 L124 22 L162 42 L172 168 L150 170 L144 96 L148 184 L52 184 L56 96 L50 170 L28 168 L38 42 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M76 22 L98 96 L124 22 L114 22 L100 62 L86 22 Z" fill="{shade(c, 0.85)}" stroke="{d}" stroke-width="2"/>'
        f'<line x1="104" y1="96" x2="104" y2="184" stroke="{d}" stroke-width="2"/>'
        + "".join(f'<circle cx="{x}" cy="{y}" r="2.8" fill="{d}"/>' for x in (92, 116) for y in (110, 134, 158))
        + f'<path d="M62 120 L84 120 M116 120 L138 120" stroke="{d}" stroke-width="2"/>'
        f'<rect x="56" y="94" width="88" height="7" fill="{d}" opacity=".35"/>'
    )


def leather_jacket(c):
    d = shade(c, 1.5)
    return svg(
        f'<path d="M78 34 L122 34 L158 54 L168 150 L148 152 L142 98 L142 158 L58 158 L58 98 L52 152 L32 150 L42 54 Z" '
        f'fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
        f'<path d="M78 34 L96 62 L84 72 L100 104 L102 158" fill="none" stroke="{d}" stroke-width="2"/>'
        f'<path d="M122 34 L106 62 L118 70 L100 104" fill="{shade(c, 1.2)}" stroke="{d}" stroke-width="2"/>'
        f'<rect x="58" y="150" width="84" height="8" fill="{shade(c, 1.15)}" stroke="{d}" stroke-width="1.6"/>'
        f'<line x1="66" y1="112" x2="84" y2="104" stroke="{d}" stroke-width="2.4"/><line x1="134" y1="112" x2="118" y2="106" stroke="{d}" stroke-width="2.4"/>'
    )


def sneakers(c, sole="#ffffff"):
    d = shade(c, 0.78)
    one = (
        f'<path d="M30 132 Q34 104 58 100 L74 92 Q86 110 104 112 L132 120 Q144 124 142 138 L30 138 Z" fill="{c}" stroke="{d}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<rect x="28" y="136" width="116" height="10" rx="5" fill="{sole}" stroke="{d}" stroke-width="2"/>'
        f'<path d="M66 102 l10 8 M72 98 l10 8 M78 95 l10 8" stroke="{d}" stroke-width="2"/>'
        f'<path d="M96 122 Q110 126 122 124" fill="none" stroke="{shade(c, 0.6)}" stroke-width="2.2"/>'
    )
    return svg(f'<g transform="translate(12 -16)">{one}</g><g transform="translate(34 24)">{one}</g>')


def boots(c):
    d = shade(c, 0.7)
    one = (
        f'<path d="M50 60 L86 60 L88 116 Q120 118 132 130 Q138 138 136 146 L46 146 Z" fill="{c}" stroke="{d}" stroke-width="2.4" stroke-linejoin="round"/>'
        f'<rect x="44" y="144" width="94" height="9" rx="3" fill="{shade(c, 0.55)}"/>'
        f'<rect x="66" y="64" width="14" height="40" rx="3" fill="{shade(c, 0.82)}"/>'
        f'<rect x="46" y="144" width="18" height="12" fill="{shade(c, 0.5)}"/>'
    )
    return svg(f'<g transform="translate(-6 -12)">{one}</g><g transform="translate(38 18)">{one}</g>')


def loafers(c):
    d = shade(c, 1.6)
    one = (
        f'<path d="M34 128 Q36 108 60 106 L106 106 Q136 110 142 130 Q142 140 132 140 L34 140 Z" fill="{c}" stroke="{d}" stroke-width="2" stroke-linejoin="round"/>'
        f'<path d="M84 108 Q110 106 124 118" fill="none" stroke="{d}" stroke-width="2"/>'
        f'<rect x="96" y="114" width="20" height="5" rx="2" fill="{d}" opacity=".7"/>'
        f'<rect x="32" y="138" width="112" height="7" rx="3" fill="{shade(c, 1.3)}"/>'
    )
    return svg(f'<g transform="translate(6 -14)">{one}</g><g transform="translate(26 22)">{one}</g>')


def bag(c):
    d = shade(c, 0.7)
    return svg(
        f'<path d="M72 78 Q72 38 100 38 Q128 38 128 78" fill="none" stroke="{d}" stroke-width="7" stroke-linecap="round"/>'
        f'<path d="M44 78 L156 78 L166 168 L34 168 Z" fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M44 78 L156 78 L150 112 Q100 124 50 112 Z" fill="{shade(c, 0.88)}" stroke="{d}" stroke-width="2"/>'
        f'<rect x="92" y="108" width="16" height="14" rx="3" fill="#C9A646" stroke="{d}" stroke-width="1.6"/>'
    )


def scarf(c):
    d = shade(c, 0.75)
    fringe = "".join(f'<line x1="{x}" y1="170" x2="{x}" y2="182" stroke="{d}" stroke-width="2"/>' for x in range(104, 136, 5))
    return svg(
        f'<path d="M60 40 Q100 20 140 40 Q150 70 128 82 Q100 92 72 82 Q50 70 60 40 Z" fill="{c}" stroke="{d}" stroke-width="2.5"/>'
        f'<path d="M100 84 L136 84 L136 170 L102 170 Z" fill="{c}" stroke="{d}" stroke-width="2.5" stroke-linejoin="round"/>'
        f'<path d="M110 84 L110 170 M120 84 L120 170 M128 84 L128 170" stroke="{d}" stroke-width="1.2" opacity=".5"/>'
        f'<path d="M72 60 Q100 74 128 60" fill="none" stroke="{d}" stroke-width="1.6" opacity=".6"/>{fringe}'
    )


ASSETS = {
    "white-tee": tshirt("#FBFBF8"),
    "striped-tee": tshirt("#F4F1EA", stripes="#2F3E5C"),
    "oxford-shirt": shirt("#B9D0E8"),
    "cream-sweater": sweater("#EFE3CB"),
    "blue-jeans": trousers("#4F6F99", denim=True),
    "beige-chinos": trousers("#D4BE96"),
    "black-trousers": trousers("#2B2B2E"),
    "olive-skirt": skirt("#7C8452"),
    "burgundy-dress": dress("#7E2639"),
    "navy-blazer": blazer("#273452"),
    "camel-coat": coat("#B98A5A"),
    "leather-jacket": leather_jacket("#1F1F22"),
    "white-sneakers": sneakers("#FAFAF7", sole="#E7E2D9"),
    "brown-boots": boots("#6E4A30"),
    "black-loafers": loafers("#1E1E20"),
    "tan-bag": bag("#B07A4A"),
    "grey-scarf": scarf("#9B9DA3"),
}


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, markup in ASSETS.items():
        cairosvg.svg2png(bytestring=markup.encode(), write_to=str(OUT / f"{name}.png"))
        print("wrote", name)
