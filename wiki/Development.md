For working on Hoard itself. How it's built, in depth, is in
[docs/ARCHITECTURE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/ARCHITECTURE.md).

## The repository

| Folder | What's in it |
|---|---|
| `hoard/` | The app, in Python: store readers (`library.py`), downloads (`downloader.py`, `downloads.py`), the local server (`server.py`), sign-ins (`browser.py`), the desktop app (`app.py`), and the safety rules they share (`safety.py`, `egress.py`) |
| `hoard/web/` | The two pages, Library and Downloads, each one HTML file with one inline script, and their fonts |
| `Packages/soloflighter.hoard/` | Hoard for Unity. `Editor/Core` is plain C# with no Unity references, so it can be tested without Unity |
| `tests/` | Every test (see below) |
| `scripts/` | `build_release.py` (the source zip) and `build_vpm.py` (the Unity package) |
| `packaging/` | The apps: PyInstaller spec (Windows and Mac), Inno Setup installer, icons, and `flatpak/` (the Linux Flatpak's manifest and files) |
| `docs/` | Architecture, command line, data formats, and responses to security reviews |
| `wiki/` | This wiki, and its Japanese and Korean translations in `wiki/ja/` and `wiki/ko/`. It's published from here (see [Releasing](Releasing#the-wiki)) |
| `share/` | Hoard's share server, for [short links](Sets#short-links) to shared sets: a Cloudflare Worker (`worker.mjs`), its configuration and its setup guide ([share/README.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/share/README.md)). See [Forks and the share server](#forks-and-the-share-server) |
| `Website/` | The VCC listing's page on GitHub Pages |
| `.github/workflows/` | Checks, releases, the VCC listing and the wiki |

The repository is also a Unity project in VRChat's template-package layout: open it in Unity 2022.3 to work on
Hoard for Unity.

## Running from source

`Hoard.bat` (Windows) or `./run.sh` (macOS, Linux) sets up `.venv` on first run, with every package
hash-checked, then starts Hoard. `Hoard.bat sync`, `./run.sh verify` and so on run commands. See
[Installing Hoard](Installing-Hoard#from-source-windows-macos-linux).

## Tests

```
python -m unittest discover -s tests -v
```

- They need the packages in `requirements.txt`, but no network, no store accounts and no real data: stand-in
  stores and pages run on your computer, and Hoard's data folder is a temporary one.
- The browser tests (`test_pages.py`, `test_readers.py`) need Playwright's Chromium:
  `python -m playwright install chromium`.
- The Unity core tests need Mono (`mono-mcs` and `mono-runtime` on Debian and Ubuntu).
- The share server's tests (`share/worker.test.mjs`, and `test_shortlinks.py`, which runs Hoard against the real
  Worker on your computer) need Node.js 20 or newer.
- Without those, their tests are skipped. GitHub Actions has both, and the **Check** workflow runs everything on
  Ubuntu and Windows for every pull request and every push to `main`, then builds the zips, the Unity package and
  the Windows app, the Mac app and its `.pkg`, and the Flatpak, and runs each app's self-test.

Each security test names the review finding it guards.

## Rules that keep Hoard safe

Tests enforce most of these, so a change that breaks one fails its check.

- **Every store request goes through `hoard/egress.py`**: https only, public addresses only, redirects checked one
  hop at a time, a store's cookies only for that store. No other module makes its own requests.
- **The share server never gets a set's key.** The page locks a set (`lockSet` in `shared.js`) before Hoard
  sends it, and the key only goes in the link, after its `#`. Hoard's requests to the server go through
  `egress.send`.
- **Every request from a page goes through `api()`**, which sends the access key, and every image through
  `keyed()`. Don't call `fetch()` directly.
- **Pages have one inline script and no inline event handlers.** The Content-Security-Policy allows the script
  by its hash, which is worked out as the page is served.
- **Store text is escaped** (`esc()`) and store links pass `safeUrl()` and `storeUrl()` in the page, as well as
  `safe_url()` and `store_link()` in Python.
- **Files are written with `write_file_safely`**, and records Hoard keeps are sealed.
- **Shared code stays identical:** the two pages' tags and settings blocks match, and each piece of security
  code is defined exactly once.
- **Dependencies are hash-locked,** and workflows pin every action to a commit.
- **No invisible formatting characters** anywhere in the project, docs and wiki included.

## Forks and the share server

Short links keep a locked copy of a set on Hoard's share server, `https://hoard-share.furryup.link`, a Cloudflare
Worker deployed from `share/` by Hoard's maintainer. A fork can't change or deploy it: the KV namespace id in
`share/wrangler.toml` only works for whoever is signed in to the Cloudflare account that has it, and only the owner
of `furryup.link` can put a Worker at that address. Nothing in `share/` is a secret.

A fork's own builds still make their short links there, as every copy of Hoard does, within the server's limits (a
set of 48 KB at most, 10 a minute from one address, each gone after 14 days). To run your own server instead, set
it up on your own Cloudflare account and domain, then change its address in `hoard/shortlinks.py` (`SERVER`),
`site/set.js` (`SHARE_SERVER`) and `site/set.html` (`connect-src`), as
[share/README.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/share/README.md#in-a-fork) says.

## Dependencies

`requirements.txt` and `requirements-app.txt` are generated, never edited by hand. Change `requirements.in` or
`requirements-app.in`, then regenerate:

```
pip-compile --generate-hashes --strip-extras --no-emit-index-url requirements.in
uv pip compile requirements-app.in --python-platform x86_64-pc-windows-msvc --python-version 3.12 \
  --generate-hashes --no-header --output-file requirements-app.txt
```

## Writing

Docs, messages and this wiki use plain words: say what happens and what to do, name buttons as they appear, and
keep sentences short.
