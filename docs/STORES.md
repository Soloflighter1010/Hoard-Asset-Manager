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
