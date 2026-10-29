/* The share Worker's tests: node --test share/worker.test.mjs (tests/test_shortlinks.py runs them). Not deployed. */
import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "./worker.mjs";
import { fakeKV, fakeLimit } from "./fake_kv.mjs";

const HERE = "https://hoard-share.furryup.link";
// Bytes as URL-safe base64.
const b64 = bytes => Buffer.from(bytes).toString("base64url");
// A made-up encrypted set: n random bytes, as Hoard sends one.
const locked = (n = 200) => b64(crypto.getRandomValues(new Uint8Array(n)));
// The SHA-256 of some text, as URL-safe base64.
const sha256 = async text => b64(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))));

// One request to the Worker, as Hoard makes them (JSON, and its token when it has one).
function call(env, method, path, { body, token, headers = {} } = {}) {
  const init = { method, headers: { ...headers } };
  if (body !== undefined) {
    init.body = typeof body === "string" ? body : JSON.stringify(body);
    init.headers["Content-Type"] ??= "application/json";
  }
  if (token) init.headers.Authorization = `Bearer ${token}`;
  return worker.fetch(new Request(HERE + path, init), env);
}
// An answer's status, headers and JSON.
const json = async r => ({ status: r.status, headers: r.headers, ...(r.status === 204 ? {} : await r.json()) });

test("a set is kept, read, updated and deleted, and only by the Hoard that made it", async () => {
  const env = { SETS: fakeKV() }, data = locked();
  const made = await json(await call(env, "POST", "/v1/sets", { body: { data } }));
  assert.equal(made.status, 201);
  assert.match(made.id, /^[0-9A-Za-z]{10}$/);
  assert.match(made.token, /^[A-Za-z0-9_-]{43}$/);
  const days = (made.expires - Date.now() / 1000) / 86400;
  assert.ok(days > 13.99 && days <= 14, "kept 14 days");
  const kept = env.SETS.kept.get(made.id);
  assert.equal(b64(kept.bytes), data, "kept as it came: locked");
  assert.deepEqual(kept.metadata, { h: await sha256(made.token), e: made.expires }, "the token's hash, never the token");
  assert.equal(kept.expiration, made.expires);

  const read = await json(await call(env, "GET", `/v1/sets/${made.id}`));
  assert.equal(read.status, 200);
  assert.equal(read.data, data);
  assert.equal(read.expires, made.expires);
  assert.equal(read.headers.get("Access-Control-Allow-Origin"), "https://hoard.furryup.link", "only the viewer may read it");
  assert.equal(read.headers.get("Cache-Control"), "no-store");

  const other = locked(300);
  for (const token of [undefined, "x", locked(32), made.token.slice(1) + "A"]) {
    assert.equal((await call(env, "PUT", `/v1/sets/${made.id}`, { body: { data: other }, token })).status, 403);
    assert.equal((await call(env, "DELETE", `/v1/sets/${made.id}`, { token })).status, 403);
  }
  assert.equal(b64(env.SETS.kept.get(made.id).bytes), data, "unchanged by anyone else");
  const updated = await json(await call(env, "PUT", `/v1/sets/${made.id}`, { body: { data: other }, token: made.token }));
  assert.deepEqual([updated.status, updated.id], [200, made.id]);
  assert.equal((await json(await call(env, "GET", `/v1/sets/${made.id}`))).data, other);
  assert.equal(env.SETS.kept.get(made.id).metadata.h, await sha256(made.token), "the same token still opens it");

  assert.equal((await call(env, "DELETE", `/v1/sets/${made.id}`, { token: made.token })).status, 204);
  const gone = await json(await call(env, "GET", `/v1/sets/${made.id}`));
  assert.equal(gone.status, 404);
  assert.match(gone.error, /14 days/);
  assert.equal(gone.headers.get("Access-Control-Allow-Origin"), "https://hoard.furryup.link", "the viewer can say why");
  assert.equal((await call(env, "DELETE", `/v1/sets/${made.id}`, { token: made.token })).status, 404);
  assert.equal((await call(env, "PUT", `/v1/sets/${made.id}`, { body: { data }, token: made.token })).status, 404);
});

test("after 14 days a set is gone, and an update keeps it 14 days more", async () => {
  const realNow = Date.now;
  let now = realNow();
  Date.now = () => now;
  try {
    const env = { SETS: fakeKV(() => now) };
    const a = await json(await call(env, "POST", "/v1/sets", { body: { data: locked() } }));
    const b = await json(await call(env, "POST", "/v1/sets", { body: { data: locked() } }));
    now += 10 * 86400 * 1000;
    const kept = await json(await call(env, "PUT", `/v1/sets/${b.id}`, { body: { data: locked() }, token: b.token }));
    assert.equal(kept.expires, Math.floor(now / 1000) + 14 * 86400);
    now += 5 * 86400 * 1000;
    assert.equal((await call(env, "GET", `/v1/sets/${a.id}`)).status, 404, "15 days: gone");
    assert.equal((await call(env, "GET", `/v1/sets/${b.id}`)).status, 200, "updated 5 days ago: kept");
  } finally {
    Date.now = realNow;
  }
});

test("what isn't a locked set, or is too big, isn't kept", async () => {
  const env = { SETS: fakeKV() };
  const tries = [
    [{ body: { data: locked(48 * 1024 + 1) } }, 413], [{ body: { data: locked(48 * 1024) } }, 201],
    [{ body: { data: locked(30) } }, 400], [{ body: { data: locked(31) } }, 201],
    [{ body: { data: "not base64!" } }, 400], [{ body: { data: 5 } }, 400], [{ body: {} }, 400], [{ body: "{" }, 400],
    [{ body: { data: locked() }, headers: { "Content-Type": "text/plain" } }, 415],
    [{ body: JSON.stringify({ data: locked(), pad: "x".repeat(80 * 1024) }) }, 413],
  ];
  for (const [opts, want] of tries) assert.equal((await call(env, "POST", "/v1/sets", opts)).status, want, JSON.stringify(opts).slice(0, 80));
  assert.equal(env.SETS.kept.size, 2);
  // a body bigger than it says it is stops being read at the limit
  const big = new ReadableStream({ start(c) { for (let n = 0; n < 100; n++) c.enqueue(new Uint8Array(1024).fill(65)); c.close(); } });
  const r = await worker.fetch(new Request(HERE + "/v1/sets", { method: "POST", body: big, duplex: "half",
                                                                  headers: { "Content-Type": "application/json" } }), env);
  assert.equal(r.status, 413);
});

test("only Hoard writes: a web page can't, and one address can't make many", async () => {
  const env = { SETS: fakeKV(), WRITES: fakeLimit(3) };
  const page = await call(env, "POST", "/v1/sets", { body: { data: locked() }, headers: { Origin: "https://evil.example" } });
  assert.equal(page.status, 403);
  const from = { "CF-Connecting-IP": "203.0.113.5" };
  const got = [];
  for (let n = 0; n < 5; n++) got.push((await call(env, "POST", "/v1/sets", { body: { data: locked() }, headers: from })).status);
  assert.deepEqual(got, [201, 201, 201, 429, 429]);
  assert.equal((await call(env, "POST", "/v1/sets", { body: { data: locked() }, headers: { "CF-Connecting-IP": "203.0.113.6" } })).status, 201);
  assert.equal(env.SETS.kept.size, 4);
  const pre = await call(env, "OPTIONS", "/v1/sets/abcdefghij", { headers: { Origin: "https://hoard.furryup.link" } });
  assert.equal(pre.status, 204);
  assert.equal(pre.headers.get("Access-Control-Allow-Methods"), "GET", "a page may only read");
});

test("when KV can't keep more today, Hoard is told so", async () => {
  const env = { SETS: { ...fakeKV(), async put() { throw new Error("KV PUT failed: 429 Too Many Requests"); } } };
  const r = await json(await call(env, "POST", "/v1/sets", { body: { data: locked() } }));
  assert.equal(r.status, 503);
  assert.match(r.error, /long link/);
});

test("anything else is not here", async () => {
  const env = { SETS: fakeKV() };
  for (const [method, path, want] of [["GET", "/", 404], ["GET", "/v1/sets", 405], ["GET", "/v1/sets/short", 404],
                                      ["GET", "/v1/sets/abcdefghij/x", 404], ["GET", "/v1/sets/abc-efghij", 404],
                                      ["POST", "/v1/sets/abcdefghij", 405], ["PUT", "/v1/sets", 405],
                                      ["PATCH", "/v1/sets/abcdefghij", 405], ["GET", "/v1/sets/abcdefghij", 404]]) {
    assert.equal((await call(env, method, path)).status, want, `${method} ${path}`);
  }
});

test("ids are 10 letters and digits, every one as likely", async () => {
  const env = { SETS: fakeKV() }, ids = new Set(), seen = new Map();
  for (let n = 0; n < 300; n++) {
    const { id } = await json(await call(env, "POST", "/v1/sets", { body: { data: locked(40) } }));
    ids.add(id);
    for (const c of id) seen.set(c, (seen.get(c) || 0) + 1);
  }
  assert.equal(ids.size, 300);
  assert.ok(seen.size > 55, "all 62 in use");
  assert.ok(Math.max(...seen.values()) < 3000 / 62 * 2, "none much more likely");
});
