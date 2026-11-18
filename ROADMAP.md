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
