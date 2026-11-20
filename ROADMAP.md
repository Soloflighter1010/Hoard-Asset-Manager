# Hoard roadmap

The live task tracker is [roadmap issue #363](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/363).
This document consolidates roadmap issues
[#308](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/308) and
[#315](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/315).
Individual issues own requirements, discussion and completion status. Sections group
work; they do not promise release dates or rank the new requests.

## Open bugs and investigations

- [ ] [#327](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/327) — Windows Defender quarantined the Tauri experiment; investigate the detection.
- [ ] [#335](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/335) — Project package updates reported complete without the expected result.
- [x] [#368](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/368) — Local products listed on a NAS or drive that doesn't answer stopped the library from loading; fixed in PR #369 (#366 is the offline rescue for a library that already stopped).

## Architecture and rollout

- [x] [#316](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/316) — Test isolation and parallel CI: each test its own folders, shuffled and run twice in six shards per system; one run of the suite takes about a third of the 16 to 19 minutes it did.
- [x] [#322](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/322) — Store adapters and health checks: the store-specific branches moved behind each store's adapter (PR #365).
- [ ] [#324](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/324) — Choose one desktop shell using cross-platform measurements and tester results; Mac signing remains outstanding.
- [ ] [#320](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/320) — SQLite metadata and stable product IDs: implemented behind an opt-in flag, not enabled by default.
- [ ] [#348](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/348) — JSON compatibility, recovery, sealing cost and identity collisions are addressed in PR #365. Native packaged validation and beta activation remain, after the desktop transition settles.

Implementation evidence and reproduction commands live in [the architecture implementation notes](docs/ROADMAP-315.md).

## Requested features and UI improvements

Each of these is done in PR #365, for the next beta.

- [x] [#354](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/354) — Export and import sets and lists as JSON (PR #365).
- [x] [#355](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/355) — Improve the sets and lists interface (PR #365).
- [x] [#356](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/356) — Explain source control for new users (PR #365).
- [x] [#357](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/357) — Automatically update a project’s assets, packages, or both (PR #365).
- [x] [#358](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/358) — Placeholder entries for local, unfound or not-yet-created assets in sets (PR #365).
- [x] [#359](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/359) — Currency conversion in wishlists (PR #365).
- [x] [#360](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/360) — Replace underlined actions with buttons (PR #365).
- [x] [#362](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/362) — List dependencies for the set as a whole (PR #365).

## Beta 9 notes

Testers' notes on beta 9, filed as one issue each. The rest of the list (sets and lists as JSON, placeholders,
currency conversion and the others above) was done in PR #365.

- [x] [#372](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/372) — Read my wishlists offers only the stores you're signed in to (PR #389).
- [x] [#373](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/373) — The setup assistant is no longer held up by store reads after a sign-in (PR #389).
- [x] [#374](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/374) — The setup assistant's browser choice is the size of its words (PR #389).
- [x] [#380](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/380) — Star us on GitHub, in the app and on the website (PR #389).
- [x] [#381](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/381) — The total price of what isn't yours yet, on wishlists and sets (PR #389).
- [x] [#383](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/383) — Next gives a small shake after 3 minutes without input in the setup assistant (PR #389).
- [x] [#384](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/384) — Sets added from someone's link show prices, read from the products' public pages (PR #389).
- [x] [#375](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/375) — Projects: the packages you use most, first in Add packages (PR #391).
- [x] [#376](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/376) — Projects: a new project's products from your library as tiles, with Leave out on each (PR #391).
- [x] [#378](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/378) — Projects: take a product out of a project again, only the files Hoard put in for it (PR #391).
- [x] [#386](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/386) — Projects: a new project from a backup, with its Git history and packages (PR #391).
- [x] [#385](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/385) — Settings: change the location of each of Hoard's folders (Hoard's own folder, its logs and sign-ins move as Hoard next starts).
- [x] [#388](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/388) — Local: a sync folder on this computer whose contents are added by themselves (files over 100 MB and folders over 1 GB refused; no network drives).
- [x] [#387](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/387) — Payhip: products added to wishlists by their link (read in Hoard's browser when Cloudflare refuses), and Payhip wishlists read.
- [x] [#379](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/379) — Sets on the website: build and share a set without Hoard (as a long link: the share server takes sets only from Hoard).
- [x] [#377](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/377) — Research: preparing a new Unity project ahead of time: [docs/PREPARING-NEW-PROJECTS.md](docs/PREPARING-NEW-PROJECTS.md) (PR #391); what's worth building is #390.
- [ ] [#390](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/390) — Projects: Get it ready imports a new project in the background, in Unity's batch mode (from #377's research).
- [x] [#382](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/382) — Research: a .unitypackage from a Local asset without opening Unity: built as Make a Unity package ([docs/UNITYPACKAGE-FROM-LOCAL.md](docs/UNITYPACKAGE-FROM-LOCAL.md)).

## Requested after beta 10

- [x] [#396](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/396) — `hoard://` links: open a shared set, a product to add to a wishlist, or a product in your library, with **Open in Hoard** on the website's set viewer and set maker.
- [ ] [#394](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/394) — Try Hoard on the website: a demo in the browser with a pretend sign-in and real products (waiting on the list of products to show).
- [x] [#410](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/410) — The Local sync folder in Windows' File Explorer: Hoard's icon on it, and Add to Hoard, Sync with Hoard now and Open in Hoard in the right-click menu.
- [ ] [#411](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/411) — The same in macOS's Finder and on Linux.
- [x] [#413](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/413) — Send to Hoard: a bookmark that sends a store's product page, or a set shared from the website, to Hoard as a `hoard://` link.
- [x] [#414](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/414) — Hoard for Unity: a tool a product carries (lilToon, Poiyomi) is left out of the import when the project has it at the same version or a newer one.

### Beta 10 notes

- [x] [#398](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/398) — Projects: each package shows its own version again after a page refresh.
- [x] [#399](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/399) — Clearer words: moving a folder in Settings, the editable copies folder, a download check's changed files.
- [x] [#400](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/400) — A file changed after it was downloaded has its own mark (a blue circle with a pencil), apart from errors.
- [x] [#401](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/401) — Downloading a product waits for its whole list of files, and opens it.
- [x] [#402](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/402) — The download panel tucks itself away 10 seconds after a download starts; the bar brings it back.
- [x] [#403](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/403) — Tasks side by side: a small task runs beside a download or store read when they share nothing; settings wait only for a task that uses them.
- [x] [#404](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/404) — A set's photos are small previews on its page, with Show larger.
- [x] [#405](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/405) — Export JSON works in the app: Hoard writes the file itself, in Exported sets.
- [x] [#406](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/406) — Pictures that don't flicker or go blank: kept across redraws, asked for again when one doesn't load.
- [x] [#407](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/407) — Hoard for Unity's pictures: kept at the size they're drawn, never let go on screen, retried; WebP and AVIF get a PNG copy.

## Later and research

- [ ] [#306](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/306) — New products and sales from followed creators; previously deferred to Hoard V6.
- [x] [#332](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/332) — Research a Hoard domain and self-hosted Kutt links: the recommendation is in [docs/DOMAIN-AND-SHARING.md](docs/DOMAIN-AND-SHARING.md) (PR #365); nothing bought or moved.

## Legacy work awaiting review

The old roadmap included these unfinished entries without dedicated issues.
They remain here until reviewed against current behavior; their presence does not
mean they are confirmed missing or scheduled.

- Unity plugin/VPM integration and Pages listing.
- Standalone apps, installer, macOS/Linux support and app updater; reconcile the remaining desktop work with #324.
- Library: manual add/remove/archive, configurable owned-asset update checks,
  selected-asset highlighting, accessibility controls, multiple drives,
  striped duplicate highlighting, and new-asset indicators.
- Validate itch.io readers against real accounts and broaden Gumroad testing.
- Server paging for very large libraries (P-01); only rewrite changed `asset.json` files (P-09).
- Store-ID migration for tags and marks (B-02; related to #320/#348).
- SHA-256 download manifests checked by Unity before import (S-02).
- Remove only known default product pictures, not all matching pictures (P-10).

The creator-listing request is tracked by #306. Historical Payhip notes do not
promise downloads: Payhip remains a library reader.

## Completed work and previous decisions

Completed feature work: #303 code information in Look inside, #304 private product
notes, #305 KonoAsset import, and #307 Patreon/Ko-fi/pixivFANBOX readers.
Completed architecture work: #317 export schemas, #318 translation parsing,
#319 route registry, #321 incremental app shell, and #323 background scheduler.
See the individual issues for scope and the implementation notes for evidence.

Previous decisions remain: no full stack rewrite, wholesale frontend migration,
SvelteKit migration or central internet server for Hoard libraries. Outfit-fit
metadata, per-product license tracking, update changelogs and unused-project-asset
reporting were not planned in #308.

[Historical roadmap](docs/ROADMAP-HISTORY.md) preserves the earlier release notes
and original wording. Update this file when work changes; keep technical evidence
in the linked implementation documents rather than maintaining another plan.
