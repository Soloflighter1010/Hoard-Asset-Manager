Hoard keeps local copies of what you own, and keeps them up to date when creators update their files.

## Downloading

- **Sync** (top right) reads what you own from each store you use, then downloads anything new, as one job.
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
  Gumroad/  Jinxxy/  Payhip/
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
Gumroad or Booth, or the same file name under a new label on Jinxxy or Payhip. Updated files are downloaded
again, replacing the old ones, and listed as updated in the summary.

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

Payhip sometimes won't let an automated browser download. Products Hoard couldn't get are listed in
`Payhip/_download-yourself.html`, with each download page and the folder its files go in. Save them there
yourself, and the next sync records them. See [Stores](Stores#payhip).
