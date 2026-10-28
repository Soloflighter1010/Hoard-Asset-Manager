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
  space.py             Downloads' Disk space: the same file kept more than once, from the integrity check's fingerprints
  packages.py          Look inside: a .unitypackage's assets and previews, and a .zip's files and packages, read in place
  needs.py             What it needs: the GUIDs each package names and has, read in the background; known_tools.json
  previous.py          Previous versions: the file an update replaces, kept in the product's folder, and Restore
  sets.py              Sets: products grouped to use together (sets.json), listed in catalog.json for Import set
  wishlists.py         wishlists: reading them from the stores and saved pages, and a product from its store link
  shortlinks.py        short links for shared sets: Hoard's share server (share/), through egress.send
  backup.py            Backup and restore: settings, tags, sets, choices and the library list in one file
  jobs.py              background work, one job at a time: refresh, sign in or out, download, install the
                       browser; Schedule, the routine check
  setup.py             the onboarding assistant's checks: browser, sign-in status, installing, moving 1.x across
  marks.py             archive, hide and remove choices, and the hidden library's PIN
  server.py            the local server behind both views
  cli.py               the command line (docs/COMMAND-LINE.md)
  app.py               the desktop app: its window (pywebview), one copy at a time, log file, clean quit
  notify.py            a notification from the system when the routine check finds something to download
  updater.py           checking GitHub for a newer release; downloading, checking and running its installer
  vpm/                 Projects: the Unity projects shared with ALCOM and the Creator Companion, their VPM packages,
                       and your library in them (see "Projects" below); templates/ holds vrc-get's VRChat templates
  web/                 library.html, downloads.html, shared.js (what both pages share), looks.css (the styles),
                       styleguide.html (every part of the pages, at /styleguide) and the bundled fonts
Hoard.bat, Setup.bat   Windows launchers (run.sh, setup.sh on Linux and macOS)
requirements.in/.txt   dependencies, and the hash-locked list Setup installs
brand/                 logo files (the wordmark is outlined, so no font is needed)
scripts/build_release.py   builds the release zip
packaging/             the apps: hoard.spec (PyInstaller: Hoard.exe and hoard-cli.exe on Windows; Hoard.app on
                       macOS), hoard.iss (Inno Setup installer), the icons; flatpak/ (the Linux Flatpak's
                       manifest, python3-deps.json, launcher, .desktop and metainfo); built by release.yml,
                       checked by check.yml
requirements-app/-mac/-flatpak.in/.txt   each app's hash-locked dependencies, pinned to requirements.txt's
scripts/build_macos_pkg.sh   wraps dist/Hoard.app in Hoard-<version>-macos-<chip>.pkg (pkgbuild, /Applications)
scripts/flatpak_deps.py   writes packaging/flatpak/python3-deps.json from requirements-flatpak.txt
scripts/build_vpm.py   builds Hoard for Unity's release files: the .zip, a .unitypackage and package.json
Packages/soloflighter.hoard/  Hoard for Unity (a VPM package, editor-only). Editor/Core is plain C# with no
                       Unity references (catalog, seal, .unitypackage GUIDs), tested by tests/test_unity.py
                       with Mono against files Hoard's own Python code writes; Editor/ is the window
Packages/, ProjectSettings/, Assets/, source.json, Website/   VRChat's template-package layout: the repository
                       is also a Unity 2022.3 project. unity-release.yml ("Build Release") publishes the
                       package; build-listing.yml builds the VCC listing and its page (Website/) with VRChat's
                       package-list-action, pinned, from every release
share/                 Hoard's share server, for short links: a Cloudflare Worker (worker.mjs) with Workers KV,
                       its wrangler.toml, and a stand-in KV and server for the tests; deployed by hand
                       (share/README.md), not by a workflow
tests/                 security tests, run on every change
.github/workflows/     check.yml runs the tests and the build; release.yml publishes tagged versions; wiki.yml
                       publishes wiki/ to the repository's GitHub wiki
docs/                  this guide and the others
wiki/                  the wiki's pages, written and reviewed here (tests/test_wiki.py checks their links and facts)
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
  `allow_unprotected_signins` is set (`_key_args`). After signing in, `check_saved_signin` reads the cookie
  database and deletes the profile if any cookie used Chromium's fixed fallback key.
- Signing in (issue #21) starts the browser as itself, not through Playwright: `SignInWindow` runs
  `browser_program` (the chosen channel's executable, or Playwright's Chromium) with `--user-data-dir` set to the
  store's profile, the same `_key_args`, and the store's sign-in pages (`library.sign_in_urls`), holding the
  store's `ProfileLock`. Google and similar providers refuse browsers under automation. The job waits while the
  process runs or Chromium's own lock is held in the profile (`_profile_in_use`: `SingletonLock` naming a live
  process, or a `lockfile` held open on Windows). A link pasted from an email is passed to the open window by
  starting the browser again on the same profile. `automated_sign_in` keeps the old Playwright window.
  Chromium's own sandbox stays on where it can start (`_without_sandbox`: off in the Flatpak, as root, and for
  Playwright's Chromium under Ubuntu's AppArmor user-namespace restriction). On Windows, Playwright's Chromium is
  first given the sandbox groups' read access to its folder (`_let_sandbox_read`, icacls), without which its
  network service can't start; if that fails, it starts without the sandbox.
- `sign_out()` asks the store to end the session (Gumroad's `/logout`, or the store's own sign-out
  control via `SIGN_OUT_JS`), deletes the store's profile, checks no other profile holds its cookies,
  and returns a sentence saying what happened.
- Only store cookies are ever copied out of the browser (Gumroad, Booth and Jinxxy downloads use them for
  resumable HTTP), and those copies are cleared when the run ends.

## Reading stores

| Store | How purchases are found | Notes |
|---|---|---|
| Gumroad | The library page's embedded Inertia data (`data-page` JSON), 15 purchases a page, archived ones read separately | The most dependable reader; the data shapes follow Gumroad's open-source code |
| Booth | `BOOTH_JS` reads each card on `accounts.booth.pm/library`, `/library/gifts` and `/library/free_downloads`, page by page | Files come from the download-button placeholders' `data-href` (`test=downloadable`). They redirect to a short-lived address; if Booth refuses the direct request, `booth_fetch` downloads that file through the browser (and, refused twice running, the rest of the run); a dropped connection is retried directly. The reader and the downloader page through the library with the same `library.booth_cards` |
| Jinxxy | `JX_CARDS_JS` reads the inventory cards, scrolling and clicking "load more" until nothing new appears | No buyer API. Card text skips buttons, menus and screen-reader labels |
| Payhip | Purchases live in each shop (`<shop>/b-account`, often on the shop's own domain). `PAYHIP_SHOP_JS` reads each shop listed in settings (`payhip.shops`), crediting each card to the shop its link is in; on a creator's own shop (its menu's Creator/Customer switch leads back to the page) the cards are their purchases from everywhere, with no creator on them, so they're left as Unknown creator (issue #25). `config.apply_store_sites` adds the listed shops to Payhip's trusted sites | Read only: Hoard lists Payhip purchases and never downloads them (`DOWNLOADABLE` leaves it out). Payhip shows automated browsers a bot check, so a refresh uses a visible window and waits for the user to complete it; most people import each shop's saved pages instead |
| itch.io | Its API (`itch.py`), with an API key kept by `vault.py` (DPAPI, the Keychain or the Secret Service), since its website stops automated browsers with a Cloudflare check: `/profile/owned-keys`, then `/games/<id>/uploads` and `/uploads/<id>/download` per project. The key is sent only to `api.itch.io` (egress keeps it off the file hosts). For imports, `ITCH_JS` reads `itch.io/my-purchases` by its addresses rather than its layout: a project is `<creator>.itch.io/<project>`, and one you own has a download page, `<creator>.itch.io/<project>/download/<key>`. Items are known by itch.io's project number, from the API or a saved page alike | `KEY_FORMAT` checks a pasted key before it's sent anywhere; `POST /api/itch-key` checks it with itch.io (`/profile`) before keeping it. Game builds are files whose `traits` include an operating system |

The readers are JavaScript strings evaluated inside the store page, so they see what the user sees.
When a store changes its layout, the `debug <store>` and `probe jinxxy` commands save the
page, its links and what the reader found, which is usually enough to fix a reader.

**Importing saved pages** (`import_saved_pages` in `library.py`): the user saves store pages from their
own browser, any number at once (a library often spans several pages, and Payhip has one per shop). Each is
read offline, all in one browser, with every network request blocked and every `<script>` removed, and
parsed with the same reader. Every page gets its own result: its items, an error, or the Payhip shop it's
from when that shop isn't in the user's list (it's only added when the user confirms it: `trust_shops`).

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
| `POST /api/import` | Read saved store pages, up to `MAX_IMPORT_FILES` a request (`{"store", "files": [{"filename", "content"}], "trust_shops"}`); a result for each |
| `POST /api/enter` | Trade the one-time link a page was opened with (`{"token"}`) for the access key |

## Downloads (`downloader.py`, `downloads.py`)

- Each store has a `sync_<store>` function. They all record progress in a per-store `Manifest`
  (`<root>/<Store>/_manifest.json`): for every product its folder and, for every file, where it's saved,
  its size and when it was downloaded. A product keeps its folder even if it's renamed on the store.
  While downloading, `checkpoint()` saves it at most every `SAVE_EVERY` seconds (rewriting a large
  manifest after every file and product adds up), and every sync ends with `save_changes()` in a `finally`,
  so a stop or an error never loses a finished file's record. A manifest is only written when something
  changed: `cmd_sync` treats a store with no manifest as one you don't use.
- Gumroad and Booth download over HTTP with `egress.download`, which resumes from a `.part` file. It only
  adds to one the part that follows it (206, `Content-Range` starting where it ends), counts it as finished
  only when the store says the file ends there (416, `Content-Range: bytes */<that size>`), starts again
  otherwise, and puts a file in place only once it's as long as the store said. It asks for the file's own
  bytes (`Accept-Encoding: identity`), so sizes and ranges are exact. itch.io downloads the same way, from its
  API's download address, and checks each file against itch.io's MD5. Jinxxy clicks each file's download
  button in the browser (`click_download`), because its files are only handed out that way.
  Payhip isn't downloaded from at all: `cmd_sync` only syncs `DOWNLOADABLE` stores, and the server refuses a
  download of Payhip alone. Its folder and manifest, from earlier versions, stay in the catalog.
- A file counts as **updated** when a store offers a new version of it: a different size or file link on
  Gumroad or Booth, the same file name under a new label on Jinxxy, or a different name or size shown for
  the same file on itch.io (its MD5, or else its name, size and date). itch.io files marked for an operating system (game builds)
  are skipped while `itch.skip_game_builds` is on.
- Checking for updates (issue #26) is a dry run of the same sync (`jobs.Jobs._download(check=True)`, from
  `POST /api/check-updates`): nothing is downloaded, and each store's `would_get()` notes a file the store has
  that isn't on disk. For a product already downloaded (and not a file deleted here), it goes in
  `Report.available`; `asset_updates.AssetUpdates` keeps those in `asset-updates.json` in the app data folder,
  replacing only what an earlier check found for the stores (or products) this one read to the end.
  `/api/assets` adds each asset's `update` files and `updates_checked`; `/api/library` an `update` flag.
  `POST /api/download` and `/api/check-updates` take `keys` (tag keys), which `skip_product()` limits the sync
  to; a download takes a product off the list once a file of its is saved and none of its files failed.
- `collect_catalog()` builds the catalog and tags from the manifests; `build_catalog()` writes them to
  `catalog.json`, `tags.json` and each product's `asset.json`. With nothing downloaded, an existing
  `catalog.json` and `tags.json` are rewritten empty, so they never go on listing what's gone; a folder
  that never had them doesn't get them.
- `downloads.py` builds the Downloads view's index from the manifests. The server caches it and rebuilds
  it after a download, a tag change, a settings change or a rescan. Its routes are `/downloads`,
  `/api/assets`, `/files/<image>` and `POST /api/open` (open a folder). `POST /api/download` starts a
  download job; `POST /api/cancel` stops it within a few seconds (a half-downloaded file resumes next time where the store allows).
- `jobs.Jobs._download` runs the same sync as the command line, but captures its progress messages
  (`common.capture_log`) for the page, which polls `/api/status`. Stopping raises `common.Cancelled`, a
  `BaseException` so per-file error handling can't swallow it; the catalog is still rebuilt on the way out.
- Each library item gets `on_disk`: the Downloads id of the same product (matched by `tag_key`), if any.
- A download of chosen products (the Library's item key, `items`; Downloads' `keys`; or `only`) is given
  `args.targets` by `downloader.direct_targets`: those products from the library, for the stores whose readers can
  open them one by one (a Jinxxy item's page, a Gumroad purchase's download page). Other stores are read in full.
- Store browsers: `browser._track` notes each one Hoard starts, and `browser.end_browsers()` ends them all (and
  Playwright's driver), from any thread, so a job waiting on one that stopped answering fails at once instead of
  waiting for ever. `Jobs.cancel` does that when Stop hasn't taken effect after `FORCE_AFTER` seconds, and
  `Jobs._watch` notes in the launch's log where a job is after `STUCK_AFTER` seconds without progress. A store tab or
  browser that closes by itself is opened again (`downloader.reopen_tab`), up to `REOPENS` times a sync.
- Closing the desktop window: `app.close_decision` minimizes the window to the taskbar (`close_to_taskbar`, on by
  default), quits, or asks the
  page (the `hoard-close` event), which answers at `POST /api/app/close` (`wait`: `app.quit_when_done`,
  `background`, or `now`: `app.quit_now`). `POST /api/quit` answers 409 `busy` while something runs, and the
  page asks the same.

- What it needs (`needs.py`): `NeedsReader` (started by `serve()`, never while a job runs) reads each downloaded
  `.unitypackage`, and each one in a `.zip`, once: the GUIDs of its assets and the GUIDs its YAML text assets name
  (`packages.read_unitypackage(refs=...)`), kept in `package-needs.json` by path, size and time. `work_out()` takes
  away each product's own GUIDs and names the rest: a tool from `known_tools.json` (built from the tools' own
  repositories and VRChat's package listing by `scripts/build_known_tools.py`), another downloaded product that has
  them, or a count of the rest. `/api/assets` gives each asset's `needs` (leaving out hidden products while locked),
  and `build_catalog` writes them into `catalog.json` (`needs.add_to_catalog`), checked by `valid_needs`. After a
  read finds something new, the catalog is written again if no job is running.
- Look inside's **Extract** (`POST /api/look-inside/extract`, `packages.extract`): the page sends what's ticked
  (`p:<package>:<path>`, `d:<package>:<folder>`, `z:<zip member>`, or `all`), and the server writes it into a new
  folder in `edits_root(cfg, root)/Extracted` (the folder editable copies go in), named after the file. A package
  is read once, in order (`read_unitypackage(on_asset=...)`), and no further than its last chosen file (`_Done`),
  each asset streamed to a temp file beside where it goes, given `FILE_MODE` (a new file's permissions, not
  mkstemp's 0600) and moved into place. `out_parts` makes each path's parts names every system allows and refuses
  `..`; `Writer` makes folders one level at a time and never through a link (that stops it all), gives a name
  already taken " (2)", keeps an asset's name and its `.meta`'s as a pair (`place(meta=True)`) so they always match,
  a folder's `.meta` its exact name (`exactly`), and stops (`CantExtract`) when the disk is full or would have less
  than `ROOM_TO_SPARE` left. One file that can't be written (`_Skip`: a file in the way, a path too long, a path
  that climbs out) is left out with why and the rest carry on, the bytes it would have taken read past so the
  package's reader stays in step. A zip's members are found by the names Look inside gave them (`member_name`,
  shared with `read_zip`), and a package in a zip goes under its own path in the zip. Nothing written at all says
  why (`Nothing could be taken out.`, with what was left out); a failure part way deletes the half-made folder.

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
  `--host 0.0.0.0` every action endpoint still only accepts requests from the computer itself.
- Every request for data, images or an action needs the server's access key (`check_access`), new on
  every start, from the computer itself too. The pages send it in the `X-Hoard-Key` header through
  `api()`; images, which the browser loads by itself, carry it as `?k=` (`keyed()`). It's never a cookie,
  because browsers send cookies for 127.0.0.1 to every port. Hoard opens its page with a one-time link
  (`entry_url()`, `#enter=...`) that the page trades for the key at `/api/enter`, so the key never appears
  on a browser's command line; `hoard serve` prints an address with the key itself (`#key=...`), which
  is also what other devices open. The pages and fonts hold nothing private and need no key.
  `/api/show` (a second copy of Hoard) proves itself with the token in the running copy's private file.
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

## Short links (`shortlinks.py`, `share/`)

From 5.0 a set is shared only by a short link (issue #162): `/api/sets` (`share`) gives the page the set's code to
lock, never a long link. A long link (`set.html#H1.…`, from Hoard before 5.0) holds the set itself, and the viewer
and **Add a shared set** still read one. A short link (`set.html#S1.<id>.<key>`) holds only an id and a key:

- **Making one:** the page locks the set's code with AES-GCM under a new random 128-bit key (`lockSet` in
  `shared.js`) and posts the locked set, with the key and the code it locked, to `/api/sets` (`short`). The
  server checks that the code is the set's code now, then sends only the locked set to the share server
  (`shortlinks.make`, through `egress.send`), which answers with an id and a token. `sets.json` keeps the id, key,
  token, expiry and which code it holds (`code_mark`), so the dialog can say when the set has changed since.
- **The share server** (`share/worker.mjs`) keeps a locked set in Workers KV for 14 days, with the token's
  SHA-256 as its metadata. Only that token updates (`PUT`) or deletes (`DELETE`) it; anyone may read it, but only
  the set viewer's origin in a browser (CORS), and a write that carries an `Origin` header is refused. It never
  sees a key, logs nothing, caps a set at 48 KB and limits writes per address.
- **Opening one:** the set viewer (`site/set.js`) fetches the locked set by its id (its Content-Security-Policy
  allows only that `connect-src`) and unlocks it in the page; **Add a shared set** asks Hoard's server to fetch it
  (`open-short`), unlocks it in the page, and adds the code as any other.
- **Deleting one:** **Delete the short link** (`unshort`), and deleting the set, delete it from the server with
  the token. Backups leave short links out; a restore keeps this computer's.
- **Too big for one:** the share server takes a locked set of up to 48 KiB, measured once it's decoded from
  base64url (`shortlinks.MAX_DATA`, `MAX_BYTES` in the Worker; sent, it's up to 64 KiB of base64url);
  `shortlinks.fits(code)` says whether a code locks to that. `/api/sets` (`share`) says `fits`, and when it doesn't,
  how many `parts` it takes, or `why` none would do (one product too big on its own): `sets.share_parts()` cuts the
  set's products, in order, into parts each as full as fits, hidden products taking no room. Each product is packed
  once (`share_rows`, `_pack`); each part's end is searched for from the last part's length, in growing steps then
  halving; each part is sized under `part_name(name, 1, 1)`, the longest in bytes any part's real name can be (a
  longer "(n of N)" leaves fewer of the name's characters, each a byte or more); a set that doesn't fit under its
  own name is at least two parts; and the last few answers are kept, by what they were worked out from. `split`
  makes them new sets (`SetStore.split`, named with `part_name`), working the parts out under the sets' lock from
  what the set holds then: a wishlist's are wishlists without a `source`, so reading the store's list again
  changes only the wishlist itself.

A fork's builds use the same share server; a fork can't deploy to it (see `share/README.md`, "In a fork").

## Sets and Wishlists (`sets.py`, `wishlists.py`)

Wishlists are sets of kind `wishlist` in `sets.json`; the page shows them, with sets, in **Sets and Wishlists**.

- **A product's picture** in a set is `/setpic/<set>/<place>?p=<hash>` (`server.pic_for`: the first 12 hex digits
  of the SHA-256 of its product key). Taking a product out moves the rest up a place, so the server serves a picture
  only when `p` names the product at that place now, and the browser never shows one it kept for another.
- **Pages elsewhere:** a Jinxxy list's product on a site that isn't a store keeps that page as `elsewhere`
  (`wishlists.jinxxy_products`, checked by `sets.outside_link`: plain https on a public name), served with the set
  and opened by the tile (`outsideUrl`), but never put in a share code: the viewer opens only the stores' own pages.
- **Suggested tags:** `library.common_words()` (the same words Hoard suggests for a store's products) over a
  wishlist's product names gives `words` in `/api/sets`. With a wishlist open (`openWish()`), the filters beside it
  are its own: `renderTagFacets` and the pages' Creators count its products (`wishTagItems`, `wishCreators`), with
  your tags on those in your library (`wishOwnTags`, by tag key), and `wishFits` filters by `state.tags` and
  `state.creator` as the page does, plus a price range (in one currency); `wishScope()` starts them again on the way
  into or out of one. The page's sort orders its two groups (`WISH_SORTS`; Recently added keeps the store's order).
- **Add products by link** (`/api/sets`, `add-links`, at most 30): `wishlists.from_product_page()` takes only a
  product's page on Booth, Gumroad, Jinxxy, Payhip or itch.io (`LINK_HOSTS`) and reads it through
  `server.read_store_page()`, which is `fetch_public` held to that store's hosts, redirects included, sending no
  sign-in. Booth's item JSON (`booth.pm/<lang>/items/<id>.json`) gives a Booth product; other pages give it from
  their schema.org Product (JSON-LD) or their Open Graph tags. `SetStore.add_products()` keeps what's read through
  `clean_product()`, the same check as a set's other products (a link only to the store's own public page). The answer says for each link what was
  added or why not.
- **Reading wishlists again** is a job (`wishlists`); when it ends, the page loads the sets again
  (`jobEnded` in `shared.js`), so the lists it changed show at once.

## Projects (`vpm/`)

Projects is a project manager that works as [vrc-get and ALCOM](https://github.com/vrc-get/vrc-get) do, written in
Python from vrc-get's Rust (MIT): the same versions chosen, the same files kept, so Hoard, ALCOM and the VRChat
Creator Companion can be used side by side on one set of projects.

```
vpm/
  version.py       versions, npm-style ranges (with vrc-get's prerelease rules) and Unity versions
  manifest.py      a package's package.json, checked; which Unity versions it fits (unity_compatible)
  environment.py   the Creator Companion's folder (HOARD_VCC_DIR in tests), its settings.json (every key kept),
                   ALCOM's own settings, and vcc.liteDb, read only
  litedb.py        reads LiteDB 5 files (vcc.liteDb), never writes them
  fetch.py         repository listings and package downloads, through egress.fetch
  repos.py         repositories: their cached listings in Repos/, adding, removing and refreshing them; finding a
                   package version (Selector) across them and your package folders
  project.py       a Unity project: its vpm-manifest.json, its installed and embedded packages, its Unity version
  resolve.py       package changes, as vrc-get works them out: add, upgrade, remove, repair; legacy packages and
                   files; then made with everything staged and moved aside first, so a failure (or Stop) puts the
                   project back as it was
  templates.py     VRChat's avatar and world templates (vrc-get's, in templates/), Blank, ALCOM's .alcomtemplate
                   files, and making a project from one
  unitypackage.py  puts a .unitypackage's files straight into a project (as ALCOM does), never over one already there
  preload.py       your library in a project: which .unitypackage and VPM package files a download has, and putting
                   them in; the VPM packages for the tools What it needs knows
  listing.py       the project list (settings.json's userProjects, or vcc.liteDb's), and Hoard's notes on each
                   (vpm-projects.json)
  presets.py       presets for new projects (vpm-presets.json), and writing one as an ALCOM template
  unity.py         the Unity editors Unity Hub knows, which one a project opens with, and whether it has it open
  backup.py        a project's backup zip
  logbook.py       Projects' log, as ALCOM and the Creator Companion keep theirs: this run's entries for the Logs
                   tab, and logs/projects-<date>_<time>.log (the newest 30 kept)
  api.py           what the server answers about all of this, and the work it hands to a "project" job
```

Every change to a project is a job (`jobs.py`, task "project"), so it's in Tasks and Stop stops it; the page asks
the server what a change will do first (`/api/vpm/preview`) and shows it. Projects' jobs run in a lane of their own
(`srv.project_jobs`, a second `Jobs` with `lane=PROJECTS`; see [The job queue and Tasks](#the-job-queue-and-tasks)),
so they never wait behind a sync or a download. New projects get Hoard for Unity (`api.HOARD_PACKAGE`) unless the
page leaves it out, its repository (`api.HOARD_REPO`) added first when it isn't there. Deleting a project
(`/api/vpm/delete-project`, only with its name as `confirm`) is a project job too: `api.Service.deletable()` refuses a
folder that isn't a listed Unity project, that Unity has open, that's too high up, or that holds Hoard's data,
downloads or backups folder; then it's backed up (unless asked not to), taken off the list, and deleted. Only projects on the list are changed:
`api.Service.listed()` checks each path the page sends. Downloads go through `egress.fetch` like everything else:
public addresses only, a repository's headers sent to its own host only, and a package's SHA-256 checked when its
listing gives one. `tests/test_vpm_resolve.py` is vrc-get's own resolver tests, ported; `tests/test_vpm_version.py`
has its (and node-semver's) range cases; `tests/data/vcc-sample.liteDb.gz` is a Creator Companion database made with
vrc-get's LiteDB writer.

Projects' log (`logbook.py`, the Logs tab) has what a project job says as it goes (a line said as `logbook.Warn` is a
warning) and how it ended (`Jobs._project`); what the server does for Projects outside a job (opened in Unity, put on
the list or taken off, repositories, Unity and folders, presets, backups deleted); a repository that couldn't be read
when they're loaded; and whatever a Projects request couldn't do: `_vpm_logged` notes the request's name
(`server.VPM_ACTIONS`), and `_json` logs an error reply under it (a 409 as a warning). `GET /api/vpm/logs?after=<n>`
gives this run's entries after the one numbered n, and `run` (when this run's log began), so a page that's open while
Hoard starts again starts over.

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
- Sharing a set (Sets, **Share...**) needs Hoard's share server: without it, Hoard says so. A long link from
  before 5.0 opens offline as ever.
- The pages show a notice while the browser reports being offline, and Hoard's Refresh and Sign in
  buttons explain instead of trying. Sign out works offline because it only touches local files.

## The pages

`library.html` and `downloads.html` share one design system. The CSS custom properties at the top of each
file (`--cave`, `--ledge`, `--gold`, the store colours) are the brand's colours for dark and light mode.
The script both pages share (windows, Settings, Tasks, Projects, choosing what to download, tags) is in
`web/shared.js`, written once: `server.page_source` puts it into each page's own script where the page says
`//@include shared.js`, so each page is still served as one inline script, allowed by its hash in the
Content-Security-Policy.
Script state lives in a single `state` object that's mirrored in the address bar, so views can be
bookmarked. Rendering rebuilds the grid with `innerHTML`, always through `esc()`.

The three styles (Standard, Treasure and Workbench, Settings, Appearance) are `web/looks.css`, put into both
pages after their own stylesheet; the page is marked with the one chosen (`<html data-style>`). Standard has no
mark: it's the pages as written. A style changes how the same markup is laid out, so a new part needs no markup
of its own for each style.

**The style guide** is at `/styleguide` on a running Hoard (`web/styleguide.html`, `server.guide_source`): every
part of the pages (colours, buttons, fields, chips, tiles, details, windows, questions, menus, Tasks, Projects,
sets, setup and the tour), each with its markup to copy, drawn with the Library's or Downloads' own stylesheet,
`looks.css` and a theme, so it's always as the pages are. Its bar chooses the page, style, theme, Light or Dark,
font, text size, store colours and spacing, kept in its address. It holds nothing of yours and needs no access
key. `tests/test_styles.py` checks that every class it uses is still one of the pages'.

## Releasing

1. Raise `__version__` in `hoard/__init__.py` and add a
   `## <version>` section to `CHANGELOG.md`.
2. Run **Actions → Release → Run workflow** with the tag (`v<version>`), or push the tag. `release.yml`
   makes a tag that doesn't exist yet (after checking it matches `__version__`) and runs
   `scripts/build_release.py`, which checks the versions, compiles the Python and builds the zips from an
   explicit file list. It makes the release as a draft, adds the Windows app, the Mac packages (Apple Silicon
   and Intel runners) and the Flatpak, then publishes it with that
   version's changelog section. Published releases are immutable, and so is their tag: a failed run leaves a
   draft that running it again fills in. The wiki's Releasing page has the details.

### The job queue and Tasks

`Jobs.start` runs a job at once when the runner (`busy`) is free and nothing is waiting, and otherwise queues it
(issue #49); it returns `"started"`, `"queued"` or `None` (a duplicate of a waiting job, the queue full, or
`queue=False`, which the scheduled sync uses). Whenever the runner is let go (`_wrap`, or `reseal_in_background`)
`kick()` starts the next waiting job. Each job's messages are kept as it runs (`_set`), and when it ends
`_finish()` adds it to `history` (the last 60, in `tasks.json`). `GET /api/tasks` gives the Tasks window the
current job, the queue and the history; `POST /api/queue/remove`, `/api/queue/clear` and `/api/tasks/clear`
change them. While the hidden library is locked, `public_job()` masks hidden products' names in job state, logs
and labels (`/api/status`, `/api/library`, `/api/assets`, `/api/tasks`).

Projects' tasks have a second `Jobs`, `lane=PROJECTS` (`server.project_jobs`): its own queue, runner, thread and
history (`project-tasks.json`, job ids starting with `p`), so a project's change and a download run side by side. Each
lane's progress stays its own: `common.set_lane()` marks a job's thread, and `capture_log` and `log`/`tick` pass a
message only to the sinks of the lane it was said in (a thread never marked is the main lane's). `GET /api/tasks`
gives both lanes (`current` and `project`, the queues together, the history merged newest first); `/api/status` adds
`project_job`; `POST /api/cancel` takes `{"lane": "projects"}`; a waiting job's id says its lane. Projects' Stop
(`cancel` and `force_stop` alike) only asks its job to stop at its next step, which puts back what it was changing:
it never ends the store browsers or a sign-in window, which are the main lane's. Closing or quitting Hoard waits for,
or stops, both lanes (`app._lanes`).

`downloader.with_retries()` wraps each file download (Booth, Gumroad, itch.io, and Jinxxy's click-to-download):
a failure is tried again `download_retries` times after `RETRY_WAITS`, except for refusals that can't change
(`worth_retrying`: 4xx answers such as 404/403, `NotLoggedIn`, `UnsafeRequest`, `UnsafePath`). A Stop is still
noticed at once, through the log line written before each wait.

`Library._stamp()` gives each item the time it first appeared (`added`) and each store the time of its first
read (`first_read`); `/api/library` marks an item `new` when it appeared after that first read and within
`new_days`.

### The pages' windows

Both pages share one block of script for the Tags, Stores, Settings and Tasks windows (`makeWindow`: a title bar
to move it, the corner to resize it, the position kept in `localStorage`, Escape closing the one in front), the
sidebar that folds (`wireSidebar`), and Settings saved as they change (`autosave`, sending only the changed
setting; `JOB_SETTINGS` wait for a running job to end).

### The routine check (issue #113)

`jobs.Schedule` runs in the desktop app (`AppServer.start_schedule`, from `app.run_app`) and ticks once a minute.
The check is due when `routine_hours(cfg)` isn't 0, setup is done, no job is running, Hoard started over
`FIRST_WAIT` ago, and `routine.json` says it last ran that long ago. The `routine` job (`Jobs._routine`) refreshes
the enabled stores except `UNATTENDED` (Payhip, which opens a visible window), checks the downloads
(`check_integrity` with `fresh_since`, so files new since the last check aren't read yet), and checks the
downloadable stores for updates (a dry run). It downloads nothing: it keeps how many new products and updates there
are (`Jobs.find_choices`, which the server points at `AppServer.download_choices`) in `routine.json`, and the pages
show them with **Choose what to download** (`POST /api/routine/seen` once you've looked). When no store is
reachable it waits `OFFLINE_RETRY` rather than recording errors on every store row.

Jobs you start go first (issue #110): `Jobs.start` queues them ahead of automatic ones, and when an automatic job
is running, `make_way` stops it safely and queues it again after yours. Tasks shows it as having made way.

### Updating

`updater.py` asks `api.github.com/repos/<repo>/releases` (through egress) and picks the highest published
`vX.Y.Z` release: drafts, pre-releases and `unity-v` tags are ignored. It asks when **Check now** is chosen
(`POST /api/update/check`) and, while `check_for_updates` is on, in the background each time the desktop app starts
and once a day after that (`Updates.check_in_background`, a daemon thread); the last answer is kept in
`update.json`. `check_for_updates` is on for new installs (5.1.0); a settings file that already says `false` keeps
it off. A copy that can't install an update gets `how` in `/api/update` (`updater.how_to_update`): the
Mac app's `.pkg` for its chip, the Flatpak's `.flatpak` (`paths.in_flatpak`), or the releases page.
`POST /api/update/install` works only in the installed Windows app (an `unins*.exe` beside
`Hoard.exe`) and never during a job: it downloads `Hoard-Setup-<version>.exe` into `updates/`, requires its SHA-256
to match the release's `SHA256SUMS-windows.txt` and the asset's `digest` (when GitHub lists one) and its size to
match, then quits. `app.run_app` runs the installer only after the server has stopped and the instance lock is
released, re-checking the hash first, with `/SILENT /SP- /NORESTART /RELAUNCH=1`; `hoard.iss` opens Hoard again
when it sees `/RELAUNCH=1`. The next start deletes installers for its own version or older.

## Conventions

- Text people see is plain and specific: say what happened and what to do next, without blame or
  exclamation marks.
- Never commit personal files. `.gitignore` covers `config.json`, `library.json`, sign-in folders,
  downloads and troubleshooting output, and the build refuses to package anything not on its list.
- Windows launchers need CRLF line endings; `.gitattributes` keeps them right.
