// api.fomertech.com → Hugging Face Space. Hugging Face can't serve a custom domain,
// so this Worker forwards every request unchanged to the hf.space host.
// fetch() sets Host from the target URL; method, headers and body pass through as is.
//
// CORS is decided here, not upstream: Hugging Face's edge answers OPTIONS itself (without
// Access-Control-Allow-Credentials) and echoes any Origin on other responses, so FastAPI's
// CORS middleware never gets a say. The Worker answers preflights and rewrites the CORS
// headers of every response from ALLOWED_ORIGINS (comma-separated; empty = no origin allowed).

const UPSTREAM = "ftmakyldz-smartwardrobe-api.hf.space";
const ALLOW_METHODS = "GET,POST,PATCH,DELETE,OPTIONS";
const DEFAULT_ALLOW_HEADERS = "authorization,content-type";
const MAX_AGE = "86400";

function allowedOrigins(env) {
  return (env.ALLOWED_ORIGINS || "").split(",").map((o) => o.trim()).filter(Boolean);
}

// Vary: Origin added once, whatever upstream already listed (Hugging Face sends Vary twice).
function withVaryOrigin(headers) {
  const seen = new Map();
  for (const value of (headers.get("vary") || "").split(",")) {
    const v = value.trim();
    if (v && !seen.has(v.toLowerCase())) seen.set(v.toLowerCase(), v);
  }
  if (!seen.has("origin")) seen.set("origin", "Origin");
  headers.set("vary", [...seen.values()].join(", "));
}

function preflight(request, origin, allowed) {
  if (!origin || !allowed.includes(origin)) return new Response(null, { status: 403 });
  const headers = new Headers({
    "access-control-allow-origin": origin,
    "access-control-allow-credentials": "true",
    "access-control-allow-methods": ALLOW_METHODS,
    "access-control-allow-headers": request.headers.get("access-control-request-headers") || DEFAULT_ALLOW_HEADERS,
    "access-control-max-age": MAX_AGE,
    vary: "Origin",
  });
  return new Response(null, { status: 204, headers });
}

async function forward(request) {
  const url = new URL(request.url);
  url.protocol = "https:";
  url.hostname = UPSTREAM;
  url.port = "";

  const headers = new Headers(request.headers);
  // Cloudflare-only headers mean nothing to the Space.
  for (const name of [...headers.keys()]) {
    if (name.startsWith("cf-")) headers.delete(name);
  }
  // The visitor's IP, for the API's rate limits. The API only believes it from trusted proxies.
  const client = request.headers.get("cf-connecting-ip");
  if (client) headers.set("x-forwarded-for", client);
  headers.set("x-forwarded-proto", "https");
  headers.set("x-forwarded-host", new URL(request.url).host);

  return fetch(url, {
    method: request.method,
    headers,
    body: request.body,
    // Hand redirects back to the client instead of following them here.
    redirect: "manual",
  });
}

export default {
  async fetch(request, env = {}) {
    const origin = request.headers.get("origin");
    const allowed = allowedOrigins(env);
    if (request.method === "OPTIONS") return preflight(request, origin, allowed);

    const upstream = await forward(request);
    // Same status, body and headers (Set-Cookie included, untouched); only CORS is rewritten.
    const response = new Response(upstream.body, upstream);
    for (const name of [...response.headers.keys()]) {
      if (name.startsWith("access-control-")) response.headers.delete(name);
    }
    if (origin && allowed.includes(origin)) {
      response.headers.set("access-control-allow-origin", origin);
      response.headers.set("access-control-allow-credentials", "true");
    }
    withVaryOrigin(response.headers);
    return response;
  },
};
