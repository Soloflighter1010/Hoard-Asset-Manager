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

1. checks the updates' key and `shell/updater.pub` agree (see **Updates' key** below), builds the source zip and its
   checksums, signs its build provenance, and makes the release **as a draft**;
2. builds Hoard for each system, from 5.2.0 beta 6 with Tauri and Nuitka (`shell/README.md`): the server compiled
   by Nuitka (`scripts/build_nuitka.py`) and checked with its self-test, then the window, then its installer.
   Windows: every program and library signed, then `Hoard-<version>-windows-setup.exe`, signed too. The Macs, on an
   Apple silicon and an Intel runner: `Hoard-<version>-macos-apple-silicon.dmg` and `...-macos-intel.dmg`, with the
   `.app.tar.gz` each updates from. Linux: `Hoard-<version>-linux-x86_64.AppImage` and
   `Hoard-<version>-linux-amd64.deb`. Each system's files have their checksums (`SHA256SUMS-<system>.txt`), and each
   file the window updates from is signed with the updates' key;
3. builds the Flatpak from the .deb (`shell/flatpak`; flatpak-builder, in Flathub's GNOME 51 container; its build
   checks every library the window needs is in the runtime and runs the self-test in the sandbox), and attaches
   `Hoard-<version>-linux-x86_64.flatpak` and `SHA256SUMS-flatpak.txt`;
4. makes `Hoard-update.json` from each system's signed files (`scripts/update_manifest.py`): what Hoard's window
   updates from;
5. has VirusTotal scan every file people download (`scripts/scan_release_virustotal.py`), and adds each file's
   result and report link to the release notes;
6. publishes the release, once every file is on it and none was flagged.

Every file has signed build provenance (`gh attestation verify`). The Windows programs, libraries and installer are
code-signed (see **Code signing (Windows)** below); the Mac app isn't signed or notarized by Apple: see
[Installing Hoard](Installing-Hoard) for what users see. Never name a file `Hoard-Setup-<version>.exe` with a
`SHA256SUMS-windows.txt` beside it: Hoard 5.1.3 and earlier install that pair by themselves, and the new Hoard is a
new app (the old one is uninstalled first). A test holds the workflows to that.

Every push and pull request builds the same, unsigned (**Check**), so a build that breaks is found before a
release.

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
   finished `3.1.0` when it's out. Hoard installs a beta itself, as it does a release (but the Flatpak).

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
  VirusTotal's report. A new program, or one Apple hasn't signed, is sometimes flagged by one or two engines by
  mistake. Open the report: if it's a false positive (a generic or heuristic name, from an engine or two), run the
  workflow again for the tag with **Publish even if VirusTotal flags a file** ticked. That builds nothing: it
  publishes the draft as it is, the files whose reports you checked (a build is never the same file twice, so a
  new one would be a file nobody checked). It looks them up on VirusTotal again, notes that they were checked by
  hand, and publishes, but only with the flags the draft's notes showed you: a file flagged by more engines since,
  or one that was clean, keeps it a draft for you to check that report too. If it looks real, don't publish: find
  out why first. Report a false positive to the engine's maker, which clears it: Windows won't let a browser
  download a file Microsoft's engine flags, so the run keeps the flagged files under **Artifacts**
  (`virustotal-flagged-files`), in a zip with the password `infected`. Upload that zip as it is (for Microsoft, at
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

`Hoard.exe`, `hoard-server.exe` with every library beside it, and the setup are signed with **Azure Artifact
Signing** (Microsoft's Trusted Signing), so Windows and Defender know they're Hoard's (issue #327: Defender took an
early build, whose libraries weren't signed, for a trojan). Signing happens in the release's Windows build, only
where it's set up: a fork, or this repository before it's set up, builds unsigned. The setup's uninstaller isn't
signed yet.

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

### Updates' key

From 5.2.0 beta 6, Hoard's window installs updates itself, only when the file carries the signature of Hoard's own
key (`shell/README.md`, **Updates**). The key's private half and its password are the repository's Actions secrets
`TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, made once on your own computer and never put
anywhere else; its public half is `shell/updater.pub`. The release refuses to build with one and not the other.
Lose the key, and the copies out there can't update themselves any more: everyone downloads the next one by hand,
once.

### Dependencies

`requirements.txt` (what Hoard runs on) is locked with hashes, made from `requirements.in` by the `uv pip compile`
command at its top; `requirements-nuitka.txt` pins Nuitka, which compiles the server, by its hash. The window's Rust crates
are locked by `shell/Cargo.lock`, and the Tauri command line by `shell/package-lock.json`. (`requirements-app.txt`,
`requirements-mac.txt` and `requirements-flatpak.txt`, with `packaging/hoard.spec` and `packaging/hoard.iss`, built
Hoard 5.1 and the 5.2.0 betas before beta 6.)

### Flathub

`shell/flatpak/io.github.soloflighter1010.Hoard.yml` builds the Flatpak from the release's .deb. Before Flathub
would take it, it needs to build from source (Flathub builds offline, from pinned sources), as
`packaging/flatpak/io.github.soloflighter1010.Hoard.yml` did for the Hoard before.

## Hoard for Unity

1. Raise `version` in `Packages/soloflighter.hoard/package.json`, and add a `## <version>` section to
   `Packages/soloflighter.hoard/CHANGELOG.md`.
2. Merge to `main`.
3. In **Actions**, open **Build Release** and choose **Run workflow**. It tests the package's core, builds the
   `.zip`, `.unitypackage` and `package.json` and makes the release **as a draft**, has VirusTotal scan the `.zip`
   and `.unitypackage` (adding each result to the notes, as for the app), then publishes it, tagging
   `unity-v<version>`. If VirusTotal flags a file, the release stays a draft: check the reports as for the app (see
   **VirusTotal flagged a file?** above), then run **Build Release** again with **Publish even if VirusTotal flags
   a file** ticked, which publishes the draft as it is, without building it again.
4. **Build Repo Listing** runs after it, rebuilding the VCC listing from every release and publishing it to GitHub
   Pages (https://hoard.furryup.link/index.json, the website's own address: the github.io one only forwards there).

Once, when setting the repository up: add the repository variable `PACKAGE_NAME` = `soloflighter.hoard`
(**Settings › Secrets and variables › Actions › Variables**), and set **Settings › Pages › Source** to **GitHub
Actions**. Pages only deploys from `main`, so a listing build started by a release event is re-run on `main`.

## The share server

[Short links](Sets#short-links) need Hoard's share server, the Cloudflare Worker in `share/`, at
`https://hoard-share.furryup.link`. No workflow deploys it: set it up once, and deploy a change to
`share/worker.mjs`, with `npx wrangler deploy` from that folder, as [share/README.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/share/README.md)
says. It runs on Cloudflare, so nothing has to stay running on your computer. Deploy it before releasing a version
of Hoard that needs a change to it: a Hoard that can't reach it says so, and can't share a set until it can (from
5.0, a set is shared only by a short link).

## The website

Hoard's website (https://hoard.furryup.link/, its own address for GitHub Pages) is the `site/` folder, deployed by
**Build Repo Listing** with the VCC listing: the site at the root, VRChat's listing page at `vcc/`, and
`index.json` (and the older `vpm/index.json`) where VCC finds them. A change to `site/` reaching `main` deploys
it. It loads nothing from other sites (a test checks), nor asks any: its download buttons take the latest
release's files from `latest.json`, which the deploy writes from GitHub's list of releases (each release deploys the
site), and open the releases page without it. Its fonts are the app's, cut down to Latin characters
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

The wiki is also in Japanese (`wiki/ja/`) and Korean (`wiki/ko/`): a page for each English page but this one and
[Development](Development). Each is named in its own language (GitHub's wiki keeps every page in one folder, so the
workflow copies them in beside the English pages), and starts with the English page it's from, as that page was
when it was translated. So when an English page changes, the tests fail until its translations say the same:

- `python3 scripts/wiki_translations.py --diff` shows what changed in each English page since it was translated.
- Update the translations, then `python3 scripts/wiki_translations.py --done ja Settings` (and `ko`) records
  that each now says what the English page does.
- Use the app's own words for its buttons and settings (`hoard/web/i18n/ja.json`, `ko.json`), so a reader finds
  them as the page names them.

The docs site builds them into `docs/ja/` and `docs/ko/`, each page at its English page's address there.

## Checks on every change

**Check** runs for every pull request and every push to `main`: the tests on Ubuntu and Windows (browser tests
included, and the Unity core on Ubuntu), the release zips, the Unity package, and Hoard for each system as the
release builds it (Windows, both Macs and Linux, each server with its self-test, unsigned), and the Flatpak. See
[Development](Development#tests).
