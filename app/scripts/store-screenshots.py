"""Store screenshots from the web build, on the demo wardrobe, in both languages.

The web app renders the same React Native screens as the native builds, so these are the real screens,
captured at phone size and framed with a caption — the usual store format (6.7" iPhone 1290×2796,
Android 1080×2340). Runs against a local API on the fake AI provider so the pictures are deterministic.

    # 1. API on the fake provider (see backend/README.md "Run locally"), e.g. on :8000
    # 2. web build pointed at it, served on :8081
    cd app && EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo export -p web --output-dir /tmp/web \\
        && (cd /tmp/web && python3 -m http.server 8081 &)
    # 3. shoot
    pip install playwright pillow && playwright install chromium
    python3 scripts/store-screenshots.py --out docs/store/screenshots [--lang en|tr] [--web http://127.0.0.1:8081]

Output: <out>/<lang>/<size>/NN-<screen>.png, ready to upload. Captions live in CAPTIONS below.
"""

import argparse
import pathlib
import time

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

CAPTIONS = {
    "en": [
        ("today", "Outfits from the clothes\nyou already own"),
        ("wardrobe", "Photograph a piece —\ntags fill themselves in"),
        ("request", "Ask in your own words:\n“lots of walking, look sharp”"),
        ("saved", "Like, skip, wear —\nthe next ones follow your taste"),
        ("analysis", "See what’s missing\nand what to add next"),
        ("profile", "Your data, your rules:\nexport or delete any time"),
    ],
    "tr": [
        ("today", "Zaten sahip olduğun\nkıyafetlerden kombinler"),
        ("wardrobe", "Parçayı fotoğrafla —\netiketler kendi dolsun"),
        ("request", "Kendi cümlenle iste:\n“çok yürüyeceğim, şık olsun”"),
        ("saved", "Beğen, geç, giy —\nsonrakiler zevkine göre"),
        ("analysis", "Neyin eksik olduğunu\nve sıradakini gör"),
        ("profile", "Verin senin:\nindir ya da sil, istediğin an"),
    ],
}
SIZES = {"ios-6.7": (1290, 2796), "android": (1080, 2340)}
BG, INK, MUTED = "#ECE8E3", "#2A1B26", "#4A3A45"
FONT = pathlib.Path(__file__).resolve().parents[1] / "node_modules/@expo-google-fonts/bricolage-grotesque/700Bold/BricolageGrotesque_700Bold.ttf"


def scroll_to(pg, fraction: float) -> None:
    """Scroll the screen's ScrollView (the tallest scrollable element) to a fraction of its range."""
    pg.evaluate(
        """(f) => { const els = [...document.querySelectorAll('*')].filter(e => e.scrollHeight > e.clientHeight + 50 && getComputedStyle(e).overflowY !== 'visible');
                   const el = els.sort((a, b) => b.scrollHeight - a.scrollHeight)[0] || document.scrollingElement;
                   el.scrollTop = (el.scrollHeight - el.clientHeight) * f; }""",
        fraction,
    )
    time.sleep(0.8)


def capture(web: str, lang: str, out: pathlib.Path) -> dict[str, Image.Image]:
    """Raw screen captures at a phone viewport, keyed by screen name."""
    shots: dict[str, Image.Image] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 430, "height": 932}, device_scale_factor=3, locale="tr-TR" if lang == "tr" else "en-US")
        pg = ctx.new_page()
        pg.goto(web, wait_until="networkidle")
        time.sleep(1)
        # UI strings (app/src/lib/i18n.tsx: welcome.demo, onboarding demo button, tabs, analysis.link, today.notePlaceholder)
        t = {"en": {"demo": "Try with a sample wardrobe", "demo2": "Try with the sample wardrobe", "wardrobe": "Wardrobe", "saved": "Saved",
                    "profile": "Profile", "today": "Today", "analysis": "What’s missing?", "field": "e.g. lots of walking, want to look sharp", "like": "Like"},
             "tr": {"demo": "Örnek gardıropla dene", "demo2": "Örnek gardıropla dene", "wardrobe": "Gardırop", "saved": "Kayıtlı",
                    "profile": "Profil", "today": "Bugün", "analysis": "Ne eksik?", "field": "ör. çok yürüyeceğim, şık görünmek istiyorum", "like": "Beğen"}}[lang]
        pg.get_by_text(t["demo"]).first.click()
        time.sleep(1)
        pg.get_by_text(t["demo2"]).last.click()
        time.sleep(7)  # demo claim + first suggestion on the fake provider

        def shot(name):
            path = out / f"raw-{lang}-{name}.png"
            pg.screenshot(path=str(path))
            shots[name] = Image.open(path)

        # Like the first outfit (so Saved has one), then shoot Today scrolled to the outfit card.
        like = pg.get_by_role("button", name=t["like"])
        if like.count():
            like.first.click(); time.sleep(1)
        scroll_to(pg, 0.47)  # the first outfit card, below the weather header
        shot("today")
        scroll_to(pg, 0)
        field = pg.get_by_placeholder(t["field"]).first if pg.get_by_placeholder(t["field"]).count() else None
        if field:
            field.fill("lots of walking, want to look sharp" if lang == "en" else "çok yürüyeceğim, şık olsun")
            time.sleep(0.5)
            shot("request")
        pg.get_by_text(t["wardrobe"], exact=True).last.click(); time.sleep(2); shot("wardrobe")
        pg.get_by_text(t["saved"], exact=True).last.click(); time.sleep(2); shot("saved")
        pg.get_by_text(t["profile"], exact=True).last.click(); time.sleep(2); shot("profile")
        pg.get_by_text(t["wardrobe"], exact=True).last.click(); time.sleep(1)  # the analysis link is on the Wardrobe tab
        link = pg.get_by_role("button", name=t["analysis"])
        if link.count():
            link.first.click(); time.sleep(2); shot("analysis")
        browser.close()
    return shots


def frame(screen: Image.Image, caption: str, size: tuple[int, int]) -> Image.Image:
    """Caption on top, the screen below with rounded corners, on the app's oyster background."""
    W, H = size
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(str(FONT), int(W * 0.062))
    y = int(H * 0.06)
    for line in caption.split("\n"):
        d.text((W // 2, y), line, font=font, fill=INK, anchor="mt")
        y += int(W * 0.078)
    top = y + int(H * 0.03)
    sw = int(W * 0.84)
    sh = int(screen.height * sw / screen.width)
    img = screen.convert("RGB").resize((sw, sh), Image.LANCZOS)
    r = int(sw * 0.09)
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, sw - 1, sh - 1], r, fill=255)
    # a soft shadow
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([(W - sw) // 2 + 6, top + 18, (W + sw) // 2 + 6, min(H, top + sh) + 18], r, fill=(42, 27, 38, 60))
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), shadow).convert("RGB"))
    canvas.paste(img, ((W - sw) // 2, top), mask)
    return canvas


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("docs/store/screenshots"))
    ap.add_argument("--web", default="http://127.0.0.1:8081/")
    ap.add_argument("--lang", choices=["en", "tr"], default=None, help="default: both")
    args = ap.parse_args()
    for lang in [args.lang] if args.lang else ["en", "tr"]:
        raw = args.out / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        shots = capture(args.web, lang, raw)
        for size_name, size in SIZES.items():
            folder = args.out / lang / size_name
            folder.mkdir(parents=True, exist_ok=True)
            n = 0
            for name, caption in CAPTIONS[lang]:
                if name not in shots:
                    print(f"  skip {lang}/{name}: not captured")
                    continue
                n += 1
                frame(shots[name], caption, size).save(folder / f"{n:02d}-{name}.png")
            print(f"{lang}/{size_name}: {n} screenshots → {folder}")


if __name__ == "__main__":
    main()
