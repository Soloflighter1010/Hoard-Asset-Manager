# Code signing policy

Hoard's Windows programs (`Hoard.exe`, `hoard-cli.exe` and the installer, `Hoard-Setup-<version>.exe`) are
code-signed from 2.11.1 on, with Microsoft's Azure Artifact Signing (Trusted Signing), by the release workflow on
GitHub (see the wiki's [Releasing](https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki/Releasing) page).
Windows shows the publisher as **Sam Parker**, the maintainer's verified identity. A new publisher still has to
earn Microsoft's reputation, so Windows may say it "protected your PC" for a while after a release: choose **More
info** to see the publisher, then **Run anyway**. Every release file also carries GitHub's signed build
provenance (`gh attestation verify <file> -R Soloflighter1010/Hoard-Asset-Manager`) and a SHA-256 in the
release's checksum files, and is scanned by VirusTotal before the release is published. The Mac packages aren't
signed by Apple yet, and the installer's own uninstaller isn't signed.

## What is signed

Only files built from this repository's source, by its own GitHub Actions release workflow
(`.github/workflows/release.yml`), from a version tag on `main`. Nothing built on anyone's own computer is signed,
and nothing from another project is signed as Hoard's: the Python runtime, Playwright and the other libraries
Hoard bundles keep their makers' own signatures, if they have any. The open-source software Hoard includes is
listed in [COPYRIGHT.md](COPYRIGHT.md).

## Team and roles

| Role | Who |
| --- | --- |
| Committers and reviewers | [Soloflighter1010](https://github.com/Soloflighter1010) |
| Approvers (each signing request is approved by hand) | [Soloflighter1010](https://github.com/Soloflighter1010) |

Changes from anyone else reach `main` only as pull requests reviewed and merged by a committer.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the
user or the person installing or operating it. Hoard connects only to the stores you choose and sign in to (and
their image hosts), and to GitHub's list of Hoard releases when you check for updates (automatic checks are off
unless you turn them on). [PRIVACY.md](PRIVACY.md) has the details.
