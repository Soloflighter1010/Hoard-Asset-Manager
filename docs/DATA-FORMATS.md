# Data formats

Hoard Downloader writes three files that other programs (a Unity plugin, scripts, spreadsheets) are
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
  `gumroad.com`, `jinxxy.com` or `payhip.com`, or a subdomain of it (such as a Booth shop's `<shop>.booth.pm`),
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

A program running as the same user on the same computer (such as a Unity plugin) can read the key and
check the seal: if the `mac` doesn't match, something other than Hoard edited the file, and it shouldn't
be trusted. The key is private to your user account, so programs that can't read it can't produce a valid
seal. When a file has been edited, `python asset_dl.py verify` reports it and rebuilds the catalog files
from Hoard Downloader's own records.

## `catalog.json` (in the download folder)

```json
{
  "format": "hoard-catalog",
  "version": 2,
  "generated_at": "2026-09-23T10:00:00+00:00",
  "assets": [ <asset>, ... ]
}
```

An `<asset>`:

| Field | Type | Meaning |
|---|---|---|
| `store` | string | `Booth`, `Gumroad`, `Jinxxy` or `Payhip` |
| `name` | string | Product name |
| `creator` | string | Creator or shop name |
| `folder` | string | The product's folder, e.g. `Booth/Kitsu Studio/Rusk Avatar Base` |
| `url` | string or null | The product's store page |
| `variants` | string or null | The variant bought, when the store has variants |
| `added` | string or null | When it was first downloaded (ISO 8601) |
| `files` | list of strings | Downloaded files, relative to `folder` |
| `tags` | list of strings | Your tags |
| `suggested_tags` | list of strings | Words shared by several asset names |

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

## Records Hoard Downloader keeps for itself

`_manifest.json` in each store folder records what's downloaded and where. It's sealed the same way.
Other programs shouldn't write to it: when the seal shows it was changed, Hoard Downloader keeps its
records but stops using their store links, keeps a copy of the changed file as
`_manifest.changed-<date>.json`, and fetches the links from the store again on the next sync.

## Your tags (`tags.json` in Hoard's app-data folder)

This one belongs to the tools. Don't write to it; use Hoard's Tags panel. It's private to your user
account, both tools check every entry when they read it, and a damaged copy is kept as
`tags.damaged-<date>.json` rather than overwritten.

## Version history

- **3** (1.6.2): the `integrity` seal; `url` must be an https address on the asset's own store.
- **2** (1.6.1): `format` and `version` fields; the promises above are checked before writing.
- **1** (1.5.0): `tags` (yours) and `suggested` in `tags.json`; `tags` and `suggested_tags` per asset.
