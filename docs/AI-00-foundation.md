# SmartWardrobe — Phase AI-00 Foundation Design

Oct 19, 2026 · @fatma

## Kapsam

Bu plan, audit'teki (commit `30afd71`, 16 Ekim 2026) kod üzerine, 15 kilitli kararı uygulayacak temeli tasarlar. Kod, migration, UI, sağlayıcı faturalama veya ödeme sağlayıcısı seçimi yok; kodlama bu plan onaylandıktan sonra AI-01'den başlar.

**Kilitli kararlar (kısaca):** Claude birincil + Groq fallback; Haiku-sınıfı tagging, Sonnet-sınıfı öneri; kullanıcı başı günlük token bütçesi; R2 private + presigned URL; e-posta/şifre + doğrulama + sıfırlama + kısa access + refresh/revoke (sosyal giriş V1.1, ikisi birlikte); kullanıcı kombini + `outfit_items`; 3 soruluk onboarding + açık stil tercihi + 👍/👎 + "giydim"; senkron AI; config-driven freemium (Free 50 parça / 5 öneri-gün, Premium 300 parça); entitlement önce, sağlayıcı sonra; kapsül gardırop V1.0, seyahat V1.1; ad şimdilik SmartWardrobe AI; onboarding = 3 soru → demo kombin → kendi gardırobu; demo gardırop gerçek hesaba taşınabilir.

**Değişmeyen temel:** FastAPI + SQLAlchemy 2 + Alembic, Neon Postgres, Expo app; LLM hiçbir zaman DB'ye doğrudan yazmaz; tüm yapılandırılmış çıktı sunucu tarafından şema, vocab ve ownership kurallarıyla doğrulanır; mevcut entity'lere referans gereken özelliklerde (suggest) yalnız izin verilen id/index'ler kullanılabilir. Mikroservis, Redis, job kuyruğu yok.

**Durum: FINAL / APPROVED** (19 Ekim 2026). İkinci inceleme turundaki 7 düzeltme işlendi: LLM çıktı kuralı genelleştirildi, `ai_requests` / `ai_request_attempts` ayrıldı, bütçe her denemenin gerçek token'ını sayar, `budget_exceeded` 429 oldu, entitlements hesabı subscription state'i değiştirmez, social-login/password\_hash kararı V1.1 migration'ına bırakıldı, tablo sayısı ve `ai_tags_raw` tanımı düzeltildi. Kodlama AI-01 ile başlar; her faz: PR → test → Claude raporu → review → merge.

## 1. Target architecture

Mevcut düz yapı (`routers/` + `ai.py` + `llm.py` + `storage.py`) üç yeni pakete ayrılır: `services/`, `entitlements/`, `ai/`. Router'lar incelir; domain (iş) verisini yazan tek katman `services` olur; `ai/` paketi kullanıcı kimliği, e-posta ya da DB session almaz.

&#91;embedded content: hedef katmanlar · bağımlılık yukarıdan aşağı, yasak kenarlar notta\]

Router her AI isteğinde aynı sırayı izler: entitlement kontrolü → context derleme (services'ten okur) → gateway çağrısı → doğrulanmış sonucu services ile kaydet. LLM çıktısı DB'ye yalnız bu son adımda, sunucu doğrulamasından geçtikten sonra girer.

**İzinli bağımlılıklar:**

| Katman | Şunları çağırabilir | Şunları çağıramaz |
| --- | --- | --- |
| `routers` | services, entitlements, ai.context, ai.gateway, security | providers, storage (doğrudan), models (yazma) |
| `services` | models/db, storage, weather | ai (hiç), entitlements |
| `entitlements` | models/db (usage, subscriptions), config | ai, services, sağlayıcı SDK'ları |
| `ai.context` | yalnız DTO girdisi (router toplar), vocab | services, db session, providers |
| `ai.gateway` | ai.providers, ai.prompts, ai.schemas, `ai_requests` yazma (tek istisna, aşağıda) | models (users/items/outfits), storage, services |
| `ai.providers` | httpx / SDK | her şey |
| `storage` | boto3, config | models (R2 modunda `images` tablosu kullanılmaz) |

**DB yazma kuralı (netleştirildi):** *Business/domain state* (users, items, outfits, outfit\_items, feedback\_events, wardrobe\_images) yalnız `services` üzerinden yazılır. *Infrastructure state* yalnız sahibi olan dar repository tarafından, kendi tablosuna yazılır: `ai/telemetry` → `ai_requests`, `ai_request_attempts`; `entitlements/usage` → `usage_counters`; `entitlements/grants` → `entitlement_grants`; `entitlements/subscriptions` (V1.0'da boş, sağlayıcı webhook'u gelince dolar) → `subscriptions`; `security` → `refresh_tokens`, `auth_tokens`. Kural: **`entitlements(user)` hesaplama fonksiyonu yalnız okur; subscription ya da grant state'ini asla değiştirmez.** Bu kümeler kesişmez.

**`ai.context` saflık kuralı:** `ai.context` services'i çağırmaz. Router (ya da ince bir orchestration fonksiyonu `services/orchestration.py`) veriyi toplar ve DTO olarak verir; `ai.context` DTO alır, DTO döner, DB ve ağ görmez.

**Tek istisna:** gateway kendi telemetrisini yazar: mantıksal istek başına bir `ai_requests` satırı, sağlayıcı denemesi başına bir `ai_request_attempts` satırı. Bu yazma `ai/telemetry.py` içinde dar bir repository fonksiyonuyla yapılır ve `subject_id` (users.id, pseudonymous — e-posta/ad asla) dışında kullanıcı verisi taşımaz. Bütçe kontrolü için gateway `entitlements.check_ai_budget(subject_id, feature)` çağırır; dönen şey yalnız `allowed: bool` + `remaining`.

**Mevcut koddan eşleme:** `routers/items.py:analyze` → `services.wardrobe.store_upload` + `ai.features.tagging`; `routers/outfits.py:suggest` → `ai.context.build_suggest_context` + `ai.features.suggest` + `services.outfits.save_suggestions`; `demo.py` → `services/demo.py`; `ai.py` → `ai/features/` + `ai/schemas/`; `llm.py` → `ai/providers/groq.py`.

## 2. Database migration plan

On yeni tablo, üç mevcut tabloya alan ekleme; hepsi **tek Alembic revizyonu `0002_ai_foundation`** olarak, `0001`'in üstüne. Mevcut dört tablo (`users`, `items`, `outfits`, `images`) silinmez; `outfits.item_ids` ve `images` yalnız veri taşındıktan sonra, ayrı bir revizyonda (`0003_cleanup`) kaldırılır.

**Mevcut tablolara eklenen alanlar**

| Tablo | Yeni alanlar | Not |
| --- | --- | --- |
| `users` | `email_verified_at` (ts, null), `token_version` (int, 0), `style_profile` (JSON: onboarding cevapları + explicit tercihler), `style_summary` (text, AI/kural özeti), `style_summary_at` (ts), `plan` (str, 'free'), `onboarding_completed_at` (ts, null), `timezone` (str, null), `updated_at` | `plan` denormalize; kaynak `subscriptions`. `style_profile` şeması: `{answers:{q1,q2,q3}, liked_colors[], disliked_colors[], styles[], avoid[]}` |
| `items` | `brand` (str 80, ''), `material` (str 40, ''), `is_favorite` (bool), `wear_count` (int, 0), `last_worn_at` (ts, null), `archived_at` (ts, null), `ai_tags_raw` (JSON, null), `ai_confidence` (float, null), `ai_request_id` (FK ai\_requests, null), `updated_at` | `ai_tags_raw` = şemadan geçmiş, vocab'a zorlanmış ama kullanıcı tarafından henüz düzeltilmemiş yapılandırılmış tag seti (ham model metni saklanmaz); kullanıcı düzeltmesi `tags` ile farkı → kalite metriği |
| `outfits` | `source` (enum: ai / user / ai\_edited), `prompt_version` (str, null), `ai_request_id` (FK, null), `worn_at` (ts, null), `updated_at`; `item_ids` **kalır** (0003'te düşer) | `rating` kalır (son durum); olay geçmişi `feedback_events` |

**Yeni tablolar**

| Tablo | Amaç | Önemli kolonlar | Kısıtlar / indeksler | Retention / gizlilik |
| --- | --- | --- | --- | --- |
| `outfit_items` | kombin ↔ parça ilişkisi, sıra | `outfit_id` FK cascade, `item_id` FK cascade, `position` (int), `slot` (str: top/bottom/…) | PK (outfit\_id, item\_id); idx item\_id | parça silinince satır da silinir; outfit boş kalırsa `outfits.incomplete` görünümü app'te |
| `ai_requests` | mantıksal AI isteğinin telemetrisi (kullanıcı başına bir istek = bir satır) | `id`, `subject_id` (UUID, users.id ile **FK yok** — pseudonymous; kullanıcı silinince bağ kopar), `feature`, `prompt_version`, `status` (ok/fallback/error/budget), `final_provider`, `final_model`, `final_model_class`, `input_tokens_total`, `output_tokens_total`, `cost_usd_micro_total`, `latency_ms_total`, `attempts_count`, `fallback_used` (bool), `prompt_hash`, `created_at` | idx (subject\_id, created\_at); idx (feature, created\_at) | prompt/çıktı metni **yok**; 90 gün sonra `subject_id` null'lanır (90 güne kadar pseudonymous, sonra anonim agregat) |
| ai\_request\_attempts | her sağlayıcı denemesi (retry ve fallback dahil); maliyet ve hata analizi | id, request\_id FK ai\_requests cascade, attempt\_no (int), provider, model, status (ok/timeout/rate\_limited/bad\_output/error), error\_code, input\_tokens, output\_tokens, cost\_usd\_micro, latency\_ms, created\_at | unique (request\_id, attempt\_no); idx (provider, created\_at) | kullanıcı verisi yok; ai\_requests ile birlikte silinir/anonimleşir |
| `feedback_events` | 👍/👎 ve "giydim" olay geçmişi | `id`, `user_id` FK cascade, `outfit_id` FK set null, `item_id` FK set null, `kind` (like/dislike/unrate/worn/skip), `created_at` | idx (user\_id, created\_at) | hesap silmede cascade |
| `wardrobe_images` | R2 nesne metadata'sı | `key` PK (str 160), `user_id` FK cascade, `item_id` FK set null, `content_type`, `bytes`, `width`, `height`, `created_at`, `attached_at` (null = yetim) | idx (user\_id); idx (attached\_at) partial null | yetim 24 saat sonra silinir; `images` blob tablosunun yerini alır |
| `refresh_tokens` | oturumlar | `id`, `user_id` FK cascade, `token_hash` (sha256, unique), `family_id` (UUID), `device_label`, `expires_at`, `revoked_at`, `replaced_by` (FK self, null), `created_at`, `last_used_at` | unique token\_hash; idx (user\_id) | ham token asla saklanmaz; süresi dolan 30 gün sonra silinir |
| `auth_tokens` | e-posta doğrulama ve şifre sıfırlama | `id`, `user_id` FK cascade, `purpose` (verify\_email/reset\_password), `token_hash` unique, `expires_at`, `used_at` | idx (user\_id, purpose) | tek kullanımlık; 24 saat / 1 saat ömür |
| `subscriptions` | plan durumu (sağlayıcıdan bağımsız) | `id`, `user_id` FK cascade, `plan` (str), `status` (active/trialing/past\_due/canceled), `provider` (str, null — manual/apple/google/stripe), `provider_ref` (str, null), `current_period_end` (ts, null), `created_at`, `updated_at` | idx (user\_id, status); unique (provider, provider\_ref) partial | sağlayıcı seçilince yalnız webhook yazar |
| `usage_counters` | plan limiti sayaçları | `user_id` FK cascade, `feature` (str), `period_start` (date), `count` (int), `tokens` (int) | PK (user\_id, feature, period\_start) | UPSERT ile artar; 400 gün sonra silinir |
| entitlement\_grants | abonelik dışı haklar: promosyon, hediye premium, tester/influencer, destek kararı | id, user\_id FK cascade, plan\_override (str, null), feature (str, null), limits (JSON, null), source (promo/support/tester/manual), reason (str 200), starts\_at, ends\_at (null = süresiz), created\_by (str), created\_at | idx (user\_id, ends\_at); check: plan\_override veya feature veya limits dolu | hesap silmede cascade; reason serbest metin, PII yazılmaz |

`entitlements` tablo değil, `plans` config'i (YAML/py dict) + `subscriptions`'tan türetilen fonksiyon; ayrı tablo kurmak sağlayıcıya bağlı bir şema kilitler (bkz. §7).

**Mevcut verinin migrasyonu (0002 içinde, veri adımı):**

1. `outfits.item_ids` → `outfit_items`: her outfit için JSON listesi okunur, var olan `items.id`'lerle eşleşenler `position` sırasıyla yazılır; eşleşmeyenler atlanır (bugün de serialize'da atlanıyor). `source='ai'`.
2. `outfits.rating != 0` → `feedback_events` (kind like/dislike, created\_at = outfit.created\_at).
3. `users.plan = 'free'`, `token_version = 0`, `email_verified_at = NULL`. **Stop condition:** mevcut gerçek kullanıcı var mı? Varsa doğrulanmamış e-posta ile giriş engellenirse kilitlenirler → mevcut hesaplar `email_verified_at = created_at` ile işaretlenmeli (karar §14).
4. `images` → R2: ayrı bir komut (`scripts/migrate_images_to_r2.py`), migration içinde değil (ağ işlemi, yeniden çalıştırılabilir olmalı). Her blob R2'ye aynı key ile yüklenir, `wardrobe_images` satırı yazılır, doğrulama sonrası `0003`'te `images` düşer.
5. Demo kullanıcılar: migration öncesi `cleanup_expired_demos` çalıştırılır; kalanlar normal akışla taşınır.

SQLite testleri için: `Uuid`, `JSON`, partial index desteği sınırlı — partial index'ler `postgresql_where` ile yalnız Postgres'te oluşturulur, SQLite'ta düz indeks.

## 3. AI package design

Mevcut `ai.py` (174 satır) ve `llm.py` (64 satır) aşağıdaki pakete dağılır; dışarıya yalnız `gateway.complete()` ve `features.*` fonksiyonları açılır.

```
app/ai/
  __init__.py          # public: features, gateway, context, errors
  gateway.py           # complete(request) → response; routing, retry, fallback, bütçe, telemetri
  routing.py           # config → (feature, model_class) → [provider, model] zinciri
  errors.py            # AIError(code) hiyerarşisi; HTTP'ye çeviri routers'ta
  telemetry.py         # ai_requests yazımı (dar repository), maliyet hesabı
  providers/
    base.py            # Provider protokolü: complete_json(messages, model, schema, timeout) → ProviderResult
    anthropic.py       # Claude Messages API (resmi SDK), tool-use/JSON şema zorlaması
    groq.py            # mevcut llm.py taşınır (OpenAI-uyumlu, json_object)
    fake.py            # testler: kuyruklanmış cevaplar, hata enjeksiyonu
  prompts/
    registry.py        # get(feature, version) → PromptTemplate; sürümler dosya adında
    tagging/v1.md      # system prompt + örnek çıktı; {vocab} yer tutucuları
    suggest/v1.md
    intent/v1.md       # doğal dil → yapılandırılmış istek
    capsule/v1.md      # deterministik analiz sonucu → açıklama
  schemas/
    tagging.py         # TaggingOut (Pydantic) = model çıktısının şeması; vocab'a coerce burada
    suggest.py         # SuggestOut: outfits[{title, items[int], reason}]
    intent.py, capsule.py
    context.py         # SuggestContext, TaggingContext DTO'ları (gateway'e giden tek girdi tipi)
  context.py           # build_suggest_context(...), build_tagging_context(...): saf fonksiyonlar
  features/
    tagging.py         # tag_image(ctx) → TaggingOut (clean_tags burada)
    suggest.py         # suggest(ctx) → list[ValidatedOutfit] (validate_outfits burada)
    intent.py          # parse_request(text, lang) → SuggestIn alanları
    capsule.py         # analyze(wardrobe) deterministik + explain(ctx) LLM
```

| Parça | Sorumluluk | Bilmez |
| --- | --- | --- |
| `gateway.py` | tek giriş; `AIRequest` alır, routing'den zinciri alır, deneme/fallback döngüsünü yürütür, şema doğrular, `ai_requests` yazar | kullanıcı kimliği (yalnız `subject_id`), DB modelleri, HTTP |
| `routing.py` | `settings.ai_routes` (JSON/YAML) → model zinciri; model adı yalnız burada ve config'de | prompt içeriği |
| `providers/*` | ağ çağrısı, sağlayıcıya özgü JSON zorlama, token sayımı, hata sınıflandırma (`rate_limited`, `timeout`, `bad_output`) | feature, bütçe, retry (gateway yapar) |
| `prompts/` | metin + sürüm; `{vocab}`, `{lang}` gibi yer tutucular; sistem prompt'u sabit (prompt caching için) | kullanıcı verisi (context ayrı mesajda) |
| `schemas/` | model çıktısının katı tipi; Pydantic `model_validate` + vocab coerce (`clean_tags` mantığı) | — |
| `context.py` | services'ten okunan veriyi DTO'ya derler (§6); saf, DB'siz, test edilebilir | providers, gateway |
| `features/*` | bir ürün özelliği = context tipi + prompt + şema + doğrulama; router'ın çağırdığı yüzey | HTTP, DB yazma |

Mevcut `vocab.py` yerinde kalır (`app/vocab.py`); prompt'lar ve şemalar onu içe alır. Vocab'ı app'e de tek kaynaktan vermek için AI-05'te `GET /meta/vocab` endpoint'i eklenir (app'teki kopya düşer).

## 4. Gateway contract

Tek fonksiyon, tek girdi tipi, tek çıktı tipi. Gateway kullanıcı nesnesi, e-posta veya DB session almaz; bütçe kararını `entitlements`'a sorar, sonucu `ai_requests`'e yazar.

```python
@dataclass(frozen=True)
class AIRequest:
    feature: str                 # "tagging" | "suggest" | "intent" | "capsule_explain"
    subject_id: UUID             # pseudonymous; users.id ama gateway bunu kimlik olarak kullanmaz
    tier: str                    # entitlements.model_tier: "standard" | "premium"
    prompt_version: str          # "v1"; registry'de yoksa AIError("prompt_not_found")
    system_vars: dict            # prompt yer tutucuları (vocab, lang)
    user_content: list[Part]     # text ve image parçaları (derlenmiş context, ham DB satırı değil)
    schema: type[BaseModel]      # çıktı şeması; sağlayıcıya JSON şeması olarak da gider
    max_output_tokens: int
    timeout_s: float = 30
    idempotency_key: str | None  # aynı istek tekrarında ikinci çağrı yapılmaz (cache 60 s)

@dataclass(frozen=True)
class AIResponse:
    data: BaseModel              # şemadan geçmiş çıktı
    provider: str; model: str; model_class: str
    input_tokens: int; output_tokens: int; cost_usd_micro: int
    latency_ms: int; attempts: int; fallback_used: bool
    request_id: UUID             # ai_requests.id → outfits.ai_request_id'ye yazılır

def complete(req: AIRequest, *, budget: BudgetGate, telemetry: Telemetry) -> AIResponse: ...
```

**Akış (her çağrı):**

1. `budget.check(subject_id, feature, estimated_tokens)` → `BudgetDecision(allowed, remaining_requests, remaining_tokens)`; red → `AIError("budget_exceeded")`, `ai_requests.status='budget'` yazılır, sağlayıcıya gidilmez.
2. `routing.chain(feature, tier)` → sıralı `[(provider, model, model_class)]`, örn. `[(anthropic, haiku-x), (groq, qwen-x)]`.
3. Zincirde her aday için en fazla `attempts` deneme (config, varsayılan 2): `timeout` ve `rate_limited` → aynı adayda 1 retry (exponential backoff 0.5 s → 1.5 s), sonra sonraki aday; `bad_output` (şema hatası) → aynı adayda 1 retry "düzelt" mesajıyla, sonra sonraki aday; `auth`/`config` hatası → zincirde atla, alarm.
4. Çıktı `schema.model_validate` + vocab coerce; başarısızsa `bad_output`.
5. `telemetry.record(...)` mantıksal istek için bir ai\_requests satırı ve her sağlayıcı denemesi için bir ai\_request\_attempts satırı yazar; `budget.consume(subject_id, feature, tokens)` her denemenin gerçek token'ını yazar — başarısız ama sağlayıcının faturaladığı çağrılar dahil (timeout → retry → fallback döngüsü krediyi koruma altında); günlük istek sayacı (daily\_ai\_requests) yalnız başarılı mantıksal istekte artar. Kural: istek limiti = başarılı kullanıcı isteği, token/maliyet limiti = tüm faturalanabilir sağlayıcı çağrıları.
6. Zincir tükenirse `AIError("ai_unavailable")`.

**Hata kodları (`AIError.code` → HTTP, routers'ta çevrilir):**

| code | HTTP | Anlam |
| --- | --- | --- |
| `budget_exceeded` | 429 | günlük istek/token limiti doldu (kota, ödeme değil); detail.remaining ve `detail.reset_at` ile |
| `feature_not_allowed` | 403 | plan bu özelliği içermiyor |
| `ai_busy` | 503 | tüm adaylar rate limit/timeout |
| `ai_unavailable` | 503 | sağlayıcı hatası, zincir tükendi |
| `ai_bad_reply` | 502 | şemaya uymayan çıktı (retry sonrası) |
| `ai_not_configured` | 503 | anahtar yok (mevcut kodla aynı) |
| `prompt_not_found` | 500 | geliştirici hatası |

`402 Payment Required` ileride gerçekten ödeme gerektiren duruma (`subscription_required`) saklanır; kota aşımı 429'dur, slowapi'nin `rate_limited` 429'undan `detail.code` ile ayrılır.

**Observability kancası:** gateway her denemede `ai_request_id`, `feature`, `provider`, `model`, `status`, `latency_ms`, `attempt` alanlarıyla yapılandırılmış bir log satırı yazar (JSON); prompt metni ve `user_content` loglanmaz, yalnız `prompt_hash` ve `input_tokens`. `settings.ai_debug_log=true` iken (yalnız lokal) tam prompt stderr'e yazılır.

**Rate limit:** mevcut slowapi kullanıcı-başı saatlik limitler router'da kalır (burst koruması); günlük plan limiti ise `entitlements` üzerinden gateway'de. İki katman farklı soruya cevap verir, birleştirilmez.

## 5. Provider routing

Model adları yalnız config'de yaşar; kod `model_class` (haiku/sonnet/groq-fast/groq-vision) ve `feature` bilir. Config JSON olarak `AI_ROUTES` env'inden ya da `ai/routes.default.json`'dan okunur; env ile tek bir satır değiştirmek modeli değiştirir, deploy gerekmez.

```json
{
  "models": {
    "claude-small-vision": {"provider": "anthropic", "model": "<haiku-sınıfı model id>", "in_usd_per_mtok": 0, "out_usd_per_mtok": 0},
    "claude-mid":          {"provider": "anthropic", "model": "<sonnet-sınıfı model id>", "in_usd_per_mtok": 0, "out_usd_per_mtok": 0},
    "groq-vision":         {"provider": "groq", "model": "qwen/qwen3.8-27b", "in_usd_per_mtok": 0, "out_usd_per_mtok": 0},
    "groq-text":           {"provider": "groq", "model": "openai/gpt-oss-120b", "in_usd_per_mtok": 0, "out_usd_per_mtok": 0}
  },
  "routes": {
    "tagging":         {"standard": ["claude-small-vision", "groq-vision"], "premium": ["claude-small-vision", "groq-vision"]},
    "suggest":         {"standard": ["claude-mid", "groq-text"],   "premium": ["claude-mid", "groq-text"]},
    "intent":          {"standard": ["claude-small-vision", "groq-text"],   "premium": ["claude-small-vision", "groq-text"]},
    "capsule_explain": {"standard": ["claude-small-vision", "groq-text"],   "premium": ["claude-mid", "groq-text"]}
  },
  "attempts_per_candidate": 2,
  "timeouts_s": {"tagging": 30, "suggest": 45, "intent": 15, "capsule_explain": 30}
}
```

Model id'leri ve fiyatlar kodlama başlamadan önce docs.claude.com'dan doğrulanıp doldurulur (burada bilerek boş). Tagging için Haiku-sınıfı görsel destekli model şart; `routes.standard.suggest` de lansman döneminde Sonnet-sınıfı (C7: ilk izlenim maliyetten önce; free zaten 5 öneri/gün ile sınırlı). Kullanıcı büyüyünce free'yi Haiku-sınıfına çekmek tek satır config değişikliği.

**Sağlayıcı farkları providers/ içinde kapatılır:** Anthropic'te şema zorlaması tool-use (tek araç, `input_schema` = Pydantic JSON şeması) ile; Groq'ta `response_format: json_object` + mevcut `_extract_json`. Görseller Anthropic'e base64 `image` bloğu, Groq'a `image_url` data-URL olarak gider; `Part` tipi ikisine de çevrilir. Prompt caching: Anthropic'te sistem prompt'u `cache_control` ile işaretlenir (sabit metin, vocab dahil); Groq'ta yok sayılır.

**Sağlık ve devre kesici (V1.0 için hafif):** bir sağlayıcı 5 dakikada 5 ardışık `timeout/5xx` verirse `routing` onu 2 dakika zincirin sonuna atar (in-memory; tek instance kabulü ile uyumlu). Groq fallback'in de bir günlük token tavanı vardır (ücretsiz katman limiti), config'de `daily_cap_tokens`.

## 6. Context compilation

`ai/context.py` DB'ye dokunmaz: router önce `services` ile verileri çeker, sonra bu saf fonksiyonlara verir. Her fonksiyon aynı girdiye aynı çıktıyı üretir, dolayısıyla snapshot testi yazılabilir.

```python
def build_suggest_context(
    items: list[ItemDTO], weather: WeatherDTO | None, occasion: str, note: str,
    intent: IntentDTO | None, profile: StyleProfileDTO, summary: str,
    recent_feedback: list[FeedbackDTO], recently_worn: list[UUID], lang: str,
    *, limits: ContextLimits = DEFAULT,
) -> SuggestContext: ...
```

**Adımlar ve bütçe (token tahmini \~4 karakter/token):**

| Adım | Kural | Çıktı | Tahmini boyut |
| --- | --- | --- | --- |
| 1. Wardrobe pre-filter | arşivli parça dışarı; mevsim ∩ (bugünün mevsimi) boşsa dışarı; `warmth` hava ile uyumsuz (feels\_like > 24 → warmth ≥ 4 dışarı, < 8 → warmth ≤ 1 dışarı); occasion `formality` penceresi (casual 1-3, work 2-4, formal 4-5, sport 1-2, date 2-4, party 2-5, travel 1-3); kategori başına tavan (top 20, bottom 12, dress 8, outerwear 8, shoes 8, bag 5, accessory 8) — son giyilenler ve favoriler önce, sonra `created_at` desc | `items_kept`, `items_dropped_count`; aday < 2 kategoriyse filtre gevşetilir (mevsim → warmth → formality sırasıyla) | ≤ \~70 parça × 25 token ≈ 1.800 |
| 2. Weather | mevcut `_weather_line` + mevsim etiketi | 1 satır | 40 |
| 3. Occasion + note + intent | intent varsa (doğal dil parse edilmiş) occasion/kısıtlar ondan; `note` 200 kr ile sınırlı, PII regex'i (e-posta, telefon) maskelenir | 2 satır | 80 |
| 4. Style profile | onboarding cevapları + explicit tercihler → 3-4 kısa satır ("prefers: minimal, dark neutrals; avoids: floral") |  | 60 |
| 5. Feedback summary | ham 20 kombin listesi yerine `users.style_summary` (periyodik üretilen tek paragraf, §10) + son 5 olayın kombin imzası (kategori+renk, id değil) |  | 150 |
| 6. Recently worn | son 7 günde `worn_at` olan parçalar: "recently worn, prefer variety" listesi (index numaraları) |  | 40 |

Toplam sistem prompt (sabit, cache'lenebilir) \~600 token + context \~2.200 token; bugünkü "tüm gardırop + 20 geçmiş" yaklaşımına göre 300 parçalı kullanıcıda yaklaşık üçte bir.

**Tagging context:** 640 px JPEG + `lang` + vocab; kullanıcı verisi yok (bugünkü gibi).

**Deterministiklik:** parça sıralaması `(is_favorite desc, last_worn_at desc nulls last, created_at desc, id)` ile sabit; index numaraları bu sıraya göre verilir ve `SuggestContext.index_to_item_id` ile birlikte döner — `validate_outfits` bu haritayı kullanır. Tarih/mevsim fonksiyona `today` parametresi olarak girer (test için sabitlenir).

## 7. Entitlements & usage

Router'lar yalnız `entitlements(user)` çağırır ve dönen nesneye bakar; plan adı, sağlayıcı ve ücret hiçbir router'da geçmez. Plan tanımları config'dir, sağlayıcı yalnız `subscriptions` satırını günceller.

```python
@dataclass(frozen=True)
class Entitlements:
    max_items: int                 # free 50, premium 300
    daily_ai_requests: int         # free 5, premium 60 (placeholder)
    daily_ai_tokens: int           # token bütçesi (gateway bunu sorar)
    allowed_features: frozenset[str]   # {"tagging","suggest","intent"} | + {"capsule","user_outfits"...}
    model_tier: str                # "standard" | "premium" → routing anahtarı
    history_limit: int             # Saved'de kaç kombin

def entitlements(user: User, db) -> Entitlements        # base plan → aktif subscription → entitlement_grants (override)
def require_feature(ent, feature)                      # AIError("feature_not_allowed")
def check_ai_budget(db, subject_id, feature, est_tokens) -> BudgetDecision
def consume(db, subject_id, feature, tokens)           # UPSERT usage_counters
```

**Plan config (`plans.default.json`, env ile override):**

```json
{
  "free":    {"max_items": 50,  "daily_ai_requests": 5,  "daily_ai_tokens": 40000,  "features": ["tagging","suggest","intent","user_outfits"], "model_tier": "standard", "history_limit": 30},
  "premium": {"max_items": 300, "daily_ai_requests": 60, "daily_ai_tokens": 600000, "features": ["tagging","suggest","intent","user_outfits","capsule"], "model_tier": "premium", "history_limit": 500},
  "demo":    {"max_items": 17,  "daily_ai_requests": 5,  "daily_ai_tokens": 40000,  "features": ["suggest","intent"], "model_tier": "standard", "history_limit": 10}
}
```

Demo hesap ayrı bir "plan" olarak modellenir (ekstra bayrak yerine); mevcut `is_demo` alanı kalır, `plan='demo'` ile eşlenir.

**Entitlement grants (eklendi):** `entitlement_grants` tablosu promosyon, hediye premium, test/influencer hesabı, destek tarafından verilen hak ve mağaza ↔ web abonelik çakışmasını DB hack'i olmadan çözer. `entitlements(user)` üç katmanı sırayla uygular: (1) `plans[users.plan ?? "free"]` taban; (2) aktif `subscriptions` satırı varsa onun planı; (3) `starts_at ≤ now < ends_at` olan grant'ler — `plan_override` varsa planı değiştirir, `feature` varsa yalnız o özelliği ekler, `limits` JSON'u varsa alan bazında üst üste yazar. Birden çok grant'te en cömert değer kazanır. Sonuç 60 saniye bellekte cache'lenir (tek instance).

**Gün sınırı:** `period_start = (now at users.timezone ?? UTC).date()`; timezone yoksa UTC. Limit mesajı `reset_at` taşır.

**Sayaç ↔ `ai_requests` mutabakatı:** `usage_counters` hızlı yol (tek UPSERT, limit kontrolü); `ai_requests` doğruluk kaynağı. Günlük bir komut (`scripts/reconcile_usage.py`, V1.0'da elle/CI cron ile) dünün `ai_requests` toplamını `usage_counters` ile karşılaştırır, farkı loglar ve sayaçları `ai_requests`'e göre düzeltir. Fark %1'i geçerse uyarı. Bu, in-memory ya da yarışma kaynaklı kaymaları kendi kendine onarır; Redis gerekmez.

**Yarış durumu:** `check` + `consume` iki ayrı sorgu; eşzamanlı iki istek limiti 1 aşabilir. V1.0 için kabul edilir (bütçe güvenlik ağı, faturalama değil); istenirse `UPDATE ... WHERE count < limit RETURNING` ile atomik hale getirilir, şema değişmez.

**`max_items`:** mevcut `MAX_ITEMS = 300` sabiti `routers/items.py`'den çıkar, `ent.max_items` olur; arşivli parçalar sayılmaz.

## 8. Storage foundation

Mevcut `Storage` protokolü ve `S3Storage` sınıfı korunur; eksik olan **private bucket + presigned URL + metadata tablosu**. `DbStorage` yalnız test/lokal için kalır (SQLite ile çalışsın diye), üretimde `STORAGE_BACKEND=s3` zorunlu olur.

| Konu | Tasarım |
| --- | --- |
| Bucket | tek private R2 bucket (`smartwardrobe-media`), public access kapalı, CORS yalnız app origin'leri; `S3_PUBLIC_BASE_URL` kullanımdan kalkar |
| Object naming | mevcut `u/{user_hex}/{uuid}.webp` korunur (ownership prefix'te); ileride `u/{user}/items/{uuid}.webp` ve `u/{user}/thumbs/{uuid}.webp` (256 px küçük görsel, grid için) |
| Ownership | `wardrobe_images.user_id` + key prefix; `POST /items` zaten prefix'i doğruluyor, buna ek olarak `wardrobe_images` satırının o kullanıcıya ait ve `attached_at IS NULL` olması şartı |
| Presigned URL | `GET` için 15 dakikalık presigned URL; `ItemOut.image_url` bu URL'yi taşır. App tarafında TanStack Query `staleTime` 10 dk → URL dolmadan yenilenir; `expo-image` cache key olarak URL değil `image_key` kullanır (query param değişse de cache'ten okur) |
| Upload flow | V1.0'da mevcut akış kalır (app → API → R2): API zaten yeniden kodlayıp EXIF temizliyor, bu da R2'ye doğrudan yüklemeyi (presigned PUT) dışarıda bırakıyor. `analyze`: normalize → `storage.put` → `wardrobe_images` (attached\_at NULL) → AI → cevap. `POST /items`: `attached_at = now`, `item_id` set. |
| Delete flow | `DELETE /items/{id}`: DB satırı silinir, R2 silme **sonra** ve hata toleranslı (başarısızsa `wardrobe_images.item_id=NULL`, `attached_at=NULL` ile yetim gibi işaretlenir, cleanup alır) |
| Orphan cleanup | `scripts/cleanup_orphans.py`: `attached_at IS NULL AND created_at < now-24h` → R2 sil + satır sil; ayrıca R2 `list_objects` ile DB'de olmayan nesneler (çift yönlü mutabakat), haftalık |
| Migration from DB blobs | `scripts/migrate_images_to_r2.py`: `images` tablosunu sayfalar hâlinde okur, `put` eder, `wardrobe_images` satırı yazar (`user_id` key prefix'ten), `items.image_key` değişmez. İdempotent (var olan key atlanır). Doğrulama: `items` ∖ `wardrobe_images` boş olmalı. Sonra `STORAGE_BACKEND=s3`, sonra `0003` ile `images` düşer. |
| Account deletion | mevcut `delete_prefix(u/{user}/)` korunur, R2'de sayfalı silme zaten var; `wardrobe_images` cascade |
| Cache policy | `Cache-Control: private, max-age=900` (presigned ömrüyle aynı); `immutable` ve public cache kalkar; CDN yok |
| Demo görselleri | her demo hesapta 17 görsel kopyalamak yerine `demo/{file}.webp` altında bir kez yüklenir; demo item'ların `image_key` bu paylaşımlı key'i gösterir, `wardrobe_images.user_id = NULL` (sistem nesnesi), silmeden muaf. Gerçek hesaba taşıma (karar 15) kopya ile yapılır. |

**Mevcut kodla çakışma:** `/images/{key}` endpoint'i R2 modunda gereksizleşir; DB modunda kalır ama `current_user` zorunlu olur ve key'in kullanıcıya ait olması kontrol edilir (yetkisiz görsel erişimi testi §12).

## 9. Auth foundation

Mevcut HS256 JWT ve Argon2id kalır; değişen şey token ömrü, refresh/revoke tabloları ve iki e-posta akışı. E-posta göndermek yeni bir bağımlılık (karar §14'te işaretli).

| Konu | Tasarım |
| --- | --- |
| Access token | JWT, **15 dakika**, payload `{sub, iat, exp, tv}` (`tv` = `users.token_version`). `current_user` token'daki `tv` ≠ DB'dekiyse 401. Bu, şifre değişikliği / "tüm cihazlardan çık" için tek satırlık global revoke sağlar. |
| Refresh token | 32 byte rastgele, yalnız `sha256` hash'i `refresh_tokens`'ta; **30 gün**; her kullanımda **rotasyon** (yeni token, eski `replaced_by` ile işaretlenir, aynı `family_id`). Eski bir token yeniden kullanılırsa (çalıntı belirtisi) tüm `family` revoke. |
| Endpoint'ler | `POST /auth/login` → `{access, refresh, user}`; `POST /auth/refresh {refresh}` → yeni çift; `POST /auth/logout {refresh}` → o token revoke; `POST /auth/logout-all` → `token_version += 1` + tüm refresh revoke. Mevcut `TokenOut.token` → `access` olarak yeniden adlanır (app değişikliği AI-03'te). |
| E-posta doğrulama | kayıtta `auth_tokens(purpose=verify_email, 24 saat)`; kullanıcı doğrulamadan uygulamayı kullanabilir ama AI özellikleri `email_verified_at` ister (`feature_not_allowed` yerine `email_unverified` 403). Demo hesaplar muaf. `POST /auth/verify {token}`, `POST /auth/resend-verification` (5/saat). |
| Şifre sıfırlama | `POST /auth/forgot {email}` → her zaman 200 (enumeration önleme), `auth_tokens(reset_password, 1 saat)`; `POST /auth/reset {token, password}` → şifre güncellenir, `token_version += 1`, tüm refresh revoke. |
| Account deletion | mevcut `/me DELETE` korunur; ek: refresh/auth token cascade (FK), `ai_requests.subject_id` anonimleştirilir (FK yok, ayrı UPDATE), R2 prefix silme. Silme tek transaction + storage adımı sonra. |
| Web token handling | `localStorage` yerine access token yalnız bellekte; refresh token **httpOnly, Secure, SameSite=Lax cookie** (`/auth/refresh` ve `/auth/logout` path'inde). CORS `allow_credentials=True` + origin listesi zorunlu olur (`CORS_ORIGINS` boş = `*` kabul edilmez üretimde). |
| Mobile token handling | ikisi de SecureStore; app açılışında access süresi dolmuşsa `refresh` çağrısı; 401 → refresh dene → yine 401 → sign out (mevcut `onUnauthorized` kancası genişler). |
| Rate limit | login 20/15dk, forgot 5/saat, refresh 60/saat (kullanıcı), register 10/saat (IP). `ProxyHeadersMiddleware.trusted_hosts` HF Space proxy aralığına kısıtlanır. |
| Sosyal giriş (V1.1) | `users.password_hash` V1.0'da NOT NULL kalır; sosyal hesaplar için `auth_identities(user_id, provider, provider_sub)` tablosu V1.1'de eklenir. Social-only hesaplara ("Apple ile devam et", şifre yok) izin verilecekse V1.1 migration'ında password\_hash nullable yapılır ya da credentials ayrı tabloya taşınır; bu karar o migration'da alınır, V1.0 şeması onu zorlamaz ama otomatik de çözmez. |

**E-posta gönderimi:** V1.0 için transactional e-posta sağlayıcısı gerekir (C2 kararı: Resend — ücretsiz katman başlangıç için yeterli). `services/email.py` arkasında tek `send(template, to, vars)` fonksiyonu; test ortamında `fake` backend token'ı loga yazar.

## 10. Onboarding & personalization data flow

Hedef akış "3 soru → anında demo kombin → kendi gardırobu"; mevcut demo altyapısı bunu neredeyse bedavaya sağlar. Aşağıda her adımda hangi tablo yazılır ve AI context'ine ne girer.

| Adım | Kullanıcı ne yapar | Ne yazılır | Context'e etkisi |
| --- | --- | --- | --- |
| 1. Stil soruları (max 3) | Q1 tarz (3-4 chip: minimal / klasik / rahat / cesur), Q2 renk dünyası (nötr / koyu / canlı / pastel, çoklu), Q3 "kombin seçerken öncelik" (rahatlık / şıklık / hava / çeşitlilik) | `users.style_profile.answers` (hesap yoksa app state'inde tutulur, hesap/demo açılınca yazılır) | §6 adım 4 "style profile" satırları |
| 2. Anında demo kombin | hesap açmadan: `POST /auth/demo {locale, style_profile}` → demo gardırop + cevaplar; Today'de ilk öneri otomatik tetiklenir (bir `suggest` kotası) | `users(plan=demo)`, 17 demo item (paylaşımlı görsel), `outfits(source=ai)` | ilk öneri zaten profil + hava ile |
| 3. Beğeni | 👍/👎 | `feedback_events(kind)` + `outfits.rating` | son 5 olay imzası |
| 4. Gerçek hesaba geçiş | "kendi gardırobumu kur": kayıt formu; `POST /auth/register {..., claim_demo_token}` | demo user'ın `style_profile`, `outfits`, `feedback_events` yeni kullanıcıya **taşınır** (user\_id güncellenir); demo item'lar isteğe bağlı kopyalanır ("örnek parçaları tut" seçeneği) — karar 15 | profil korunur |
| 5. Kendi parçaları | foto ekle → AI etiket → onay | `items` (+ `ai_tags_raw`, `ai_confidence`), `wardrobe_images.attached_at` | gardırop ön filtre |
| 6. Explicit tercihler | Profile'da "sevdiğim renkler / kaçındıklarım / tarz" chip'leri | `users.style_profile.{liked_colors, disliked_colors, styles, avoid}` | style profile satırları |
| 7. "Bugün giydim" | kombin kartında tek dokunuş | `outfits.worn_at`, her parça için `items.wear_count += 1`, `last_worn_at`; `feedback_events(kind=worn)` | recently worn listesi (7 gün) |
| 8. Tercih özeti | sistem; **LLM değil, kural tabanlı** V1.0'da: son 30 olayın parça/renk/formality dağılımı → 3-4 cümle şablon ("koyu nötrleri, loafer'ı tercih ediyor; floral'dan kaçınıyor") | `users.style_summary`, `style_summary_at`; her 10 olayda ya da 7 günde bir, senkron (ucuz) | §6 adım 5; ham geçmiş listesi prompt'tan çıkar |

**Ne yazılmaz:** onboarding cevapları AI'ya ham değil, kısa etiketler olarak gider; `note` metni özete girmez; demo kullanıcının verisi 24 saat sonra silinir (claim edilmediyse).

**Mevcut kodla ilişki:** `demo.py`'deki `create_demo_user` `style_profile` parametresi alır; `routers/auth.py:register` `claim_demo_token` ile demo kullanıcıyı doğrular (geçerli demo JWT) ve taşıma yapar. `today.tsx` "ilk açılışta otomatik öner" davranışı yalnız `plan=demo` ve `outfits` boşken.

## 11. Observability & cost

İki kaynak: `ai_requests` tablosu (doğruluk, sorgulanabilir) ve yapılandırılmış JSON log satırları (anlık). Ayrı bir metrik sistemi V1.0'da yok; HF Space logları + Neon'da birkaç SQL görünümü yeter.

**Saklanan alanlar (her `ai_requests` satırı):** `feature`, `prompt_version`, `provider`, `model`, `model_class`, `status` (ok/fallback/error/budget), `error_code`, `input_tokens`, `output_tokens`, `cost_usd_micro`, `latency_ms`, `attempt`, `fallback_from`, `prompt_hash`, `subject_id`, `created_at`. Maliyet, `routes` config'indeki `in/out_usd_per_mtok` ile anında hesaplanır (fiyat değişirse config değişir; geçmiş satırlar o günkü fiyatla kalır).

**İki seviye:** `ai_requests` mantıksal isteğin toplamını (`*_total`, `attempts_count`, `fallback_used`, `final_*`) taşır; `ai_request_attempts` her denemenin `provider`, `model`, `status`, `error_code`, token ve maliyetini. `outfits.ai_request_id` ve `items.ai_request_id` yalnız `ai_requests.id`'ye bağlanır. Fallback oranı ve hata oranı attempts tablosundan, maliyet/kullanıcı requests tablosundan hesaplanır.

**Türetilen metrikler (SQL görünümleri, `scripts/ai_report.py` ile günlük özet):**

| Metrik | Hesap | Alarm eşiği (öneri) |
| --- | --- | --- |
| Maliyet / gün ve / kullanıcı | `sum(cost_usd_micro)` by date, by subject | gün > 10 USD; tek kullanıcı > 1 USD |
| Token in/out by feature | sum by feature, model | suggest ortalama input > 4.000 token (context şişmiş) |
| Latency p50/p95 by feature, provider | percentile\_cont | suggest p95 > 20 s |
| Fallback oranı | `status='fallback'` / toplam | > %10 |
| Hata oranı | `status='error'` / toplam, by error\_code | > %5 |
| Budget red oranı | `status='budget'` / toplam | > %20 (limitler çok sıkı) |
| Kullanıcı/gün kullanım | distinct subject by date; `usage_counters` ile mutabakat | — |
| Tag düzeltme oranı | `items.ai_tags_raw` ≠ kaydedilen tag (kategori/renk) | > %30 (prompt/model kalitesi) |
| Öneri kabul oranı | like / (like+dislike), worn / suggested | — |

**Varsayılan olarak loglanmayanlar:** prompt metni, model çıktısı, görsel, `note`, e-posta, ad, konum koordinatı. Groq/Anthropic hata gövdeleri ilk 200 karakterle sınırlı ve `subject_id`'siz. `AI_DEBUG_LOG=true` yalnız lokal; config `database_url` Postgres ise bu bayrak başlangıçta reddedilir (mevcut `SECRET_KEY` kontrolüyle aynı desen).

**Retention:** `ai_requests.subject_id` 90 gün sonra NULL; satırlar 13 ay saklanır (yıllık karşılaştırma), sonra aylık agregata indirilir. Uygulama hata takibi için Sentry benzeri bir araç AI-09'da (V1.0 hardening) değerlendirilir, zorunlu değil.

## 12. Test strategy

Mevcut düzen korunur: pytest + SQLite + `TestClient` + `monkeypatch`; buna `providers/fake.py` ve Postgres karşı bir CI işi eklenir. Hedef: AI-04 sonunda her hata kodu ve her katman sınırı için en az bir test.

| Katman | Yöntem | Kapsanan senaryolar |
| --- | --- | --- |
| Unit — `ai/context` | saf fonksiyon, sabit `today`, snapshot | ön filtre kuralları (sıcak/soğuk/formality/kategori tavanı), gevşetme sırası, deterministik sıralama, PII maskeleme, token tahmini üst sınır |
| Unit — `ai/schemas` | Pydantic | LLM **invalid output**: eksik alan, yanlış tip, vocab dışı değer, 999 id, aynı kategori iki parça, tekrar eden kombin (mevcut `test_suggest_validates_and_learns` buraya taşınır) |
| Unit — `ai/gateway` + `providers/fake` | fake provider: cevap kuyruğu + hata enjeksiyonu (`timeout`, `rate_limited`, `bad_output`, `auth`) | retry sayısı, **fallback** zinciri (Claude → Groq), `ai_busy` vs `ai_unavailable`, idempotency cache, devre kesici, telemetri satırı her denemede, `cost_usd_micro` hesabı |
| Unit — `entitlements` | SQLite | plan config yükleme, `entitlements(user)` demo/free/premium, **daily budget exceeded** (`budget_exceeded` + `reset_at`), timezone gün sınırı, `max_items` **entitlement limit**, `feature_not_allowed` |
| Integration — API | `TestClient`, fake provider, fake storage, fake email | analyze → create → suggest → feedback → worn → summary akışı; `email_unverified` 403; demo claim taşıması; `GET /meta/vocab` |
| Security | `TestClient` | **unauthorized image access** (başka kullanıcının key'i, presigned URL olmadan `/images` 401/404); **cross-user wardrobe access** (başkasının item/outfit id'si → 404, başkasının `image_key` ile POST /items → 400 — mevcut test genişler); **expired/revoked refresh token** (401; reuse → family revoke); `token_version` artınca eski access 401; `trusted_hosts` ile `X-Forwarded-For` sahteciliği limiti atlatamıyor; CORS origin dışı reddi |
| Migration | CI'da Postgres servisi: `alembic upgrade head` → `downgrade -1` → `upgrade head` | **migration parity**: `0002` sonrası `Base.metadata` ile DB şeması farkı yok (`alembic check`); veri adımı: örnek `outfits.item_ids` → `outfit_items` satır sayısı eşit, rating → feedback\_events; SQLite'ta aynı migration'lar çalışıyor |
| Storage | moto/`fake S3` ya da `DbStorage` | presigned URL üretimi ve süresi, yetim temizliği (24 saat), silme hatasında yetim işaretleme, demo paylaşımlı görsel silinmiyor, hesap silmede prefix temizliği |
| Smoke (manuel, AI-04 ve AI-09) | gerçek Claude + Groq anahtarıyla 5 tagging + 5 suggest | şema uyumu, gerçek latency, maliyet kaydı |

**Test altyapısı değişiklikleri:** `conftest.py`'ye `fake_provider`, `fake_storage`, `fake_email`, `frozen_time` fixture'ları; `AI_ROUTES` testte fake provider'a işaret eder; limiter `reset()` korunur. CI `backend.yml`'e Postgres service container ve `alembic check` adımı eklenir.

## 13. Implementation phases

Sıra mevcut koddaki bağımlılıklara göre belirlendi; önerilen listeden tek fark, **storage/auth'un (AI-05) gateway'den (AI-03) önce değil sonra** gelmesi: gateway ve entitlements app'i hiç değiştirmeden backend'de bitirilebilirken, auth değişikliği app'e dokunur ve e-posta sağlayıcısı kararını bekler. Her faz kendi PR'ı, kendi testleri ve yeşil CI ile biter.

| Faz | Kapsam | Bağımlılık | Çıkış kriteri |
| --- | --- | --- | --- |
| **AI-01 Quick fixes** | `analyze`'ı sync/threadpool; Today önerilerini query cache'e; `trusted_hosts` daraltma; `MAX_ITEMS` sabitini config'e; `AGENTS.md`/README güncelle | — | mevcut testler yeşil, app davranışı aynı |
| **AI-02 Schema migration** | `0002_ai_foundation` (tüm tablolar/alanlar, veri adımı), modeller, `alembic check` CI, Postgres CI servisi | AI-01 | parity testi; eski endpoint'ler aynı çıktıyı veriyor (`item_ids` hâlâ okunuyor) |
| **AI-03 AI gateway + entitlements** | `app/ai/` paketi, `providers/anthropic ∥ groq ∥ fake`, `routing`, `telemetry`, `entitlements/`, `usage_counters`; mevcut iki özellik gateway'den geçer; `plans` config | AI-02 | fake provider testleri, fallback/budget testleri; gerçek Claude anahtarıyla 5 tagging + 5 suggest smoke |
| **AI-04 Context + services** | `services/` ayrımı (router incelir), `ai/context.py`, tercih özeti (kural tabanlı), `outfit_items` kullanımı, `GET /meta/vocab`, feedback/worn endpoint'leri (`POST /outfits/{id}/worn`, `POST /outfits` user kombini) | AI-03 | context snapshot testleri; suggest input token'ı ölçüldü |
| **AI-05 Storage + auth foundation** | R2 private + presigned, `wardrobe_images`, yetim temizliği, blob migration script'i; access/refresh/revoke, doğrulama, sıfırlama, e-posta servisi; app token akışı | AI-02 (şema); e-posta: Resend; alan adı: api.fomertech.com | security testleri; `STORAGE_BACKEND=s3` ile smoke; `0003_cleanup` hazır ama uygulanmamış |
| **AI-06 Intelligence features** | doğal dil intent, eksik parça analizi, kapsül gardırop (deterministik + açıklama), premium model routing | AI-04 | her feature için şema + fake testi; maliyet ölçümü |
| **AI-07 Onboarding + personalization (app)** | 3 soru, demo'dan claim, otomatik ilk öneri, explicit tercih ekranı, "giydim", kullanıcı kombini düzenleme ekranı, eksik parça / kapsül ekranları, yeni auth ekranları | AI-04, AI-05, AI-06 | uçtan uca akış cihazda; EN/TR |
| **AI-08 Entitlements UI + usage** | limit mesajları, "premium" bayrakları (ödeme yok), `reconcile_usage`, `ai_report` | AI-03, AI-07 | limitler config'den değişince app'te yansıyor |
| **AI-09 Public V1.0 hardening** | `0003_cleanup` uygulama, gizlilik politikası sayfası, export endpoint'i, Sentry kararı, uptime, store metadata, marka/bundle id kararı | hepsi | Phase 3/4 roadmap maddeleri kapanır |

AI-03 ve AI-05 paralel yürütülebilir (farklı dosyalar; ikisi de AI-02'ye yaslanır). AI-07 en büyük faz; gerekirse AI-07a (onboarding/claim) ve AI-07b (kombin düzenleme/kapsül) olarak bölünür.

## 14. Stop conditions / open conflicts

Kilitli kararlardan hiçbiri mevcut kodla **teknik olarak çakışmıyor**; aşağıdakiler varsayım yapmadan karar istediğim noktalar. Her biri bir satırla kapanır; kapanmadan ilgili faz başlamaz.

| # | Konu | Neden karar gerekiyor | Seçenekler | Blokladığı faz |
| --- | --- | --- | --- | --- |
| C1 | **Üretim DB'sinde gerçek kullanıcı var mı?** | Varsa `email_verified_at` NULL kalınca AI özelliklerinden kilitlenirler; `item_ids` → `outfit_items` taşıması gerçek veriyle test edilmeli | (a) henüz canlı değil, veri yok → migration düz; (b) var → mevcut hesaplar `email_verified_at = created_at` ile işaretlenir, Neon branch'inde prova | AI-02 |
| C2 | **E-posta sağlayıcısı** | Doğrulama ve sıfırlama e-posta ister; yeni bağımlılık ve alan adı DNS kaydı (fomertech.com) | Resend / Postmark / Amazon SES / Cloudflare Email… — ücretsiz katman ve TR teslimat oranına göre | AI-05 |
| C3 | **Doğrulanmamış hesap neleri kullanabilir?** | Karar 5 doğrulamayı şart koşuyor ama "ilk 60 saniye" hedefi sürtünme istemiyor | (a) gardırop serbest, AI doğrulama ister (önerim); (b) her şey doğrulama ister; (c) 7 gün grace | AI-05 |
| C4 | **R2 görsel URL'leri app'te nasıl yenilenir?** | 15 dk presigned URL, Saved listesindeki eski outfit görselleri süresi dolmuş URL taşıyabilir | (a) her yanıt taze URL üretir + app `staleTime` 10 dk (önerim); (b) 24 saatlik URL; (c) API proxy `GET /images/{key}` auth'lu (R2'den geçirir, basit ama API bant genişliği) | AI-05 |
| C5 | **Demo görselleri paylaşımlı mı?** | Bugün her demo hesap 17 kopya üretiyor; paylaşımlı key `wardrobe_images.user_id = NULL` istisnası getirir | (a) paylaşımlı (önerim, DoS maliyeti düşer); (b) kopya, mevcut davranış | AI-05 |
| C6 | **Groq fallback görsel için şart mı?** | Claude Haiku-sınıfı vision düşerse Groq vision (qwen) farklı kalitede etiket üretir | (a) fallback var, `ai_requests.fallback_from` ile işaretli (önerim); (b) tagging'de fallback yok, `ai_busy` döner | AI-03 |
| C7 | **Free katmanda suggest modeli** | Routing taslağında free = Haiku-sınıfı; kalite farkı kullanıcıya hissedilirse ilk izlenim zayıflar | (a) free de Sonnet-sınıfı, limit düşük (5/gün zaten az; maliyet 200 USD içinde); (b) Haiku-sınıfı | AI-03 |
| C8 | **Web refresh token cookie** | httpOnly cookie API ve web'in farklı origin'lerde olmasını (hf.space ↔ vercel/fomertech) `SameSite=None; Secure` ve CORS credentials'a bağlar; üçüncü taraf cookie kısıtları Safari'de risk | (a) API'yi `api.fomertech.com` alt alanına alıp cookie'yi aynı site yapmak (önerim); (b) web'de de SecureStore gibi bellek + localStorage refresh (daha zayıf) | AI-05 |
| C9 | **`0003_cleanup` zamanı** | `images` ve `outfits.item_ids` düşürülmesi geri alınamaz | R2 migration doğrulandıktan ≥ 1 hafta sonra, AI-09'da (önerim) | AI-09 |
| C10 | **Model id'leri ve fiyatlar** | Config'de boş bırakıldı; kodlama öncesi docs.claude.com'dan doğrulanmalı | ben AI-03 başında doğrular, config'i doldururum | AI-03 |

**Kararlar (19 Ekim 2026, kilitlendi):**

- C1 → (a): canlı değil; yine de migration öncesi Neon'da `SELECT count(*) FROM users` zorunlu; test kullanıcısı varsa veri korunur, doğrulama davranışı lansman öncesi olduğu için sorun değil.
- C2 → Resend (ücretsiz katman: aylık 3.000 / günlük 100 e-posta; gerekirse Pro).
- C3 → (a): gardırop serbest, AI isteği doğrulama ister; demo hesaplarda AI doğrulamasız çalışır.
- C4 → (a): her yanıtta taze 15 dk presigned URL, app `staleTime` 10 dk.
- C5 → (a): demo görselleri paylaşımlı.
- C6 → (a): tagging'de Groq vision fallback, `fallback_from` ile işaretli.
- C7 → free'de de Sonnet-sınıfı (lansman dönemi); routing config'i §5'te güncellendi.
- C8 → (a): API `api.fomertech.com`, web `app.fomertech.com`; refresh cookie aynı site.
- C9 → `0003_cleanup` R2 migration doğrulandıktan ≥ 1 hafta sonra, AI-09'da.
- C10 → model id'leri ve fiyatlar AI-03 başında resmi dokümandan doğrulanır, şimdi sayı kilitlenmez.

Ek karar: `entitlement_grants` tablosu şemaya eklendi (§2, §7).

**Veri kaybı riski taşıyan adımlar (özel dikkat):** `0003_cleanup` (C9), R2 migration'da `images` okunurken Neon free tier bağlantı süresi (sayfalı ve idempotent script bu yüzden), demo claim'de `user_id` güncellemesi (transaction içinde).

## Final output

**ARCHITECTURE** — Mevcut FastAPI yapısı üç pakete ayrılır: `services/` (business/domain state'in tek yazıcısı; infrastructure tabloları kendi dar repository'leriyle yazılır), `entitlements/` (plan/limit, sağlayıcı bilmez), `ai/` (gateway + providers + prompts + schemas + context + features). Router orkestre eder: entitlement → context → gateway → services ile kaydet. Yasak kenarlar: ai→DB, ai→storage, services→ai, routers→providers. Tek istisna gateway'in `ai_requests` telemetrisi.

**DATA MODEL** — Tek revizyon `0002_ai_foundation`: `users` (+verified, token\_version, style\_profile/summary, plan, onboarding, timezone), `items` (+brand, material, favorite, wear\_count, last\_worn\_at, archived\_at, ai\_tags\_raw \[şemadan geçmiş, düzeltilmemiş tag seti\], ai\_confidence), `outfits` (+source, prompt\_version, ai\_request\_id, worn\_at); on yeni tablo: `outfit_items`, `ai_requests`, `ai_request_attempts`, `feedback_events`, `wardrobe_images`, `refresh_tokens`, `auth_tokens`, `subscriptions`, `usage_counters`, `entitlement_grants`. Veri adımı: `item_ids` → `outfit_items`, `rating` → `feedback_events`. `images` ve `item_ids` `0003_cleanup`'ta düşer.

**AI GATEWAY CONTRACT** — `complete(AIRequest) → AIResponse`; girdi: feature, pseudonymous subject\_id, tier, prompt\_version, şema, derlenmiş içerik; kimlik/DB yok. Akış: bütçe → routing zinciri → deneme/fallback → şema doğrulama → telemetri (bir `ai_requests` + deneme başına `ai_request_attempts`) + consume (her denemenin gerçek token'ı; istek sayacı yalnız başarıda). Hata kodları `budget_exceeded 429`, `feature_not_allowed 403`, `ai_busy/ai_unavailable 503`, `ai_bad_reply 502`; 402 ileride `subscription_required` için. Routing config-driven: tagging Haiku-sınıfı, suggest Sonnet-sınıfı (free dahil, lansman dönemi), Groq fallback.

**STORAGE & AUTH** — R2 private bucket, mevcut key şeması, 15 dk presigned GET, `wardrobe_images` metadata, 24 saat yetim temizliği, idempotent blob migration script'i, paylaşımlı demo görselleri. Auth: 15 dk access JWT + `token_version`, 30 gün rotasyonlu refresh (hash'li, family revoke), e-posta doğrulama (24 s) ve şifre sıfırlama (1 s) tek kullanımlık token'larla, web'de httpOnly cookie, mobilde SecureStore.

**ENTITLEMENTS** — `entitlements(user) → {max_items, daily_ai_requests, daily_ai_tokens, allowed_features, model_tier, history_limit}`; plan config JSON (free/premium/demo), `subscriptions` sağlayıcıdan bağımsız, `usage_counters` hızlı yol + `ai_requests` ile günlük mutabakat. Router plan adı bilmez.

**TEST STRATEGY** — Saf context snapshot testleri, şema/invalid output testleri, fake provider ile retry/fallback/budget, entitlement limitleri, security (görsel erişimi, cross-user, revoked refresh, token\_version, proxy header), Postgres CI'da `alembic check` + up/down parity, storage fake'i, gerçek anahtarla smoke.

**IMPLEMENTATION ORDER** — AI-01 quick fixes → AI-02 schema migration → AI-03 gateway + entitlements ∥ AI-05 storage + auth → AI-04 context + services → AI-06 intelligence features → AI-07 onboarding/personalization (app) → AI-08 entitlements UI + usage → AI-09 V1.0 hardening (cleanup migration dahil).

**OPEN CONFLICTS** — Teknik çakışma yok. C1–C10 19 Ekim'de kilitlendi (§14): canlı kullanıcı yok ama sayım zorunlu; Resend; AI için doğrulama, gardırop serbest; 15 dk presigned + 10 dk staleTime; paylaşımlı demo görselleri; tagging fallback açık; free'de de Sonnet-sınıfı; `api.fomertech.com`; cleanup ≥ 1 hafta sonra; model/fiyat AI-03 başında. Plan onaylı; AI-01 → AI-02 → AI-03 başlayabilir.
