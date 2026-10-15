# Hoard's share server

Short links for shared sets. A set is shared as a code (see [Sets](../wiki/Sets.md)). A short link keeps that
code here, locked, for 14 days, so the link is about 70 characters instead of thousands:

    https://hoard.furryup.link/set.html#S1.<id>.<key>

Hoard locks the set in its page (AES-GCM, with a new random 128-bit key) before sending it. The key is only in the
link, after the `#`, which a browser never sends anywhere. So this server, Cloudflare and Hoard's maintainers can't
read a set: only whoever has the link can. Nothing is logged.

`worker.mjs` is a [Cloudflare Worker](https://developers.cloudflare.com/workers/), and the locked sets are kept in
[Workers KV](https://developers.cloudflare.com/kv/):

| Request | What it does |
|---|---|
| `POST /v1/sets` `{"data"}` | Keeps a locked set for 14 days. Answers `{"id", "token", "expires"}`. |
| `GET /v1/sets/<id>` | The locked set, `{"data", "expires"}`. Only the set viewer's page may read it in a browser. |
| `PUT /v1/sets/<id>` `{"data"}` | With `Authorization: Bearer <token>`: the set as it is now, kept 14 days from now. |
| `DELETE /v1/sets/<id>` | With the token: deletes it now. |

The token stays in the sharer's Hoard (in `sets.json`), so only the Hoard that made a link can update or delete it.
The server keeps only the token's SHA-256. A locked set is 48 KB at most (a set of about 500 products), and one
address can make, update or delete 10 a minute.

## Setting it up

You need a Cloudflare account (the free plan is enough) with `furryup.link` on it, and Node.js.

1. In this folder, sign in: `npx wrangler login` (it opens your browser).
2. Make the namespace the sets are kept in: `npx wrangler kv namespace create hoard-share`. Put the `id` it prints
   in `wrangler.toml`, in place of `PUT-THE-NAMESPACE-ID-HERE`. The id isn't a secret.
3. Deploy: `npx wrangler deploy`. Cloudflare makes `hoard-share.furryup.link` (its DNS record and certificate). The
   address mustn't already have a CNAME record.
4. Check it: `https://hoard-share.furryup.link/v1/sets/abcdefghij` should answer `{"error": "There's no set at
   that address: ..."}`.

If `wrangler deploy` says the rate limit (`[[ratelimits]]`) isn't available on your plan, delete that block: the
Worker works without it.

Change `worker.mjs`, then run `npx wrangler deploy` again. To deploy it from GitHub Actions instead, use
[wrangler-action](https://github.com/cloudflare/wrangler-action) with a Cloudflare API token kept as a repository
secret. Never put the token in a file here.

## Limits

On Cloudflare's free plan, every day (resetting at midnight UTC), across everyone using Hoard:

- 1,000 short links made or updated (KV writes),
- 100,000 short links opened (Worker requests and KV reads).

Past them, making a short link fails and Hoard says to share the long link, which always works. Workers Paid
($5 a month) has no daily limits (it includes 1 million KV writes and 10 million reads a month, and charges for
more). A short link that runs out, or that its sharer deletes, says so in the viewer.

## Taking a link down

If someone reports a link, delete it by its id (the part after `S1.` and before the next `.`):

    npx wrangler kv key delete --binding SETS <id> --remote

## Tests

`node --test share/worker.test.mjs`, from the repository's folder (`tests/test_shortlinks.py` runs them with
Hoard's tests), against `fake_kv.mjs`, a stand-in for KV. The tests and `fake_kv.mjs` aren't deployed.
