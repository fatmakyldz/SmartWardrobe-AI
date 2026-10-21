# Store privacy forms — what to tick

The answers below follow what the code does (see the in-app policy, `app/src/content/privacy.ts`, and design §9).
Re-check them whenever a new SDK or data flow lands. No ads, no analytics SDK, no tracking across apps.

Facts the forms are built on:

| Data | Where it goes | Why |
|---|---|---|
| E-mail, name | our DB (Neon) · Resend (verification / reset mails only) | account |
| Password | our DB, hashed (Argon2id) | account |
| Language, time zone | our DB | app functionality |
| City + coordinates (optional; device location read once with permission, or a city search) | our DB · Open-Meteo (coordinates only, no account) | weather for outfits |
| Photos of clothes | our object store (R2, private, expiring links) · Anthropic / Groq (reduced copy, for tagging) | app functionality |
| Tags, outfits, likes/skips/worn, style answers, taste summary | our DB · Anthropic / Groq (piece descriptions, never photos, for suggestions) | app functionality, personalisation |
| Daily AI request counts; AI request records linked to the account for ≤ 90 days | our DB | plan limits, abuse prevention |
| Pseudonymous user id | Sentry (with crash reports), AI request records | diagnostics, grouping |
| IP address | server logs / rate limiter, transient; never with the account; stripped from Sentry | abuse prevention |
| Crash / error data (stack, route, app version, device model/OS) | Sentry | diagnostics |

Not collected: contacts, health, financial info, purchases (no IAP yet), browsing/search history outside the app,
device identifiers for advertising, precise location history (a single read, only when the person taps "use my location").

## App Store Connect → App Privacy

**Do you or your third-party partners collect data from this app?** Yes.

Data types (tick these; for each: *linked to the user's identity* = Yes, *used for tracking* = No, purposes as listed):

| Data type | Linked | Tracking | Purposes |
|---|---|---|---|
| Contact Info → Email Address | Yes | No | App Functionality |
| Contact Info → Name | Yes | No | App Functionality |
| Location → Precise Location | Yes | No | App Functionality *(only if the person uses "use my location"; the city they pick otherwise)* |
| User Content → Photos or Videos | Yes | No | App Functionality |
| User Content → Other User Content *(tags, outfits, style answers, notes)* | Yes | No | App Functionality, Product Personalization |
| Identifiers → User ID | Yes | No | App Functionality, Analytics *(usage counters)* |
| Usage Data → Product Interaction *(likes, skips, worn, request counts)* | Yes | No | App Functionality, Product Personalization, Analytics |
| Diagnostics → Crash Data | Yes *(Sentry events carry the pseudonymous user id)* | No | App Functionality |
| Diagnostics → Performance Data | No — not collected (tracing off) | | |

Not ticked: Health & Fitness, Financial Info, Contacts, Browsing History, Search History *(the free-text outfit request is not a search history; it is user content)*, Sensitive Info, Purchases, Advertising Data, Device ID, Other Diagnostic Data.

**Tracking:** No. The app does not use data to track across apps/websites and does not show ads; no App Tracking Transparency prompt is needed.

**Privacy policy URL:** `https://wardrobe.fomertech.com/privacy` (the in-app page; public, EN/TR by device language).

**Account deletion:** in-app (Profile → Delete account), immediate — required by guideline 5.1.1(v). Data export is also in-app (Profile → Download my data).

**Age rating questionnaire:** none of the content flags (no violence, no mature themes, no gambling, no unrestricted web access); the app does not target children; 4+ / "Made for Kids" = No. Policy says not intended for under-16.

## Google Play Console → Data safety

**Does your app collect or share any of the required user data types?** Yes.
**Is all of the user data collected by your app encrypted in transit?** Yes (HTTPS everywhere; the API is behind Cloudflare).
**Do you provide a way for users to request that their data is deleted?** Yes — in-app account deletion; also e-mail `support@fomertech.com`.

Per data type (Collected = Yes; Shared = as noted; Processed ephemerally = No unless noted; Required/Optional; purposes):

| Data type | Shared? | Required | Purposes |
|---|---|---|---|
| Personal info → Email address | Shared with Resend (service provider, mail delivery only) | Required | Account management |
| Personal info → Name | No | Required | Account management, App functionality |
| Location → Precise location | Shared with Open-Meteo (coordinates only; service provider) | Optional | App functionality |
| Photos and videos → Photos | Shared with Anthropic / Groq (reduced copy; service providers, no training) | Optional *(the demo wardrobe needs none)* | App functionality |
| App activity → Other user-generated content *(tags, outfits, style answers, free-text requests)* | Shared with Anthropic / Groq (descriptions only) | Optional | App functionality, Personalization |
| App activity → App interactions *(likes, skips, worn, request counts)* | No | Optional | App functionality, Personalization, Analytics |
| App info and performance → Crash logs | Shared with Sentry (service provider) | Optional | Analytics *(Play's closest purpose for diagnostics)* |
| Device or other IDs → *not collected* (no advertising id; the account id is "Personal info → User IDs")  | | | |
| Personal info → User IDs *(pseudonymous account id)* | Shared with Sentry (crash reports) | Required | Account management, Analytics |

Not collected: Financial info, Health and fitness, Messages, Audio, Files and docs, Calendar, Contacts, Web browsing, Installed apps, Approximate location (precise or nothing), Device or other IDs.

**Security practices:** Data is encrypted in transit — Yes. Users can request deletion — Yes. (Independent security review — No.)

**Sharing wording for the policy:** every "shared" row above is a service provider acting on our behalf, no data is sold, and none is shared for advertising — this matches the policy's "we do not sell it" and the providers list.

## Permissions the app declares (for the review notes)

- Photos / camera — to photograph clothes (`expo-image-picker`; strings in `app.json`).
- Location, while in use — optional, to pick the city for the weather (`expo-location`).
- No background location, no contacts, no microphone, no Bluetooth.

## Review notes to paste (both stores)

> The app suggests outfits from the clothes the user photographs. A sample wardrobe is available without an account (Welcome → "Try with a sample wardrobe"), so reviewers can see every feature without adding photos. AI tagging and suggestions use third-party model providers (Anthropic, Groq) as processors; photos are stored privately and never used for training. Account deletion and data export are in Profile. Privacy policy: https://wardrobe.fomertech.com/privacy
