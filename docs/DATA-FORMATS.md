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
- **Links are web addresses.** `url` is `null` or an `http://` or `https://` address.
- **Tags follow the tag rules.** Lower case; letters, marks and digits in any script, plus space and
  `- _ . + & '`; at most 40 characters; never `constructor`, `prototype` or `__proto__`.
- **Files are complete.** Each file is written to a temporary file and swapped in, so a reader never
  sees half of one.

Still, treat them as data from outside your program: check `format` and `version`, and before opening
a path, confirm it resolves inside the download folder. Never run anything named in them.

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

## Your tags (`tags.json` in Hoard's app-data folder)

This one belongs to the tools. Don't write to it; use Hoard's Tags panel. It's private to your user
account, both tools check every entry when they read it, and a damaged copy is kept as
`tags.damaged-<date>.json` rather than overwritten.

## Version history

- **2** (1.6.1): `format` and `version` fields; the promises above are checked before writing.
- **1** (1.5.0): `tags` (yours) and `suggested` in `tags.json`; `tags` and `suggested_tags` per asset.
