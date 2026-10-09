For maintainers. Every release is built by GitHub Actions from this repository.

## Hoard

1. Raise `__version__` in `hoard/__init__.py`, and add a `## <version>` section at the top of `CHANGELOG.md`. That
   section becomes the release's notes, and the build refuses a version without one. The Flatpak's metainfo
   lists the version by itself: its build adds it to the top of `<releases>` (`scripts/flatpak_metainfo.py`,
   with the section's first sentence as its summary), so there's no need to edit that file.
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

Every file has signed build provenance (`gh attestation verify`). The Windows programs and installer are
code-signed (see **Code signing (Windows)** below); the Mac packages aren't signed or notarized by Apple: see
[Installing Hoard](Installing-Hoard) for what users see.

### Betas

A beta is a release of the next version before it's finished, for testers, from this same repository. Tag it
`v<version>-beta.<n>`: `v3.1.0-beta.1`, then `v3.1.0-beta.2`, and `v3.1.0` when it's done.

1. Set `__version__ = "3.1.0-beta.1"`, and add a `## 3.1.0-beta.1` section to `CHANGELOG.md` (the beta's notes on
   GitHub; the website's What's new page leaves beta sections out). The Flatpak's build lists it in the metainfo
   as a development release by itself.
2. Run **Release** with the tag `v3.1.0-beta.1`, as above. The release is titled **Hoard 3.1.0 beta 1** and published
   as a **pre-release**, which never becomes Latest, so the website's download buttons, and everyone else's update
   checks, stay on the last release.
3. Testers turn on **Get beta updates** (Settings, under Updates). Hoard then offers each newer beta, and the
   finished `3.1.0` when it's out. The Windows app installs a beta itself, as it does a release.

When `3.1.0` is ready, fold the beta sections of `CHANGELOG.md` into one `## 3.1.0` and release it as usual.

The Windows and Mac builds take numbers-only versions for the parts of the system that need them (a beta
`3.1.0-beta.1` is `3.1.0` there); the file names and Hoard itself say the whole version.

### Kinds of release, and Latest

Every kind of release shares this repository's **Releases** page, told apart by its tag and title
(`scripts/release_info.py`):

| Tag | Title | Status |
|---|---|---|
| `v3.1.0` | Hoard 3.1.0 | a release, and **Latest** |
| `v3.1.0-beta.2` | Hoard 3.1.0 beta 2 | a pre-release |
| `unity-v0.6.0` | Hoard for Unity 0.6.0 | a release, never Latest |
| `unity-v0.6.0-beta.1` | Hoard for Unity 0.6.0 beta 1 | a pre-release |

Latest always stays on the newest release of the app: the website's download buttons and the README's badge
follow it. The release workflows set all of this themselves. To bring older releases in line (titles, pre-release
status, Latest), run **Actions › Tidy releases › Run workflow**: unticked, it only lists what it would change in
the run's log; ticked, it changes it. It never touches a release's files, notes or tag. (It's
`scripts/tidy_releases.py`: on your own computer, run it as it is to see the changes, and with `--apply` and
`GH_TOKEN` set, from `gh auth token`, to make them.)

### Releases are immutable

This repository has immutable releases turned on: once a release is published, no file can be added to it or
changed, and its tag can never be used for another release, even after deleting the release. (Its title, notes and
pre-release status can still be edited.) That's why
the release stays a draft until every file is attached.

- **A build failed?** The run cleans up after itself: it deletes the draft (never published), and the tag too
  when the run made it. Fix the problem on `main`, then run the workflow again with the same tag. (A tag you pushed
  yourself is left for you to delete, under **Code › Tags**, or release the next version.) To re-run only the
  failed jobs instead, tick **If a build fails, keep its draft and tag** when you start the run. The workflow
  also checks the Flatpak's metainfo before building anything, so a broken one stops it at once.
- **VirusTotal flagged a file?** The release stays a draft, and its notes list each file's result with a link to
  VirusTotal's report. Unsigned apps built with PyInstaller are sometimes flagged by one or two engines by
  mistake. Open the report: if it's a false positive (a generic or heuristic name, from an engine or two), run the
  workflow again for the tag with **Publish even if VirusTotal flags a file** ticked; it scans again, notes that
  it was checked by hand, and publishes. If it looks real, don't publish: find out why first. Report a false
  positive to the engine's maker, which clears it: Windows won't let a browser download a file Microsoft's engine
  flags, so the run keeps the flagged files under **Artifacts** (`virustotal-flagged-files`), in a zip with the
  password `infected`. Upload that zip as it is (for Microsoft, at
  [microsoft.com/wdsi/filesubmission](https://www.microsoft.com/en-us/wdsi/filesubmission), as a software
  developer), and give the password where it asks.

### VirusTotal

Once, when setting the repository up: make a free account at [virustotal.com](https://www.virustotal.com/), copy
the API key from your profile, and add it as the repository secret `VT_API_KEY` (**Settings › Secrets and
variables › Actions › New repository secret**). Without it the release stays a draft, saying so.

The scan uses VirusTotal's public API (4 requests a minute, 500 a day): a file VirusTotal already knows is only
looked up, and new ones are all uploaded, then their scans waited for together, so a release takes about 10 to 20
minutes more. The log says what it's doing as it goes (`Waiting for VirusTotal (6 min so far): … queued`): a busy
day's queue can be slow, so leave it running. It waits up to 40 minutes; if VirusTotal still hasn't finished, the
job fails saying which files, and **Re-run failed jobs** later picks up the finished scans without sending anything
again. Only the
scan step sees the key. Files sent to VirusTotal are shared with its security partners, as with any upload there;
they're the same files the release makes public.
- **Published something broken?** Don't delete it expecting to reuse the version. Raise the version and release
  again (2.4.0 was re-released as 2.4.1 this way).

### Code signing (Windows)

`Hoard.exe`, `hoard-cli.exe` and the setup are signed with **Azure Artifact Signing** (Microsoft's Trusted
Signing), so Windows and Defender know they're Hoard's. Signing happens in the release's Windows job, only where
it's set up: a fork, or this repository before it's set up, builds unsigned, as before. The setup's uninstaller
isn't signed yet.

Once, when setting it up (an Azure subscription with a payment method; the Basic plan is about $10 a month):

1. In the [Azure portal](https://portal.azure.com), create an **Artifact Signing account** (search "Artifact
   Signing" or "Trusted Signing"), in a region near you, on the Basic plan. Note its **name** and its
   **endpoint** (on its Overview, such as `https://eus.codesigning.azure.net/`).
2. In the account, under **Identity validations**, start a **Public** validation for yourself as an individual,
   and finish Microsoft's identity check. It can take a few days. (Before you can, you may need to give your own
   Azure user the **Artifact Signing Identity Verifier** role on the account, under **Access control (IAM)**.)
3. Once validated, under **Certificate profiles**, create a **Public Trust** profile using that validation, and
   note its **name**.
4. Let GitHub sign in without a password: in **Microsoft Entra ID › App registrations**, register an app (say
   "Hoard release signing"). In it, under **Certificates & secrets › Federated credentials**, add one for
   **GitHub Actions deploying Azure resources**: organisation `Soloflighter1010`, repository
   `Hoard-Asset-Manager`, entity **Environment**, environment `release-signing`.
5. On the signing account, under **Access control (IAM)**, give that app the **Artifact Signing Certificate Profile
   Signer** role.
6. In this repository, under **Settings › Environments**, open (or create) `release-signing`, and add:
   - secrets `AZURE_CLIENT_ID` (the app's **Application (client) ID**), `AZURE_TENANT_ID` (its **Directory
     (tenant) ID**) and `AZURE_SUBSCRIPTION_ID` (your subscription's ID);
   - variables `AZURE_SIGNING_ENDPOINT`, `AZURE_SIGNING_ACCOUNT` and `AZURE_SIGNING_PROFILE` (from steps 1 and 3).

   Optionally, under the environment's **Deployment branches and tags**, allow only `main` and tags `v*`.

The next release is signed. Its Windows job checks each signature as Windows sees it, and fails if one isn't
valid. Reputation with SmartScreen and Defender builds over the first few signed releases.

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
3. In **Actions**, open **Build Release** and choose **Run workflow**. It tests the package's core, builds the
   `.zip`, `.unitypackage` and `package.json` and makes the release **as a draft**, has VirusTotal scan the `.zip`
   and `.unitypackage` (adding each result to the notes, as for the app), then publishes it, tagging
   `unity-v<version>`. If VirusTotal flags a file, the release stays a draft: check the reports as for the app (see
   **VirusTotal flagged a file?** above), then run **Build Release** again with **Publish even if VirusTotal flags
   a file** ticked.
4. **Build Repo Listing** runs after it, rebuilding the VCC listing from every release and publishing it to GitHub
   Pages (https://hoard.furryup.link/index.json, the website's own address: the github.io one only forwards there).

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

Its **What's new** page (`changelog.html`) is built from `CHANGELOG.md` on each deploy
(`scripts/build_site_changelog.py`), with each release's date from GitHub, so a change to the changelog reaching
`main` updates it; nothing generated is kept in the repository. **Testers** (`site/testers.html`) thanks the people
who test releases: add a name there, one `<li>` each.

## The wiki

The wiki is written in the repository's `wiki/` folder and reviewed like code. When a change to `wiki/` reaches
`main`, the **Wiki** workflow publishes it, replacing every page, so edit the pages there, not on GitHub.

Once, before the first publish: open the repository's **Wiki** tab and save any first page. GitHub only creates
the wiki's storage when its first page is saved; the workflow then replaces it.

## Checks on every change

**Check** runs for every pull request and every push to `main`: the tests on Ubuntu and Windows (browser tests
included, and the Unity core on Ubuntu), the release zips, the Unity package, the Windows app with its
self-test, the Mac app (Apple Silicon) with its self-test and `.pkg`, and the Flatpak. See [Development](Development#tests).
