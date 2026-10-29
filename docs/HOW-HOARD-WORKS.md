# How Hoard works

A guide for contributors, and for the stores Hoard reads, to how Hoard fits together: what each part does, where
its code and its files are, and what happens, step by step, when Hoard syncs a store. It's the map; the detail is in
[ARCHITECTURE.md](ARCHITECTURE.md) (each part in depth) and [DATA-FORMATS.md](DATA-FORMATS.md) (the files Hoard
writes, for other programs). Every file and function named in backticks here exists: `tests/test_guide.py` checks.

## The parts, and where they are

Hoard is one Python program, `hoard/`, with no build step. It runs a small web server on this computer, and its
window (or your browser) shows the pages that server serves. Everything else is a part of that program.

| Part | What it does | Code | Its files |
| --- | --- | --- | --- |
| The window | Starts the server, opens a window on it (pywebview: Edge WebView2, WebKit), one copy at a time, and quits cleanly | `hoard/app.py`: `run_app()`, `open_window()`, `quit_cleanly()` | `logs/` in the app-data folder |
| The local server | Serves the pages and their API (`/api/...`), only to requests that carry this run's key | `hoard/server.py`: `AppServer`, `Handler`; `hoard/safety.py`: `check_access()` | `config.json` (settings) |
| The pages | The Library and Downloads, with Projects, Sets, Tasks and Settings as windows over them; plain HTML and script, translated in place | `hoard/web/library.html`, `hoard/web/downloads.html`, `hoard/web/shared.js`, `hoard/web/looks.css`, `hoard/web/i18n/` | the window's own storage (`window/`) |
| Tasks | Long work, one task at a time in each lane (Projects has its own), queued, stoppable, kept in Tasks | `hoard/jobs.py`: `Jobs` (`start`, `_finish`, `cancel`, `force_stop`), `Schedule` | `tasks.json`, `project-tasks.json` |
| Sign-ins | A real Chromium (Playwright), one profile per store, belonging to Hoard alone | `hoard/browser.py`: `launch_context()`, `signin_protection()` | `sign-ins/` |
| Reading stores | What you own on each store: its library pages read in Hoard's browser (itch.io: its API) | `hoard/library.py`: `fetch_booth()`, `fetch_gumroad()`, `fetch_jinxxy()`, `fetch_payhip()`, `fetch_itch()`, `FETCHERS`; `hoard/itch.py` | `library.json` |
| The network rules | Every request for a store's pages, data or files: https only, public addresses only, one checked hop at a time, a store's cookies only to that store | `hoard/egress.py`: `session()`, `get()`, `download()`, `check_hop()` | `.part` files while downloading |
| Downloading | What's new or changed on each store, downloaded into `<Store>/<Creator>/<Product>`, resumable, recorded | `hoard/downloader.py`: `cmd_sync()`, `sync_booth()`, `sync_gumroad()`, `sync_jinxxy()`, `sync_itch()`, `Manifest`, `left_out()` | each store's `_manifest.json` |
| The catalog | What's on disk, for Hoard for Unity and other programs, sealed | `hoard/downloader.py`: `build_catalog()`, `write_catalog_files()`; `hoard/downloads.py`: `build_index()` | `catalog.json`, `asset.json`, `tags.json` |
| Tags and types | Your tags, suggested tags, store tags, and what kind of product each is | `hoard/tags.py`: `TagStore`, `tag_key()`, `product_type()`; `hoard/library.py`: `enrich()` | `tags.json` |
| Your choices | Archived, hidden and removed products, the hidden library's PIN | `hoard/marks.py`: `MarkStore` | `marks.json` |
| Sets and wishlists | Products grouped to use together; wishlists read from the stores, with their prices | `hoard/sets.py`: `SetStore`; `hoard/wishlists.py`: `from_product_page()`, `merge_lists()` | `sets.json`, `set-pictures/` |
| Short links | A set shared by a link to Hoard's share server, locked on your computer first | `hoard/shortlinks.py`: `make()`, `fetch()`; `share/worker.mjs` | (the server's) |
| Projects | Unity projects shared with ALCOM and the Creator Companion: VPM packages, and your products put in | `hoard/vpm/api.py`: `Service`; `hoard/vpm/preload.py`, `hoard/vpm/resolve.py`, `hoard/vpm/listing.py` | `vpm-projects.json`, `vpm-presets.json` |
| Hoard for Unity | A package in a project: what of your hoard it uses, its credits, and putting more in | `Packages/soloflighter.hoard/Editor/HoardWindow.cs`, `Packages/soloflighter.hoard/Editor/Core/Catalog.cs` | `projects/<id>.json` (its reports) |
| Checks | The routine check (stores, downloads, updates, on a schedule) and the check of your downloads (each file's SHA-256) | `hoard/jobs.py`: `Schedule`, `_routine`, `_verify`; `hoard/downloader.py`: `check_integrity()`, `resolve_problem()` | `routine.json`, `integrity.json` |
| Notifications | The system's own, and Apprise's (to services you give addresses for): counts, never names | `hoard/notify.py`: `show()`; `hoard/alerts.py`: `send()`, `deliver()` | Apprise's addresses: `hoard/vault.py` |
| Secrets | API keys and Apprise's addresses, kept by the operating system | `hoard/vault.py`: `save_key()`, `save_secret()` | `keys/` (Windows), Keychain, keyring |
| Backups | Settings, tags, sets, choices and the library list in one file | `hoard/backup.py`: `make()`, `restore()` | `Hoard backups/` in your Documents |
| Updates | A newer release from GitHub, checked against its published checksums before it runs | `hoard/updater.py`: `Updates`, `fetch_latest()`, `download_installer()` | `updates/` |

Where the app-data folder is: `%LOCALAPPDATA%\Hoard` on Windows, `~/Library/Application Support/Hoard` on macOS,
`~/.local/share/Hoard` on Linux (`hoard/paths.py`: `data_dir()`). The downloads folder is yours to choose
(`hoard/config.py`: `root_dir()`).

## A sync, end to end

**Sync** is the job most of Hoard exists for. Here's what happens, in order.

1. **The page asks.** The Library's **Sync** asks before it starts (`hoard/web/shared.js`: `confirmSync()`), then
   posts to `/api/sync`. The server starts a task: `Jobs.start("sync", stores)`. If another task is running, this
   one waits in the queue; Tasks shows both.
2. **Each store is read** (`Jobs._sync` calls `_refresh`). Hoard opens its browser on the store's own library
   page, signed in with the profile only Hoard uses, and reads what you own from the page as you would see it:
   `FETCHERS[store](...)`, for example `fetch_booth()`. itch.io is read through its API with the key you gave
   Hoard. Between pages Hoard waits (`request_delay` in Settings), and it never reads faster than a person
   scrolling would. The list replaces that store's part of `library.json` (`Library.replace_store`), unless the
   read failed or came back empty, when the old list is kept and the store says why.
3. **What's new is worked out** (`Jobs._download`, then `cmd_sync()`). For each store, its download pages are read
   again for the files themselves (Booth's library lists them; Gumroad and Jinxxy each product's page; itch.io the
   API). Each product's record (`Manifest.record`) says which files are on disk, at what size and link. A file the
   record doesn't have, or one whose size or link changed, is to be downloaded; your rules and earlier choices
   leave some out (`left_out()`), and products you always skip are skipped.
4. **Files are downloaded** through `egress.download()`: https only, to public addresses only, each redirect
   checked before it's followed, into a `.part` file that resumes where it stopped, and only renamed into place
   once it's whole. A file the store refuses to hand over directly is downloaded through Hoard's browser instead.
   A file an update replaces is kept in `_Previous versions` (`hoard/previous.py`: `keep()`).
5. **What came is recorded.** Each product's record gets its files' sizes, links and when they came, and the
   store's `_manifest.json` is saved, sealed, as it goes (`Manifest.checkpoint`) and at the end.
6. **The catalog is rebuilt** (`build_catalog()`): `catalog.json` lists every product on disk with its files,
   tags and types, sealed, for Hoard for Unity and anything else that reads it; each product's folder gets an
   `asset.json`.
7. **The pages hear.** The task ends (`Jobs._finish`): its outcome, its counts and its progress go into Tasks; the
   downloads index is rebuilt (`build_index()`); notifications you chose are sent (`AppServer._news`).

Later, the check of your downloads (`check_integrity()`) reads each file's SHA-256 once and keeps it in its record,
so later checks only read a file again when its size or time changed; what it finds can be dealt with from its
results (`resolve_problem()`).

## For stores

Hoard is a tool for people to keep the files they've bought. If you run one of the stores it reads, here's what it
does on your site, and what it never does.

**What Hoard reads:** the signed-in customer's own library or purchases pages, each product's download page, the
customer's wishlists when they ask, and public product pages (for a product added to a wishlist or a set by its
link, and for the tags a creator gave it). It reads them as a browser shows them, in a real Chromium, signed in
by the customer on your own sign-in page.

**What it never does:** it never sees or keeps a password (the customer signs in on your page; Hoard keeps only
the session your site hands out, encrypted by the operating system); it never gets past a bot check for anyone
(a customer passes it themselves, in the window); it never reads another customer's anything, or anything a
customer couldn't see; it never sends anything you serve to anyone else (no telemetry, no server of Hoard's
in between); and it waits between pages, reading no faster than a person would.

**What would make Hoard work better with your store:**

- Stable markup on the library and download pages (data attributes, or JSON in the page), so a redesign doesn't
  break customers' downloads.
- An API for a customer's own purchases and their files, with a key the customer makes (as itch.io has), which
  Hoard would use in place of reading pages.
- File sizes and a checksum (or a stable ETag) on download links, so Hoard can tell an update from the same file.
- Your rate limits, written down, so Hoard can stay well within them.

To talk about any of this, open an issue on GitHub, or see `SECURITY.md` for anything security-related.

## Adding a store

A store is a reader, a downloader and a few names. Each piece is small; what's hard is reading the store's pages
reliably.

1. **Its name and sites:** `STORES` in `hoard/library.py` (its label, whether Hoard downloads from it), and its
   sites in `store_sites()` (`hoard/safety.py`): a store's cookies only ever go to these.
2. **Reading what you own:** a `fetch_<store>()` in `hoard/library.py` that returns `item()`s, added to
   `FETCHERS`. Read the page's own data where there is some (`extract_page_json()`), not its look.
3. **Downloading:** a `sync_<store>()` in `hoard/downloader.py`, added to `cmd_sync()`'s list, using
   `Manifest.record`, `would_get()` for a check, `left_out()` for files you didn't choose, and `egress.download()`
   for every file.
4. **The pages:** its colour (`--<store>` in `hoard/web/library.html` and `hoard/web/downloads.html`, and in each
   theme in `hoard/themes.py`), and its name in the translations.
5. **Tests:** saved pages made up for the test (never a real customer's) in `tests/data/`, read by a test in
   `tests/test_readers.py`, and a stand-in store for the downloads in `tests/test_app.py`.
6. **The wiki:** its section in `wiki/Stores.md`, and the translations of it.

## Running the tests

```
python3 -m unittest discover -s tests          # everything (about 15 minutes; the page tests need Playwright's Chromium)
python3 -m unittest tests.test_app             # one file
python3 -m unittest tests.test_app.DownloadChoices.test_always_skip   # one test
```

The tests need no network, no store account and no browser sign-in: stores are stand-ins serving made-up pages.
The page tests (`tests/test_pages.py` and the others that open pages) need Playwright's Chromium
(`python -m playwright install chromium`). Hoard for Unity's core is tested with Mono (`tests/test_unity.py`), and
skipped without it. Every change runs them all on GitHub (`.github/workflows/check.yml`).

## Making a release

`wiki/Releasing.md` has the steps. In short: the version in `hoard/__init__.py` (and Hoard for Unity's in
`Packages/soloflighter.hoard/package.json` when it changed), the changelog in `CHANGELOG.md`, a tag `v<version>` on
`main`, and `.github/workflows/release.yml` builds, signs and publishes the zips, the Windows installer, the Mac
packages and the Flatpak, each checked by VirusTotal before the release is published.

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md): how to propose a change, the tests a change needs, and how Hoard's words
are written.
