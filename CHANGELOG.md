# Changelog

## 3.3.2

- **Notifications are in Hoard's language.** When the routine check finds something while Hoard runs in the
  background, the notification from your system is in Japanese or Korean too, not only English.
- **Fixed: in Japanese and Korean, a message Hoard has no translation for could come out half translated**, with
  words swapped for marks ("All 12 files / 3 downloads…"). It now stays whole, in English, until it's translated.
- **Fixed: products with no name to go by** (one that's only marks, such as "★★") **stacked into one tile** with
  every other such product by the same creator.
- **"1 file", not "1 files"**, when moving a product, rescanning or adding to Local.
- **The links to Hoard's website** (in the READMEs, the Hoard for Unity README and the site's own link previews) go
  to https://hoard.furryup.link/ directly; the old address forwarded without HTTPS.

## 3.3.1

- **Fixed: in Japanese and Korean, the Stores panel said how your sign-ins are kept in English** ("encrypted by
  your Windows account", or your Mac's Keychain, Linux keyring or folder), in the middle of the translated
  sentence. It's translated now.

## 3.3.0

- **Hoard in Japanese and Korean (日本語, 한국어).** Settings, Appearance has a new **Language** choice: **Match my
  computer** (the language your system or browser asks for, English if it's neither), **English**, **日本語** or
  **한국어**. Both pages, Settings, the panels and dialogs, and Hoard's own messages on the page are translated.
  Product names, creators, tags and files stay as they are. Korean uses Malgun Gothic, Apple SD Gothic Neo or Noto
  Sans KR when you have them, and breaks lines between words. The translations were made with AI help, and
  Hoard says so beside the Language setting and in setup: if something reads oddly, there's a new **Translation
  fix** issue form for telling us. The task log, Hoard for Unity and the website are still in English for now.
- **The setup assistant starts by asking your language**, with the question written in all three, so you can
  set Hoard up in yours from the first screen.
- **The README in Japanese and Korean** ([README.ja.md](README.ja.md), [README.ko.md](README.ko.md)), linked from
  the top of the English one.
- **Fixed: Updates, in Downloads, showed "undefined"** when nothing needed updating. It says **Nothing to update**.

## 3.2.0

- **Themes, and Light or Dark.** Settings has a new **Appearance** section: choose **Match my computer**, **Light**
  or **Dark**, and one of ten themes, each with a light and a dark version: **Hoard** (as before), **Dragonfire**,
  **Frost Cave**, **Geode**, **Mossy Ruins**, **Synthwave**, **Sakura**, **Midnight & Paper** (true black for OLED
  screens, and white), **High contrast** and **Spooky Hoard**. The pages open in your theme from the first moment.
  Every theme keeps text easy to read, at the same contrast as Hoard's own colours. Where a theme's accent is close
  to a store's colour, that store's colour shifts a little so the two can't be mistaken for each other.
- **Text on gold buttons is darker in the light theme**, so **Sync**, **Download** and the like are easier to read.
  Warnings in the light theme are a little darker too.

## 3.1.1

- **The logo glows while an update to Hoard is waiting**, and gives a little shake now and then. Choose it to open
  Updates in Settings. With reduced motion (Settings, or your system's), it only glows.
- **There are a few things to find in Hoard.**
- **Fixed: a stacked tile with a tall picture grew to the picture's height** instead of staying square.

## 3.1.0

- **Disk space, in Downloads.** A new view lists your downloads biggest first, with how much they take, and two
  ways to narrow it down:
  - **Same file kept twice**: files you have more than once, in two products (a bundle and the product also sold
    on its own, the same package bought from two stores) or in two library folders, with how much you'd free.
    Open one to see where else its files are. It's worked out from the fingerprints Hoard's download check
    already keeps, so it reads nothing; files the check hasn't seen yet are counted, with **Check now**.
  - **Not in any Unity project**: downloads none of your projects use (as Hoard for Unity reports them).
  Choose **Select** to move several to another library folder, archive them, or delete their downloaded files.
- **Select in Downloads can archive, and delete downloaded files, for several at once**, in any view.
- **A notification when the routine check finds something.** With Hoard open in the background, your system
  tells you how many new products and updates the routine check found (never their names), once: the same again
  isn't news. Turn it off in Settings, under **Routine check**. On Linux it needs `notify-send` or `gdbus`; the
  Flatpak asks to talk to the notification service for it.
- **Copies on two stores stack.** A product you have on two stores is one tile now, in the Library and in
  Downloads (which stacks copies too, with **Stack copies** beside Sort): by the same name and creator, or, when a
  creator's shops have different names, by the same name and a picture that looks the same, though each store
  saved it its own way. The page works out how pictures look once, and Hoard keeps it (`picture-looks.json`).
  Pictures several creators use stack names that are nearly the same, too. Names still need the same numbers and
  (variants), so "Hair Pack 1" and "Hair Pack (Pink)" stay apart.
- **The setup assistant asks what closing Hoard's window does**: keep Hoard running, minimized to the taskbar
  (the Dock on a Mac), or quit it. It's the same choice as **Closing Hoard** in Settings.
- **Hoard for Unity 0.6.0**: right-click files in the Project window and choose **Hoard › Which Product Is This
  From?**, and products in your project with a newer download are marked, to import the update. See its
  changelog.

## 3.0.3

- **Fixed: in Hoard's window, Settings' Add a folder... filled the whole row**, pushing the box for a folder's path
  and its **Add** button out of the panel (a sliver of them showed at the edge). It's as wide as its label now, with
  the box and **Add** beside it. **Install update**, in Settings' Updates, had the same problem when an update was
  waiting.

## 3.0.2

- **Downloads only shows the store tabs you have something in.** A store with nothing downloaded in the view
  you're in has no tab, as in the Library; Local's tab still shows when you open Local with nothing in it yet.
- **The store tabs in Downloads show how many things are in each**, as the Library's tabs do.
- **Downloads can unlock your hidden items.** Choosing **Hidden** in Downloads asks for your PIN there, as the
  Library does, instead of sending you to the Library first; **Lock now** locks them again from Downloads too.
  Setting, changing and resetting the PIN stay in the Library.
- **Sync is the last button in the header on both pages.** In Downloads, **Download new** sat after the gold
  **Sync**; it's now before it, so Sync is in the same place on every page.
- **Projects' Credits dropdown looks like the others**: the same arrow, height and text size as Sort and the
  dropdowns in Settings, instead of the system's own.
- **Settings and Add to Local start with the same size of text as Stores and Tags.**

## 3.0.1

- **Fixed: the store tabs' counts went to 0 after a while.** The tabs (Everything, Booth, Gumroad...) count what's
  in the view you're in: the Library, Archive, Removed or Hidden. They were only redrawn when your library was read
  again, so if that happened while you were looking at another view (when a routine check or a task finished,
  say), they kept counting that view: every tab read 0 back in the Library, while the heading still said how many
  things you have. They now follow the view you're in.

## 3.0.0

Hoard 3.0 is the biggest update since Hoard began. It's an app on **Windows, macOS and Linux** now, with a new look
built around your stores' colours. Signing in works with Google, Discord or X. Downloads queue up, retry
themselves, show their speed and time left, and can't hang; you choose what downloads, down to each file, and any
task can be force stopped. One routine check keeps your library up to date and asks before downloading anything.
And Hoard can keep working in the background while its window is closed.

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
- **Betas, for testers.** Betas of the next version now come out here, as pre-releases ("Hoard 3.1.0 beta 1").
  Turn on **Get beta updates** in **Settings › Updates** to be offered each one, and the finished version when
  it's out. Everyone else only ever sees releases.
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
- **Signing in installs Hoard's browser if it needs to,** showing its progress, then opens the sign-in window.
  Signing in to Payhip before you've added your shops says it's done, and to add them (a shop's address is in your
  purchase email) or import their saved pages.
- **Save a whole Payhip shop in one go.** Importing Payhip meant saving every page of every shop's library by
  hand. The **Save for Hoard** bookmark (in Stores, under Import saved pages: drag it to your browser's bookmarks
  bar) reads every page of a shop's library in your usual browser, as you, and saves them as one file to import.
  It reads only that shop's own library pages, and sends nothing anywhere. Run it on each shop, then import the
  files together.
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
- **Browse for folders.** Choosing the downloads folder (in setup and Settings) and adding your own packages have a
  **Browse** button that opens your system's own folder or file picker, instead of typing a full path.
- **Stores offers Sign in or Sign out, whichever applies,** instead of both for every store, and the panels use more
  of the window's width.
- **Panels work from the keyboard.** A panel takes the keyboard when it opens, Tab goes round inside it instead of
  wandering through the dimmed page, and closing it hands the keyboard back to the button you opened it with.
- **Questions in Hoard's own dialog.** "Delete its downloaded files too?" and the like ask in a dialog that matches
  the rest of Hoard, with buttons that say what they do, instead of the browser's plain pop-up.
- **Store tabs stay in sight.** In a smaller window, or at a larger text size, Sort and the tile size go up a row
  of their own instead of covering the later store tabs. In a very narrow window the tabs scroll, and fade at the
  edge where there are more.
- **Local is a place of its own** in the top bar: choosing it highlights Local, not Downloads.
- **Easier to read in the light theme:** gold links and buttons are a darker gold, at least 4.5:1 against the
  background.
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
- **Buttons line up.** Every button is one of two heights, gold and plain alike, with its text centred; the bar's
  buttons stay on one row with the search box down to narrower windows; tickboxes are gold everywhere.
- **What's new, in Hoard.** **Settings › Updates › What's new in Hoard** shows every change, version by version,
  with the version you're running marked; betas too when you tick **Include beta updates**.

### Accessibility

- **Store colours you can tell apart** (issue #112). Settings, under **Accessibility**, has **Store colours**:
  **Standard**, **Easier to tell apart (colour blindness)**, a set chosen to stay distinct with the common kinds of
  colour blindness and clear on light and dark backgrounds, or **My own**, a colour you pick for each store.
- **The glow can be turned off** (issue #112): untick **Coloured glow behind the page** for a plain background.

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
  different shop is credited to the shop it's from. Products from shops at `payhip.com/<name>` keep their creator and link even when your own
  shop is at payhip.com too (issue #97).
- While your hidden library is locked, hidden products' names stay out of job progress and the Tasks list, and
  locking it closes any hidden product's details you had open.
- **Remove a download completely** (issue #81). Removing something you've downloaded asks whether to delete its
  downloaded files too, so it no longer lingers in Downloads. **Delete downloaded files** is in every download's
  details, in the Library and in Downloads, and for a selection: a product still in your library stays there, to
  download again. Only the files Hoard downloaded go; anything of your own in the folder stays.
- **Local: your own packages** (issue #80). Packages you make, to move textures and materials between projects or
  to hand to commissioners, live beside what you bought: **Add your own** takes a folder or file on this computer,
  with who it's for. You choose each time whether Hoard copies it in (checked like a download) or lists it where
  it is (never written to; **Rescan** picks up changes). Tagged, searched and imported into Unity like the rest.
- **Add a folder of folders to Local** (issue #109). In **Add your own**, **Folders inside it** makes each folder
  one, two or three levels down a package of its own, named for its folder; from two levels down, the folder above
  is who made it. Hoard lists what it would add first, and adding the same folder again only adds what's new.
- **Clearer buttons in an item's details** (issue #108). There's one thing to do, in gold: **Download** when you
  don't have a copy yet, **Show in Downloads** when you do (with **See the update** when there's one), or **Open on
  Payhip** for Payhip's. The store's own pages are named for the store (**Open on Gumroad**, **Store page**), and
  **Archive**, **Hide** and **Remove** sit under **Organise**.
- **Copies stack** (issue #111). Copies of the same product on one store (bought more than once, or in several
  versions) show as one tile marked ×3, say. Hoard knows them by their picture: the same image, byte for byte, not
  the same name, so "Hair Pack 1" and "Hair Pack 2" stay apart. A picture several creators share (a store's default
  banner) stacks nothing. Choose a stack to see every copy. Untick **Stack copies**, beside **Sort**, to show each
  on its own.
- **Projects** (issue #86). Every Unity project you open Hoard's window in (Hoard for Unity 0.4.0) shows up under
  **Projects**: each product it uses, all of it or part, which have updates waiting, and its credits list (the
  same one the Unity window makes, with your changes there), ready to copy in any style. Downloads says which
  projects use each product.

### Downloads you can leave running

- **Choose what downloads** (issue #107). **Download new**, **Download everything new**, a store's **Download** and
  **Update all** first list what they'd get: what's in your library with nothing on disk yet, and the updates the
  last check found. Untick anything you don't want this time. Where Hoard knows a product's files before
  downloading (an update's new and changed files, and a Booth product's files), **Choose files** lets you untick
  them one by one. Only the stores switched on in Settings are included.
- **Always skip** (issue #107) leaves a product out of every download and sync, automatic ones included, until you
  choose **Stop skipping**. Choosing it by name still downloads it.
- **Download several at once** (issue #106): select products in the Library and choose **Download**. They download
  as one job, across stores.
- **Jobs wait their turn** (issue #49). Start a sync, download, refresh or sign-in while something is running, and
  it joins the queue instead of being refused with "Hoard is busy". So does taking something out of Local,
  rescanning it, or deleting a removed product's downloaded files. Take one off the queue in Tasks.
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
- **Force stop, for any task.** The running task in **Tasks** has **Force stop** beside it, whatever it is: a
  refresh, a sign-in, installing the browser, as well as downloads and syncs. It closes the store's browser (or the
  sign-in window, or the browser download) at once, so the task ends straight away. What finished is kept, and a
  file part way through resumes next time where it can. It asks first.
- **Your tasks go first** (issue #110). Start something while an automatic one runs and it stops safely to make way
  (Tasks says so), then carries on after yours.
- **Jinxxy files download straight from Jinxxy,** with your sign-in, the way Booth's do, so a download that's
  interrupted picks up where it stopped and progress shows its size and speed. If Jinxxy turns that away, Hoard
  downloads through the browser instead.
- **A resumed download is never joined onto a different file:** if the creator uploaded a new file under the same
  name since, it starts again from the beginning.
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
- **Library folders on other drives.** When your downloads drive fills up, add a folder on another drive (an
  external disk, say) in Settings, under **Library folders**: **Add a folder…** picks it and adds it. Hoard reads
  it as part of your library, and Downloads gives each folder a tab of its own, with how many downloads it holds.
  Downloads, Hoard for Unity, the routine checks and syncing all cover it. New downloads still go to your downloads
  folder, and a product already in another folder is updated where it is. To move a product, open its details and
  choose **Move here** (or select several and move them together): Hoard copies its files, checks every one, and only then deletes them where they were. When
  a folder's drive isn't connected, its products are left alone, not downloaded again; removing a folder in
  Settings only stops Hoard reading it.
- **One routine check, which asks before downloading** (issues #83 and #113). Every 6 or 12 hours, once a day, a
  week or a month (or off, until you choose), while Hoard is open it reads your stores (not Payhip), checks your
  downloads are there and unchanged (by size and SHA-256 fingerprint, reading only files that changed since the last
  check), and checks for updates. When it finds something new, it asks: **Choose what to download** shows the list
  **Download new** does, or **Not now**. It never downloads by itself. If you'd turned on **Sync automatically**,
  it keeps that timing. Downloads shows when your downloads were last checked and what was found, with **Check
  now**; Tasks names any changed or missing files.

### Working in the background, and closing safely

- **Closing the window minimizes Hoard to the taskbar** (the Dock on a Mac), and downloads, syncs and automatic
  syncs carry on; click it there to bring the window back. **Quit Hoard** in Settings stops it. It's on unless you
  turn it off in Settings, and then the close button quits.
- **Quitting while Hoard is working asks first:** **Stop it, then close** (Hoard closes once what's running has
  stopped), **Minimize, and keep working**, or **Close now**, which ends everything at once. Before, closing
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

- **Store pictures didn't load in the Mac app** (2.10, issue #93): every tile showed its initials. The app's Python looked
  for the system's trusted certificates where they were on the computer that built it, so every picture's secure
  connection failed, without a word. Hoard now always trusts the same certificate bundle its downloads use, still
  checking every certificate, and notes in its log, once, why a picture couldn't be fetched. The build's own check
  of each app now makes sure it has certificates to trust, and on a Mac that its window's parts are there.
- **The Library no longer asks your keyring on every load.** Whether there's an itch.io key, and how sign-ins are
  protected, were looked up each time the page loaded: on Linux that started gdbus and secret-tool every time,
  on a Mac the Keychain's security tool, and a locked keyring could ask to be unlocked again and again. Hoard now
  remembers the answers, and updates them when you add or remove the key.
- **Command-Q quits Hoard on a Mac** (and Quit in its menu or the Dock), asking first only while something is
  running. It went through the same step as the window's close button, so with the window going to the Dock on
  close, Hoard couldn't be quit that way.
- Downloads' tiles no longer crowd the heading above them, which they cut into when no filter was chosen.
- **A sync that read none of your stores said Done,** in green. It now fails and says which stores it couldn't read
  (each store's row in Stores says why), and doesn't try to download. A sync that read only some is **Partly done**,
  and so is a download where some files failed.
- The download panel could cover the last tiles. The page now has room to scroll them clear of it, and after a job
  that went well it closes by itself a few seconds later (Tasks keeps the result).
- The top bar could stay two rows tall after the window was made wider again, and differed between Library and
  Downloads. It now fits its contents, and is laid out the same on both pages.
- The setup assistant ticked every store, so someone who'd never used Payhip was asked for Payhip shops. The first
  time, only the stores you already have items from are ticked.
- A library with many products of the same name (on different stores or by different creators) was slow to open:
  finding each product's copies on other stores took time that grew with the square of how many shared the name.
  It's now worked out once per store.
- Your own folders listed where they are now have a picture: a copy of one of their images, kept in Hoard's
  `Local` folder (made again on **Rescan**).
- Sign-ins kept on another drive (`advanced_signin_location`) that wasn't plugged in when Hoard started made every
  store's list vanish, as if you'd signed out. Hoard now leaves the lists alone when that whole folder is missing.
- "Hoard is busy" just after starting: checking the catalog's seal no longer holds up the first thing you choose.
- The store tabs no longer make the page bounce as the pointer moves along them.
- The pages' scripts run in strict mode again.
- A PIN test could fail when its digits happened to appear inside a random hash.
- **One itch.io project's revoked download key** no longer counts as your API key being refused, which stopped every
  itch.io download and asked you to sign in again.
- **Booth:** one dropped connection no longer sends every later file through the browser (the file resumes
  instead), and a new file in a product you have counts as new, not updated.
- **Jinxxy:** pictures several products share are kept instead of being deleted (and downloaded again) every sync,
  and a file whose button moves on the page is still the file downloaded.
- A product both hidden and removed stays hidden while the hidden library is locked; reading your Jinxxy inventory
  only follows Jinxxy's own pages.
- Adding a folder with your downloads folder inside it (your whole Documents folder, say) to Local is refused, and
  one file name your system can't take no longer stops a copy part way.
- A Gumroad product downloaded from the Library gets its picture; removing one product no longer deletes a picture
  another uses.
- Requests Hoard can't make sense of get a clear error instead of a dropped connection, and the pages run faster:
  your hidden, archived and removed choices are read once until they change.

### Hoard for Unity 0.3.0 to 0.5.2

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
- **Library folders on other drives**: products kept in another of Hoard's library folders are listed and
  imported like any other (0.5.0).
- **Only what's in Assets counts as in your project** (issue #114, 0.5.1): a package's own copy of something VCC
  installs under `Packages/` (Poiyomi, VRCFury, the VRChat SDK) no longer makes a product look imported, and only
  files count, not the folders a creator's products share (0.5.2).
- **Nothing is cut off in a narrow window** (0.5.1): long names end in "…", and the toolbar's buttons move to a
  second row instead of off its edge.
- **Importing a package with scripts is remembered** (0.5.2), a damaged `imports.json` is kept aside rather than
  written over, a library folder that's a whole drive works, and "Checking packages" no longer gets stuck.

### A website, and thanks

- **Hoard has a website:** https://soloflighter1010.github.io/Hoard-Asset-Manager/ with downloads for your
  computer, Hoard for Unity, and a **What's new** page that follows this changelog. VCC's listing address hasn't
  changed.
- **Thank you to the testers** who tried every beta of 3.0 on their own libraries and told us what broke:
  puzzlella, dx_nacca, kyrmeso, xionite02, vixendavali, djfin, loafevr, doctorlucymoth, surfur, hallowokin,
  cheapthrill, petra.synth and xkittygoddessx.

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

## 2.11.1

- **Fixed: Payhip products bought from other creators were credited to you** (issue #25). If you sell on Payhip
  too, your own shop's library page lists everything you've bought on Payhip, from every shop, and doesn't say
  who made each one. Hoard credited them all to the shop whose page it was: yours. Now they show as Unknown
  creator. And a product another shop's library page lists from a different shop is now credited to the shop it's
  from (its link says which), not to the shop whose page it was.
- **The release's VirusTotal check no longer looks stuck.** It waited for each file's scan in turn, without a word,
  which with several new files could run for most of an hour. Now it sends every file first, waits for all the
  scans together, and says how they're getting on. It gives up after 40 minutes, naming the files still being
  scanned, and running it again picks up where VirusTotal got to.

## 2.11.0

Sign in with Google, Discord or X.

- **Sign in with Google, Discord or X works** (issue #21). Google and the others refuse to sign in from a browser
  a program is driving, which Hoard's sign-in window was. Now signing in opens your chosen browser as itself (Edge,
  Chrome or Hoard's own), on that store's own sign-in folder, so you can sign in however you normally do. Close the
  window when you're done (on a Mac, quit the browser with Command-Q) and Hoard reads the store, as before. Your
  sign-in is saved and protected exactly as it was. A link from a sign-in email still opens in that window when
  you paste it into Hoard. `"automated_sign_in": true` in `config.json` brings back the old window if you need it.
- **Fixed: Stop could miss the download it was meant to end.** Stop was acted on by whichever part of Hoard wrote
  to the log next, which wasn't always the download. Only the download itself acts on it now.
- **Every release is scanned by VirusTotal before it's published.** The release notes link each file's report.

## 2.10.0

Hoard is now an app on macOS and Linux too: a package for the Mac, and a Flatpak for Linux, each opening in Hoard's
own window, like the Windows app.

- **Hoard for macOS.** `Hoard-2.10.0-macos-apple-silicon.pkg` (M-series Macs) and
  `Hoard-2.10.0-macos-intel.pkg` install **Hoard** in Applications. macOS 11 or newer. They aren't signed by
  Apple yet, so macOS won't open them at first: choose **Done**, then **System Settings › Privacy & Security ›
  Open Anyway**.
- **Hoard for Linux, as a Flatpak.** `Hoard-2.10.0-linux-x86_64.flatpak` installs from your software centre or
  with `flatpak install --user`, on the GNOME runtime from Flathub. Its sandbox allows the network, its window,
  your keyring (for sign-ins), and your home folder and drives (for your downloads folder), and nothing else. It
  uses the same `~/.local/share/Hoard` as Hoard run from source, so your library carries over and Hoard for
  Unity finds it. The manifest follows Flathub's rules, ready to submit there.
- **Updates say which file to get.** On the Mac and in the Flatpak, **Settings › Updates** names the new
  version's package for your computer (the Windows app still updates itself).
- Every file on a release has signed build provenance and a checksum file, and every pull request builds the
  Mac app and the Flatpak, with their self-tests, as a release would.

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
- **Fixed: Booth's free items weren't downloaded.** Booth lists your free downloads without their files ("no
  files listed in your library"); Hoard now opens each such item's page and downloads from its buttons there.
- **Fixed: a Gumroad product that is only pictures downloaded nothing.** Some download pages list no files: the
  product is pictures in the page itself (a set of PNG textures, say). Hoard now saves those into a **Page
  images** folder, in page order, each typed by what it is. Pictures beside real files (previews, instructions)
  still aren't downloaded.
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
