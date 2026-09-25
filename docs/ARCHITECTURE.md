# How Hoard is built

A guide for anyone reading or changing the code. Both tools are plain Python with no build step: each
page is a single HTML file with its styles and script inline, served by the tool itself.

## Repository layout

```
hoard/                 the app (python -m hoard); each piece of code exists once
  __init__.py          version
  __main__.py          python -m hoard
  paths.py             where everything lives: Hoard's app-data folder, the downloads folder
  config.py            settings (config.json in the app-data folder)
  common.py            progress messages (with a hook the app uses to show them), shared errors
  safety.py            data files, seals, store links, and the web rules for the local server
  net.py               is a store reachable?
  egress.py            the one path for store pages, data and files: https, public addresses, hop by hop
  browser.py           store sign-ins and the store browser
  tags.py              your tags
  library.py           reading what you own from each store; the library list
  downloader.py        downloading, the records of what's on disk, the catalog files, verify
  downloads.py         the Downloads view's index of what's on disk
  jobs.py              background work, one job at a time: refresh, sign in or out, download, install the browser
  setup.py             the onboarding assistant's checks: browser, sign-in status, installing, moving 1.x across
  marks.py             archive, hide and remove choices, and the hidden library's PIN
  server.py            the local server behind both views
  cli.py               the command line (docs/COMMAND-LINE.md)
  web/                 library.html, downloads.html and the bundled fonts
Hoard.bat, Setup.bat   Windows launchers (run.sh, setup.sh on Linux and macOS)
requirements.in/.txt   dependencies, and the hash-locked list Setup installs
brand/                 logo files (the wordmark is outlined, so no font is needed)
scripts/build_release.py   builds the release zip
scripts/build_vpm.py   builds Hoard for Unity's release files: the .zip, a .unitypackage and package.json
Packages/soloflighter.hoard/  Hoard for Unity (a VPM package, editor-only). Editor/Core is plain C# with no
                       Unity references (catalog, seal, .unitypackage GUIDs), tested by tests/test_unity.py
                       with Mono against files Hoard's own Python code writes; Editor/ is the window
Packages/, ProjectSettings/, Assets/, source.json, Website/   VRChat's template-package layout: the repository
                       is also a Unity 2022.3 project. unity-release.yml ("Build Release") publishes the
                       package; build-listing.yml builds the VCC listing and its page (Website/) with VRChat's
                       package-list-action, pinned, from every release
tests/                 security tests, run on every change
.github/workflows/     check.yml runs the tests and the build; release.yml publishes tagged versions
docs/                  this guide and the others
```

The two pages share one design system and several blocks of script (tags, settings, downloading), each
connected to its page through a small adapter object `T`.

## Sign-ins

Both tools drive a real Chromium browser through Playwright, with one profile per store that belongs
to Hoard alone. The "sign-ins" section near the top of each Python file handles it (the copies in
all in `browser.py`):

- `profile_dir(cfg, store)` is `sign-ins/<store>` in Hoard's app-data folder.
- `launch_context(p, cfg, headless, store)` moves sign-ins saved by older versions into per-store
  profiles (`_migrate_old_signins`, keeping only each store's own cookies), takes that store's
  `ProfileLock` (an OS file lock released automatically on exit), and starts Chromium through `_launch`.
- `_launch` drops Playwright's `--password-store=basic` and `--use-mock-keychain` switches, so cookies are
  encrypted by the operating system. On Linux it asks D-Bus for a Secret Service or KWallet keyring
  (`linux_keyring`) and passes it explicitly; with none it raises `SigninsUnprotected` unless
  `allow_unprotected_signins` is set. After signing in, `check_saved_signin` reads the cookie database
  and deletes the profile if any cookie used Chromium's fixed fallback key.
- `sign_out()` asks the store to end the session (Gumroad's `/logout`, or the store's own sign-out
  control via `SIGN_OUT_JS`), deletes the store's profile, checks no other profile holds its cookies,
  and returns a sentence saying what happened.
- Only store cookies are ever copied out of the browser (Gumroad and Booth downloads use them for
  resumable HTTP), and those copies are cleared when the run ends.

## Reading stores

| Store | How purchases are found | Notes |
|---|---|---|
| Gumroad | The library page's embedded Inertia data (`data-page` JSON), 15 purchases a page, archived ones read separately | The most dependable reader; the data shapes follow Gumroad's open-source code |
| Booth | `BOOTH_JS` reads each card on `accounts.booth.pm/library`, `/library/gifts` and `/library/free_downloads`, page by page | Files come from the download-button placeholders' `data-href` (`test=downloadable`). They redirect to a short-lived address; if Booth refuses the direct request, `booth_fetch` downloads through the browser |
| Jinxxy | `JX_CARDS_JS` reads the inventory cards, scrolling and clicking "load more" until nothing new appears | No buyer API. Card text skips buttons, menus and screen-reader labels |
| Payhip | Purchases live in each shop (`<shop>/b-account`, often on the shop's own domain). `PAYHIP_SHOP_JS` reads each shop listed in settings (`payhip.shops`), which `config.apply_store_sites` also adds to Payhip's trusted sites | Payhip shows automated browsers a bot check, so the downloader uses a visible window and waits for the user to complete it |

The readers are JavaScript strings evaluated inside the store page, so they see what the user sees.
When a store changes its layout, the `debug <store>` and `probe jinxxy` commands save the
page, its links and what the reader found, which is usually enough to fix a reader.

**Importing a saved page** (`import_saved_page` in `library.py`): the user saves a store page from their
own browser. The file is read offline in a browser with every network request blocked and every
`<script>` removed, and parsed with the same reader.

## The library (`library.py`, `jobs.py`, `server.py`)

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

## Downloads (`downloader.py`, `downloads.py`)

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
- `downloads.py` builds the Downloads view's index from the manifests. The server caches it and rebuilds
  it after a download, a tag change, a settings change or a rescan. Its routes are `/downloads`,
  `/api/assets`, `/files/<image>` and `POST /api/open` (open a folder). `POST /api/download` starts a
  download job; `POST /api/cancel` stops it after the current file.
- `jobs.Jobs._download` runs the same sync as the command line, but captures its progress messages
  (`common.capture_log`) for the page, which polls `/api/status`. Stopping raises `common.Cancelled`, a
  `BaseException` so per-file error handling can't swallow it; the catalog is still rebuilt on the way out.
- Each library item gets `on_disk`: the Downloads id of the same product (matched by `tag_key`), if any.

## Tags

Your tags live in `tags.json` in the app-data `Hoard` folder, shared by both views. `tags.py` holds the code:

- `tag_key(store, name)` identifies a product by store and normalised name. That's the one identifier
  the library and the downloads can both compute, since stores number some products differently.
- `TagStore` holds `tags` (every tag, with an optional word to match), `items` (tags put on products),
  `excluded` (matched tags taken off a product) and `hidden` (dismissed suggestions). `tags_for()` works
  out a product's tags: assigned, plus matched, minus excluded.
- `TagStore.change()` applies one change from a page (`assign`, `create`, `keep`, `match`, `rename`,
  `delete`, `hide`, `unhide`). It re-reads the file under a thread lock and an OS file lock, so two processes
  can save at once without losing anything.
- Suggestions are still worked out fresh for each response (`enrich()` in Hoard, `collect_catalog()` in the
  downloader). Hidden words and words that are already your tags are left out.
- Both servers accept changes at `POST /api/tags`, under the same rules as other actions: only from the
  computer itself, only as JSON. The pages share one block of tag code (from "tags: your own tags" to the
  end of `wireTags`), connected to each page through a small adapter object `T`.

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
  `safe_url()` on the server.
- Server-side fetches go through `fetch_public`. Its connection classes (`_PublicHTTPConnection`,
  `_PublicHTTPSConnection`) look the host up once, refuse it if any address isn't public, and connect to
  exactly the checked address (TLS still verifies the certificate against the host name), so DNS
  rebinding can't slip in between check and connection. Every redirect opens a new, checked connection.
- Only raster images are cached or served (`IMAGE_TYPES`); every response that isn't a page is sent with
  `Content-Security-Policy: default-src 'none'; sandbox`.
- With `--host 0.0.0.0`, `network_tls` requires `--tls-cert`/`--tls-key` (served through
  `TLSServerMixin`, handshake in each request's thread) or an explicit `--plain-http`.

## Data files

Each Python file carries the same "data files" section (a test checks the copies match):

- `clean_text()` removes control and invisible formatting characters from any text from a store or a
  data file; `safe_name()` does the same for file and folder names.
- `read_json_file()` reads with a size limit and turns damage (bad JSON, absurd nesting) into
  `DataFileError`; callers `set_aside()` a damaged file under a new name and carry on.
- `write_file_safely()` writes through `tempfile.mkstemp` and `os.replace`, so a planted symlink is
  replaced rather than followed. With `root`, the target folder must resolve inside it.
- In the downloader, `rel_to_path()` only accepts plain relative paths (`valid_rel`) that resolve inside
  their base, and `clean_manifest()` applies it, plus text and link cleaning, to every record read from
  `_manifest.json`. `no_link()` clears planted links before `.part` files are written.
- `validate_catalog_entry()` states the promises in [DATA-FORMATS.md](DATA-FORMATS.md);
  `build_catalog()` leaves out any entry that fails it.
- `TagStore.sanitize()` checks every entry of the tag file on load, converting names the rules don't
  allow; `TAG_LIMITS` caps its size.
- `store_link(store, url)` is the only way a link reaches a page or a data file: https, on that store's
  own site (`STORE_LINK_SITES`). The pages repeat the rule in `storeUrl()`, and a test keeps the two lists
  identical. Downloads never use stored links.
- `seal()` adds an HMAC-SHA256 `integrity` field keyed by `integrity_key()` (random, in the app-data
  folder); `check_seal()` answers `sealed`, `unsealed`, `foreign` or `changed`, using
  `remember_sealed()`'s list of files this install has sealed so a removed seal counts as `changed`.
  `Manifest` and `Library` drop links from anything not `sealed` or `unsealed`; `cmd_verify` reports and
  re-seals changed manifests without their links, then rebuilds the catalog.

## Tests and dependencies

`tests/test_security.py` covers each finding from the September 2026 reviews
([security-review-2026-09.md](security-review-2026-09.md)) and checks that the code the two tools share
hasn't drifted apart. It needs no network or browser: `python -m unittest discover -s tests -v`.

Dependencies are listed in `requirements.in` and locked, with hashes, in `requirements.txt`:
`pip-compile --generate-hashes --strip-extras --no-emit-index-url requirements.in`. Setup installs with
`--require-hashes`, so a changed package fails to install rather than running.

## Offline

Nothing a page needs comes from outside the computer:

- The typefaces are in `hoard/web/fonts/`, served at `/fonts/<file>` (`font_path()` in `server.py`).
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

1. Raise `__version__` in `hoard/__init__.py` and add a
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
