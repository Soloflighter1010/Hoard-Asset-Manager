# Response to the review of 2.3.1

An outside review (25 September 2026) read the 2.3.1 source and reported five security findings, four bugs,
ten performance findings and one hygiene note. Each was checked against the current code (2.4.1) before
anything changed. For each: what we found, what changed in 2.4.2 (or why not yet), and the tests that keep
it fixed. Tests are in `tests/`; run them with `python -m unittest discover -s tests -v`. The browser tests
(`test_pages.py`, `test_readers.py`) need Playwright's Chromium, and the Unity core tests need Mono; GitHub
Actions installs both, so every test runs on every change.

## Security

### S-01 (High): the local server had no key of its own

**Confirmed.** Actions were accepted from any program on the computer (`127.0.0.1`) that sent JSON, and
reading needed nothing at all. So another program, or another account on a shared computer, could read your
library, or point the downloads folder somewhere else with `POST /api/settings` and read images from there
through `/files/`.

**Fixed.** Every request for data, images or an action now needs an access key made at start-up (32 random
bytes, in memory only), from this computer too (`safety.check_access`).

- The pages send it in the `X-Hoard-Key` header through one function, `api()`. Images, which the browser
  loads by itself, carry it as `?k=` (`keyed()`). It's never a cookie: a browser sends a cookie for
  127.0.0.1 to every program listening there, whatever its port.
- Hoard opens its window (or a browser) with a one-time link, `#enter=...`, which the page trades for the
  key at `/api/enter`. Each link works once, for five minutes. So the key never appears on a browser's
  command line, which other accounts can read on some systems. The key is kept in `localStorage`, which
  belongs to that one address and port.
- Started as a server from the command line, Hoard prints an address with the key itself (`#key=...`). That
  address is also what other devices open in network mode.
- The pages and fonts hold nothing private and need no key. `/api/show`, a second copy of Hoard asking the
  running one to come to the front, still proves itself with the token in the running copy's private file.

**Tests:** `LocalAccess` covers data, actions, images, pages, the one-time links and a new key on each start,
and checks that a cookie or `?key=` in an address never counts. `NetworkMode` covers `check_access` itself.
`Pages.test_every_request_carries_the_key` fails if a page reaches the server any other way. In a real
browser, `test_pages.AccessKey` opens both pages with a one-time link and checks every request, pictures
included, is let in. It also checks that a used link or no key gets nothing, and that `hoard serve`'s address
works. `DesktopApp` checks that the window and the browser are opened with one-time links.

### S-02 (Medium–High): `.unitypackage` files aren't tied to the sealed records

**Confirmed, as missing hardening.** The manifests and catalog are sealed, but the package files themselves
aren't hashed, so a package changed on disk still shows as the product you bought. Importing is always your
choice, through Unity's own import dialog, which lists every file first.

**Not yet.** It needs the downloader to record each file's SHA-256 in the sealed manifest, and the Unity
window to check it before offering **Import**. On the roadmap.

### S-03 (Medium): a hostile package could make the Unity window allocate gigabytes

**Confirmed.** A GNU long-name entry was read into memory at whatever size its header claimed, before the
4,096-byte limit on names applied. The test package claiming an 8 GB name made the old reader try to
allocate it.

**Fixed** in Hoard for Unity 0.1.2. `UnityPackageReader` refuses any name longer than a real path before
allocating anything. It also refuses a package whose headers add up to more than 64 GB, rather than reading
it to the end. Either counts as "not a package", as a damaged one always has.

**Tests:** `tests/unity/CoreTests.cs` (run by `test_unity.UnityCore`) reads two hostile packages made by
`test_unity.tar_header`: an 8 GB long name, and an entry claiming 64 GB.

### S-04 (Low–Medium): Payhip's "download it yourself" page could list an unchecked link

**Confirmed.** Once Payhip blocked the automated browser, later products went onto
`Payhip/_download-yourself.html` before their download link was checked. Escaping stopped a link breaking
the page, but not a `javascript:` or lookalike address becoming a working link.

**Fixed.** Every product's link is checked first, whether it's opened or listed. `write_payhip_todo` checks
each link again and leaves out any that isn't https on Payhip or one of your shops.

**Tests:** `PayhipToDo` runs a sync where Payhip blocks after the first product, with a `javascript:` link
and a lookalike address among the rest.

### S-05 (Low–Medium): the list of sealed files could forget entries

**Confirmed in the code, unreachable in practice.** `remember_sealed` kept the 20,000 alphabetically last
entries, not the newest. But only files that can't be rebuilt are noted (each store's manifest and the
library list), a handful per downloads folder.

**Fixed anyway.** Nothing is dropped.

**Test:** `Seals.test_nothing_sealed_is_forgotten`.

## Bugs

### B-01: an emptied downloads folder kept its old catalog

**Confirmed.** With nothing downloaded, `build_catalog` returned without touching `catalog.json` or
`tags.json`, so they went on listing what was gone (and the Unity window showed it).

**Fixed.** Existing ones are rewritten empty (and sealed). A folder that never had them doesn't get them.

**Tests:** `EmptyLibrary`.

### B-02: products are known by their name

**Confirmed.** Tags, hidden, removed and archived marks, and matching a library item to its download all use
`tag_key` (store plus name without versions or `[labels]`), so "Cool Asset v1" and "Cool Asset v2" are one
product to them. It's by design: the library and the downloader identify products differently (Gumroad's
downloads, for example, are per variant), and the name is what both have.

**Not yet.** Moving to store IDs needs each store's IDs mapped between the two, and existing tags and marks
moved over. That's a data migration to plan and test, not a quick change. On the roadmap.

### B-03: resumed downloads trusted the store's answer

**Confirmed.** A `.part` file was added to on any `206` answer, whatever part it held. On a `416` it was
taken as finished without checking its size, so a smaller new version of a file could leave the old, longer
one in its place.

**Fixed.** `egress.download` only adds the part that follows the `.part` file (`Content-Range` starting where
it ends). It only counts it as finished when the store names that size (`416` with `bytes */<size>`). It
starts again otherwise, and only puts a file in place once it's as long as the store said. Downloads ask for
the file's own bytes (`Accept-Encoding: identity`), so sizes and ranges are exact.

**Tests:** `Resuming` runs against a stand-in store. It covers the right part, the wrong part, no
`Content-Range`, a finished part, a changed file, a `416` without a size, and a short answer, which is kept
and resumed next time.

### B-04: `_download-yourself.html` was written directly

**Confirmed.** **Fixed** with S-04: it's written with `write_file_safely`, inside the downloads folder, like
every other file. **Test:** `PayhipToDo.test_a_planted_link_is_replaced_not_followed`.

## Performance

The review measured these against libraries of 100,000 to 200,000 products. Most people's are far smaller,
but nothing should fall over at that size.

| ID | Finding | 2.4.2 |
|---|---|---|
| P-01 | `/api/assets` and `/api/library` send the whole library | **Confirmed; roadmap.** Paging and filtering on the server is an architecture change for both pages. |
| P-02 | The Downloads page draws every card | **Confirmed; roadmap**, with P-01: only what's on screen should be drawn. |
| P-03 | The Unity window draws every row and keeps every thumbnail | **Fixed** in Hoard for Unity 0.2.0: loaded in the background, only visible rows drawn, pictures read in the background and at most 256 kept. Tests: `CoreTests.cs` (visible rows; a 3,000-product library). |
| P-04 | Tag matching tries every tag on every name | **Confirmed; roadmap** (a word-to-tags index). |
| P-05 | Finding a picture walked the whole library | **Fixed.** A lookup table, made again whenever the list changes. 1,000 pictures in a 100,000-item library: 10.3 s before, 45 ms now. Test: `LibraryLookups`. |
| P-06 | `/api/library` copied the library through JSON | **Fixed.** A snapshot (`Library.snapshot`): 730 ms before, 3 ms now at 100,000 items. Test: `LibraryLookups`. |
| P-07 | The downloads index is rebuilt while holding its lock | **Confirmed; roadmap.** |
| P-08 | Each manifest was rewritten after every file and product | **Fixed.** Saved at most every 10 seconds while downloading (`Manifest.checkpoint`), and whatever's newer is saved when each sync ends, however it ends. A 5,000-product sync with nothing new wrote its 1.4 MB manifest 5,000 times; it now writes it twice. This also fixed a bug found on the way: a file that had just finished when you pressed Stop went unrecorded and was downloaded again. Tests: `ManifestSaves`. |
| P-09 | Every `asset.json` is rewritten on every catalog build | **Confirmed; roadmap.** |
| P-10 | Jinxxy's default-banner cleanup hashes every picture and deletes any two that match | **Confirmed; roadmap.** Two products can share a real picture; only known banners should go. |

## Hygiene

### C-01: `__pycache__` in the source

**Already done.** No compiled files are in the repository, and `.gitignore` excludes `__pycache__/` and
`*.pyc`. The ones the review saw were in the copy it was given, made by running it.
