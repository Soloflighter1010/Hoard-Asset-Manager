# Response to the September 2026 security reviews

Two reviews were received on 23 September 2026: a static review of the repository and a review of how
sign-ins are stored. This page lists each finding and what was done, in version 1.6.0. Every item marked
fixed has an automated test in `tests/test_security.py`.

## Repository review

| ID | Finding | Status |
|---|---|---|
| H-01 | DNS rebinding could bypass the public-address check on image fetches | **Fixed.** The name is looked up once, every address checked, and the connection made to exactly that address; each redirect is checked the same way. The downloader's image fetches use the same connection. |
| H-02 | Network mode sent the access key and library over plain HTTP | **Fixed.** Network mode needs HTTPS (`--tls-cert`, `--tls-key`), or `--plain-http` to say the network is already encrypted (a VPN such as Tailscale). The access cookie is marked `Secure` over HTTPS. |
| H-03 | A Gumroad session cookie could be kept in `config.json` | **Fixed.** Removed. Neither `config.json` nor the `HOARD_GUMROAD_SESSION` variable is read any more; the tool says so if either is present. |
| H-04 | The `requests` version range allowed releases with known vulnerabilities | **Fixed.** Now at least 2.32.4, which also covers CVE-2024-47081. |
| H-05 | Dependencies and the browser build weren't pinned | **Fixed.** `requirements.txt` pins every package, including indirect ones, with hashes, and Setup installs with `--require-hashes`. The Playwright version fixes the Chromium build. |
| H-06 | GitHub Actions referenced by tag | **Fixed.** Pinned to commit SHAs; jobs get only the permissions they need. |
| H-07 | SVG thumbnails were served from the app's own address | **Fixed.** Only raster images are fetched, cached or served, older cached SVGs are removed, and every non-page response is sandboxed. |

## Sign-in review

| ID | Finding | Status |
|---|---|---|
| CRED-01 | Linux without a keyring fell back to unencrypted storage | **Fixed.** Sign-ins aren't saved without a keyring, and after signing in the saved cookies are checked; any saved without the keyring's key are deleted. `allow_unprotected_signins` exists for computers without a desktop and is off by default. |
| CRED-02 | Plain-text Gumroad session cookie | **Fixed**, as H-03. |
| CRED-03 | One browser profile held every store's sign-in | **Fixed.** One profile per store. Existing sign-ins are split between them automatically, keeping only each store's own cookies. |
| CRED-04 | Malware running as the same user | **Reduced and documented.** Not preventable by an app; now an explicit limit in SECURITY.md. Copied cookies are only the store's own, stay in memory, and are cleared when a download run ends. |
| CRED-05 | The program folder could be changed by others | **Reduced.** Setup restricts the program folder to your account. Release zips carry signed build provenance once the repository is public. A signed installer that installs to a protected location is on the roadmap. |
| CRED-06 | Sign-out wasn't verified | **Fixed.** Sign-out asks the store to end the session where possible, deletes the store's profile, checks nothing is left in other profiles, and reports each step. |
| P2 | Security regression tests and threat model | **Done.** `tests/test_security.py` runs on every change; the threat model is in SECURITY.md. |

## Follow-up: tags and data files (1.6.1)

A review of the tag file and the downloader's data files found further gaps, fixed in 1.6.1:

| Finding | Status |
|---|---|
| Paths in `_manifest.json` weren't checked, so a tampered manifest could make a sync or `asset.json` write outside the download folder | **Fixed.** Every path must be plain, relative and resolve inside its folder, through symlinks too; other records are ignored. |
| Store names could carry right-to-left overrides and zero-width characters into file and folder names (`photo\u202egpj.exe` shown as `photoexe.jpg`) | **Fixed.** Removed from names and from all stored text. |
| Writes followed symlinks planted at `catalog.json`, `asset.json`, `.part` files and images | **Fixed.** Files are written through a new temporary file and swapped in. |
| Data files were read without size limits or checks; a damaged `library.json` or manifest stopped the tool | **Fixed.** Read with limits, checked entry by entry, damaged copies kept aside. |
| Tag names allowed any character; the tag file had no limits and was trusted on load | **Fixed.** Strict tag characters and reserved names, product keys checked, limits, private file, checked on load; old names are converted rather than lost. |
| The downloads browser read request bodies of any size | **Fixed.** Actions accept at most 1 MB (imports 80 MB); nested or non-object JSON is refused. |
| Other programs had no stated contract for the catalog files | **Fixed.** `docs/DATA-FORMATS.md`, with `format` and `version` fields; entries are checked before writing. |

## Follow-up: edited links (1.6.2)

| Finding | Status |
|---|---|
| A program could edit a record's `url` in `_manifest.json`, `asset.json` or Hoard's list; any https address was accepted, so **Open on Booth** could lead to a lookalike sign-in page | **Fixed.** Links must be https addresses on the item's own store, checked on read, on write and in the pages. Downloads never used stored links, and still don't. |
| Edits by other programs went unnoticed | **Fixed.** Data files are sealed (HMAC-SHA256, key private to the user account). A changed or unsealed-after-sealing file keeps its data but loses its links until the store is read again, a copy is kept, and the user is told. `verify` checks everything and rebuilds the catalog. |
