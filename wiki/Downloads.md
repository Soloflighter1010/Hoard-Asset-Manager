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
finished, newest first, each with how it went, how long it took, any problems and its full progress. Take a
waiting job off the queue with its **×**, or **Clear** them all; **Stop** stops a download or sync within a few
seconds. What's running also shows beside the store tabs; click it to open Tasks. The list of finished tasks is
kept between runs (the last 60), in `tasks.json`. While your hidden library is locked, hidden products' names are
left out of it.

**Stop** pauses safely within a few seconds, even part way through a big file. A file Hoard downloads itself
(Gumroad, itch.io, and Booth unless it turns Hoard away) resumes where it stopped next time; one the browser
downloads (Jinxxy, and Booth when it does) starts again. Everything that finished is recorded. If the store's
browser has stopped answering, so the job can't notice Stop, Hoard closes that browser after 20 seconds and the
job ends; `hoard.log` notes where it was waiting. A job that goes 5 minutes without any progress says so, and
`hoard.log` notes where it is.

If a store's browser closes by itself part way through (Jinxxy, or Booth through the browser), Hoard opens it
again and tries the product it was on once more, then carries on. If it keeps closing, Hoard leaves the rest of
that store for next time, with one message saying so, rather than a failure for every product left.

### Closing Hoard while it's working

Closing Hoard's window (or **Quit Hoard** in Settings) while something is running, or waiting its turn, asks
what to do:

- **Stop it, then close:** what's waiting is taken off the queue, what's running is stopped as **Stop** does,
  and Hoard closes as soon as it has.
- **Keep working in the background** (in Hoard's own window): the window hides and Hoard carries on. Open Hoard
  again to bring the window back. To always do this when the window closes, turn on **Keep Hoard running when
  its window is closed** in [Settings](Settings).
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

## Payhip

Hoard doesn't download from Payhip: its check for automated browsers made that unreliable. Your Payhip purchases
are in the Library, each with **Open download page**, where you download the files from Payhip. **Sync** and
the download buttons leave Payhip out. What earlier versions of Hoard downloaded from Payhip stays in the
`Payhip` folder, and in this view. See [Stores](Stores#payhip).

## itch.io

itch.io's files go in the `Itch` folder. Game builds (files marked for Windows, macOS, Linux or Android) are
skipped unless you turn off **Skip game builds** in [Settings](Settings), and files kept on other websites are
skipped too; both are listed in the summary. See [Stores](Stores#itchio).
