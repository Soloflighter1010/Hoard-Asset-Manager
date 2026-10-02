Hoard keeps local copies of what you own on Booth, Gumroad, Jinxxy and itch.io, and keeps them up to date when
creators update their files. Payhip is listed, not downloaded: see [Payhip](#payhip).

## Downloading

- **Sync** (top right) reads what you own from each store you use, then downloads anything new, as one job.
- **Sync automatically** (in **Settings**, off unless you choose how often: every 6 or 12 hours, once a day or
  once a week) does the same by itself while Hoard is open, counting from your last sync, whoever started it.
  It leaves Payhip out (Payhip needs you there for its bot check), waits for any other job to finish, and
  when you're offline it tries again 15 minutes later instead of marking your stores as unreachable. Its
  progress shows like any sync, and **Stop** stops it. Hoard doesn't sync while it's closed.
- **Download new** (in Downloads) and **Download everything new** (in **Stores**) download without refreshing
  your Library list first. A store's **Download** button does one store.
- **Download a copy** in an item's details (in the Library) downloads just that product, and so do **Update**
  and **Update all** in Downloads. Hoard goes straight to it on Jinxxy (its item page) and Gumroad (its download
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
seconds. What's running also shows beside the store tabs; click it to open Tasks. The list of finished tasks is
kept between runs (the last 60), in `tasks.json`. While your hidden library is locked, hidden products' names are
left out of it.

**Stop** pauses safely within a few seconds, even part way through a big file. A file Hoard downloads itself
(Gumroad, itch.io, and Booth unless it turns Hoard away) resumes where it stopped next time; one the browser
downloads (Jinxxy, and Booth when it does) starts again. Everything that finished is recorded. If the store's
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

When your downloads drive fills up, add a folder on another drive in [Settings](Settings), under **Other library
folders** (up to 10). Each is laid out like the downloads folder, a folder per store, and Hoard reads them all as
one library: Downloads, Hoard for Unity, the routine checks and syncing cover every one.

- **New downloads** go to the downloads folder. A product already in another folder is kept up to date there.
- **Moving a product:** open it in Downloads and, under **Library folder**, choose where and **Move here**. Hoard
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
again from the start.

## The Downloads view

- **Search** matches names, creators, tags and file names. Filter by store, creator, tag or **File types**, and
  sort by name, creator, newest or size.
- Open a product to see its files, sizes and folder. **Open folder** opens it in Explorer (or Finder), **Show in
  folder** shows one file there, and **Copy path** copies the folder's location.
- A file that's been moved or deleted since it was downloaded shows as missing. **Rescan** checks the folder again,
  say after you've tidied it yourself.

### Checking your downloads

While Hoard is open, it checks once a week (Settings, **Check your downloads**) that your downloads are as it
downloaded them: every file there, the size it was downloaded at, and unchanged since. The first check reads each
file in full and keeps its fingerprint (SHA-256) in Hoard's records; later checks read a file again only if its
size or modified time changed, so they're quick. It also checks the seal on Hoard's own records.

The Downloads sidebar says when it last checked and what it found, with **Check now**. The check is a task like a
sync, so Tasks lists it, with the files that are missing or changed. A file that changed may be your own edit;
see the next section for editing safely. Delete a changed file and sync to download it again as the store has it.

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
are in the Library, each with **Open download page**, where you download the files from Payhip. **Sync** and
the download buttons leave Payhip out. What earlier versions of Hoard downloaded from Payhip stays in the
`Payhip` folder, and in this view. See [Stores](Stores#payhip).

## itch.io

itch.io's files go in the `Itch` folder. Game builds (files marked for Windows, macOS, Linux or Android) are
skipped unless you turn off **Skip game builds** in [Settings](Settings), and files kept on other websites are
skipped too; both are listed in the summary. See [Stores](Stores#itchio).
