// node --test infra/cloudflare-worker/test/index.test.mjs  (Node 22: fetch, Request, Response are global)
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import worker from "../src/index.js";

const WEB = "https://wardrobe.fomertech.com";
const env = { ALLOWED_ORIGINS: `${WEB}, https://smartwardrobe-ai-app.vercel.app` };
const realFetch = globalThis.fetch;
let calls;

// Upstream as Hugging Face answers it: any Origin echoed, Vary twice, two cookies.
function fakeUpstream() {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const headers = new Headers({ "content-type": "application/json", vary: "Origin" });
    headers.append("vary", "origin, access-control-request-method");
    headers.set("access-control-allow-origin", init.headers.get("origin") || "*");
    headers.set("access-control-expose-headers", "*");
    headers.append("set-cookie", "sw_refresh=abc; HttpOnly; Secure; SameSite=lax; Path=/auth");
    headers.append("set-cookie", "other=1; Path=/");
    return new Response('{"ok":true}', { status: 200, headers });
  };
}

afterEach(() => {
  globalThis.fetch = realFetch;
});

const req = (method, origin, extra = {}) =>
  new Request("https://api.fomertech.com/auth/refresh", {
    method,
    headers: { ...(origin ? { origin } : {}), ...extra },
  });

test("preflight from an allowed origin is answered here, with credentials", async () => {
  fakeUpstream();
  const r = await worker.fetch(
    req("OPTIONS", WEB, { "access-control-request-method": "POST", "access-control-request-headers": "content-type,x-auth-cookie" }),
    env,
  );
  assert.equal(r.status, 204);
  assert.equal(r.headers.get("access-control-allow-origin"), WEB);
  assert.equal(r.headers.get("access-control-allow-credentials"), "true");
  assert.equal(r.headers.get("access-control-allow-methods"), "GET,POST,PATCH,DELETE,OPTIONS");
  assert.equal(r.headers.get("access-control-allow-headers"), "content-type,x-auth-cookie");
  assert.equal(r.headers.get("access-control-max-age"), "86400");
  assert.equal(r.headers.get("vary"), "Origin");
  assert.equal(calls.length, 0, "preflight must not reach upstream");
});

test("preflight without requested headers gets the default list", async () => {
  fakeUpstream();
  const r = await worker.fetch(req("OPTIONS", "https://smartwardrobe-ai-app.vercel.app"), env);
  assert.equal(r.status, 204);
  assert.equal(r.headers.get("access-control-allow-headers"), "authorization,content-type");
});

test("preflight from another origin, or none, is refused", async () => {
  fakeUpstream();
  for (const origin of ["https://evil.example.com", undefined]) {
    const r = await worker.fetch(req("OPTIONS", origin), env);
    assert.equal(r.status, 403);
    assert.equal(r.headers.get("access-control-allow-origin"), null);
  }
  assert.equal((await worker.fetch(req("OPTIONS", WEB), {})).status, 403, "unset ALLOWED_ORIGINS allows nothing");
  assert.equal(calls.length, 0);
});

test("responses to an allowed origin get our CORS headers; cookies pass untouched", async () => {
  fakeUpstream();
  const r = await worker.fetch(req("POST", WEB), env);
  assert.equal(r.status, 200);
  assert.equal(await r.text(), '{"ok":true}');
  assert.equal(r.headers.get("access-control-allow-origin"), WEB);
  assert.equal(r.headers.get("access-control-allow-credentials"), "true");
  assert.equal(r.headers.get("access-control-expose-headers"), null);
  assert.equal(r.headers.get("vary"), "Origin, access-control-request-method");
  assert.deepEqual(r.headers.getSetCookie(), [
    "sw_refresh=abc; HttpOnly; Secure; SameSite=lax; Path=/auth",
    "other=1; Path=/",
  ]);
  assert.equal(calls[0].url, "https://ftmakyldz-smartwardrobe-api.hf.space/auth/refresh");
  assert.equal(calls[0].init.redirect, "manual");
});

test("upstream's echo of a foreign origin is stripped", async () => {
  fakeUpstream();
  const r = await worker.fetch(req("POST", "https://evil.example.com"), env);
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("access-control-allow-origin"), null);
  assert.equal(r.headers.get("access-control-allow-credentials"), null);
  assert.match(r.headers.get("vary"), /^Origin/);
});

test("forwarding headers are still set and cf-* dropped", async () => {
  fakeUpstream();
  await worker.fetch(req("GET", WEB, { "cf-connecting-ip": "203.0.113.7", "cf-ray": "x" }), env);
  const h = calls[0].init.headers;
  assert.equal(h.get("x-forwarded-for"), "203.0.113.7");
  assert.equal(h.get("x-forwarded-proto"), "https");
  assert.equal(h.get("x-forwarded-host"), "api.fomertech.com");
  assert.equal(h.get("cf-ray"), null);
});
