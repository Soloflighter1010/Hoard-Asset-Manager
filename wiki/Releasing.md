For maintainers. Every release is built by GitHub Actions from this repository.

## Hoard

1. Raise `__version__` in `hoard/__init__.py`, and add a `## <version>` section at the top of `CHANGELOG.md`. That
   section becomes the release's notes, and the build refuses a version without one. Add the version to the
   top of `<releases>` in `packaging/flatpak/io.github.soloflighter1010.Hoard.metainfo.xml` too (software
   centres show it; a test checks it's there).
2. Merge to `main`, and wait for **Check** to pass.
3. In **Actions**, open **Release**, choose **Run workflow** on `main`, and enter the tag, with its `v`
   (`v2.8.0`). If the tag doesn't exist yet, the workflow makes it on `main`'s latest commit, after checking it
   matches `__version__`. Pushing the tag yourself does the same.

The **Release** workflow then:

1. builds the source zip and its checksums, signs its build provenance, and makes the release **as a draft**;
2. builds the Windows app (PyInstaller), runs its self-test, builds the installer (Inno Setup), and attaches the
   installer, the Windows zip and their checksums;
3. builds the Mac app twice, on an Apple Silicon and an Intel runner (PyInstaller, then `Hoard.app` in a `.pkg`
   by `scripts/build_macos_pkg.sh`), runs its self-test, and attaches
   `Hoard-<version>-macos-apple-silicon.pkg` and `Hoard-<version>-macos-intel.pkg` with their checksums;
4. builds the Flatpak (flatpak-builder, in Flathub's GNOME 51 container; its build checks Hoard's window support
   and runs the self-test in the sandbox), and attaches `Hoard-<version>-linux-x86_64.flatpak` and
   `SHA256SUMS-linux.txt`;
5. has VirusTotal scan every file people download (`scripts/scan_release_virustotal.py`), and adds each file's
   result and report link to the release notes;
6. publishes the release, once every file is on it and none was flagged.

Every file has signed build provenance (`gh attestation verify`). The Mac packages aren't signed or notarized by
Apple, and the Windows installer isn't code-signed: see [Installing Hoard](Installing-Hoard) for what users see.

### Releases are immutable

This repository has immutable releases turned on: once a release is published, nothing can be added to or
changed in it, and its tag can never be used for another release, even after deleting the release. That's why
the release stays a draft until every file is attached.

- **A run failed partway?** It leaves a draft. Fix the problem, then run the workflow again with the same tag: it
  fills in the draft and publishes it.
- **VirusTotal flagged a file?** The release stays a draft, and its notes list each file's result with a link to
  VirusTotal's report. Unsigned apps built with PyInstaller are sometimes flagged by one or two engines by
  mistake. Open the report: if it's a false positive (a generic or heuristic name, from an engine or two), run the
  workflow again for the tag with **Publish even if VirusTotal flags a file** ticked; it scans again, notes that
  it was checked by hand, and publishes. If it looks real, don't publish: find out why first. (Reporting a false
  positive to the engine's maker clears it for later releases.)

### VirusTotal

Once, when setting the repository up: make a free account at [virustotal.com](https://www.virustotal.com/), copy
the API key from your profile, and add it as the repository secret `VT_API_KEY` (**Settings › Secrets and
variables › Actions › New repository secret**). Without it the release stays a draft, saying so.

The scan uses VirusTotal's public API (4 requests a minute, 500 a day): a file VirusTotal already knows is only
looked up, a new one is uploaded and its scan waited for, so a release takes about 10 to 20 minutes more. Only the
scan step sees the key. Files sent to VirusTotal are shared with its security partners, as with any upload there;
they're the same files the release makes public.
- **Published something broken?** Don't delete it expecting to reuse the version. Raise the version and release
  again (2.4.0 was re-released as 2.4.1 this way).

### The Mac's and the Flatpak's dependencies

Like `requirements-app.txt` for Windows, `requirements-mac.txt` and `requirements-flatpak.txt` are locked with
hashes, and made from their `.in` files by the `uv pip compile` command at the top of each. They're constrained
to `requirements.txt` and `requirements-app.txt`, so every Hoard runs the same versions (a test checks). The
Flatpak builds offline, so after regenerating `requirements-flatpak.txt`, run `python scripts/flatpak_deps.py`
to rewrite `packaging/flatpak/python3-deps.json` (each file's address and hash).

### Flathub

`packaging/flatpak/io.github.soloflighter1010.Hoard.yml` is written to Flathub's rules (a stable runtime, every
source pinned by hash, a narrow sandbox, AppStream metainfo), so it can be submitted there. A Flathub submission
lives in its own repository, with the manifest's `hoard` source changed from this folder to a `git` source at
the release's tag and commit.

## Hoard for Unity

1. Raise `version` in `Packages/soloflighter.hoard/package.json`, and add a `## <version>` section to
   `Packages/soloflighter.hoard/CHANGELOG.md`.
2. Merge to `main`.
3. In **Actions**, open **Build Release** and choose **Run workflow**. It tags `unity-v<version>` itself, tests the
   package's core, and publishes the `.zip`, `.unitypackage` and `package.json`.
4. **Build Repo Listing** runs after it, rebuilding the VCC listing from every release and publishing it to GitHub
   Pages (https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json).

Once, when setting the repository up: add the repository variable `PACKAGE_NAME` = `soloflighter.hoard`
(**Settings › Secrets and variables › Actions › Variables**), and set **Settings › Pages › Source** to **GitHub
Actions**. Pages only deploys from `main`, so a listing build started by a release event is re-run on `main`.

## The website

Hoard's website (https://soloflighter1010.github.io/Hoard-Asset-Manager/) is the `site/` folder, deployed by
**Build Repo Listing** with the VCC listing: the site at the root, VRChat's listing page at `vcc/`, and
`index.json` (and the older `vpm/index.json`) where VCC finds them. A change to `site/` reaching `main` deploys
it. It loads nothing from other sites (a test checks); its download buttons ask GitHub's API for the latest
release's files, and open the releases page without it. Its fonts are the app's, cut down to Latin characters
with `pyftsubset` (fontTools), and its screenshot is of the app with a sample library.

## The wiki

The wiki is written in the repository's `wiki/` folder and reviewed like code. When a change to `wiki/` reaches
`main`, the **Wiki** workflow publishes it, replacing every page, so edit the pages there, not on GitHub.

Once, before the first publish: open the repository's **Wiki** tab and save any first page. GitHub only creates
the wiki's storage when its first page is saved; the workflow then replaces it.

## Checks on every change

**Check** runs for every pull request and every push to `main`: the tests on Ubuntu and Windows (browser tests
included, and the Unity core on Ubuntu), the release zips, the Unity package, the Windows app with its
self-test, the Mac app (Apple Silicon) with its self-test and `.pkg`, and the Flatpak. See [Development](Development#tests).
