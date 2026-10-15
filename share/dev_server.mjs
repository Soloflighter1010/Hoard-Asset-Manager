/* The share Worker on this computer, kept in memory (fake_kv.mjs): for Hoard's tests (tests/test_shortlinks.py),
   and for trying it out. `node share/dev_server.mjs [port]` prints the address it's at. Not deployed. */
import http from "node:http";
import worker from "./worker.mjs";
import { fakeKV } from "./fake_kv.mjs";

const env = { SETS: fakeKV() };
const HOP = new Set(["host", "connection", "content-length", "transfer-encoding", "keep-alive"]);
const server = http.createServer(async (req, res) => {
  const parts = [];
  for await (const part of req) parts.push(part);
  const headers = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (!HOP.has(k)) headers.set(k, Array.isArray(v) ? v.join(", ") : v);
  headers.set("CF-Connecting-IP", req.socket.remoteAddress || "");
  const body = ["GET", "HEAD", "OPTIONS"].includes(req.method) ? undefined : Buffer.concat(parts);
  const r = await worker.fetch(new Request(`https://hoard-share.furryup.link${req.url}`, { method: req.method, headers, body }), env);
  res.writeHead(r.status, Object.fromEntries(r.headers));
  res.end(Buffer.from(await r.arrayBuffer()));
});
server.listen(Number(process.argv[2] || 0), "127.0.0.1", () => console.log(`http://127.0.0.1:${server.address().port}`));
