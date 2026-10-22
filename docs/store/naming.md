# Name search — 22 Oct 2026

Brief: a real fashion-culture concept (not an invented startup word), short, global, pronounceable in Turkish.
Rejected earlier for collisions or trademark risk: SmartWardrobe (generic, many "Smart …" apps), FitCheck (three
"FitCheck" wardrobe/AI-stylist apps on the App Store, two on Play, plus US "FITCHECK" software trademark filings from
2023 and Feb 2025), Closy (two apps), Vestra, Garderob, Kombin (existing apps).

Method: every candidate got at least two web searches (`"<name>" app outfit OR wardrobe OR closet`, `"<name>" app
store`); the shortlist also trademark/domain searches. DEAD = a fashion/wardrobe app or well-known fashion brand
already uses it; RISKY = adjacent use or too generic to own; CLEAN = nothing in fashion after both searches.

## Finalists

| Name | Status | Why it fits | TR pronunciation | Subtitle | Risk |
|---|---|---|---|---|---|
| **Lookwise** | CLEAN | "look" is the fashion noun for an outfit; "-wise" = smart about looks (weather, taste) | luk-vayz | Outfits from your own closet | coinage of two real words; Looker/Looka exist in unrelated spaces |
| **Pairwell** | CLEAN | pairing pieces well is the product; "wears well" | per-vel | Your clothes, paired daily | Pair Networks has litigated "Pair"-prefixed names; keep one word, file early |
| Lapel | RISKY | garment-culture word, tailored/premium feel, matches the dark icon | la-pel | Daily outfits from what you own | dormant 2012 LA menswear concierge "Lapel"; LAPELS dry-cleaning TM; no app conflict |
| Lineup | RISKY | the day's lineup of pieces | layn-ap | Today's outfit, from your wardrobe | many sports/event "Lineup" apps; noisy store search |
| Worn | RISKY | calm, honest: what you've worn / will wear | vorn | Wear what you already own | very generic; pending WORN clothing TM (class 25) |
| Rail | RISKY | the clothes rail — exactly the icon | reyl | Outfits from your rail | one letter from the Rails fashion brand; needs a qualifier |
| Cuff | RISKY | garment detail, short | kaf | Dress from your own closet | "Cuff & Collar" retailer app, a Cuff BP tracker |
| Hem | RISKY | three letters, tailoring | hem | — | Turkish conjunction ("hem … hem"); sounds like H&M |

Recommendation: Lookwise, then Pairwell; Lapel if a single dictionary word matters more than a clean mark.

## Everything screened

| Candidate | Status | Evidence |
|---|---|---|
| The Edit | DEAD | "The Edit" outfit app (apps.apple.com id6744655316); Net-a-Porter magazine |
| Daily Fit | DEAD | DailyFit fitness apps (id1498034568, id1609715138) |
| Wearlist | DEAD | "Wearlist: Outfit Planner" (id6761500544) |
| Rotation / The Rotation | DEAD | By Rotation rental app (id1476610390); Rotation Exchange (id6757110238) |
| Rotate | DEAD | Danish fashion brand ROTATE |
| Staples / Staple | DEAD | Staples retailer; Staple Design / Staple Pigeon |
| GetDressed | DEAD | "Dressed" wardrobe app (id883938724) |
| Lookbook | DEAD | "LookBook: Endless Fashion Recs" (id6745403880); lookbook.nu |
| Capsule | DEAD | "CAPSULE - Wardrobe" (id1614620831); Capsule Wardrobe Builder (id1633936834) |
| Layered | DEAD | "AI Outfit Maker: Layered" (id6746713932) |
| Layers | RISKY | Layered above; Layr Style startup |
| OOTD | DEAD | "Outfit Planner: OOTD" (id6757398954); OOTD.io |
| Uniform | DEAD | "UNIFORM" — outfits from what you already own (id6547170781) |
| GRWM | DEAD | GRWM AI Stylist (id6737596512), GRWM AI (id6742329531) |
| Looks | DEAD | "Looks: Outfits Manager" (id1603511595); Looksy |
| Daily Look | DEAD | DailyLook styling subscription (id807735146) |
| Wear Today | DEAD | WearToday (2014) |
| Rewear | DEAD | "AI Clothes Changer: ReWear" (id6740744747) |
| Wearlog | DEAD | LookLog (id6738351992); WEARLOG trademark |
| Dress Code | DEAD | "Dress code" shop app; "Dresscode: AI Clothes Changer" |
| Outfitted | DEAD | outfitted.carrd.co; OUTFITTED trademark |
| Styled | DEAD | generic, dozens of listings |
| Rack | DEAD | Rack Tribe (id1572059904); Nordstrom Rack |
| Rails | DEAD | Rails LA clothing brand |
| Hanger / Hangr | DEAD | "HangRr: Outfit Ideas" (id1191937444); hanger.io |
| Wearwell | DEAD | wearwell styling subscription |
| Wornwell | DEAD | WornWell Clothing |
| Fitwise / Fitboard / Good Fit | DEAD | fitness apps; GOODFIT trademark |
| FitList | RISKY | "Fits" app dominates; generic |
| Seam | DEAD | Seam designer marketplace |
| Silhouette | DEAD | "Silhouette AI" try-on (id1439773567) |
| Ensemble | RISKY | Shopify "Ensemble" outfit app |
| Tailor | DEAD | "Tailor: Style & Color Analysis" (id6739644750) |
| Dapper | DEAD | Dapper menswear app |
| Drop | DEAD | "Style Drop: Wardrobe Organizer" (id6754234221) |
| Pieces | RISKY | "Concept Pieces" sneaker app; generic |
| Garb | RISKY | GarbShare startup |
| Everyday | RISKY | generic |
| Lookwise, Pairwell | CLEAN | see finalists |
| Lapel, Lineup, Worn, Rail, Cuff, Hem | RISKY | see finalists |

## Rename checklist (once decided)

`app/src/lib/brand.ts` (`APP_NAME` — the policy, e-mails and every screen read it), `app/app.json` `name`,
backend `EMAIL_FROM` default (`app/config.py`, `.env.example`, the Space secret), `docs/store/listing.md`
(`{{NAME}}`), READMEs, Sentry project names (cosmetic). Keep: bundle id / package `com.fomertech.smartwardrobe`,
EAS slug, repo name, `wardrobe.fomertech.com` (add a second hostname later if wanted).
