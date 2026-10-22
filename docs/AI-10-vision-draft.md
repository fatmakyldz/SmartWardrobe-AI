# After V1.0: from "digital closet" to a decision engine — DRAFT, not approved

Status: a proposal for discussion (22 Oct 2026). `AI-00-foundation.md` stays the approved architecture; nothing here
changes it until it is folded into §13 as new rows. The thesis (Fatma's note of 22 Oct): the category is a feature
race, so the way to stand out is not another feature but a loop — **scan → learn → dress → learn → buy smarter** —
where the app knows the person and predicts what they will wear.

## What already exists (so the plan builds, not rebuilds)

| Vision piece | In V1.0 today | Gap |
|---|---|---|
| "It learns from behaviour, no forms" | `feedback_events` (like / skip / worn), `recently_worn`, `RECENT FEEDBACK` line in the suggest prompt, `build_summary` → `TASTE SUMMARY` (8 template sentences from liked/skipped/worn) | the learning is a *text summary* read by the model; no per-attribute weights, no "this jacket keeps getting skipped" memory, no occasion-conditioned habits |
| "Good morning, here's your fit" | Today auto-suggests on open with weather + occasion; outfits carry a `reason`; `Wear this / Try another` ≈ `Wore it today / Suggest again` | occasion is still asked; no calendar; the reason is the model's prose, not grounded facts ("not worn for 23 days") |
| "Zero-effort wardrobe" | one photo → tags in seconds (tagging v2 with confidence) | one piece per photo; experiment harness for several-per-photo in `scripts/experiments/multi_garment.py` |
| "What's missing / what to add" | deterministic `ai/analysis.py` gaps + capsule | no link to shopping; no cost-per-wear |
| Style DNA percentages | style questionnaire (3 answers) + taste summary | no numeric profile |

## The six engines and where they land (revised 22 Oct, after the beta plan)

One data loop feeds everything: wardrobe → wear history → Style Brain → declutter → gaps → shopping. The engines are
not features to add; they are views on the same profile, so AI-10 comes first and the rest read it.

| Engine | What it is | Version | Needs beyond V1.0 data |
|---|---|---|---|
| 1 Style Brain | the taste profile: what you choose, skip, wear, pair; per occasion | **Public V1.0** (gated on beta Tur 2) | AI-10 row in §13 |
| 2 Wardrobe Intelligence | never / rarely / most worn, forgotten pieces, hard-to-combine, duplicates, heroes | V1.1 | nothing: `wear_count`, `last_worn_at`, `analysis.py` |
| 3 Revive | "not worn for 4 months — here are 3 outfits with it" | V1.1 | suggest with an `include` piece (exists for intent) |
| 4 Declutter | Keep / Restyle / Sell / Donate, one piece at a time, with the reasons from 1–3 | V1.2 | `archived_at` (exists), a decision event, optional `items.price` for cost-per-wear |
| 5 Shopping Intelligence | "should I buy this?" — tag a shared photo/link, match against the real wardrobe; wardrobe gaps as a shopping list | V2 | share-sheet entry, no retailer integration |
| 6 Shopping Agent / search | "a jacket under 3.000 TL that makes 10+ outfits with my wardrobe", "pack for Italy in May and find what's missing" | V2.x | web search, price/stock/size, affiliate — the separate beast |

Fast Wardrobe (multi-item scan) sits beside these as an onboarding engine, gated on the #32 experiment (≥ 18/20).
Public V1.0 = Fast Wardrobe + AI Styling + Style Brain (+ multi-item if it passes). Nothing else, by decision.

Data to collect from now on so the later engines have history: like / skip / worn / last worn (collected),
suggested-but-never-chosen (derivable from `outfit_items` + feedback), raw AI tags vs edited (collected since the
beta-instrumentation PR), piece price (optional field, AI-10 schema), declutter decisions (V1.2 event).

## Proposed phases (one PR each, same discipline as AI-01…09)

### AI-10 Taste model (the learning loop) — V1.1
Replace the prose-only memory with a small, deterministic **taste profile** computed from the person's own events —
no new prompts, no LLM in the loop, pure functions in `ai/analysis.py`-style code:
- per-attribute scores from like / skip / worn with time decay: colour pairs, silhouettes (subcategory), formality
  band, layering, pattern; per-occasion where there are enough events ("work: plain, dark"; "evening: bolder").
- per-piece signals: skip streak ("suggested 5×, never chosen"), days since worn, favourite pairings.
- `style_summary` keeps being generated, but from the profile (fewer, truer sentences), and the suggest context gets
  a compact `TASTE PROFILE:` line (budgeted ~120 tokens) plus `AVOID:` pieces with long skip streaks.
- Style DNA for the person: `GET /me/style` returns the top axes as percentages (Minimal 72 % …) — derived from the
  same scores, shown on the Style screen; no quiz.
- Schema: one new table `taste_profiles(user_id, computed_at, profile JSON)` recomputed after feedback (cheap) — or
  computed on the fly for V1.1 and cached; decide in the design row.
- KPI: like-rate of the first suggestion per day (baseline from `ai_report.py` first), skip-rate of "AVOID" pieces → 0.

### AI-11 Proactive morning fit — V1.1
"Open the app, no questions":
- the occasion comes from habit (`taste profile` per weekday/hour) and, if connected, the calendar (`expo-calendar`,
  read-only, on device; only the next event's title words and time leave the phone — opt-in, in the policy).
- grounded `Why this?`: facts assembled server-side before the model writes (rain after 17:00 → no suede; jacket
  unworn 23 days; matches liked outfits) and passed as `WHY FACTS:` so the prose cannot invent them.
- one notification at the person's usual time ("Your fit for today is ready") — `expo-notifications`, opt-in.
- KPI: time from app open to "Wore it" < 20 s; share of days with a worn outfit.

### AI-12 Zero-effort wardrobe — V1.2, **only if the experiment passes**
- run `multi_garment.py` on 20 real photos first (rule in ROADMAP: ≥ 18/20 boxed cleanly).
- if yes: `POST /items/analyze-many` → boxes → one upload + tagging per crop (reuses the single-piece path; the
  per-crop confidence from tagging v2 decides what to show as "check this"); the app shows a grid "8 pieces found —
  add all / fix".
- closet video scan: not before AI-12 proves the photo path; a video is just frames + the same detector.

### AI-13 Buy smarter — V1.3
- "Should I buy this?": the person shares a product link or photo → tag it like a piece (no upload to the wardrobe)
  → deterministic match against the real wardrobe (`analysis.py`: how many outfits it unlocks, near-duplicates,
  gaps it fills) → `Wardrobe match 91 % · pairs with 14 pieces · you already own two black blazers`.
- cost-per-wear from `wear_count` / price if entered. Affiliate revenue is a later decision, not a V1.3 goal.
- KPI: share of shares that end in "not buying" (the honest one) and in "added to wishlist".

## Order and why
AI-10 first: it is pure code on data we already collect, needs no permission prompts, and every later phase (why-
facts, proactive occasion, buy-match) reads the same profile. AI-11 second because it is the daily ritual. AI-12 is
gated on evidence. AI-13 last; it is the most novel and the one that earns a paid plan.

## Not in this draft
Virtual try-on, social sharing / "rate my fit", wishlist sync with retailers — the competitors' feature race; revisit
only if the loop above works and users ask.
