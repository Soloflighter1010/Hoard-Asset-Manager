Hoard keeps two sets of things: your downloads, in the folder you choose, and everything else in a private
app-data folder that belongs to your user account.

## Hoard's app-data folder

| Windows | macOS | Linux |
|---|---|---|
| `%LOCALAPPDATA%\Hoard` | `~/Library/Application Support/Hoard` | `~/.local/share/Hoard` |

| What | What it's for |
|---|---|
| `sign-ins/` | Your store sign-ins, one folder per store, encrypted by your operating system. Never share this folder |
| `config.json` | Your settings. See [Settings](Settings) |
| `library.json` | Your library list: names, creators, links and picture addresses for what you own. Its itch.io download page addresses open those pages for anyone, which is one more reason to keep this folder to yourself |
| `tags.json` | Your tags |
| `marks.json` | What you've archived, hidden or removed, and your hidden library's PIN and recovery words, each only as a salted, slow hash |
| `integrity.key` | The key Hoard seals its records with (see [Seals](#seals)). Private to your account |
| `sealed-files.json` | Which records this install has sealed, so a removed seal is noticed |
| `cache/thumbs/` | Product pictures, saved so the library works offline |
| `logs/hoard.log` | What Hoard would print, when it runs without a console: what it read, what it downloaded, and any errors (no passwords, cookies or page contents). Past 2 MB, the older part moves to `hoard.old.log` |
| `window/` | The window's own storage |
| `debug/` | Troubleshooting files, only when you run `debug` or `probe` |

None of this leaves your computer unless you share it yourself.

## Your downloads folder

A `Hoard` folder in your Documents, unless you chose another in [Settings](Settings). Products are in
`<Store>/<Creator>/<Product>` folders, and Hoard keeps its records next to them:

| What | What it's for |
|---|---|
| `catalog.json` | Every downloaded product: store, name, creator, folder, store page, files and tags. Other programs, such as [Hoard for Unity](Hoard-for-Unity), read it |
| `tags.json` | Every tag, and every suggested tag, with the products that have it |
| `<product>/asset.json` | The same details for one product, in its own folder |
| `<product>/_thumbnail.*` | The product's picture |
| `<Store>/_manifest.json` | Hoard's own record of what it downloaded from that store and where. Don't edit it |
| `*.part` | A download that stopped partway. The next download picks up where it ended |
| `Payhip/_download-yourself.html` | Left by versions before 2.5.0, which listed Payhip products for you to download yourself. Hoard doesn't download from Payhip any more (see [Stores](Stores#payhip)), so it no longer writes or reads this page: delete it if you like |

`catalog.json`, `tags.json` and `asset.json` are written for other programs to read, and promise clean text,
plain relative paths and links only to the product's own store. Their exact format is in
[docs/DATA-FORMATS.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/DATA-FORMATS.md).

## Seals

Every record Hoard writes (its library list and marks, and in the downloads folder each store's `_manifest.json`,
`catalog.json`, `tags.json` and every `asset.json`) carries a seal made with `integrity.key`. When a record was changed by something other than
Hoard, the seal shows it, and Hoard:

- tells you, and keeps a copy of the changed file to look at (`_manifest.changed-<date>.json`, say);
- keeps the records, but not their links, and fetches the links from the store again on the next refresh or
  sync (an edited `marks.json` keeps your choices but drops the hidden library's PIN).

`hoard-cli verify` checks every record in the downloads folder, then rebuilds the catalog files. A damaged file
(not valid JSON, say) is kept aside as `<name>.damaged-<date>.json`, and Hoard carries on without it.

## One downloads folder, two computers

Each computer's Hoard seals its records with its own key, so each would treat the other's records as unverified
("saved by Hoard on another computer") and fetch store links again. To share one downloads folder, on a NAS say,
copy `integrity.key` from Hoard's app-data folder on one computer to the same place on the other.

## Backing up, and moving to a new computer

- **Your downloads folder** is ordinary files, with Hoard's records alongside: back it up, or move it, as a whole.
- **Hoard's app-data folder** holds your settings, library list, tags, marks and `integrity.key`. Copy it to the
  same place on a new computer to keep them, with valid seals.
- **Sign-ins don't move.** They're encrypted for your account on the computer they were made on, so on a new
  computer, sign in to your stores again.

If your downloads folder is somewhere else on the new computer, choose it in [Settings](Settings).

## Deleting everything

1. In **Stores**, choose **Sign out of every store**. That ends the sessions where Hoard can and removes every
   store's items from your library.
2. Uninstall Hoard (see [Installing Hoard](Installing-Hoard#uninstalling)).
3. Delete Hoard's app-data folder (above), and your downloads folder if you don't want the files.

The full list, with the reason for each, is in
[PRIVACY.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/PRIVACY.md).
