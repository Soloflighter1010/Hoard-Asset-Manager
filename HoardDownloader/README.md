# Hoard Downloader

Downloads everything you own on **Booth**, **Gumroad**, **Jinxxy** and **Payhip**, one folder per
product, with each store kept in its own subdirectory and its own manifest so nothing gets downloaded twice.

```
<root>/
  Booth/<Creator>/<Product>/            files + _thumbnail + asset.json
  Gumroad/<Creator>/<Product>/          (Gumroad's own sub-folders are kept)
  Jinxxy/<Creator>/<Product>/
  Payhip/<Creator>/<Product>/
  <Store>/_manifest.json                what's been downloaded from that store
  catalog.json                          every asset from every store + suggested tags
  tags.json                             tag -> list of asset folders, most common first
```

## Setup

**Windows:** double-click `Setup.bat` once. It makes a private Python environment in this folder and
installs the browser used for store sign-ins (about 150 MB). Then open `config.json` and set `"root"` to
where your downloads should go, for example `"D:/VRChat Assets"`.

**Linux / macOS:** run `./setup.sh`, then edit `config.json`.

Then double-click `Hoard Downloader.bat` (or run `./run.sh`), choose **Sign in to a store**, and sign in
to each store you buy from. A browser window opens; sign in there, then press Enter in the menu window.
Stores you never sign in to are skipped.

Your sign-ins are encrypted by your operating system and kept in a private folder outside this one,
shared with Hoard; the main README's "Your sign-ins" section has the details. **Sign out of a store** in
the menu removes Hoard's copy of a sign-in, for one store or for all of them.

If Google sign-in refuses the automated browser, sign in with email and password instead, or set
`"browser_channel": "chrome"` in `config.json` to use your installed Chrome.

## Use

The menu in `Hoard Downloader.bat` covers everyday use: preview what would download, download
everything new, and browse your library. For the rest, pass a command to the launcher (or to `./run.sh`):

```
"Hoard Downloader.bat" sync                        every store you're signed in to
"Hoard Downloader.bat" sync --store booth           one store: booth, gumroad, jinxxy or payhip
"Hoard Downloader.bat" sync --dry-run              list what would download
"Hoard Downloader.bat" sync --only "hoodie"        just matching products (handy for a first test)
"Hoard Downloader.bat" sync --store jinxxy --headed    watch the browser work
"Hoard Downloader.bat" sync --store payhip --payhip-page "Payhip library.mhtml"   see Payhip below
"Hoard Downloader.bat" tags                        rebuild catalog.json / tags.json only
"Hoard Downloader.bat" browse                      search and browse your library
```

Re-running `sync` only fetches what's new. If a creator changes a file (different size or name),
it's re-downloaded and listed under **"Updated on the store since last sync"** in the summary,
so a sync doubles as an update check. A product renamed on the store keeps its existing folder.
Buying the same Gumroad product twice doesn't create a second copy; the same asset bought on two
stores is kept once per store, on purpose.

## Tags

Asset names from every store are split into words (`FoxyHoodie v2` gives `foxy`, `hoodie`), filler words
and version numbers are dropped, and plurals are folded (`textures` becomes `texture`). A word becomes a
suggested tag when it appears in at least `min_count` names but not in more than `max_share` of them.
Suggestions land in `tags.json`, `catalog.json` and each product's `asset.json`. Add words you don't
want to `tags.blocklist` and run the `tags` command.

## Browsing

**Browse your downloads** in the menu (or `browse`) opens them at http://127.0.0.1:8765. It's read-only: it never
moves, renames or deletes anything.

- Search matches names, creators, tags and file names. Press `/` to jump to the search box.
- Filter by store, tags, file types and creator; filters combine, and the counts show what's left.
  The address bar keeps your filters, so you can bookmark a view like "all Rusk hoodies".
- Click an asset for its files and sizes, a link to its store page, **Open folder**, **Copy path**,
  and **Show in folder** for a single file.
- Thumbnails come from the store's product image, or a preview image among the files; anything
  without one gets a lettered tile. The coloured strip along each tile's bottom edge shows the store.
- Assets you have from more than one store are pointed out on each copy. Files deleted from disk are flagged.
- After a `sync`, click **Rescan** instead of restarting.

`--host 0.0.0.0` makes it reachable from other devices on your network (opening folders still only
works on the PC itself). `--port` changes the port.

## How each store is handled

**Gumroad** reads your library (including archived purchases) and each product's download page, then
downloads files through Gumroad's signed links. Interrupted downloads resume. This was written against
Gumroad's open-source code (antiwork/gumroad), so the data shapes are known.

**Booth** reads your library and gifts pages, which list a link for every file, then downloads each
file straight from Booth. Interrupted downloads resume. When a creator uploads a new version, it's
downloaded and listed as updated. Include or skip gifts with `booth.include_gifts`.

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

**Payhip** keeps a buyer library while your account is in **Customer** mode (Account menu, Use Payhip
as), and it puts a bot check in front of automated browsers. So Payhip runs in a visible browser window.
If a "verify you are human" check appears, complete it in that window and the downloads carry on
(`payhip.bot_check_wait` sets how long it waits, 3 minutes by default).

If Payhip won't let the tool in at all:

- **Can't read your library:** save your library page from your usual browser (scroll to the bottom,
  Ctrl+S, "Webpage, Single File") and run
  `"Hoard Downloader.bat" sync --store payhip --payhip-page "Payhip library.mhtml"`.
- **Can't open a download page:** those products are listed in `Payhip/_download-yourself.html`, each
  with its download page and the folder its files belong in. Download them in your usual browser into
  those folders; the next sync records them.

Only purchases attached to your Payhip account show up. For older purchases you only have receipt emails
for, open the receipt's download link and choose **Get Started** to add it.

## Notes

- Runs on Windows and Linux. On a headless machine, Gumroad can use your `_gumroad_app_session` cookie
  from the `HOARD_GUMROAD_SESSION` environment variable. Keep it out of `config.json`, which is easy to
  share by accident. Booth and Jinxxy need one `login` with a display, and Payhip needs a display every
  time.
- Sessions expire now and then (Gumroad's after about a month). When sync says a store isn't signed in,
  sign in to it again from the menu.
- Folder and file names are cleaned for Windows and capped in length. If you still hit path-length
  errors, enable Windows long paths or use a shorter `root`.
