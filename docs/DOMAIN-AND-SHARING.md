# A Hoard domain and set-link hosting

Research for #332, reviewed 15 November 2026. This is a recommendation, not a
purchase, deployment or migration. Prices are USD and may change. It builds on
the [earlier issue recommendation](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/332#issuecomment-6803768547), adding current primary-source pricing and an API-compatibility inventory.

## Recommendation

If Hoard wants its own project identity, choose an available non-premium `.com`
and retain the existing encrypted share Worker. Keep the current addresses working
for supported releases. Do not add Kutt solely to shorten set links: it adds an
application and database without replacing the encrypted-payload service.

Candidate names below are suggestions. Availability and premium status have **not**
been checked; confirm both at checkout before making a decision.

| Candidate | Published standard TLD registration | Renewal per year | Reason to consider |
| --- | ---: | ---: | --- |
| `hoardassetmanager.com` | $11.81 | $11.81 | Clear product name; preferred if available |
| `gethoard.com` | $11.81 | $11.81 | Shorter, less descriptive |
| `gethoard.app` | $8.75 first-year promotion | $14.93 | App-focused alternative; budget for renewal |

These are the registrar's TLD prices, not quotes for the particular names.
[Porkbun's pricing table](https://porkbun.com/products/domains) lists non-premium,
single-year prices including ICANN fees. Taxes, premium names and later increases
can change the actual charge. Budget about $15/year for the recommended domain,
then verify the renewal total rather than relying on a first-year promotion.

## Hosting costs

The current code uses a Cloudflare Worker and KV. Cloudflare currently includes
100,000 Worker requests/day on Free; KV includes 100,000 reads/day, 1,000
writes/day, 1,000 deletes/day and 1 GB storage. The paid Workers subscription
starts at $5/month, with usage charges beyond its included allowances. Review
account-wide usage before assuming spare capacity.
[Cloudflare pricing](https://developers.cloudflare.com/workers/platform/pricing/).

| Option | Illustrative annual baseline with a standard .com | Additional work |
| --- | ---: | --- |
| Current hosts, within existing allowances | No new domain charge; current account costs unknown | Maintain current DNS and Worker |
| Own domain, existing Worker within Free allowances | $11.81 | Domain renewals and compatibility hosts |
| Own domain, $5/month Workers subscription | $71.81 before overages | Budget and monitor usage |
| Own domain, Kutt on a 1 GiB VM | $83.81 before extras | App/OS updates, TLS, database backups and monitoring |
| Own domain, Kutt on a 2 GiB VM | $155.81 before extras | Same maintenance, more memory |

The VM examples use DigitalOcean's $6/month 1 GiB and $12/month 2 GiB Basic
Droplets. They are planning examples, **not** measured Kutt capacity requirements.
Backup storage, mail, taxes and bandwidth overages are excluded.
[DigitalOcean prices](https://www.digitalocean.com/pricing/droplets).

Kutt has no need for a separate paid database in its basic setup: its current
README specifies Node.js 20+, SQLite by default, and optional PostgreSQL,
MySQL/MariaDB or Redis. A small deployment could use SQLite on persistent storage;
it still needs a backup/restore plan and application maintenance.
[Kutt setup](https://github.com/thedevs-network/kutt#setup).

## What set sharing must preserve

Repository evidence:

- [shortlinks.py](../hoard/shortlinks.py): the service stores ciphertext for 14
  days; a separate token authorizes updates/deletion. The decryption key is in
  the viewer link's fragment, not in the API request.
- [worker.mjs](../share/worker.mjs): stores encrypted data and a hash of the
  management token; viewer access is restricted to its configured origin.
- [set.js](../site/set.js): fetches the ciphertext and decrypts in the browser.

Kutt is a redirect service, not an encrypted-set payload store. Storing a complete
Hoard set link as a shortener's destination would put the fragment, including its
key, into the shortener's submitted data. That would change the current
server-cannot-read-the-set property. This is an architectural inference from the
link format, not a claim that a Kutt integration has been built or audited.

A future Kutt design would need to keep keys exclusively in client-held fragments,
retain a ciphertext service, define how IDs and fragments reach the viewer, and
test the whole path. It must also retain the 14-day expiry and management-token
behavior, or explicitly redesign them. Kutt's password/expiry controls alone do
not provide the existing client-side encryption protocol. Keep it out of this
migration unless there is a separate need for managed public redirects.

## Migration inventory and compatibility

A later migration issue should cover:

1. Website, set viewer and static asset paths, including download/archive links.
2. VCC listing `index.json`, package URLs, the `HOARD_REPO` constant in
   [vpm/api.py](../hoard/vpm/api.py), workflow-generated listing/security URLs,
   wiki/docs, badges and the site build's domain configuration. Preserve published
   schema `$id` identifiers and keep old schema URLs available; a website move
   does not require rewriting identifiers in existing catalog files.
3. The share API address in both the app and viewer; temporarily allow old and
   new viewer origins in the Worker, and update `site/set.html`'s CSP connection
   allowlist together with `site/set.js`. Keep using the same KV namespace so existing
   encrypted sets are not lost.
4. Old website paths should continue working or redirect with their paths and
   queries preserved. Verify real browser fragment preservation with both long
   codes and `S1` links; do not assume a registrar's forwarding UI handles this.
5. **Keep the old API host serving requests or proxying them.** The app's
   `egress.send` deliberately does not follow redirects; redirecting its API would
   break old versions, including update/delete requests with bearer tokens.
6. Keep old API compatibility while supported old apps can still create links,
   then for at least a further 14 days. Fourteen days after launch is insufficient
   if an older app can create a fresh link on day fifteen.
7. Store-facing contact addresses can move to project-domain email after testing
   inbound delivery. Forwarding and a paid mailbox are different decisions; no
   mailbox budget is included here.

Acceptance evidence should include an old app opening a previously shared link,
updating/deleting it, an old VCC listing still fetching packages, new links opened
in the browser, and expiry/CORS behavior. Nothing in this document changes hosts.

## Ownership and renewal

A designated maintainer must accept responsibility for the registrar/DNS account,
renewal funding, two-factor authentication and a recovery contact. The payer and
backup maintainer are not assigned by this proposal. Record the renewal date and
reminders outside public source control; never commit account or billing secrets.

If funding stops or a domain lapses, its website, listing and share links can fail
or eventually point to another owner. A domain is not permanent link storage.
Keep current compatibility hosts funded for the support window. A user can retain
JSON exports and re-share a set later, but expired ciphertext is not recoverable
from a short link alone. Prefer the current setup over a new domain without an
owner willing to renew it.
