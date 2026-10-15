# Hoard's share server

This folder is the server behind short links for shared sets. When someone chooses **Make a short link** in
Hoard, Hoard locks the set on their computer and sends the locked copy here. The server keeps it for 14 days, and
the set viewer on Hoard's website fetches it from here when someone opens the link. The key that unlocks a set is
only in the link, so this server can't read what it keeps.

It's a [Cloudflare Worker](https://developers.cloudflare.com/workers/) (`worker.mjs`), with the sets kept in
[Workers KV](https://developers.cloudflare.com/kv/), at `https://hoard-share.furryup.link`. Until it's set up,
**Make a short link** in Hoard says it can't reach the share server, and the long link works as always.

## Setting it up

You do this once. It takes about 15 minutes.

### What you need

- The Cloudflare account that has `furryup.link`. The free plan is enough.
- [Node.js](https://nodejs.org/), version 20 or newer (the "LTS" download). To check, run `node --version` in a
  terminal.
- This repository on your computer: the `share` folder is all you need from it.

### Step 1: Open a terminal in this folder

Open a terminal (on Windows, PowerShell or Command Prompt) and go to this folder:

    cd path\to\Hoard-Asset-Manager\share

Every command below is run from here.

### Step 2: Sign in to Cloudflare

    npx wrangler login

The first time, `npx` asks to install Wrangler (Cloudflare's tool): type `y` and press Enter. Your browser opens
Cloudflare: sign in if it asks, then choose **Allow**. The terminal then says you're logged in.

### Step 3: Make the storage for the sets

`wrangler.toml` already names the storage of Hoard's own share server (its `id`). Skip steps 3 and 4 if you're
deploying to that same Cloudflare account; to set it up on another account, do them, and use your new id instead.

    npx wrangler kv namespace create hoard-share

It prints a few lines ending like this:

    [[kv_namespaces]]
    binding = "hoard_share"
    id = "0f2ac74b498b48028cb68387c421e279"

Copy the `id` (the 32 letters and digits in quotes). If Wrangler offers to add it to your configuration for you,
say no: step 4 puts it in the right place.

### Step 4: Put that id in `wrangler.toml`

Open `wrangler.toml` (in this folder) in any text editor. Find the `id = "..."` line under `[[kv_namespaces]]`,
replace what's between the quotes with the id you copied, and save the file. The id isn't a secret, so it's fine to
commit it.

### Step 5: Make sure the address is free

In the [Cloudflare dashboard](https://dash.cloudflare.com/), open `furryup.link`, then **DNS**, then **Records**.
There mustn't be a record named `hoard-share`. If there is, delete it. Cloudflare makes the record itself in step 6.

### Step 6: Deploy

    npx wrangler deploy

It uploads the Worker, and should end with something like:

    Deployed hoard-share triggers
      hoard-share.furryup.link (custom domain)

If it stops with an error about `ratelimits`, your plan doesn't have Cloudflare's rate limiting. Open
`wrangler.toml`, delete the four lines from `[[ratelimits]]` to `simple = { limit = 10, period = 60 }`, save, and
run `npx wrangler deploy` again. The Worker works without it.

### Step 7: Check it's working

Open this address in your browser:

    https://hoard-share.furryup.link/v1/sets/abcdefghij

You should see a short message: `{"error":"There's no set at that address: short links last 14 days, and the sharer
can delete one sooner."}`. That's the right answer: the server is up, and there's simply no set with that id. If the
page doesn't load at all, wait a few minutes: Cloudflare can take a little while to issue the address's
certificate.

### Step 8: Try it from Hoard

In Hoard 4.3 or later, open **Sets**, choose a set, then **Share...** and **Make a short link**. Open the short
link: the set viewer should show the set. **Delete the short link** in the same dialog, open the link again, and
the viewer should say it's gone.

## Later

- **Changing the Worker:** edit `worker.mjs`, then run `npx wrangler deploy` here again.
- **Deleting a link someone reports:** a short link looks like `https://hoard.furryup.link/set.html#S1.<id>.<key>`.
  Copy the `<id>` (the 10 letters and digits after `S1.`) and run:

      npx wrangler kv key delete --binding SETS <id> --remote

  Or, in the Cloudflare dashboard, open **Storage & Databases**, **KV**, `hoard-share`, find the key with that id,
  and delete it. You can't see what's in a set (it's locked), only that it exists.
- **How much it's used:** in the dashboard, **Workers & Pages**, `hoard-share`, **Metrics**.
- **Deploying from GitHub instead:** Cloudflare's [wrangler-action](https://github.com/cloudflare/wrangler-action)
  can run `wrangler deploy` with a Cloudflare API token kept as a repository secret. Never put a token in a file
  here.

## In a fork

A fork can't change or deploy this server: the namespace id in `wrangler.toml` only works for whoever is signed in
to the Cloudflare account that has it, and only the owner of `furryup.link` can put a Worker at
`hoard-share.furryup.link`. Nothing in this folder is a secret; your Cloudflare sign-in stays on your own computer.

A fork's own builds of Hoard still use this server, as every copy of Hoard does (that's what the limits below are
for). To run your own instead, deploy this folder to your own Cloudflare account and domain (steps 3 to 7, with
your own `routes` pattern in `wrangler.toml`), then change the address in `hoard/shortlinks.py` (`SERVER`),
`site/set.js` (`SHARE_SERVER`) and `site/set.html` (its Content-Security-Policy's `connect-src`), and, if your
set viewer isn't at `hoard.furryup.link`, `VIEWER` in `worker.mjs`.

## Limits

On Cloudflare's free plan, every day (resetting at midnight UTC), across everyone using Hoard:

- 1,000 short links made or updated (KV writes),
- 100,000 short links opened (Worker requests and KV reads).

Past them, making a short link fails and Hoard says to share the long link, which always works. Workers Paid
($5 a month) has no daily limits (it includes 1 million KV writes and 10 million reads a month, and charges for
more). A short link that runs out, or that its sharer deletes, says so in the viewer.

A locked set is 48 KB at most (a set of about 500 products), and one address can make, update or delete 10 short
links a minute (where the rate limit from step 6 is on).

## How it works

| Request | What it does |
|---|---|
| `POST /v1/sets` `{"data"}` | Keeps a locked set for 14 days. Answers `{"id", "token", "expires"}`. |
| `GET /v1/sets/<id>` | The locked set, `{"data", "expires"}`. Only the set viewer's page may read it in a browser. |
| `PUT /v1/sets/<id>` `{"data"}` | With `Authorization: Bearer <token>`: the set as it is now, kept 14 days from now. |
| `DELETE /v1/sets/<id>` | With the token: deletes it now. |

Hoard locks a set with AES-GCM and a new random 128-bit key, which goes only in the link, after the `#`: a browser
never sends that part anywhere. The token stays in the sharer's Hoard (in `sets.json`), so only the Hoard that made
a link can update or delete it. The server keeps only the token's SHA-256. Writes from a web page are refused,
and nothing is logged. `docs/DATA-FORMATS.md` has the details.

## Tests

From the repository's folder: `node --test share/worker.test.mjs` (`tests/test_shortlinks.py` runs them with
Hoard's tests). They use `fake_kv.mjs`, a stand-in for KV, and `dev_server.mjs` runs the Worker on your computer
for Hoard's own tests. None of those three files is deployed.
