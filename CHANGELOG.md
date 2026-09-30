# Changelog

## 2.9.2

The downloader fix: a store browser that closes or stops answering no longer fails, or holds up, a whole sync.
Downloading one product goes straight to it. And Hoard can carry on in the background, and close safely while
it's working.

- **Fixed: a Jinxxy sync failed every product after the browser closed.** When Hoard's browser for a store
  closed by itself part way through (Jinxxy, or Booth through the browser), every product after it failed at once
  ("Target page, context or browser has been closed"): 258 of them in one sync. Now Hoard opens the browser again
  and tries that product once more, then carries on; if it keeps closing, the rest of that store is left for next
  time with one message saying so.
- **Fixed: a sync could stop moving, and Stop couldn't end it.** Some of what Hoard asks a store's browser has no
  time limit, so a browser that stopped answering held the job, and every job after it, until Hoard was closed.
  Now Stop ends such a browser after 20 seconds, so the job finishes; and a job with no progress for 5 minutes
  says so. Either way, Hoard's log notes where it was waiting, so the cause can be found.
- **Downloading one product goes straight to it.** **Download a copy** (Library) and **Update** (Downloads) used
  to read through the whole store to find the product: on Jinxxy, opening every item's page, one after another,
  until the name matched. Now they open just that item's page on Jinxxy, and just that purchase's download page on
  Gumroad. (Booth's files are only on its library pages, and itch.io is read through its API, as before.)
- **Keep Hoard running in the background.** A new setting, **Keep Hoard running when its window is closed**:
  closing the window hides it, and downloads, syncs and automatic syncs carry on. Open Hoard again to bring the
  window back; **Quit Hoard** in Settings stops it.
- **A log for each time Hoard starts,** kept for 30 days (the newest 10 however old), instead of one log that
  every run added to. **Open logs folder** in Settings (Troubleshooting) opens where they are, and a support
  report includes this run's log and the one before.
- **Closing Hoard while it's working asks first:** **Stop it, then close** (Hoard closes once what's running has
  stopped), **Keep working in the background**, or **Close now**, which closes at once, ending any store browser,
  for when stopping takes too long. **Quit Hoard** in Settings asks the same. Before, closing gave a download 5
  seconds to stop.
- **The first setup goes through to the end (#21).** The first time Hoard opens, the setup assistant can't be
  skipped or closed; a step that isn't done yet (Hoard's browser not installed, no store picked) keeps you on it,
  and going on without signing in to any store, or without a Payhip shop, asks first. Run again from Settings, it
  can still be left at any step.
- **Hoard always installs into `%LOCALAPPDATA%\Programs\Hoard` (#21),** a folder only your account can change,
  which Hoard's sign-in protection counts on. The installer no longer offers another folder, and a Hoard installed
  elsewhere by an older setup is installed there when it updates (the old folder can then be deleted).

## 2.9.1

- **Fixed: the page bounced when the pointer went along the store tabs.** A tab rising under the pointer made the
  whole row of tabs taller, so everything below it moved down and back. Only the tab moves now.

## 2.9.0

Folder tabs, floating windows, and jobs that wait their turn; downloads that can't stall.

- **The store tabs are folder tabs:** the one you're looking at is raised, and the page glows up from the bottom in
  its store's colour. On **Everything**, the colours of the stores you're signed in to drift slowly through the
  glow (still, when motion is reduced). Sort, tile size and what's running moved up beside the tabs.
- **Tags, Stores and Settings are windows** that float over the page: move one by its title bar, resize it from
  its corner, keep several open side by side. A click elsewhere no longer closes them; **×** or Escape does
  (the one in front). Each opens where you left it.
- **Settings save as you change them.** No more **Save**: a box or a list is saved straight away, a folder or the
  Payhip shops when you leave the field. While a job runs, only where files go, the browser, the stores and the
  Payhip shops wait for it to finish; everything else changes at once.
- **The sidebar folds.** **Hide filters** folds it to a thin strip, and each section (your tags, suggestions,
  Show, creators) folds by its heading. Both are remembered.
- **Tasks** (next to Library and Downloads) shows what's running with its progress, what's waiting, and what
  finished, with how it went, how long it took, any problems and its full progress (the last 60, kept between
  runs).
- **Jobs wait their turn (#49).** Start a sync, download, refresh or sign-in while something is running, and it's
  queued instead of refused ("Hoard is busy"); it starts when its turn comes. Take one off the queue in Tasks.
- **Failed downloads are tried again (#19),** twice unless you choose otherwise in Settings (**Failed downloads**),
  after a short wait, before they count as failed. A store saying the file isn't there, or isn't yours, isn't
  tried again.
- **New, and Recently added (#18).** Something that appears in your library after a refresh has a **New** badge for
  a week (**New in your library** in Settings: a day to a month, or never), and **New** under **Show** filters to
  them. **Recently added** sorts the newest first. What was already there when Hoard first read a store isn't new.
- While your hidden library is locked, hidden products' names are left out of job progress and the Tasks list.
- **Downloads that stall no longer hang Hoard.** A file the store stopped sending part way through, without hanging
  up, used to wait for ever when it came through the browser (Jinxxy, and Booth when it turns direct downloads
  away): the download never finished, its item stayed busy, and every job after it waited, with **Stop** unable to
  reach it. Now a download with nothing new for 2 minutes is given up on and tried again, whichever way it comes.
- **Stop works part way through a file,** within a few seconds.
- **Download progress, speed and time left.** While a file downloads, the download panel and Tasks show it with a
  progress bar, how much has come in of how much, how fast it's coming (smoothed over the last few seconds) and
  how long is left. A file coming through the browser (Jinxxy, and Booth when it turns direct downloads away)
  shows how much and how fast; the browser doesn't say how big it is, so there's no time left for those.

### Fixed since 2.8.6

- **Fixed: support reports showed product and creator names from the end of a sync.** The list of what was
  updated, skipped and failed that ends each sync in `hoard.log` went into reports as it was. Those names are now
  hidden like the rest, and a name with "secret" or "token" in it is no longer mangled as if it were a password.
- **Fixed: sign-ins kept on another drive** (`advanced_signin_location`) that wasn't plugged in when Hoard
  started made every store's list disappear, as if you'd signed out. Hoard now leaves the lists alone when that
  whole folder is missing.
- **Fixed: "Hoard is busy" just after starting.** The check of the catalog's seal no longer holds up the first
  thing you choose when there's nothing to reseal.
- The pages' script runs in strict mode again (the splash's code had been put before `"use strict"`, which
  switched it off), and `PRIVACY.md` says where support reports really go: `Hoard\Support Reports` in your
  Documents folder.

## 2.8.6
UI Improvements
A UI and usability update focused on knowing what's downloaded, smoother startup, better window behavior and accessibility.

- Downloaded status in the Library. Downloaded assets now show a small download indicator on their thumbnails, with an accessible label for screen readers. A new Downloaded filter provides `Downloaded` and `Not downloaded yet` options with live counts. Filters work with the existing filter system, can be cleared normally, survive reloads through the URL, and stay in sync with the item's actual on-disk status.

- Splash screen while the Library loads. The Library and Downloads pages now show a full-window Hoard splash with the logo and "Opening your hoard" while the initial library is being read. The splash stays visible for at least 1.2 seconds, appears immediately on the first page, only fades in on later page loads when loading takes longer, and is removed after loading finishes, an error, or a 20-second safety timeout. Reduced-motion settings disable the animation.

- Remember window size and position. Hoard now remembers the window's size, position and maximized state between launches. Invalid or damaged saved settings are ignored safely, off-screen windows are repositioned to the center, and the previous normal size and position are preserved when maximizing or minimizing.

- Improved large-text layouts. Fixed an accessibility issue where the Largest text setting could cause panels sized relative to the window to extend beyond the visible area. Window-based sizing now accounts for the active zoom level across Settings, Stores, the sidebar, details panel, selection bar, dialogs, setup card and download panel.

- **Check for updates to what you've downloaded.** In Downloads, **Check for updates** (under **Updates**) reads
  your stores without downloading anything, and lists each download whose store has newer files: files the
  creator added or changed since you downloaded it. **Update all**, or **Update** one from its details (which also
  have **Check for updates** for just that one). In the Library, such items say **Update available**.

## 2.8.5

- **Security: the September 2026 code-scanning findings.** Nothing here is known to have been exploitable (the
  server already needed this run's access key, and imported pages were already opened with scripts off), but each
  guard is now one CodeQL can follow, with tests for each:
  - Imported store pages are cleaned with an HTML parser instead of patterns, so no way of writing a script tag
    (`<SCRIPT>`, `</script >`, a tag split over lines) or an event handler slips through, and `<style>` inside SVG
    can't carry markup.
  - The page scripts' Content-Security-Policy hashes are found the same way, however the tags are written.
  - Images from the downloads folder are served from a path rebuilt from a checked path inside the folder, with a
    type from a fixed list; fonts from Hoard's own list of names.
  - No response header can carry a line break.
  - Jinxxy links are recognised by their host (`jinxxy.com` or a subdomain, over https), not by the text
    "jinxxy.com" somewhere in the address.
  - Support reports hide asset and creator names without patterns that could take very long on an unusual line.

- **Store sign-ins and setup.** On macOS, background store reads now use the same full Chromium as the sign-in window so Keychain-encrypted cookies can be read. On Windows, an open browser's locked cookie database no longer makes setup status fail; the Library takes over count updates if the setup assistant is closed during sign-in. Settings, sign-in messages, logs and support reports now show which browser Hoard actually uses, including fallback to its own browser.
- **Downloads and library.** Jinxxy browser downloads now accept OneDrive cloud files without treating them as symlinks. Fully deleted downloads leave Downloads on rescan and can be downloaded again; partially missing ones remain marked. Downloads gains Archive, Removed and Hidden views, with sidebar counts following the current view. Removing a browser store's sign-in folder while Hoard is closed clears that store's refreshed Library list at startup without deleting downloaded files or imported lists.
- **Privacy and interface.** Support reports now redact Windows user paths with doubled separators and downloaded filenames in progress lines, using consistent placeholders throughout the ZIP. Locking Hidden clears any open hidden-item details. Downloads Settings now includes the update controls. A PIN test no longer fails if its digits happen to occur inside a random hash.

## 2.8.4

- **Local support reports.** Settings, store errors and failed downloads can now create a sanitized support ZIP without using the command line. The report is built locally, keeps raw diagnostics and tracebacks private, replaces local paths, credentials, tokens, purchase names and creator names with placeholders, and is never uploaded automatically.

## 2.8.3

Faster with large libraries, in both pages and behind them. (There's no 2.8.2: a release by that name was
published by mistake without its files.)

- **Only the cards near the screen are drawn.** Both pages drew every card on each filter click or search
  keystroke; now they draw the first 120 and add more as you scroll.
- **Tags that match a word are found through a word index,** instead of trying every such tag on every name:
  20,000 names with 300 matching tags take about 0.1 s instead of 28 s, every time the library loads.
- **The Downloads index is rebuilt without holding anything up.** A sync no longer pauses after each download while
  the Downloads page asks for the index, and the Library page never waits for it.
- **The library and downloads lists are gzipped** when they're large: 28 times smaller, which helps when Hoard is
  opened from another device.

## 2.8.1

- **Hoard for Unity loads large libraries quickly,** and recognises your own catalog: see its 0.2.0 changelog.
- **The catalog is sealed again when Hoard starts,** if it isn't sealed with this computer's key. The Unity window
  reads `catalog.json`, and one sealed by a Hoard with a different key (Hoard on another computer, an earlier
  install, or Hoard run on Microsoft Store Python) showed there as "made on another computer" until the next
  download. Hoard rebuilds it in the background, and not while a job is running (that job rebuilds it anyway).
- **Fixed: a blank page from files with Windows line endings.** Browsers check a page's script against Hoard's
  security policy after turning CRLF line endings into LF, and Hoard didn't, so a page file saved with CRLF (a
  checkout whose git settings override `.gitattributes`) had its script refused.
- **Microsoft Store Python:** when Hoard runs on it, the log and `verify` say so. Windows keeps a Store app's
  AppData separately, so that Hoard's settings, sign-ins and sealing key aren't the installed app's.

## 2.8.0

- **Sync automatically.** In **Settings**, choose every 6 or 12 hours, once a day or once a week (it's off unless
  you do). While Hoard is open, it syncs by itself that often, counting from your last sync, whoever started
  it: it reads your stores and downloads anything new or updated. Payhip is left out, since it needs you there
  for its bot check. It waits for any other job, and when you're offline it tries again 15 minutes later
  instead of marking every store as unreachable. An open page shows its progress, and **Stop** stops it.
- **The open item stays marked.** While an item's details are open, its tile is outlined in gold, in both
  views, and screen readers hear it as the current item.
- **Owned twice, striped.** Something you own on more than one store has a spine striped in both stores'
  colours, and its label says where else you own it.
- **Accessibility settings,** in **Settings**, for both views:
  - **Text size:** Normal, Larger, Large or Largest.
  - **Pause animated pictures:** animated product pictures show as a still of their first frame.
  - **Reduce motion:** no sliding panels, lifting tiles or animated progress, as when your computer asks for
    less motion (which Hoard already followed).

## 2.7.0

- **Hoard updates itself.** **Settings** has a new **Updates** section. **Check now** asks GitHub whether there's
  a newer version. In the Windows app installed with `Hoard-Setup`, **Update to** then downloads the new
  installer, checks it, closes Hoard, installs it and opens Hoard again. Your settings, library, sign-ins and
  downloads stay as they are. Hoard only runs an installer whose SHA-256 matches both the release's
  `SHA256SUMS-windows.txt` and the checksum GitHub lists for the file, and it won't update in the middle of a
  refresh or download. The portable zip and Hoard run with Python say there's a newer version and link to it.
- **Check for updates automatically,** off unless you turn it on: Hoard asks GitHub once a day, when it starts,
  and shows **Update to** at the bottom of the page when there's a new version. A check sends GitHub nothing but
  the request itself (GitHub sees your IP address, as with any website). The privacy notes say so.

## 2.6.0

- **itch.io signs in with an API key.** Its website shows automated browsers a Cloudflare check that never lets
  them through, so signing in to itch.io in Hoard's window couldn't work. Now **Add API key** on itch.io's row
  in **Stores** shows where to make a key on itch.io, checks it with itch.io, and keeps it protected by your
  operating system (your Windows account, your Mac's Keychain or your Linux keyring), never in `config.json`.
  Hoard reads your itch.io library and downloads your files through itch.io's API, as itch.io's own app does:
  no browser, downloads that resume, and each file checked against itch.io's checksum. The key is only ever
  sent to itch.io's API. **Sign out** deletes it. From the command line: `login itch`.
- itch.io items are known by itch.io's own project number, so a page you import and the API agree.

## 2.5.2

- **Hoard's own browser, in the Windows app:** installing it now works. The app looked for the browser inside its
  own program folder, while installing put it in your user account's usual folder
  (`%LOCALAPPDATA%\ms-playwright`), so setup went on saying it "isn't installed". Both now use that folder: a
  browser you'd already downloaded is found straight away, and updating Hoard never removes it.

## 2.5.1

- **Hoard's own browser:** when **Settings** names Microsoft Edge or Google Chrome and it isn't installed, Hoard
  now uses its own browser instead. Setup offered to install it for that case, but afterwards still said the
  chosen browser "isn't installed", and signing in failed. Installing it is now also written to `hoard.log`.

## 2.5.0

Payhip becomes a library Hoard reads, saved pages can be imported in bulk, and itch.io joins.

- **Payhip is listed, not downloaded.** Payhip's check for automated browsers made downloading from it
  unreliable, so Hoard now lists everything you bought there, with each product's download page, and you
  download the files from Payhip yourself. **Sync**, **Download** and **Download everything new** leave Payhip
  out. Files Hoard downloaded from Payhip before stay where they are, in Downloads and in the catalog.
  `sync --payhip-page` is gone, with the page Hoard used to write listing Payhip products to download yourself.
  Refreshing Payhip with no shops listed no longer opens a window just to say so: it suggests importing.
- **Import saved pages in bulk.** A store's library often spans several pages, and Payhip keeps one per shop,
  so one saved page couldn't hold everything. **Import pages** (in **Stores**) now takes any number of saved
  pages at once, **Import a folder** takes a whole folder of them, and files or folders can be dropped on the
  window. They're read together, offline, and each page gets its own result, shown at the end: one that can't
  be read doesn't stop the rest. Pages from Payhip shops you haven't added are asked about once, together. On
  the command line, `import` takes several files and folders, and `--trust-shop` can be given more than once.
- **itch.io,** a new store. Sign in, and Hoard reads your itch.io library (what you bought, and what you
  claimed from bundles or "name your own price" pages) and downloads each project's files from its download
  page. If you set Hoard up before this version, turn itch.io on in **Settings** first: Hoard keeps the stores
  you chose. Game builds (files the creator marked for Windows, macOS, Linux or Android) are skipped unless you
  turn off **Skip game builds** in **Settings**, so a library with games in it doesn't fill your drive. A download
  page's address holds a key that opens it for anyone, so it's kept like a sign-in: only in Hoard's private
  library list, and taken out of troubleshooting files. If Hoard reads your itch.io library wrong, `debug itch`
  saves what it read (scrubbed of your details) for a report.
- **Hoard for Unity 0.1.3** shows itch.io's assets too. It's a separate release: see its own changelog.

## 2.4.2

Fixes from an outside review of 2.3.1. What was found and what changed, finding by finding, is in
`docs/security-review-2.3.1-response.md`.

- **Only Hoard's own window can use Hoard:** every request for your library, your downloads, their pictures or
  an action now needs a key that's new each time Hoard starts, even from your own computer. Other programs,
  and other people's accounts on a shared computer, could reach Hoard's address and, for example, point its
  downloads folder somewhere else. Hoard opens its window with a one-time link that the page trades for the
  key. Started as a server from the command line (`--no-open`, `--port` or `--host`), Hoard prints an
  address that includes it.
- **Payhip:** when Payhip blocks the automated browser, the page listing products for you to download yourself
  only links to Payhip and your own shops, whatever a product's record says (a record could have held a
  `javascript:` link), and it's written the same careful way as every other file.
- **Resumed downloads:** a half-finished file is only continued with the part that follows it, and only counts
  as finished when the store says the file ends there. Otherwise it's downloaded again from the start rather
  than stitched together from two different versions, and a file is only put in place once it's as long as
  the store said.
- **An emptied downloads folder:** `catalog.json` and `tags.json` no longer go on listing products that aren't
  there any more (the Unity window showed them).
- **Stop:** the file that had just finished downloading when you pressed Stop is recorded, instead of being
  downloaded again next time.
- **Faster with large libraries:** product pictures are found without going through the whole library
  (1,000 pictures in a 100,000-item library: 10 seconds before, 0.05 now); opening the Library no longer copies
  the whole list through JSON (0.7 seconds to 3 milliseconds at 100,000 items); and during a sync each store's
  record is saved at most every 10 seconds, instead of after every product and file (a 5,000-product sync
  with nothing new rewrote a 1.4 MB file 5,000 times).
- The list of files Hoard has sealed never drops an entry (past 20,000 it could, in principle).
- **Hoard for Unity 0.1.2:** a `.unitypackage` whose headers claim impossible sizes is refused before anything
  is set aside for it. It's a separate release: see its own changelog.

## 2.4.1

The 2.4.0 Windows app, released again: 2.4.0's release couldn't take the installer, and its version number can't
be reused. Nothing else changed: what's new is under 2.4.0 in CHANGELOG.md.

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
