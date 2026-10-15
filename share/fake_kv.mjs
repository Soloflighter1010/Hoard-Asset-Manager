/* For the share Worker's tests (worker.test.mjs, and tests/test_shortlinks.py's stand-in server): Workers KV and the
   rate-limit binding, in memory, as strict as Cloudflare documents them. Not deployed. */

// Workers KV: put(key, string | ArrayBuffer | ReadableStream, {expiration, expirationTtl, metadata}), get and
// getWithMetadata ({type: "text" | "arrayBuffer" | "stream"}), delete. A key past its expiration is gone.
export function fakeKV(now = () => Date.now()) {
  const kept = new Map();
  const live = key => {
    const x = kept.get(key);
    if (x && x.expiration && x.expiration * 1000 <= now()) { kept.delete(key); return undefined; }
    return x;
  };
  const as = (bytes, type) => type === "arrayBuffer" ? bytes.slice().buffer
    : type === "stream" ? new Blob([bytes]).stream() : new TextDecoder().decode(bytes);
  return {
    kept,
    async put(key, value, opts = {}) {
      if (typeof key !== "string" || !key || new TextEncoder().encode(key).length > 512) throw new Error("KV PUT failed: bad key");
      if (opts.metadata !== undefined && JSON.stringify(opts.metadata).length > 1024) throw new Error("KV PUT failed: metadata too large");
      const at = opts.expiration ?? (opts.expirationTtl ? Math.floor(now() / 1000) + opts.expirationTtl : undefined);
      if (at !== undefined && at * 1000 < now() + 60000) throw new Error("KV PUT failed: expiration less than 60 seconds away");
      let bytes;
      if (typeof value === "string") bytes = new TextEncoder().encode(value);
      else if (value instanceof ArrayBuffer) bytes = new Uint8Array(value.slice(0));
      else if (value instanceof ReadableStream) bytes = new Uint8Array(await new Response(value).arrayBuffer());
      else throw new TypeError("KV PUT failed: a value is a string, an ArrayBuffer or a ReadableStream");
      if (bytes.length > 25 * 1024 * 1024) throw new Error("KV PUT failed: value too large");
      kept.set(key, { bytes, metadata: opts.metadata ?? null, expiration: at });
    },
    async getWithMetadata(key, opts = {}) {
      const x = live(key);
      return x ? { value: as(x.bytes, opts.type || "text"), metadata: x.metadata } : { value: null, metadata: null };
    },
    async get(key, opts = {}) { return (await this.getWithMetadata(key, opts)).value; },
    async delete(key) { kept.delete(key); },
  };
}

// The rate-limit binding: limit({key}) is {success: false} past `limit` calls for one key
export function fakeLimit(limit) {
  const seen = new Map();
  return { seen, async limit({ key }) { seen.set(key, (seen.get(key) || 0) + 1); return { success: seen.get(key) <= limit }; } };
}
