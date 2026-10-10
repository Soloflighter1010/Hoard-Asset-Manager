Hoard keeps two sets of things: your downloads, in the folder you choose, and everything else in a private
app-data folder that belongs to your user account.

## Hoard's app-data folder

| Windows | macOS | Linux |
|---|---|---|
| `%LOCALAPPDATA%\Hoard` | `~/Library/Application Support/Hoard` | `~/.local/share/Hoard` |

The Linux Flatpak uses `~/.local/share/Hoard` too (not a folder of its own under `~/.var/app`), so it shares a
library with Hoard run from source, and Hoard for Unity finds it. Only its copy of Hoard's browser is its own, in
`~/.var/app/io.github.soloflighter1010.Hoard/cache`.

| What | What it's for |
|---|---|
| `sign-ins/` | Your store sign-ins, one folder per store, encrypted by your operating system. Never share this folder |
| `config.json` | Your settings. See [Settings](Settings) |
| `library.json` | Your library list: names, creators, links and picture addresses for what you own |
| `keys/` | On Windows: your itch.io API key, encrypted by your Windows account. (On a Mac it's in your Keychain, on Linux in your keyring.) See [Stores](Stores#itchio) |
| `tags.json` | Your tags |
| `picture-looks.json` | How product pictures look (a 64-bit hash of each, by the picture's SHA-256), so copies of one product saved differently by two stores stack. See [Library](Library#finding-things) |
| `asset-updates.json` | What the last **Check for updates** found: for each thing you've downloaded, the files its store has that you don't yet. See [Downloads](Downloads#checking-for-updates-without-downloading) |
| `marks.json` | What you've archived, hidden or removed, and your hidden library's PIN and recovery words, each only as a salted, slow hash |
| `projects/` | One small report per Unity project you've opened Hoard's window in (Hoard for Unity 0.4.0 and newer): its name and folder, which of your assets it uses, and its credits settings. **Projects** in Hoard shows them; **Forget this project** deletes one. See [Hoard for Unity](Hoard-for-Unity#projects-in-hoard) |
| `library_folders.json` | Which products each of your other library folders held when Hoard last read it, so a sync leaves them alone while that drive isn't connected. See [Downloads](Downloads#library-folders-on-other-drives) |
| `integrity.key` | The key Hoard seals its records with (see [Seals](#seals)). Private to your account |
| `sealed-files.json` | Which records this install has sealed, so a removed seal is noticed |
| `cache/thumbs/` | Product pictures, saved so the library works offline |
| `cache/inside/` | What **Look inside** read from a package or zip, with its previews, for the 40 you looked inside most recently (4.0). See [Downloads](Downloads#the-downloads-view) |
| `package-needs.json` | For each package you've downloaded, the IDs of what's in it and of what it uses, so **What it needs** knows without reading it again (4.0) |
| `logs/hoard-<date>_<time>.log` | What Hoard would print, when it runs without a console: what it read, what it downloaded, and any errors (no passwords, cookies or page contents). One for each time Hoard starts, kept for 30 days (the newest 10 whatever their age); a run that writes more than 20 MB carries on in `-part2`. **Open logs folder** in Settings opens this folder. (Before 2.9.2, one `hoard.log` for every run.) |
| `diagnostics/incidents.jsonl` | Private local record of recent errors and crash tracebacks, used to build support reports; it is never sent automatically |
| `window/` | The window's own storage |
| `window-place.json` | The window's size and place when you last closed it, and whether it was maximized, so it opens there again. Delete it to open at the usual size, centred |
| `tasks.json` | The Tasks window's list of finished jobs (the last 60): what each did, how it went, and its progress. Delete it, or **Clear** in Tasks, to empty the list |
| `sync.json` | When the last sync started |
| `routine.json` | When the routine check last ran, so it knows when the next is due, and how much it found that you haven't looked at yet |
| `update.json` | When Hoard last checked for updates, and the newest version it found |
| `updates/` | A new version's installer, downloaded and checked, while Hoard updates. Deleted once the update is installed |
| `debug/` | Troubleshooting files, only when you run `debug` or `probe` |

None of this leaves your computer unless you share it yourself.

## Support reports

When you choose **Create support report**, Hoard writes a sanitized ZIP to `Documents/Hoard/Support Reports` and opens the folder/selects the new report. This export folder is outside Hoard's private app-data so the ZIP is easy to find and attach. The raw logs, sign-ins, library file and other private app-data files are not copied into the ZIP. Review the report before attaching it to a public issue.

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
2. Uninstall Hoard (see [Installing Hoard](Installing-Hoard#uninstalling): on a Mac, drag it from Applications
   to the Trash; the Flatpak, `flatpak uninstall --delete-data io.github.soloflighter1010.Hoard`).
3. Delete Hoard's app-data folder (above), and your downloads folder if you don't want the files.
4. Hoard's own browser, if it downloaded one: `%LOCALAPPDATA%\ms-playwright` on Windows,
   `~/Library/Caches/ms-playwright` on a Mac, `~/.cache/ms-playwright` on Linux (the Flatpak's goes with
   `--delete-data`). Other programs that use Playwright may share it.

The full list, with the reason for each, is in
[PRIVACY.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/PRIVACY.md).
