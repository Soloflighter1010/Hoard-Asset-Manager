# Store adapters

Each module in `hoard/stores/` owns one store's purchase, wishlist, saved-page
and download parsers. Its `STORE` value implements the common `Adapter`
contract. The registry discovers these modules, orders them by `STORE.order`,
and derives the purchase, wishlist and download registries from capabilities.
Payhip explicitly refuses downloads; itch.io explicitly refuses wishlists.

The shared browser and HTTP boundary, rate limiter, retries, file selection,
download records and metadata remain outside the adapters. `list_files` and
`check_updates` force read-only mode while retaining the caller's selected
products and files. Quick reads use the existing bounded pagination rules.
The Jinxxy adapter declares its 120 requests/minute limit; `pace.py` still
enforces it across browser and HTTP requests together.

Existing imports such as `library.fetch_booth`, `downloader.sync_gumroad` and
`itch.owned_keys` remain available. They refer to the store implementations;
there is no second parser. Lazy shared-service references keep the established
test injection points working, including the request and browser fakes. These
compatibility names may be retired independently after downstream callers move.

To add a store, add its adapter and recordings under `tests/data/stores/<key>`.
Declare unsupported capabilities explicitly. The registry and contract tests
find the new module automatically. A store with new authentication, host
permissions or settings also needs those policies in the shared configuration
and network boundary; a parser must never grant itself additional host access.

`test_store_adapters.py` reads every library recording through its adapter.
`test_wishlists.py`, `test_readers.py` and `test_quick.py` cover the larger
recorded layouts, pagination and partial reads. The fixtures contain synthetic
account data only. See their README for how to capture a layout change.

## Health and reporting

The private SQLite document `store-health.json` keeps each operation's last
attempt, last success and fixed failure category. A failed attempt preserves
the previous successful timestamp. Partial downloads do not claim success;
cancellation does not count as a store failure.

Stores shows this state and provides a **Report a problem** link. The prefilled
GitHub issue contains only Hoard's version, the store, the operation and a
fixed failure code. Exception messages, purchase names, local paths, addresses,
cookies and download tokens are never copied into that report. The user can
review and add a description before submitting it. Hoard does not submit the
issue itself.

## What each store is read for

The website's page for stores (`site/stores.html`) links its older claims to code
pinned at Hoard 4.3.1. These are the newer ones, by where they're done:

- **Quick refresh** (issues #300, #331): `common.quick_done()` ends a read after
  `QUICK_PAGES` pages or `QUICK_ITEMS` products, whichever comes first; each
  adapter's reader asks it. `jobs.Jobs._quick_refresh()` reads every store you
  use, or one, then the start of the wishlists kept from them;
  `jobs.Jobs._quick_wishlist()` reads one list, named to its reader by
  `wishlists.wanted()`. What a quick read doesn't reach is kept
  (`library.Library.replace_store(keep_others=True)`, a wishlist's `"partial"`).
- **Wishlists** (issue #158): `wishlists.READERS`, each adapter's
  `wish_read_*()`, read only when asked, in the store's own signed-in window.
- **Creators' tags and the adult flag** (issues #206, #311):
  `library.store_tags_from_pages()` reads at most `STORE_TAG_PAGES` (40) owned
  products' public pages each time a store is refreshed, never in a quick
  refresh; `adult.on_a_page()` reads the store's own flag from what's read.
- **Each store's record** (issue #322): `stores/health.py`, from the results of
  what was done anyway. It sends nothing.
- **Pacing**: `pace.py`, with each adapter's `requests_per_minute` (Jinxxy's 120).
