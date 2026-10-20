# api.fomertech.com proxy

A Cloudflare Worker that forwards `https://api.fomertech.com/*` to the Hugging Face Space
(`ftmakyldz-smartwardrobe-api.hf.space`), which can't serve a custom domain itself.
Method, path, query, headers and body pass through unchanged; `Host` becomes the hf.space host.
Redirects are returned to the client, not followed.

## Deploy

```bash
cd infra/cloudflare-worker
npx wrangler@4 login     # once
npx wrangler@4 deploy    # creates the Worker and the api.fomertech.com custom domain
curl https://api.fomertech.com/   # {"status":"ok","service":"smartwardrobe-api"}
```

Or in the dashboard: Workers & Pages → Create → Worker `smartwardrobe-api-proxy` → paste
`src/index.js` → Deploy → Settings → Domains & Routes → Add → Custom domain `api.fomertech.com`.

## Notes

- The app still calls the hf.space URL; switching it to `api.fomertech.com` is part of AI-05.
- Client IP: the Worker sets `X-Forwarded-For` to the visitor's IP. The API believes it only
  with `CLOUDFLARE_PROXY=true` on the Space (see `backend/README.md`, "Behind a proxy");
  without it, requests via `api.fomertech.com` share the Worker's IP for anonymous rate limits.
