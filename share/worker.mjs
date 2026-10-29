/* Hoard's short links for shared sets: a Cloudflare Worker, with Workers KV for storage (see README.md here).

   A set is shared as a code (hoard/sets.py). A short link keeps that code here, locked: Hoard locks it (AES-GCM, in
   its page, with a new random key) before sending it, and the key goes only in the link, after its "#", which a
   browser never sends anywhere. So what's kept here can't be read by anyone, this Worker, Cloudflare and Hoard's
   maintainers included: only by whoever has the link.

     POST   /v1/sets        {"data"}: keep a locked set for 14 days. Answers {"id", "token", "expires"}.
     GET    /v1/sets/<id>   the locked set: {"data", "expires"}. The set viewer (site/set.js) reads it.
     PUT    /v1/sets/<id>   {"data"}, with "Authorization: Bearer <token>": the set as it is now, kept 14 days more.
     DELETE /v1/sets/<id>   with the token: gone now.

   "data" is the locked set (12 bytes of nonce, then the set and its 16-byte tag) in base64url. The token is
   what the sharer's Hoard keeps, to update or delete it: only its SHA-256 is kept here. Nothing else is kept, and
   nothing is logged. */

const VIEWER = "https://hoard.furryup.link";   // the one page that may read a set from here
const LIFETIME = 14 * 24 * 60 * 60;            // seconds a set is kept, after it's made or updated
const MAX_BYTES = 48 * 1024;                   // a locked set at most (a set of 500 products is about 47 KB)
const MIN_BYTES = 12 + 16 + 3;                 // nonce, tag, and "H1." at least
const MAX_BODY = 72 * 1024;                    // a request's body at most: {"data": ...} of MAX_BYTES
const ID = /^[0-9A-Za-z]{10}$/;
const TOKEN = /^[A-Za-z0-9_-]{43}$/;
const B64 = /^[A-Za-z0-9_-]+$/;
const LETTERS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

// Bytes as URL-safe base64.
const b64 = bytes => {
  let s = "";
  for (let n = 0; n < bytes.length; n += 0x8000) s += String.fromCharCode(...bytes.subarray(n, n + 0x8000));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
// URL-safe base64 as bytes.
const unb64 = text => Uint8Array.from(atob(text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - text.length % 4) % 4)),
                                      c => c.charCodeAt(0));
// The SHA-256 of some text, as URL-safe base64.
const sha256 = async text => b64(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))));

// A new id: 10 letters and digits, each equally likely (bytes past 247 are skipped: 248 is 4 times 62)
function newId() {
  let id = "";
  while (id.length < 10) {
    for (const b of crypto.getRandomValues(new Uint8Array(16))) if (b < 248 && id.length < 10) id += LETTERS[b % 62];
  }
  return id;
}

// A JSON answer, never cached or sniffed.
function answer(status, body, extra = {}) {
  return new Response(body === null ? null : JSON.stringify(body), { status, headers: {
    ...(body === null ? {} : { "Content-Type": "application/json" }), "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", ...extra } });
}
const READABLE = { "Access-Control-Allow-Origin": VIEWER, "Vary": "Origin" };   // the viewer may read it
const GONE = "There's no set at that address: short links last 14 days, and the sharer can delete one sooner.";

// The locked set a request sends, as bytes, or a Response saying what's wrong with it
async function lockedSet(request) {
  if (!/^application\/json\s*(;|$)/i.test(request.headers.get("Content-Type") || "")) return answer(415, { error: "Send JSON." });
  if (Number(request.headers.get("Content-Length") || 0) > MAX_BODY) return answer(413, { error: "That set is too big for a short link." });
  const reader = request.body ? request.body.getReader() : null, parts = [];
  let size = 0;
  while (reader) {   // (read up to MAX_BODY, whatever Content-Length said)
    const { done, value } = await reader.read();
    if (done) break;
    size += value.length;
    if (size > MAX_BODY) { reader.cancel(); return answer(413, { error: "That set is too big for a short link." }); }
    parts.push(value);
  }
  let data;
  try {
    const sent = JSON.parse(new TextDecoder().decode(await new Blob(parts).arrayBuffer()));
    if (typeof sent?.data !== "string" || !B64.test(sent.data)) throw new Error();
    data = unb64(sent.data);
  } catch (e) {
    return answer(400, { error: "That isn't a locked set." });
  }
  if (data.length > MAX_BYTES) return answer(413, { error: "That set is too big for a short link." });
  return data.length < MIN_BYTES ? answer(400, { error: "That isn't a locked set." }) : data;
}

// Writes from one address, a few a minute at most (the WRITES rate limit, where it's set up)
async function tooMany(request, env) {
  if (!env.WRITES) return false;
  const { success } = await env.WRITES.limit({ key: request.headers.get("CF-Connecting-IP") || "" });
  return !success;
}

// What the sharer's token opens: the set's metadata, or a Response
async function owned(request, env, id) {
  const token = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  const got = await env.SETS.getWithMetadata(id, { type: "stream" });
  if (got.value) await got.value.cancel();   // (only its metadata is wanted)
  if (got.value === null || !got.metadata) return answer(404, { error: GONE });
  return TOKEN.test(token) && await sha256(token) === got.metadata.h ? got.metadata
    : answer(403, { error: "That short link was made by someone else's Hoard." });
}

// Keep a set's code for LIFETIME, returning when it ends.
async function keep(env, id, data, hash) {
  const expires = Math.floor(Date.now() / 1000) + LIFETIME;
  await env.SETS.put(id, data.buffer, { expiration: expires, metadata: { h: hash, e: expires } });
  return expires;
}
const BUSY = { error: "Hoard's share server can't keep more sets today. Share the long link, or try again tomorrow." };

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname.match(/^\/v1\/sets(?:\/([^/]*))?$/);
    if (!path) return answer(404, { error: "This is Hoard's share server: see https://hoard.furryup.link/." });
    const id = path[1], method = request.method;
    if (id !== undefined && !ID.test(id)) return answer(404, { error: GONE }, READABLE);
    if (method === "OPTIONS") {
      return answer(204, null, { ...READABLE, "Access-Control-Allow-Methods": "GET", "Access-Control-Max-Age": "86400" });
    }
    if (method === "GET" && id) {
      const got = await env.SETS.getWithMetadata(id, { type: "arrayBuffer" });
      if (got.value === null || !got.metadata || got.metadata.e * 1000 <= Date.now()) return answer(404, { error: GONE }, READABLE);
      return answer(200, { data: b64(new Uint8Array(got.value)), expires: got.metadata.e }, READABLE);
    }
    const writes = { POST: id === undefined, PUT: !!id, DELETE: !!id };
    if (!writes[method]) return answer(405, { error: "Not here." }, { "Allow": id ? "GET, PUT, DELETE" : "POST" });
    // Writes come from Hoard itself, never from a web page (which would send its Origin)
    if (request.headers.get("Origin")) return answer(403, { error: "Only Hoard makes short links." });
    if (await tooMany(request, env)) return answer(429, { error: "That's a lot of short links at once: wait a minute." });
    try {
      if (method === "POST") {
        const data = await lockedSet(request);
        if (data instanceof Response) return data;
        const made = newId(), token = b64(crypto.getRandomValues(new Uint8Array(32)));
        return answer(201, { id: made, token, expires: await keep(env, made, data, await sha256(token)) });
      }
      const mine = await owned(request, env, id);
      if (mine instanceof Response) return mine;
      if (method === "DELETE") {
        await env.SETS.delete(id);
        return answer(204, null);
      }
      const data = await lockedSet(request);
      if (data instanceof Response) return data;
      return answer(200, { id, expires: await keep(env, id, data, mine.h) });
    } catch (e) {   // KV's daily limits, or one too many writes to one set in a second
      return answer(503, BUSY, { "Retry-After": "3600" });
    }
  },
};
