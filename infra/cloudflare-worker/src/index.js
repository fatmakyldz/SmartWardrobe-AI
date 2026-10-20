// api.fomertech.com → Hugging Face Space. Hugging Face can't serve a custom domain,
// so this Worker forwards every request unchanged to the hf.space host.
// fetch() sets Host from the target URL; method, headers and body pass through as is.

const UPSTREAM = "ftmakyldz-smartwardrobe-api.hf.space";

export default {
  async fetch(request) {
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
  },
};
