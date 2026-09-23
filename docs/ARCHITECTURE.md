# How Hoard is built

A guide for anyone reading or changing the code. Both tools are plain Python with no build step: each
page is a single HTML file with its styles and script inline, served by the tool itself.

## Repository layout

```
Hoard/                 the library: everything you own, from every store, on one page
  library.py           store readers, sign-ins, the local server, the command line
  library.html         the page (styles, markup and script in one file)
HoardDownloader/       the downloader: keeps local copies of everything you own
  asset_dl.py          store downloaders, sign-ins, manifests, tags, the command line
  asset_browser.py     the local server behind "Browse your downloads"
  browser.html         that page
brand/                 logo files (the wordmark is outlined, so no font is needed)
fonts/                 the pages' typefaces (WOFF2) and their licenses, bundled for offline use
scripts/build_release.py   builds the release zips
.github/workflows/     check.yml runs the build on every push; release.yml publishes tagged versions
docs/                  this guide
```

Each tool folder also has its launchers (`Setup.bat`, `Hoard.bat` / `Hoard Downloader.bat`, `setup.sh`,
`run.sh`), `requirements.txt`, `config.example.json` and its own README. The two tools share no code
at runtime, so each works when it's the only one installed. Where they need the same logic (sign-ins,
web safety, the Booth and Payhip readers), each file carries its own copy. When you change one,
change the other.

## Sign-ins

Both tools drive a real Chromium browser through Playwright, with a profile that belongs to Hoard
alone. The "sign-ins" section near the top of each Python file handles it:

- `profile_dir()` picks the folder: the user's app-data `Hoard/sign-ins`, shared by both tools.
- `launch_context()` takes a `ProfileLock` (an OS file lock released automatically on exit), moves
  profiles left over from before 1.2 (`_migrate_legacy_profiles`), and starts Chromium **without**
  Playwright's `--password-store=basic` and `--use-mock-keychain` switches, so cookies are encrypted by
  the operating system rather than a well-known key.
- `sign_out()` clears one store's cookies and site storage, or deletes the whole profile.

## Reading stores

| Store | How purchases are found | Notes |
|---|---|---|
| Gumroad | The library page's embedded Inertia data (`data-page` JSON), 15 purchases a page, archived ones read separately | The most dependable reader; the data shapes follow Gumroad's open-source code |
| Booth | `BOOTH_JS` reads each card on `accounts.booth.pm/library` and `/library/gifts`, page by page, until a page adds nothing new | File links (`/downloadables/<id>`) answer with a redirect to a short-lived download address |
| Jinxxy | `JX_CARDS_JS` reads the inventory cards, scrolling and clicking "load more" until nothing new appears | No buyer API. Card text skips buttons, menus and screen-reader labels |
| Payhip | `PAYHIP_CARDS_JS` finds product cards by their cover image and links | Payhip shows automated browsers a bot check, so the downloader uses a visible window and waits for the user to complete it |

The readers are JavaScript strings evaluated inside the store page, so they see what the user sees.
When a store changes its layout, `debug <store>` (Hoard) and `probe jinxxy` (Hoard Downloader) save the
page, its links and what the reader found, which is usually enough to fix a reader.

**Importing a saved page** (`import_saved_page` in `library.py`): the user saves a store page from their
own browser. The file is read offline in a browser with every network request blocked and every
`<script>` removed, and parsed with the same reader.

## Hoard (`library.py`)

- `FETCHERS` maps each store to a function that returns a list of items built by `item()`. That's the only
  place a store's data enters the library, and it keeps only http(s) links (`safe_url`).
- `Library` keeps `library.json`: `items` (a flat list) and `stores` (per store: last update, count, any
  error, and whether the list came from a refresh or an import). A failed or empty refresh never replaces
  a store's list.
- `enrich()` adds suggested tags (words shared by several item names) and `also_in` (the same product
  owned on another store, matched by a normalised name) every time the page asks for the library.
- `Jobs` runs one browser task at a time in the background (refresh, sign in, sign out). The page polls
  `/api/status` while one runs.

| Endpoint | What it does |
|---|---|
| `GET /` | The page |
| `GET /api/library` | Items with tags and matches, store status, the job state, version |
| `GET /api/status` | Job state and store status, for polling |
| `GET /thumb/<item key>` | That item's image, fetched once from a public address and cached |
| `POST /api/refresh`, `/api/login`, `/api/logout` | Start a job (`{"stores": [...]}`) |
| `POST /api/import` | Read a saved store page (`{"store", "filename", "content"}`) |

## Hoard Downloader (`asset_dl.py`)

- Each store has a `sync_<store>` function. They all record progress in a per-store `Manifest`
  (`<root>/<Store>/_manifest.json`): for every product its folder and, for every file, where it's saved,
  its size and when it was downloaded. A product keeps its folder even if it's renamed on the store.
- Gumroad and Booth download over HTTP with `http_download`, which resumes from a `.part` file. Jinxxy and
  Payhip click each file's download button in the browser (`download_by_clicking`), because their files
  are only handed out that way.
- A file counts as **updated** when a store offers a new version of it: a different size or file link on
  Gumroad or Booth, or the same file name under a new label on Jinxxy or Payhip.
- `collect_catalog()` builds the catalog and tags from the manifests; `build_catalog()` writes them to
  `catalog.json`, `tags.json` and each product's `asset.json`.
- `asset_browser.py` serves the downloads browser (`/`, `/api/assets`, `/files/<image>`, and
  `POST /api/open` to open a folder). It reads the manifests fresh on every rescan.

## Web safety

Both servers share the rules in their "web safety" section:

- They bind to `127.0.0.1` and check the `Host` header, which stops DNS-rebinding attacks. With
  `--host 0.0.0.0` other devices need the access key (`check_access`), and every action endpoint still
  only accepts requests from the computer itself.
- Action endpoints only accept `Content-Type: application/json`, which other websites can't send
  without a CORS preflight that the servers never approve.
- Every page carries a Content-Security-Policy that allows only its own inline script, by hash
  (`content_security_policy`). If you edit the script, the hash updates by itself. Don't add inline
  event handlers (`onclick="..."`); they'd be blocked.
- Store text is always escaped (`esc()` in the pages), and links pass `safeUrl()` in the page as well as
  `safe_url()` on the server. Server-side fetches go through `fetch_public`, which refuses anything that
  isn't a public internet address, including after redirects.

## Offline

Nothing a page needs comes from outside the computer:

- The typefaces are in `fonts/`, served at `/fonts/<file>` by both tools. `font_path()` looks next to the
  program first (single-tool zips carry their own copy) and then one folder up (the repository, and the
  bundle, which keeps one shared copy). `build_release.py` places them.
- Hoard saves every product image after each refresh (`cache_images`), and after an import, in
  `.cache/thumbs`. `/thumb/` serves the saved copy without going online.
- Before refreshing, signing in or syncing, `reachable(store)` opens a connection to that store only. An
  unreachable store gets `unreachable_message()`, and its saved data is left alone. Browser errors that
  mean the connection dropped part-way (`is_network_error`, `NETWORK_ERRORS`) are reported the same way.
- The pages show a notice while the browser reports being offline, and Hoard's Refresh and Sign in
  buttons explain instead of trying. Sign out works offline because it only touches local files.

## The pages

`library.html` and `browser.html` share one design system. The CSS custom properties at the top of each
file (`--cave`, `--ledge`, `--gold`, the store colours) are the brand's colours for dark and light mode.
Script state lives in a single `state` object that's mirrored in the address bar, so views can be
bookmarked. Rendering rebuilds the grid with `innerHTML`, always through `esc()`.

## Releasing

1. Raise `__version__` in `Hoard/library.py` and `HoardDownloader/asset_dl.py` (they must match) and add a
   `## <version>` section to `CHANGELOG.md`.
2. Push a `v<version>` tag. `release.yml` runs `scripts/build_release.py`, which checks the versions,
   compiles the Python and builds the three zips from an explicit file list, then publishes a release
   with that version's changelog section. To rebuild the release for an existing tag, use
   **Actions → Release → Run workflow**.

## Conventions

- Text people see is plain and specific: say what happened and what to do next, without blame or
  exclamation marks.
- Never commit personal files. `.gitignore` covers `config.json`, `library.json`, sign-in folders,
  downloads and troubleshooting output, and the build refuses to package anything not on its list.
- Windows launchers need CRLF line endings; `.gitattributes` keeps them right.
