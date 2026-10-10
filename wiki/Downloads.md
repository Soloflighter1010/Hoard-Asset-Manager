Hoard keeps local copies of what you own on Booth, Gumroad, Jinxxy and itch.io, and keeps them up to date when
creators update their files. Payhip is listed, not downloaded: see [Payhip](#payhip).

## Downloading

- **Sync** (top right) reads what you own from each store you use, then downloads anything new, as one job.
- **The routine check** (in **Settings**: off unless you choose every 6 or 12 hours, once a day, once a week or
  once a month) runs by itself while Hoard is open: it reads your stores, checks your downloads (see [Checking
  your downloads](#checking-your-downloads)) and checks for updates. It downloads nothing itself: when it found
  something new or updated, both pages say so, with **Choose what to download** (the list **Download new** shows)
  and **Not now**. It leaves Payhip out (Payhip needs you there for its bot check), waits for any other job to
  finish, and when you're offline it tries again 15 minutes later instead of marking your stores as unreachable.
  Hoard doesn't run it while it's closed. From 3.1, with Hoard in the background, a notification from your system
  says how many new products and updates it found (never their names): once, and again only when it finds more.
  Turn that off in [Settings](Settings).
- **Your tasks go first.** Start something while the routine check runs and the check stops safely to make way;
  Tasks says so, and it carries on after yours. Anything you start also waits ahead of automatic ones in Tasks.
- **Download new** (in Downloads) and **Download everything new** (in **Stores**) download without refreshing
  your Library list first, from the stores switched on in [Settings](Settings). A store's **Download** button does
  one store. Each first lists what it would get:
  what's in your library with nothing on disk yet, and the updates the last check found. Untick anything you
  don't want this time; left all ticked, it downloads everything new as before. Where Hoard knows a product's
  files before downloading (an update's new and changed files, and a Booth product's files), **Choose files**
  under it lists them to untick one by one; what you leave out is listed as skipped, and downloaded another time
  if you choose it. **Always skip** leaves a product
  out of every download and sync, including automatic ones, until you choose **Stop skipping** (under **Always
  skipped** in the same list). **Update all** lists the updates the same way.
- **Download** in an item's details (in the Library) downloads just that product, and so do **Update** in
  Downloads and **Download** for several selected products in the Library. A product you always skip still
  downloads when you choose it like this. Hoard goes straight to it on Jinxxy (its item page) and Gumroad (its download
  page). On Booth it still reads your library list (Booth lists the files there), and on itch.io it asks
  itch.io's API.

Progress shows as Hoard works. At the end, a summary lists what's new, what was updated, what was skipped and
anything that couldn't be downloaded, with the reason. A file that fails to download is tried again first (twice,
after a short wait; **Failed downloads** in [Settings](Settings)), unless the store says it isn't there or isn't
yours.

### One thing at a time, in turn

Hoard does one job at a time, but you don't have to wait for it: start a sync, a download, a refresh or a sign-in
while something is running, and it's **queued**, and starts when its turn comes. The same job isn't queued twice.

**Tasks** (next to Library and Downloads) shows what's running, with its progress, what's waiting, and what
finished, newest first, each with how it went (**Done**, **Partly done** when a store couldn't be read or a file
couldn't be downloaded, **Failed** or **Stopped**), how long it took, any problems and its full progress. A sync
that can't read any of your stores (offline, say, or signed out of them all) fails and says which, without trying
to download. The download panel closes by itself a few seconds after a job that went well; one with problems
stays until you close it. Take a
waiting job off the queue with its **×**, or **Clear** them all; **Stop** stops a download or sync within a few
seconds. **Force stop** ends any task at once (a refresh or a sign-in too): it closes the store's browser, the
sign-in window or the browser download straight away, and keeps what finished. What's running also shows beside the store tabs; click it to open Tasks. The list of finished tasks is
kept between runs (the last 60), in `tasks.json`. While your hidden library is locked, hidden products' names are
left out of it.

**Stop** pauses safely within a few seconds, even part way through a big file. A file Hoard downloads itself
(Gumroad, itch.io, and Booth and Jinxxy unless they turn Hoard away) resumes where it stopped next time; one the
browser downloads (Booth or Jinxxy when they do) starts again. Everything that finished is recorded. If the store's
browser has stopped answering, so the job can't notice Stop, Hoard closes that browser after 20 seconds and the
job ends; Hoard's log notes where it was waiting. A job that goes 5 minutes without any progress says so, and
the log notes where it is (**Open logs folder** in [Settings](Settings); see
[Where Hoard keeps things](Where-Hoard-Keeps-Things)).

If a store's browser closes by itself part way through (Jinxxy, or Booth through the browser), Hoard opens it
again and tries the product it was on once more, then carries on. If it keeps closing, Hoard leaves the rest of
that store for next time, with one message saying so, rather than a failure for every product left.

### Closing Hoard while it's working

In Hoard's own window, closing it minimizes Hoard to the taskbar (the Dock on a Mac), and Hoard carries on with
whatever it's doing; click it there to bring the window back. **Quit Hoard** in Settings quits. To have the close
button quit instead, turn off **Closing the window minimizes Hoard to the taskbar** in [Settings](Settings).

With that off, closing Hoard's window (or **Quit Hoard** in Settings) while something is running, or waiting its
turn, asks what to do:

- **Stop it, then close:** what's waiting is taken off the queue, what's running is stopped as **Stop** does,
  and Hoard closes as soon as it has.
- **Minimize, and keep working** (in Hoard's own window): the window goes to the taskbar and Hoard carries on.
- **Close now:** Hoard closes at once, ending any store browser it has open. Use it if stopping takes too long.

While a file downloads, the download panel and Tasks show a progress bar with how much has come in, how fast,
and how long is left (for a file coming through the browser, how much and how fast: the browser doesn't say how
big it is). A download that stops coming in
(the store stops sending it but doesn't hang up) is given up on after 2 minutes with nothing new, and tried again
like any other failed download, so it can't hold up the job, or the jobs waiting after it.

Hoard waits a moment between pages on a store (1 second, `request_delay` in
[`config.json`](Settings#settings-only-in-configjson)) to stay polite.

## Your downloads folder

Downloads go to a `Hoard` folder in your Documents unless you choose another in [Settings](Settings). Inside,
everything is sorted by store, creator and product:

```
Hoard/
  Booth/
    Kitsu Studio/
      Rusk Avatar Base/
        Rusk.unitypackage
        _thumbnail.png
        asset.json
    _manifest.json
  Gumroad/  Jinxxy/  Itch/  Payhip/
  catalog.json
  tags.json
```

- A product keeps its folder even if it's renamed on the store.
- Two products or files whose names clean up alike never share a folder or overwrite each other.
- Names are cleaned before anything is saved, including invisible characters that could make a program's name
  look like a picture's.
- Downloads only ever go inside this folder.

The files Hoard writes there (`catalog.json`, `tags.json`, `asset.json` and each store's `_manifest.json`) are
explained in [Where Hoard keeps things](Where-Hoard-Keeps-Things).

### Library folders on other drives

When your downloads drive fills up, add a folder on another drive in [Settings](Settings), under **Library
folders** (up to 10): in Hoard's window, **Add a folder…** opens your system's folder picker and adds the one you
choose; or type its path. Each is laid out like the downloads folder, a folder per store, and Hoard reads them all as
one library: Downloads, Hoard for Unity, the routine checks and syncing cover every one.

- **A tab for each folder.** Once you've added one, Downloads has a tab for every library folder after the stores'
  tabs, named for the folder and its drive ("Hoard (E:)"), with how many downloads it holds. Choose one to see only
  what's in that folder; choose it again, or **Everything**, to see them all. A folder whose drive isn't connected
  shows its tab dimmed.

- **New downloads** go to the downloads folder. A product already in another folder is kept up to date there.
- **Moving products:** open one in Downloads and, under **Library folder**, choose where and **Move here**; or
  choose **Select**, pick several, and use **Move here** in the selection bar (each move is a task of its own). Hoard
  copies its files, checks each one by size and fingerprint, and only then deletes them where they were; if
  anything goes wrong, it stays where it was. Anything of your own in its folder isn't moved. Follow it in Tasks.
- **A drive that isn't connected:** its products are left out of Downloads until it's back, and a sync skips them
  rather than downloading them again. The routine check says which folders it couldn't check.
- **Removing a folder** in Settings only stops Hoard reading it; its files stay, and come back when you add it again.
- A library folder can't be inside the downloads folder or another library folder, or around one, and can't be
  Hoard's own folder or **Hoard Edits**.

## Updates from creators

A file counts as **updated** when the store offers a new version of it: a different size or file link on
Gumroad or Booth, the same file name under a new label on Jinxxy, or a new name or size shown for the same file
on itch.io. Updated files are downloaded again and listed as updated in the summary. (When the new version has
a different name, the old file stays in the folder too; Hoard never deletes your files.)

### Sets

From 4.0, a set groups products you use together: an avatar, its outfits and hair, and the shaders they need, say.
Make one with **New set** (under **Sets** in the sidebar), or choose **Select**, pick products and use **New set** (a
set of them) or **Add to set**; a product's details list its sets, with **Add** and **×** to take it out.
Choose a set in the sidebar to see just its products; **Rename set** and **Delete set** are beside its filter (deleting
a set leaves its products as they are). Sets are kept in `sets.json` in Hoard's app-data folder, and listed in
`catalog.json` for Hoard for Unity, whose **Import set** imports them in one go (see
[Hoard for Unity](Hoard-for-Unity)).

### Previous versions

From 4.0, when an update replaces a file (the same name, new contents), the old one is kept: it goes to
`_Previous versions/<date and time>/` in the product's own folder. A product's details in Downloads list them under
**Previous versions**, with when each was replaced and **Restore**, which puts it back as the current file and keeps
the one it replaces there in turn, so you can change your mind. Hoard keeps the last one of each file unless you
choose otherwise in [Settings](Settings) (**Previous versions**: none, or the last 1, 2, 3 or 5); older ones are
deleted. They stay out of everything else: the files Hoard checks, Disk space and Hoard for Unity only see the
current files. **Delete downloaded files** deletes a product's previous versions too, and **Move to** takes them
along.

### Checking for updates without downloading

**Check for updates** (in Downloads, under **Updates** on the left) reads your stores the way a download
would, but downloads nothing. It lists each thing you've downloaded that has newer files on its store: files
the creator **added** since you downloaded it, and files they **changed**. They show in the **Updates** view,
and with an **Update** badge on the card. Choose **Update all** there, or open one and choose **Update** to
download just that one. Each item's details also have **Check for updates**, to check only it. In the Library,
an item with updates says **Update available**, with a link to it in Downloads.

What counts as changed depends on what each store shows: a new file, size or file link on Booth and Gumroad,
itch.io's checksum (or else the name, size and date it shows), and on Jinxxy a new or renamed download button.
Jinxxy doesn't show sizes, so a file the creator replaced under the same button name isn't spotted there.
A file you deleted from your computer isn't counted as an update; **Download new** fetches it again. Payhip isn't
checked, because Hoard doesn't download from it.

## Resuming

A download that stops partway leaves a `.part` file, and the next download picks up where it ended. Hoard only
adds to it the part of the file that follows, and only puts the file in place once it's complete, so a file is
never stitched together from two versions: if the creator changed the file in the meantime, it's downloaded
again from the start. Beside the `.part` file Hoard keeps what the store said about the file when it started (its
ETag, date and size, in `.part-info`), and only resumes when the store says it's still that file.

## The Downloads view

- **Search** matches names, creators, tags and file names. Filter by store, creator, tag or **File types**, and
  sort by name, creator, newest or size.
- Open a product to see its files, sizes and folder. **Open folder** opens it in Explorer (or Finder), **Show in
  folder** shows one file there, and **Copy path** copies the folder's location.
- A file that's been moved or deleted since it was downloaded shows as missing. **Rescan** checks the folder again,
  say after you've tidied it yourself.
- **Look inside** (from 4.0, beside each `.unitypackage` and `.zip`) shows what it holds without extracting or
  importing anything. A Unity package's files are listed in their folders (each opens as you choose it), with
  their sizes and the preview pictures Unity keeps inside the package; **Search in it** finds a file wherever it
  is. A `.zip` lists its files, and what each Unity package in it holds. One locked with a password says so (the
  store page usually gives the password), and one that isn't what its name says, or is damaged, says that. Hoard
  keeps what it read (in its `cache` folder) for the 40 files you looked inside most recently, so a second look
  is instant.
- **What it needs** (from 4.0, in a product's details) lists what its packages use that isn't in them: tools such
  as lilToon, Poiyomi Toon (with the version its materials were made with), Modular Avatar, VRCFury, NDMF, Avatar
  Optimizer and the VRChat SDK, each with **Get it** (its own website); other products you've downloaded with Hoard,
  such as the base avatar an outfit is made for, with **View**; and a count of anything else (often a base avatar or
  a paid shader you didn't download with Hoard). Hoard works it out by reading each package once, in the background
  while nothing else is running, and again only when it changes: Unity names everything an asset uses by an ID, so
  the IDs a package's materials and prefabs name, less its own, are what it needs from elsewhere. Hoard knows the
  tools' IDs from their own published releases. Hoard for Unity uses the same list to warn you before importing.

### Checking your downloads

When you choose **Check now**, and as part of the routine check if you've turned it on in Settings, Hoard checks
that your downloads are as it downloaded them: every file there, the size it was downloaded at, and unchanged
since. The first check reads each file in full and keeps its fingerprint (SHA-256) in Hoard's records; later checks read a file again only if its
size or modified time changed, so they're quick. A file downloaded since the last check isn't read until the
next one: it was checked as it came in. It also checks the seal on Hoard's own records.

The Downloads sidebar says when it last checked and what it found, with **Check now**. The check is a task like a
sync, so Tasks lists it, with the files that are missing or changed. A file that changed may be your own edit;
see the next section for editing safely. Delete a changed file and sync to download it again as the store has it.

### Disk space

**Disk space** (beside Downloads, Updates and the rest; from 3.1) lists every download biggest first, with how much
it takes, and how much they take in all. Two ways to narrow it down:

- **Same file kept twice:** files of 1 MB or more you have more than once: in two products (a bundle and the
  product also sold on its own, the same package bought from two stores) or in two library folders. It says how
  much you'd free by keeping one of each. Open a product to see which of its files are elsewhere, and where.
  This uses the fingerprints [Checking your downloads](#checking-your-downloads) keeps, so it reads nothing
  itself: a file the check hasn't fingerprinted yet, or that changed since, isn't compared, and the view says how
  many there are, with **Check now**.
- **Not in any Unity project:** downloads none of your projects use, as Hoard for Unity reports them (see
  [Projects](Hoard-for-Unity#projects-in-hoard)).

Choose **Select** to pick several, then **Move here** (to another library folder), **Archive** (as in the
Library; the files stay) or **Delete downloaded files** (after you confirm; anything of your own in their folders
stays, and what's in your library can be downloaded again). Those work in every view, not just this one. Your
own folders listed in Local where they are aren't counted: they aren't Hoard's to free.

### Changing a download: make an editable copy

Hoard keeps the downloads folder as the stores sent it: a sync replaces a file there that was changed, so edits
made there are lost. To change a texture or anything else, open the product and choose **Make an editable copy**.
Hoard copies its files into a folder of their own, in **Hoard Edits** beside your downloads folder (or the folder
`edits_root` names in `config.json`), and opens it. A read-me there says what it is.

- Hoard never checks, updates or replaces the copy, and each copy is a new folder (`Rusk (2)` beside an earlier
  one), so your edits stay yours.
- Only files that still match what Hoard downloaded are copied. One that was changed or replaced since is left out,
  and the read-me names it, so a file someone else changed isn't passed on as the store's.
- What you add to the copy later (a texture from a website, a tool someone sent you) hasn't been checked by
  Hoard. Be as careful with it as with any download.

## Payhip

Hoard doesn't download from Payhip: its check for automated browsers made that unreliable. Your Payhip purchases
are in the Library, each with **Open on Payhip**, where you download the files from Payhip. **Sync** and
the download buttons leave Payhip out. What earlier versions of Hoard downloaded from Payhip stays in the
`Payhip` folder, and in this view. See [Stores](Stores#payhip).

## itch.io

itch.io's files go in the `Itch` folder. Game builds (files marked for Windows, macOS, Linux or Android) are
skipped unless you turn off **Skip game builds** in [Settings](Settings), and files kept on other websites are
skipped too; both are listed in the summary. See [Stores](Stores#itchio).
