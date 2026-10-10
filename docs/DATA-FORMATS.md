# Data formats

Hoard writes three files in your downloads folder that other programs (a Unity plugin, scripts, spreadsheets) are
welcome to read. This page says what's in them and what they promise, so readers can rely on it.

## What every file promises

These hold for `catalog.json`, `tags.json` and every `asset.json`. The downloader checks each entry
against them (`validate_catalog_entry`) before writing, and leaves out any entry that fails:

- **Text is clean.** Names, creators and variants contain no control characters and no invisible
  formatting characters (such as right-to-left overrides or zero-width spaces), use single spaces, and
  are at most 300 characters (creators 200).
- **Paths are plain and relative.** `folder` and every entry in `files` use `/`, never start with `/`,
  and have no `..`, `.` or empty parts, no drive letters, no `:` and none of `<>"\|?*`. `folder` is
  relative to the download folder; `files` are relative to `folder`.
- **Links lead to the store.** `url` is `null` or an `https://` address on the asset's own store: `booth.pm`,
  `gumroad.com`, `jinxxy.com`, `payhip.com` or `itch.io`, or a subdomain of it (such as a Booth shop's
  `<shop>.booth.pm`, or an itch.io creator's `<creator>.itch.io`),
  with no user name, password or port. These links are for people to open; Hoard never downloads from them.
- **They're sealed.** Each file carries an `integrity` field (below), so an edit made by any other program
  is detectable.
- **Tags follow the tag rules.** Lower case; letters, marks and digits in any script, plus space and
  `- _ . + & '`; at most 40 characters; never `constructor`, `prototype` or `__proto__`.
- **Files are complete.** Each file is written to a temporary file and swapped in, so a reader never
  sees half of one.

Still, treat them as data from outside your program: check `format` and `version`, check the seal if you
can, re-check `url` against the rule above before showing it as a link, and before opening a path,
confirm it resolves inside the download folder. Never run anything named in them.

## The seal

```json
"integrity": { "alg": "HMAC-SHA256", "key_id": "<16 hex digits>", "mac": "<64 hex digits>" }
```

`mac` is HMAC-SHA256, keyed with the 32 bytes hex-encoded in `integrity.key` in Hoard's app-data folder
(`%LOCALAPPDATA%\Hoard` on Windows, `~/Library/Application Support/Hoard` on macOS, `~/.local/share/Hoard`
on Linux), over the file's JSON with the `integrity` field removed, serialised with keys sorted by code
point, no spaces (`,` and `:` separators), non-ASCII characters written as UTF-8 rather than escaped, and
encoded as UTF-8. `key_id` is the first 16 hex digits of the key's SHA-256.

A program running as the same user on the same computer can read the key and check the seal. Hoard for
Unity (`Packages/soloflighter.hoard`) does: its C# `Seal` class is tested against files sealed by this code. if the `mac` doesn't match, something other than Hoard edited the file, and it shouldn't
be trusted. The key is private to your user account, so programs that can't read it can't produce a valid
seal. When a file has been edited, `Hoard.bat verify` (or `./run.sh verify`) reports it and rebuilds the catalog files
from Hoard's own records.

## `catalog.json` (in the download folder)

```json
{
  "format": "hoard-catalog",
  "version": 3,
  "generated_at": "2026-09-23T10:00:00+00:00",
  "assets": [ <asset>, ... ]
}
```

An `<asset>`:

| Field | Type | Meaning |
|---|---|---|
| `store` | string | `Booth`, `Gumroad`, `Jinxxy`, `Payhip`, `Itch` (itch.io) or `Local` (your own packages, from 3.0). Skip an entry with a store you don't know: later versions may add stores |
| `name` | string | Product name |
| `creator` | string | Creator or shop name |
| `folder` | string | The product's folder, e.g. `Booth/Kitsu Studio/Rusk Avatar Base` |
| `url` | string or null | The product's store page |
| `variants` | string or null | The variant bought, when the store has variants |
| `added` | string or null | When it was first downloaded (ISO 8601) |
| `files` | list of strings | Downloaded files, relative to `folder` |
| `tags` | list of strings | Your tags |
| `suggested_tags` | list of strings | Words shared by several asset names |
| `location` | string, only on some `Local` entries | A Local item listed where it is: its own folder, as a full path written as the system writes it. `files` are relative to it, and `folder` (`Local/_linked/<id>`) is only a name. Believe it only when the catalog's seal is this computer's; otherwise skip the entry |
| `note` | string, only on `Local` entries | Who or what it's for, as you wrote it |
| `library` | string, only on some entries (version 4) | A product in another of your library folders (another drive, say): that folder, as a full path written as the system writes it. `folder` and `files` are relative to it instead of the download folder. Never on an entry with `location`. Believe it only when the catalog's seal is this computer's; otherwise skip the entry |

| `needs` | list, only on some entries (4.0) | What the product's packages use that isn't in them (What it needs): see below |

`version` is 4 when any entry has `library`, and 3 otherwise, so a reader that doesn't know `library` (Hoard for
Unity before 0.5.0) still reads a library that's all in one folder.

Each of `needs` (at most 30) is one of:

- **A tool:** `{"kind": "tool", "name": "Poiyomi Toon", "url": "https://www.poiyomi.com/", "versions": ["8.1"],
  "guids": [...]}`. `url` is the tool's own website, one of those in `hoard/known_tools.json`; `versions` (each
  `major.minor`) says which versions' files are named, when the tool's versions have files of their own.
- **Another product you've downloaded:** `{"kind": "product", "name", "creator", "store", "folder", "guids"}`, where
  `store` and `folder` are as in an `<asset>`: the entry it names.

`guids` (1 to 50, each 32 lowercase hex digits) are GUIDs the product's materials, prefabs and other text assets name
and the tool or product has. A need is met in a Unity project when every one of them is there. GUIDs nothing Hoard
knows has aren't listed. A reader that doesn't know `needs` (Hoard for Unity before 0.8.0) ignores it, so the version
doesn't change.

## `asset.json` (in each product's folder)

The same fields as one `<asset>` above, plus `"format": "hoard-asset"` and `"version": 2`.

## `tags.json` (in the download folder)

```json
{
  "format": "hoard-tags",
  "version": 2,
  "generated_at": "...",
  "total_assets": 612,
  "tags":      { "<your tag>":   { "count": 12, "assets": ["<folder>", ...] } },
  "suggested": { "<suggestion>": { "count": 30, "assets": ["<folder>", ...] } }
}
```

## `marks.json` (in Hoard's app-data folder)

Your archive, hidden and removed choices, sealed like the other files. Each of `archived`, `unarchived`,
`removed` and `hidden` is a sorted list of product keys (the same keys tags use, such as
`booth:rusk`), so a choice applies in the Library and in Downloads. `pin` holds the hidden library's
PIN as an scrypt hash with its own salt and parameters, `recovery` holds the recovery phrase the same
way (never the words themselves), and `failures` and `wait_until` hold the
lockout after wrong guesses. If the file is changed outside Hoard, the choices are kept but the PIN is
dropped. It's a private record, not a promise to other tools.

## Records Hoard keeps for itself

`package-needs.json` in Hoard's app-data folder records, for each downloaded `.unitypackage` (and each one in a
`.zip`), the GUIDs of its assets (`own`) and the other GUIDs its text assets name (`refs`), with the file's size and
time, so it's read again only when it changes. It's sealed; one that isn't as Hoard sealed it is read again from
the packages.

`_manifest.json` in each store folder records what's downloaded and where. It's sealed the same way.
Other programs shouldn't write to it: when the seal shows it was changed, Hoard keeps its
records but stops using their store links, keeps a copy of the changed file as
`_manifest.changed-<date>.json`, and fetches the links from the store again on the next sync.

## Your tags (`tags.json` in Hoard's app-data folder)

This one belongs to Hoard. Don't write to it; use the Tags panel. It's private to your user
account, Hoard check every entry when they read it, and a damaged copy is kept as
`tags.damaged-<date>.json` rather than overwritten.

## `projects/<id>.json` (in Hoard's app-data folder)

Written by Hoard for Unity (0.4.0 and newer), one per Unity project, for Hoard's **Projects** (issue #86). `<id>` is
the first 16 hex digits of the SHA-256 of the project's full path. Hoard reads every field as untrusted: it checks
each one as it checks `catalog.json` entries, and leaves out what doesn't pass.

```json
{"format": "hoard-project", "version": 1, "name": "My Avatar", "path": "C:\\Unity\\My Avatar", "unity": "2022.3.22f1",
 "updated": "2026-10-01T12:00:00+00:00",
 "assets": [{"store": "Booth", "name": "...", "creator": "...", "folder": "Booth/...", "url": "https://booth.pm/...",
             "status": "yes"}],
 "credits": {"title": "Assets used", "style": "List", "left_out": ["Booth/<name>"],
             "added": [{"name": "...", "creator": "...", "url": "https://..."}]}}
```

`status` is `yes` (a package of it is all in the project), `partly`, or `imported` (only the project's import log
says so). `style` is `List`, `Markdown` or `ByCreator`. `folder` matches the product's `folder` in `catalog.json`.

## Version history

- **4** or **3**, still, in 4.0: `needs`, which readers that don't know it ignore.
- **4** (3.0): `library`, for products in another library folder. Only written when there are some; otherwise
  the catalog is still version 3.
- **3**, still, in 3.0: `Local` entries, with `location` and `note`. Readers that skip stores they don't know
  carry on as before.

- **3**, still, in 2.5.0: a new store, `Itch` (itch.io). Nothing else changed, so the version didn't; readers
  that skip stores they don't know carry on as before.
- **3** (1.6.2): the `integrity` seal; `url` must be an https address on the asset's own store.
- **2** (1.6.1): `format` and `version` fields; the promises above are checked before writing.
- **1** (1.5.0): `tags` (yours) and `suggested` in `tags.json`; `tags` and `suggested_tags` per asset.
