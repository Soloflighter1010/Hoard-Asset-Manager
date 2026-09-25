# Changelog

## 2.4.0

Hoard is a Windows app now: no command prompt, no Python to install.

- **An installer:** `Hoard-Setup-<version>.exe` installs Hoard for you only (no administrator prompt), with a
  Start menu entry, an optional desktop icon and an uninstaller. Updating is running the newer setup. Your
  data is never touched by installing, updating or uninstalling. A portable zip of the same app is there too.
- **Its own window,** using Microsoft Edge WebView2 (part of Windows). Closing it quits Hoard cleanly: a download
  in progress stops (and resumes next time), and store browsers close. Links to store pages open in your web
  browser. Without WebView2, Hoard says so and opens in your browser, with **Quit Hoard** in Settings.
- **One copy at a time:** opening Hoard again brings its window to the front.
- **No console:** anything Hoard would print goes to `logs\hoard.log` in its app-data folder, handy when
  reporting a problem.
- **The command line** is `hoard-cli.exe` in Hoard's folder (`hoard-cli sync`, `hoard-cli verify`, ...). New:
  `self-test`, which checks a copy of Hoard has everything it needs.
- From source, `Hoard.bat` also starts Hoard without leaving a console open.
- Built on GitHub for every release from hash-locked dependencies (`requirements-app.txt`), checked with the
  self-test, with signed build provenance.

## 2.3.1

- **Sync button:** next to Stores and Settings (and in Downloads). It reads what you own from each store
  you use, then downloads anything new, as one job with progress and **Stop**.
- **Fixed: Gumroad downloads failed.** Since 2.1.1, every download that redirects to a file host, which
  is every Gumroad file, was refused. The checked download path counted redirects it wasn't even
  following. Booth hid the problem by falling back to its browser route. Hoard's tests now cover the
  real HTTPS path, which would have caught it.
- **Fixed: Jinxxy downloads could look like they never finished,** which also kept **Sign out** and
  other jobs waiting. Visible download buttons get a normal click again, with the patience they had
  before 2.2.0, and waiting for a download to start now shows progress and can be stopped. A second
  download started by the same click is cancelled, and a button's class names no longer count when
  deciding which buttons never to click.
- **Fixed: an old version number after updating over an old install** (and, worse, possibly old code in
  any file whose size hadn't changed). Python reused compiled copies because every release's files had
  the same date. Release files now carry the release's own date, the launchers always start from the
  files, and Hoard notices and clears stale copies itself.
- **Fixed:** the filter chips overlapped the first row of the grid, and the heading counted archived
  items in the main library.

## 2.3.0

- **Recovery words for a forgotten PIN.** When you set your hidden library's PIN, Hoard shows 6 recovery
  words, once, and asks you to type two of them back. If you forget your PIN, choose **Forgot your
  PIN?** and enter the words to set a new one; your hidden items stay hidden. Capitals, numbering and
  the first four letters of each word are all fine, and a misspelt word is pointed out. The words
  are kept only as a slow, salted hash, and wrong ones count toward the same waits as wrong PINs.
- Already have a PIN? Unlock **Hidden** and choose **Create a recovery phrase**. **New recovery phrase**
  replaces an old one.
- The words come from the standard BIP-39 list, but they only unlock Hoard's hidden library. They
  aren't a crypto wallet phrase, and Hoard never asks for a wallet's recovery words.

## 2.2.0

Tidy your library, and keep some of it private.

- **Remove:** open an item (or choose several with **Select**) and remove it. Removed items stay out of
  your library even after a refresh, and aren't downloaded. Restore them from **Removed**, or delete
  them from Hoard for good. That's also how to clean up a library page imported by mistake.
- **Archive:** put older products that may no longer work into **Archive**, out of your main library.
  Gumroad's own archived purchases start there too. **Unarchive** moves them back.
- **Hidden library:** **Hide** things you'd rather not see by default, such as NSFW assets, behind a
  PIN. Hidden items are left out of everything (library, Downloads, counts, tags, search) until you
  unlock them in that browser, for 15 minutes past your last use. Wrong guesses wait longer each time.
  A forgotten PIN can only be cleared by deleting the hidden items, never by showing them. It's a
  privacy screen, not encryption: the files on your disk are ordinary files.
- **Payhip, large libraries:** refreshing Payhip now opens a window and waits while you complete
  Payhip's automated-browser check, instead of giving up. Libraries of up to 3,000 products are read
  page by page.
- **Payhip, one shop for everything:** a shop on payhip.com lists your purchases from every shop, so
  adding one is often enough. Shops on their own domains that turn up are offered in **Stores** to
  review and add, never trusted automatically.
- **Payhip downloads:** Hoard uses each file's own download button, names files from the name Payhip
  shows, includes files on a product's other content pages, and never touches **Reset download
  credits** (or any other reset, credit, limit or delete control, on any store).

## 2.1.1

A security release answering the independent audit of 2.1.0. Every finding is fixed; the details are in
docs/security-audit-2.1.0-response.md.

- **Downloads take one checked path.** Downloads of your files went through a different, less careful
  route than product pictures, which would have followed a redirect to your own computer or network.
  Now every store request and download goes through one path. Redirects are followed one hop at a
  time, and each hop must be https to a public internet address. Store cookies only go to the store's
  own sites; the servers hosting its files get none.
- **Store traffic is https only.**
- **Files can't be redirected on disk.** Downloads are created exclusively without following links, and
  only moved into place if they're still the file that was written. Pictures are served the same way.
- **Imported pages run nothing:** scripts are off, and event handlers are stripped too.
- **Shops from imported pages need your say-so.** Hoard shows the exact address and asks before
  adding it. Internationalised look-alike names are refused.
- **No more overwriting** when two products' or files' names clean up alike.
- **Troubleshooting files are scrubbed by default:** no email addresses, license keys, tokens, signed
  links or screenshots, and a summary instead of your purchases. `--raw` saves everything, marked
  sensitive.
- Also: time limits and a connection cap for Hoard's server; manifests are read with size and type
  checks everywhere; a custom sign-in folder needs an explicit advanced setting and can't be on a
  network share; the import picker accepts the same file again after you decline.

## 2.1.0

A setup assistant, so nobody needs a command line or has to guess what to do first.

- **The setup assistant** opens the first time you start Hoard, and any time from Settings. It covers
  the browser Hoard signs in with, which stores you use, your Payhip shops, signing in to each store,
  where downloads go, and bringing over Hoard 1.x.
- **No more `playwright install`:** if Hoard needs its own browser, one button installs it, with
  progress. On Windows, Hoard uses Microsoft Edge, which is already there. If a store is ever read
  without the browser installed, the message says what to do instead of showing Playwright's error.
- **Signing in without your saved passwords:** Hoard's window is its own browser, so it doesn't have
  what your usual browser saved. The assistant shows where to copy your password from (Chrome, Edge,
  Firefox, Safari, password managers) and other ways in: password reset, Google or Discord sign-in, and
  passkeys on Windows Hello or your phone.
- **Links from emails:** when a store emails a sign-in or "is this you?" link, paste it into the
  assistant and it opens in Hoard's window, rather than signing in your usual browser. Only links on
  that store's own site are accepted.
- **Stores you don't use are hidden**, from the tabs, the Stores panel, the grid and **Refresh all**.
- New `install-browser` command, for the command line.

## 2.0.2

Fixes from real Booth and Payhip library pages.

- **Booth downloads:** nothing downloaded, because Booth now draws its download buttons with a script. The
  addresses sit in placeholders, not links, so every item looked like it had no files. Hoard now reads
  them; the "Open in Browser" and Booth Library Manager variants of each file are skipped.
- **Booth's free downloads** are now included, with a switch in Settings.
- **Payhip shops:** Payhip keeps your purchases in each shop you bought from, on the shop's own address,
  with no single library. Add your shops in Settings under **Payhip shops**, and Hoard reads each one's
  library page and downloads from it. Signing in to Payhip opens a tab per shop. Importing a shop's
  saved page adds that shop for you.
- Only the shops you list count as Payhip's own sites, for links and downloads alike. Any other address
  is still refused.

## 2.0.1

Fixes for new testers' reports.

- **Jinxxy, new accounts:** items showed as "Navigation", by your own account name. With only one item in
  the inventory, the reader took the whole page as that item's card, sidebar and all. Cards now stop
  before the page's menus and sidebars, your own "Profile" link is never read as a creator, and page
  headings such as "Navigation" or "Product Details" are never read as names.
- **Jinxxy, pictures:** downloaded items got Jinxxy's default site banner as their picture, because it
  came from the page's share image. Hoard now takes the product's own picture beside its title. Copies of
  the banner saved by earlier versions are removed on the next sync and replaced with the real pictures.
- **Booth downloads:** when Booth turns away Hoard's direct download, as sites often do with anything
  that isn't a real browser, Hoard now downloads through the signed-in browser instead, as if you'd
  clicked the download button. The direct route is still tried first, since it's faster and resumes
  where it stopped.
- **Signing out** of a store now also removes that store's items and their cached pictures from your
  library, so whoever signs in next never sees them. Your downloaded files stay where they are.
- Store readers are now tested in a real browser, against pages copied from the layouts that broke, on
  every change.

## 2.0.0

Hoard and Hoard Downloader are now one app, and nothing needs a command prompt or a settings file.

### One app
- **Library** and **Downloads** are two views of the same app, with one set of sign-ins, tags and settings.
- Download from the page: **Download** on each store, **Download everything new**, or **Download a copy**
  on a single item. Progress shows as it goes, and **Stop** pauses safely; it carries on next time.
- Items you already have say **On disk**, with a link straight to them in Downloads.
- A **Settings** panel: the downloads folder, which stores to include (and Booth gifts, archived Gumroad
  purchases), saving images for offline use, and the browser used for store sign-ins.
- On Windows, store sign-ins use Microsoft Edge, which every PC has and Windows Update keeps patched, so
  setup no longer downloads a separate 150 MB browser. Hoard's own browser is used only if Edge is missing.

### Where things live
- Settings, the library list and cached images moved into Hoard's app-data folder, next to your sign-ins
  and tags. Downloads go to a `Hoard` folder in Documents unless you choose another in Settings.
- Coming from 1.x: sign-ins and tags carry over by themselves. `Hoard.bat migrate <old folder>` brings
  over the library list and downloads folder.
- One release zip, `Hoard-<version>.zip`, replaces the three. Start it with `Hoard.bat` (or `./run.sh`).

### Command line
- Every command from both tools, as `Hoard.bat <command>` (or `./run.sh <command>`): `sync`, `verify`,
  `login`, `refresh` and the rest. See docs/COMMAND-LINE.md. `browse` is gone: that's the Downloads view.

### Under the hood
- The code is one package, `hoard/`, with each piece in exactly one place. The security code used to be
  copied into two or three files, kept identical by tests; now there's one copy, and a test checks it.
- Fixed: recognising which store a saved library page came from only worked for pages saved from the exact
  library address, because a second definition silently replaced the first.

## 1.6.2

Stops edited links from sending you anywhere but the store.

- Links you can open (**Open on Booth**, **Open download page**, a creator's page) must now be https
  addresses on the item's own store, checked when data is read, when it's written, and in the pages. Before,
  any https address was accepted, so a program editing a record could point a button at a lookalike
  sign-in page. Downloads never came from stored links, and still don't.
- Data files (manifests, `catalog.json`, `tags.json`, `asset.json` and Hoard's library list) are sealed with a
  keyed signature. When something else edits one, the tools tell you, keep a copy, and don't use its links
  until the store is read again.
- New `verify` command in Hoard Downloader: checks every data file and rebuilds the catalog files.
- The catalog files are now format version 3 (docs/DATA-FORMATS.md). Using one download folder from two
  computers? Copy `integrity.key` between them (see the README).

## 1.6.1

Hardens tags and the downloader's data files. docs/security-review-2026-09.md lists each finding.

- Paths read from `_manifest.json` must stay inside their folder, through symlinks too, so a tampered
  manifest can't make a sync write anywhere else. Records that don't are ignored.
- File, folder and item names no longer carry invisible characters such as right-to-left overrides,
  which could make one kind of file look like another.
- Data files are written through a temporary file and swapped in, so a planted symlink can't redirect a
  write and nothing reads half a file.
- Data files are read with size limits and checked entry by entry. A damaged manifest, library list or
  tag file is kept aside under a new name and the tool carries on, instead of stopping.
- Tags may only use letters, digits, spaces and `- _ . + & '`. Existing tags that used anything else are
  converted, not lost. The tag file is private to your account and has size limits.
- `catalog.json`, `tags.json` and `asset.json` now carry `format` and `version`, and each entry is
  checked against the promises in the new docs/DATA-FORMATS.md before it's written.
- Requests to the tools are limited in size, and malformed ones are refused.
- Fixed: on Linux without a keyring, Hoard's page stopped updating after the first refresh.

## 1.6.0

Security release, answering two independent reviews. docs/security-review-2026-09.md lists every finding
and what was done.

### Your sign-ins
- Each store's sign-in is now kept separately. Existing sign-ins are split between stores automatically on
  first run, keeping only each store's own cookies.
- On Linux, sign-ins are only saved when a keyring can encrypt them, and Hoard checks after you sign in that
  they really were. Computers without a desktop can opt out with `"allow_unprotected_signins": true`.
- Sign out now asks the store to end the session where it can, deletes that store's sign-in, checks nothing
  is left, and tells you what it did.
- A copied Gumroad session cookie in `config.json` or `HOARD_GUMROAD_SESSION` is no longer read. Sign in
  with `login gumroad` instead.

### Network and pages
- Product images are fetched over a connection that goes only to the public address that was checked, so
  DNS rebinding can't point it at your network. Store download links are only followed on the store's own
  website.
- Only raster images are kept (no SVG), and everything the tools serve apart from the page is sandboxed.
- Using the tools from other devices now needs HTTPS (`--tls-cert`, `--tls-key`), or `--plain-http` to
  say the connection is already encrypted, such as over Tailscale.

### Installation and releases
- Setup limits who can change the program folder to your account.
- Every Python package is pinned to an exact version and checked against its hash when installed.
  `requests` is now at least 2.32.4.
- GitHub Actions are pinned to exact commits with minimal permissions, and release zips carry signed
  build provenance once the repository is public (`gh attestation verify`).
- Security tests run on every change. SECURITY.md now explains what Hoard protects against and what no
  desktop app can.

## 1.5.0

Tag manager.

### Both tools
- Your own tags, alongside the suggested ones. Tag an item from its details, or many items at once with
  **Select** (including **Select all shown** after filtering).
- A **Tags** panel to create, rename, merge and delete tags, and to keep or hide suggestions. Keeping a
  suggestion makes it your tag on every item whose name has that word, including ones you buy later, and
  any tag can match names that way.
- Hoard and Hoard Downloader share your tags, so tagging in one shows in the other. Tags added to a
  product apply to every copy you own on other stores.
- The sidebar lists your tags first, then suggestions.

### Hoard Downloader
- `asset.json` and `catalog.json` include your tags (`tags`) next to the suggestions (`suggested_tags`),
  and `tags.json` now lists your tags under `tags` and suggestions under `suggested`.

## 1.4.0

Works offline.

### Both tools
- The typefaces are bundled, so the pages look right without an internet connection, and they no longer
  load anything from Google Fonts. Nothing is fetched from outside your computer just to show a page.
- A notice appears when you're offline, saying what still works.
- A store that can't be reached is now reported as "couldn't reach", with your saved data left
  unchanged, instead of a raw browser error.

### Hoard
- After each refresh, every product image is saved, so your whole library shows its images offline.
  Turn this off with `"offline_images": false` in `config.json`.
- Refresh and Sign in say you're offline instead of trying. Signing out still works offline.

### Hoard Downloader
- Stores that can't be reached are skipped with a clear message, and the rest still sync.

## 1.3.0

Ready for a public release: safer pages, clear policies and documented code.

### Both tools
- A footer with the version and links to the project on GitHub, updates, problem reports, the privacy
  policy, the terms of use and the AI disclosure.
- Links from store pages and imported pages only open when they're ordinary web addresses. A crafted
  listing can't turn a link into a script.
- Product images are only fetched from public internet addresses, never from your home network or from
  files on your computer.
- The pages are sent with a strict Content-Security-Policy and headers that stop other websites from
  embedding them or reading their responses.
- With `--host 0.0.0.0`, other devices on your network need the access key the tool prints when it
  starts. Actions still only work from the computer running the tool.
- Outbound links no longer tell the store which page you came from.

### Project
- New documents: privacy policy, terms of use, copyright and credits, security policy and AI disclosure.
  Each release zip includes them.
- A developer guide in `docs/ARCHITECTURE.md`, and every function in the code now has a docstring.
- Dependency versions are capped at their current major versions.

## 1.2.1

Maintenance release; Hoard and Hoard Downloader work the same as in 1.2.0.
- Release builds no longer depend on a third-party GitHub Action, and the release for an existing
  version can be built again from the Actions tab.

## 1.2.0

Safer sign-ins, in both tools.
- Sign-ins moved out of the program folder into your user account's private app-data folder, so sharing,
  syncing or committing the program folder can't carry them. The first run moves existing sign-ins
  automatically and removes the old copy. Both tools now share one set of sign-ins.
- Saved sign-ins are encrypted by the operating system on every platform. On Linux and macOS the
  browser previously used a fixed, publicly known key, which made them readable to anything that could
  read the files. macOS users need to sign in again once.
- The two tools can no longer use the sign-ins at the same moment, which could damage them.
- Sign out of a store, or of every store, from the Hoard Downloader menu, Hoard's Stores panel, or the
  `logout` command.
- A Gumroad session cookie for headless use now comes from the `HOARD_GUMROAD_SESSION` environment
  variable. Keeping it in `config.json` still works but shows a warning.

## 1.1.0

### Hoard Downloader
- Downloads Booth purchases and gifts. Files come straight from Booth, interrupted downloads resume,
  and new versions a creator uploads are downloaded and listed as updated.
- Downloads Payhip purchases in a visible browser window, waiting while you complete Payhip's bot check.
  If Payhip won't let it in, it can read your library from a page you saved, and lists the rest in
  `Payhip/_download-yourself.html`; files you save there are recorded on the next sync.
- Stores you haven't signed in to are skipped instead of reported as failures.
- The menu has a single **Sign in to a store** entry covering all four stores.
- The downloads browser shows Booth and Payhip.

### Hoard
- No changes; version raised to match Hoard Downloader.

## 1.0.0

First release.

### Hoard
- One searchable page for everything you own on Booth, Gumroad, Jinxxy and Payhip, with store,
  tag and creator filters and links to each item's download page.
- Sign in and refresh each store from the page. A failed refresh keeps that store's previous list.
- Products you own on more than one store are pointed out, with a view of every copy.
- Booth items list their files with direct download links; Booth gifts and archived Gumroad
  purchases are labelled.
- Import a library page saved from your own browser, for stores that block automated browsers
  (Payhip today).

### Hoard Downloader
- Downloads everything you own on Gumroad and Jinxxy into one folder per product, with a separate
  manifest per store so nothing is fetched twice. Interrupted Gumroad downloads resume.
- Re-running only fetches new or changed files, and the summary lists files a creator has updated.
- Suggests tags from words shared across asset names.
- Includes a read-only library browser with thumbnails, search, filters, and buttons to open folders.
