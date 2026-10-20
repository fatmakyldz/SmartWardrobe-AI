# api.fomertech.com proxy

A Cloudflare Worker that forwards `https://api.fomertech.com/*` to the Hugging Face Space
(`ftmakyldz-smartwardrobe-api.hf.space`), which can't serve a custom domain itself.
Method, path, query, headers and body pass through unchanged; `Host` becomes the hf.space host.
Redirects are returned to the client, not followed.

**CORS is handled here.** Hugging Face's edge answers every `OPTIONS` itself (without
`Access-Control-Allow-Credentials`, so the web app's credentialed preflight fails) and echoes any
`Origin` on other responses; FastAPI's CORS middleware never decides. So the Worker:

- answers `OPTIONS` itself, without calling the Space: an origin in `ALLOWED_ORIGINS` gets `204` with
  `Access-Control-Allow-Origin: <origin>`, `-Allow-Credentials: true`,
  `-Allow-Methods: GET,POST,PATCH,DELETE,OPTIONS`, `-Allow-Headers` (the requested ones, else
  `authorization,content-type`), `-Max-Age: 86400`, `Vary: Origin`; any other origin, or none, gets `403`;
- on every other response, drops the upstream `Access-Control-*` headers, sets `Allow-Origin` and
  `Allow-Credentials` for an allowed origin only, and adds `Vary: Origin`. `Set-Cookie` is untouched.

`ALLOWED_ORIGINS` is comma-separated (spaces ignored, no trailing `/`); unset means no origin is
allowed, so the web app stops working. Keep it in line with `CORS_ORIGINS` on the Space, which still
applies to direct hf.space calls and local runs.

## Deploy

```bash
cd infra/cloudflare-worker
npx wrangler@4 login     # once
npx wrangler@4 deploy    # creates the Worker and the api.fomertech.com custom domain
curl https://api.fomertech.com/   # {"status":"ok","service":"smartwardrobe-api"}
```

Or in the dashboard: Workers & Pages → Create → Worker `smartwardrobe-api-proxy` → paste
`src/index.js` → Deploy → Settings → Domains & Routes → Add → Custom domain `api.fomertech.com`.

Updating the code from the dashboard (the Worker already exists):

1. Workers & Pages → `smartwardrobe-api-proxy` → Settings → Variables and Secrets → Add →
   Type **Text**, name `ALLOWED_ORIGINS`, value
   `https://wardrobe.fomertech.com,https://smartwardrobe-ai-app.vercel.app` → Deploy.
   Add it **before** the new code: the code refuses every origin while it is unset.
2. Edit code → replace everything with `src/index.js` → Deploy.
3. Check (expect `204` and `access-control-allow-credentials: true`, then `401` with the same CORS headers):

```bash
curl -si -X OPTIONS https://api.fomertech.com/auth/refresh \
  -H 'Origin: https://wardrobe.fomertech.com' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type,x-auth-cookie' | grep -iE '^HTTP|access-control|vary'
curl -si -X POST https://api.fomertech.com/auth/refresh \
  -H 'Origin: https://wardrobe.fomertech.com' -H 'Content-Type: application/json' -H 'X-Auth-Cookie: 1' \
  | grep -iE '^HTTP|access-control|vary'
curl -si -X OPTIONS https://api.fomertech.com/auth/refresh -H 'Origin: https://evil.example.com' | head -1   # 403
```

Tests (no install needed, Node 22): `node --test infra/cloudflare-worker/test/index.test.mjs`.

## Notes

- The app calls `api.fomertech.com` (AI-05b); the web refresh cookie only works through this domain.
- Client IP: the Worker sets `X-Forwarded-For` to the visitor's IP. The API believes it only
  with `CLOUDFLARE_PROXY=true` on the Space (see `backend/README.md`, "Behind a proxy");
  without it, requests via `api.fomertech.com` share the Worker's IP for anonymous rate limits.
