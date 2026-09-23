# Hoard Downloader

Downloads everything you own on **Gumroad** and **Jinxxy**, one folder per product, with each store kept
in its own subdirectory and its own manifest so nothing gets downloaded twice.

```
<root>/
  Gumroad/<Creator>/<Product>/          files (Gumroad's own sub-folders kept) + _thumbnail + asset.json
  Gumroad/_manifest.json
  Jinxxy/<Creator>/<Product>/
  Jinxxy/_manifest.json
  catalog.json                          every asset from both stores + suggested tags
  tags.json                             tag -> list of asset folders, most common first
```

## Setup

**Windows:** double-click `Setup.bat` once. It makes a private Python environment in this folder and
installs the browser used for store sign-ins (about 150 MB). Then open `config.json` and set `"root"` to
where your downloads should go, for example `"D:/VRChat Assets"`.

**Linux / macOS:** run `./setup.sh`, then edit `config.json`.

Then double-click `Hoard Downloader.bat` (or run `./run.sh`) and sign in to each store from the menu. A
browser window opens; sign in there, then press Enter in the menu window.

Logins are saved in `.browser-profile/` in this folder. Treat that folder like a password and never
share it. If Google sign-in refuses the automated browser, sign in with email and password instead, or
set `"browser_channel": "chrome"` in `config.json` to use your installed Chrome.

## Use

The menu in `Hoard Downloader.bat` covers everyday use: preview what would download, download
everything new, and browse your library. For the rest, pass a command to the launcher (or to `./run.sh`):

```
"Hoard Downloader.bat" sync                        both stores
"Hoard Downloader.bat" sync --store gumroad
"Hoard Downloader.bat" sync --dry-run              list what would download
"Hoard Downloader.bat" sync --only "hoodie"        just matching products (handy for a first test)
"Hoard Downloader.bat" sync --store jinxxy --headed    watch the browser work
"Hoard Downloader.bat" tags                        rebuild catalog.json / tags.json only
"Hoard Downloader.bat" browse                      search and browse your library
```

Re-running `sync` only fetches what's new. If a creator changes a file (different size or name),
it's re-downloaded and listed under **"Updated on the store since last sync"** in the summary,
so a sync doubles as an update check. A product renamed on the store keeps its existing folder.
Buying the same Gumroad product twice doesn't create a second copy; the same asset bought on both
stores is kept once per store, on purpose.

## Tags

Asset names from both stores are split into words (`FoxyHoodie v2` gives `foxy`, `hoodie`), filler words
and version numbers are dropped, and plurals are folded (`textures` becomes `texture`). A word becomes a
suggested tag when it appears in at least `min_count` names but not in more than `max_share` of them.
Suggestions land in `tags.json`, `catalog.json` and each product's `asset.json`. Add words you don't
want to `tags.blocklist` and run `the `tags` command`.

## Browsing

**Browse your library** in the menu (or `browse`) opens the library at http://127.0.0.1:8765. It's read-only: it never
moves, renames or deletes anything.

- Search matches names, creators, tags and file names. Press `/` to jump to the search box.
- Filter by store, tags, file types and creator; filters combine, and the counts show what's left.
  The address bar keeps your filters, so you can bookmark a view like "all Rusk hoodies".
- Click an asset for its files and sizes, a link to its store page, **Open folder**, **Copy path**,
  and **Show in folder** for a single file.
- Thumbnails come from the store's product image, or a preview image among the files; anything
  without one gets a lettered tile. The corner mark on each tile shows the store.
- Assets you have from both stores are pointed out on each copy. Files deleted from disk are flagged.
- After a `sync`, click **Rescan** instead of restarting.

`--host 0.0.0.0` makes it reachable from other devices on your network (opening folders still only
works on the PC itself). `--port` changes the port.

## How each store is handled

**Gumroad** reads your library (including archived purchases) and each product's download page, then
downloads files through Gumroad's signed links. Interrupted downloads resume. This was written against
Gumroad's open-source code (antiwork/gumroad), so the data shapes are known.

**Jinxxy** has no public API for buyers, so this side drives the site in a browser with your saved
login: it collects your inventory items, opens each one and clicks each file's download button. It was
written without access to a logged-in Jinxxy page, so treat it as a first pass. If it finds no items or
no download buttons, run:

```
"Hoard Downloader.bat" probe jinxxy
```

That writes `probe-output/` (screenshots, page HTML, the site's JSON traffic with emails/tokens/signed
URLs masked, and the list of links on your inventory page). Usually the fix is adjusting
`jinxxy.item_link_pattern` to match the item links in `inventory_links.txt`. Skim the folder for
personal info before sharing it.

## Notes

- Runs on Windows and Linux. On a headless machine, Gumroad works with `gumroad.session_cookie`
  (your `_gumroad_app_session` cookie); Jinxxy needs one `login` with a display.
- Gumroad sessions expire after about a month; sign in to Gumroad again from the menu when sync says so.
- Folder and file names are cleaned for Windows and capped in length. If you still hit path-length
  errors, enable Windows long paths or use a shorter `root`.
