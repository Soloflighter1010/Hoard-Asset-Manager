# Code signing policy

Hoard's Windows programs (`Hoard.exe`, `hoard-cli.exe` and the installer, `Hoard-Setup-<version>.exe`) are to be
signed through SignPath Foundation's free code signing for open-source projects:

**Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).**

Hoard has applied; until signing is in place, Windows releases are unsigned (see [Install (Windows)](README.md#install-windows)).

## What is signed

Only files built from this repository's source, by its own GitHub Actions release workflow
(`.github/workflows/release.yml`), from a version tag on `main`. Nothing built on anyone's own computer is signed,
and nothing from another project is signed as Hoard's: the Python runtime, Playwright and the other libraries
Hoard bundles keep their makers' own signatures, if they have any. The open-source software Hoard includes is
listed in [COPYRIGHT.md](COPYRIGHT.md).

Every release file also carries GitHub's signed build provenance
(`gh attestation verify <file> -R Soloflighter1010/Hoard-Asset-Manager`) and a SHA-256 in the release's checksum
files, and is scanned by VirusTotal before the release is published.

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
