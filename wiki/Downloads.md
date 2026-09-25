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
- **Download a copy** in an item's details (in the Library) downloads just that product.

Progress shows as Hoard works. At the end, a summary lists what's new, what was updated, what was skipped and
anything that couldn't be downloaded, with the reason.

**Stop** pauses safely after the file it's on. Anything half-downloaded resumes where it stopped next time,
and everything that finished is recorded. Closing Hoard's window stops a download the same way.

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
