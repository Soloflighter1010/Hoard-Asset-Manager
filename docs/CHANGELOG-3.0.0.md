<!--
Draft of Hoard 3.0.0's changelog entry: everything since 2.8.4, the last public release, gathered from the beta
releases in between (2.8.5 to 2.11.1) and what has been merged since. It is kept here, not in CHANGELOG.md, until
3.0.0 is released: the release takes its notes from CHANGELOG.md, and the website's What's new page shows every
section in it.

To release it: move everything after this comment into CHANGELOG.md as "## 3.0.0", above "## 2.11.1"; set
__version__ to 3.0.0 in hoard/__init__.py and add the release to the Flatpak's metainfo; check the "Before
releasing" notes in this file; delete this file. It uses only the Markdown the website's What's new page reads
(scripts/build_site_changelog.py): "### " headings, paragraphs, "- " lists, **bold**, `code` and https links.

Before releasing, check:
- Code signing: keep "Signed for Windows" only if the release's Windows job signed (Azure Artifact Signing set up).
- Hoard for Unity: keep each version in its section only if it's out on VCC by then (Build Release, tags unity-v0.3.1, unity-v0.4.0).
- Add anything merged after this draft was written.
-->

Hoard 3.0 is the biggest update since Hoard began. It's an app on **Windows, macOS and Linux** now, with a new look
built around your stores' colours. Signing in works with Google, Discord or X. Downloads queue up, retry
themselves, show their speed and time left, and can't hang. And Hoard can keep working in the background while
its window is closed.

Coming from 2.8.4, everything carries over by itself: your library, tags, sign-ins, settings and downloads. See
**Upgrading from 2.8** at the end.

### Hoard on every computer

- **Hoard for macOS.** `Hoard-3.0.0-macos-apple-silicon.pkg` (M-series Macs) and `Hoard-3.0.0-macos-intel.pkg`
  install **Hoard** in Applications, opening in its own window like the Windows app. macOS 11 or newer. They
  aren't signed by Apple yet, so macOS won't open them at first: choose **Done**, then **System Settings ›
  Privacy & Security › Open Anyway**.
- **Hoard for Linux, as a Flatpak.** `Hoard-3.0.0-linux-x86_64.flatpak` installs from your software centre or with
  `flatpak install --user`, on the GNOME runtime from Flathub. Its sandbox allows the network, its window, your
  keyring (for sign-ins) and your home folder and drives (for your downloads), and nothing else. It uses the same
  `~/.local/share/Hoard` as Hoard run from source, so your library carries over and Hoard for Unity finds it.
- **Updates say which file to get.** On the Mac and in the Flatpak, **Settings › Updates** names the new version's
  package for your computer. The Windows app still updates itself.
- **Hoard always installs into `%LOCALAPPDATA%\Programs\Hoard` on Windows** (issue #21): a folder only your account
  can change, which Hoard's sign-in protection counts on. A Hoard installed somewhere else by an older setup moves
  there when it updates; you can delete the old folder afterwards.

### Signing in, your way

- **Sign in with Google, Discord or X** (issue #21). Those sign-in services refuse a browser that a program is
  driving, which Hoard's sign-in window was. Now signing in opens your chosen browser as itself (Edge, Chrome or
  Hoard's own) on that store's own sign-in folder, so you sign in however you normally do: a password, a passkey,
  or Google, Discord or X. Close the window when you're done (on a Mac, quit the browser with Command-Q), and
  Hoard reads the store as before. Your sign-in is saved and protected exactly as it was. A link from a sign-in
  email still opens in that window when you paste it into Hoard. If you need the old window,
  `"automated_sign_in": true` in `config.json` brings it back.
- **Sign-ins on a Mac work in the background too.** Store reads now use the same full Chromium as the sign-in
  window, so they can read sign-ins that the Keychain protects.
- **Setup is sturdier.** On Windows, a browser holding its sign-ins open no longer makes the setup assistant's
  status fail, and the Library takes over the store counts if you close the assistant while signing in.
  Settings, sign-in messages, logs and support reports all say which browser Hoard is really using, including when
  it falls back to its own.
- **The first setup goes through to the end** (issue #21). The first time Hoard opens, the setup assistant can't be
  skipped or closed half-way: a step that isn't done yet keeps you on it (Hoard's browser not installed, say, or
  no store picked), and going on without signing in to any store, or without a Payhip shop, asks first. Run again
  from Settings, it can still be left at any step.

### A new look

- **Folder tabs and the glow.** The store tabs are folder tabs: the one you're looking at is raised, and the page
  glows up from the bottom in its store's colour. On **Everything**, the colours of the stores you use drift
  slowly through the glow (and stay still when you ask your system for less motion).
- **One panel for Tags, Stores, Settings and Tasks** (issue #84). Each opens in a panel over the middle of the
  page, one at a time: choosing another swaps it in, and the buttons along the top stay in reach. **×**, Escape or
  a click on the page around it closes it.
- **The download panel sits beside an asset's details** (issue #85) instead of over them, so you can keep using
  them while it shows. In a narrow window the details end above it.
- **Settings save as you change them.** There's no **Save** button any more: a box or a list is saved straight
  away, and a folder or the Payhip shops when you leave the field. While a job runs, only the settings it depends
  on (where files go, the browser, the stores and the Payhip shops) wait for it to finish.
- **A sidebar that folds.** **Hide filters** folds it to a thin strip, and each section (your tags, suggestions,
  Show, creators) folds by its heading. Hoard remembers both.
- **Tasks**, next to Library and Downloads, shows what's running with its progress, what's waiting, and what
  finished: how it went, how long it took, any problems, and its full progress. It keeps the last 60, between
  runs too.
- **A splash while your library opens,** with the Hoard logo and "Opening your hoard", so the page never shows
  half-loaded. It doesn't animate when you ask for less motion.
- **The window remembers its size and place,** and whether it was maximised. A window that would open off-screen
  comes back to the middle.
- **Large text fits.** With **Largest** text, panels sized to the window no longer run off its edge: Settings,
  Stores, the sidebar, details, the selection bar, dialogs, the setup card and the download panel.
- Sort, tile size and what's running sit up beside the tabs, out of the way.

### Your library

- **See what you've downloaded.** Downloaded products have a small download mark on their pictures (with a label
  for screen readers), and **Downloaded** under **Show** filters to **Downloaded** or **Not downloaded yet**, with
  live counts.
- **New, and Recently added** (issue #18). Anything that appears in your library after a refresh has a **New**
  badge for a week (change it in Settings, under **New in your library**: a day to a month, or never), and **New**
  under **Show** filters to them. **Recently added** sorts the newest first. What was already there when Hoard
  first read a store isn't counted as new.
- **Check for updates to what you've downloaded.** In Downloads, **Check for updates** (under **Updates**) reads
  your stores without downloading anything and lists every download whose store has newer files: files the
  creator added or changed since you downloaded it. **Update all**, or **Update** one from its details, which can
  also check just that one. In the Library, such products say **Update available**.
- **Downloads has Archive, Removed and Hidden views,** with the sidebar's counts following the view you're in.
- **Payhip products are credited to the right creator** (issue #25). If you sell on Payhip too, your own shop's
  library page lists everything you've bought anywhere on Payhip, without saying who made each one, and Hoard
  credited them all to you. Now they show as **Unknown creator**, and a product a shop's page lists from a
  different shop is credited to the shop it's from.
- While your hidden library is locked, hidden products' names stay out of job progress and the Tasks list, and
  locking it closes any hidden product's details you had open.
- **Remove a download completely** (issue #81). Removing something you've downloaded asks whether to delete its
  downloaded files too, so it no longer lingers in Downloads. **Delete downloaded files** is also in Removed, in
  the Library and in Downloads. Only the files Hoard downloaded go; anything of your own in the folder stays.
- **Local: your own packages** (issue #80). Packages you make, to move textures and materials between projects or
  to hand to commissioners, live beside what you bought: **Add your own** takes a folder or file on this computer,
  with who it's for. You choose each time whether Hoard copies it in (checked like a download) or lists it where
  it is (never written to; **Rescan** picks up changes). Tagged, searched and imported into Unity like the rest.
- **Projects** (issue #86). Every Unity project you open Hoard's window in (Hoard for Unity 0.4.0) shows up under
  **Projects**: each product it uses, all of it or part, which have updates waiting, and its credits list (the
  same one the Unity window makes, with your changes there), ready to copy in any style. Downloads says which
  projects use each product.

### Downloads you can leave running

- **Jobs wait their turn** (issue #49). Start a sync, download, refresh or sign-in while something is running, and
  it joins the queue instead of being refused with "Hoard is busy". Take one off the queue in Tasks.
- **Failed downloads are tried again** (issue #19): twice, after a short wait, before they count as failed (change
  it in Settings, under **Failed downloads**). A store saying a file isn't there, or isn't yours, isn't retried.
- **Progress, speed and time left.** While a file downloads, the download panel and Tasks show a progress bar, how
  much has come in of how much, how fast it's coming, and how long is left. (Files that come through the browser,
  from Jinxxy and sometimes Booth, show how much and how fast; the browser doesn't say how big they are.)
- **Nothing can hang a sync any more:**
  - A download that stops coming in, without the store hanging up, is given up on after 2 minutes and tried
    again, whichever way it comes.
  - When a store's browser closes by itself part way through (Jinxxy, or Booth through the browser), Hoard opens
    it again and carries on. Before, every product after it failed at once: 258 in one sync. If it keeps closing,
    the rest of that store waits for next time, with one message saying so.
  - A browser that stops answering is ended 20 seconds after you choose **Stop**, so the job finishes. A job with
    no progress for 5 minutes says so, and the log notes where it was waiting.
- **Stop is quick and sure:** it works part way through a file, within a few seconds, and always reaches the
  download it's meant to end.
- **One product goes straight to its download.** **Download a copy** (Library) and **Update** (Downloads) open just
  that product's page on Jinxxy, and just that purchase's download page on Gumroad, instead of reading through
  the whole store to find it.
- **Booth's free items download.** Booth lists them without their files, so Hoard now opens each one's page and
  downloads from its buttons.
- **Gumroad products that are only pictures download.** Some download pages have no files, just pictures in the
  page (a set of PNG textures, say). Hoard saves those into a **Page images** folder, in page order.
- **Jinxxy downloads into OneDrive work:** OneDrive's cloud files are no longer mistaken for shortcuts.
- **A download you delete completely leaves Downloads** on the next rescan and can be downloaded again. One with
  only some files missing stays, marked.
- Removing a browser store's sign-in folder while Hoard is closed clears that store's list from the Library at the
  next start, without touching your downloads or imported pages.
- **Make an editable copy** (issue #82). Want to change a texture? Open a download and make an editable copy: its
  files go to a folder of their own (**Hoard Edits**, beside your downloads), which Hoard never checks or replaces,
  so a sync can't undo your edits. Only files that still match what Hoard downloaded are copied, and a read-me in
  the copy says what it is.
- **Routine checks of your downloads** (issue #83). Once a week (or a day, a month, or only when you ask, in
  Settings), Hoard checks every downloaded file is there and unchanged since it was downloaded, by size and
  SHA-256 fingerprint; after the first check, only files whose size or time changed are read again, so it's quick.
  Downloads shows when it last checked and what it found, with **Check now**; Tasks names any changed or missing
  files.

### Working in the background, and closing safely

- **Keep Hoard running when its window is closed** (a new setting): closing the window hides it, and downloads,
  syncs and automatic syncs carry on. Open Hoard again to bring the window back; **Quit Hoard** in Settings stops
  it.
- **Closing Hoard while it's working asks first:** **Stop it, then close** (Hoard closes once what's running has
  stopped), **Keep working in the background**, or **Close now**, which ends everything at once. Before, closing
  gave a download 5 seconds to stop.

### Logs and support reports

- **A log for each time Hoard starts,** kept for 30 days (and the newest 10 however old), instead of one log that
  grew for ever. **Open logs folder**, in Settings under Troubleshooting, shows them, and a support report
  includes this run's log and the one before.
- **Support reports give away even less.** Product and creator names in the summary at the end of a sync are now
  hidden like the rest; Windows paths written with doubled separators and downloaded file names in progress lines
  are replaced too, with the same placeholder everywhere in the report. A name with "secret" or "token" in it is
  no longer mangled as if it were a password. `PRIVACY.md` says where reports really go: `Hoard\Support Reports`
  in your Documents folder.

### Security

- **The September 2026 code-scanning findings are fixed.** None is known to have been exploitable (Hoard's server
  already needed each run's own access key, and imported pages were already opened with scripts off), but every
  guard is now one the scanner can follow, with a test for each:
  - Imported store pages are cleaned with an HTML parser instead of patterns, so no way of writing a script tag or
    an event handler slips through, and a `<style>` inside an SVG can't carry markup.
  - The pages' Content-Security-Policy hashes are found the same way.
  - Pictures from your downloads folder are served only from checked paths inside it, as a fixed list of types;
    fonts only from Hoard's own.
  - No response header can carry a line break.
  - Jinxxy links are recognised by their address's host, over https, not by "jinxxy.com" appearing anywhere in
    it.
  - Support reports hide names without patterns that could take very long on an unusual line.
- **Safer releases.** Every file on a release is built on GitHub from this project's code, with signed build
  provenance and a checksum file, and is scanned by VirusTotal before the release is published. The release notes
  link each file's report.
- **Signed for Windows.** `Hoard.exe`, `hoard-cli.exe` and the installer are code-signed, so Windows and Defender
  know they're Hoard's. See `CODE_SIGNING.md`.

### Fixed

- Downloads' tiles no longer crowd the heading above them, which they cut into when no filter was chosen.
- Sign-ins kept on another drive (`advanced_signin_location`) that wasn't plugged in when Hoard started made every
  store's list vanish, as if you'd signed out. Hoard now leaves the lists alone when that whole folder is missing.
- "Hoard is busy" just after starting: checking the catalog's seal no longer holds up the first thing you choose.
- The store tabs no longer make the page bounce as the pointer moves along them.
- The pages' scripts run in strict mode again.
- A PIN test could fail when its digits happened to appear inside a random hash.

### Hoard for Unity 0.3.0 to 0.4.0

Released alongside, through VCC (Hoard's listing:
https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json):

- **Create Credits List** (issues #51 and #79). The **Create Credits List** button lists the creators of the
  Hoard assets fully in your project, ready to paste where you share your avatar or world: as a list with store
  links, as Markdown, or grouped by creator. Untick any you don't want credited and add others by hand; **Copy** or **Save as...**. Your changes travel with
  the project.
- **Animated pictures play** in the list and the details. Unity can't read GIFs, so the window decodes them itself.
- **A picture for more products:** when a product's saved picture is a kind Unity can't show (WebP or AVIF), the
  window uses one of the product's own images instead.
- **Your own packages** from Hoard's Local are listed and imported, with who they're for (0.4.0).
- **Projects in Hoard** (issue #86): the window tells Hoard what each project uses (0.4.0).

### A website, and thanks

- **Hoard has a website:** https://soloflighter1010.github.io/Hoard-Asset-Manager/ with downloads for your
  computer, Hoard for Unity, and a **What's new** page that follows this changelog. VCC's listing address hasn't
  changed.
- **Thank you to the testers** who tried every beta of 3.0 on their own libraries and told us what broke:
  puzzlella, dx_nacca, kyrmeso, xionite02, vixendavali, djfin, loafevr, doctorlucymoth, surfur, hallowokin and
  cheapthrill.

### Upgrading from 2.8

- **On Windows,** update from **Settings › Updates** as usual, or install `Hoard-Setup-3.0.0.exe` over your copy.
  If your Hoard was installed somewhere other than `%LOCALAPPDATA%\Programs\Hoard`, the update installs it there;
  you can delete the old folder afterwards. Your settings, library, sign-ins and downloads stay where they are.
- **Settings has no Save button:** changes save as you make them.
- **Logs:** each start of Hoard has its own log now. Use **Open logs folder** in Settings to find them.
- **Payhip sellers:** after your next refresh, products bought from other creators show as **Unknown creator**
  instead of your own shop's name.
- **Signing in with Google, Discord or X:** sign in to that store again, choosing it on the store's own sign-in
  page.
