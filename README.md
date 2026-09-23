<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo-dark.svg">
    <img src="brand/logo-light.svg" alt="Hoard" width="300">
  </picture>
</p>

<p align="center"><b>Every avatar asset you've bought, in one pile.</b><br>
Booth, Gumroad, Jinxxy and Payhip purchases in a single library you can search, filter and keep.</p>

You bought that hoodie. Was it on Booth or Gumroad? Did the creator update it? Hoard answers those
without opening four tabs.

| | Hoard | Hoard Downloader |
|---|---|---|
| What it does | Shows everything you own in one searchable page, with links to each store's download page | Downloads everything you own into tidy folders and keeps it up to date |
| Stores | Booth, Gumroad, Jinxxy, Payhip | Booth, Gumroad, Jinxxy, Payhip |
| Downloads files | No | Yes, into `<Store>/<Creator>/<Product>` folders |
| Also | Spots products you own on more than one store | Flags files a creator has updated, suggests tags, has its own browser for your downloads |

Start with **Hoard** to see what you own. Add **Hoard Downloader** when you want local copies.

## Install (Windows)

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) and tick **Add python.exe to PATH**.
2. Download a zip from [Releases](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest):
   `Hoard`, `HoardDownloader`, or `Hoard-Bundle` for both.
3. Extract it into a folder of your own, such as one inside your user folder (not Program Files).
   Setup makes sure only your account can change the program's files.
4. Double-click `Setup.bat` in each tool's folder once. It sets up a private Python environment in
   that folder and downloads the browser used for store sign-ins (about 150 MB).
5. Double-click `Hoard.bat` or `Hoard Downloader.bat`.

On Linux or macOS, run `./setup.sh` and then `./run.sh` in each tool's folder.

**Updating:** extract the new zip over the old folder. Your settings (`config.json`) and library data
aren't in the zip, and your sign-ins are kept elsewhere, so everything stays.

Each tool has its own README with the details: [Hoard](Hoard/README.md),
[Hoard Downloader](HoardDownloader/README.md).

## Your sign-ins

You sign in to each store once, on the store's own page, in a browser window that belongs to Hoard alone
(never your everyday browser). Hoard never sees or keeps your store passwords, only the sign-in the store
gives that window. Here's how those sign-ins are kept safe:

- **Kept apart, out of the program folder.** Each store's sign-in has its own folder in your user
  account's private app-data folder, so zipping, sharing, syncing or committing the program folder never
  carries them, and one store's pages never share a browser with another store's sign-in. Both Hoard
  tools use them, so you sign in once for both.

  | Windows | macOS | Linux |
  |---|---|---|
  | `%LOCALAPPDATA%\Hoard\sign-ins` | `~/Library/Application Support/Hoard/sign-ins` | `~/.local/share/Hoard/sign-ins` |

- **Encrypted by your operating system.** Windows ties them to your Windows account. On macOS they're
  protected by the Keychain (macOS asks once whether Hoard's browser may use it; choose Always Allow).
  On Linux they need a keyring: GNOME Keyring, KeePassXC with its Secret Service turned on, or KWallet.
  Without one Hoard won't save sign-ins. On a computer without a desktop, such as a NAS, you can allow
  it with `"allow_unprotected_signins": true` in `config.json`; they're then protected only by being
  readable by your user account alone.
- **One program at a time** per store, which keeps the saved cookies from getting damaged.
- **Sign out properly.** Sign out of one store, or of every store, from the Hoard Downloader menu or
  Hoard's Stores panel. Hoard asks the store to end the session where it can, deletes that store's
  saved sign-in, checks nothing is left, and tells you what it did.

Anyone who gets that folder while you're logged in to your computer could use your store accounts, so
never copy it anywhere. Sign-ins saved by older versions (one shared folder, or `.browser-profile` next to
the program) are split into one folder per store automatically on first run, and the old copies removed.

[SECURITY.md](SECURITY.md) explains what Hoard protects against and what no desktop app can.

**Using one download folder from two computers** (say, a NAS): each computer's Hoard seals its data files
with its own key, so each would treat the other's changes as unverified and fetch store links again. To
share the folder, copy `integrity.key` from Hoard's app-data folder on one computer to the same place on
the other.

## Privacy

Everything stays on your computer. The tools talk only to the stores you use, with no accounts,
analytics or tracking. [PRIVACY.md](PRIVACY.md) has the details,
including what's stored where and how to delete it.

## Tags

Hoard has two kinds of tags:

- **Your tags**, which you create and put on items yourself.
- **Suggested tags**: words that turn up in several item names (`FoxyHoodie v2` gives `foxy` and
  `hoodie`), with filler words and version numbers left out.

Ways to tag:

- **One item:** open it, then type a tag under **Tags**, or click a suggestion to add it. Remove a tag
  with the × next to it. A tag you add applies to every copy of that product you own on other stores.
- **Many items:** choose **Select**, click the items (or **Select all shown** after filtering, say by a
  creator), type a tag, then **Add tag** or **Remove tag**.
- **The Tags panel** (the **Tags** button) lists all your tags and the suggestions:
  - **Keep** a suggestion to make it your tag on every item whose name has that word, including items
    you buy later. **Hide** one to stop it being suggested.
  - **Rename** a tag. Renaming it to an existing tag's name merges the two.
  - **Match names** gives any tag that automatic matching. **Delete** removes a tag.

Your tags are saved in Hoard's private app-data folder (`%LOCALAPPDATA%\Hoard\tags.json` on
Windows), and Hoard and Hoard Downloader share them: tag something in one and it's tagged in the other.
Filter by any tag from the sidebar; filters combine.

## Offline

Both tools work without an internet connection for everything except refreshing, signing in and
downloading. Hoard saves every product image after each refresh, so your whole library, its search and
its images work offline, and the typefaces come with the tools. When a store can't be reached, the tools
say so and leave your saved library and downloads as they were.

## Things to know

- These are unofficial tools, not affiliated with or endorsed by Booth (pixiv), Gumroad, Jinxxy or
  Payhip. They only read purchases in your own accounts, with your own sign-in.
- Stores change their websites. When one does, its reader can stop working until it's updated.
  Payhip already checks for automated browsers: both tools work around it with your help (a visible
  window you can complete the check in, or a page you save from your own browser).
- Downloading doesn't change what you're allowed to do with an asset. Follow each creator's license
  and each store's terms.

## Reporting a problem

Open an issue with what you did and what happened. If a store isn't being read correctly, run
`debug <store>` (Hoard) or `probe jinxxy` (Hoard Downloader) and attach the output, after
checking it: those files show your purchases, and screenshots can show your account name.

Found a security problem? Please report it privately, as [SECURITY.md](SECURITY.md) describes.

## Made with AI

Most of Hoard's code, design and documentation was written by an AI assistant (Anthropic's Claude),
directed and tested by the maintainer. [AI-DISCLOSURE.md](AI-DISCLOSURE.md) explains what that means
for you. Hoard itself doesn't use AI, and your data never goes to one.

## For developers

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains how the tools are built: the store readers, sign-ins,
the local servers and their safety rules, and how releases are made.

To make a release, raise `__version__` in `HoardDownloader/asset_dl.py` and `Hoard/library.py`, add a
section to `CHANGELOG.md`, then push a tag such as `v1.3.1`. GitHub Actions builds the three zips and
publishes the release with that version's changelog. `python scripts/build_release.py` builds the same
zips locally into `dist/`.

## Legal

- [LICENSE](LICENSE): MIT
- [TERMS.md](TERMS.md): terms of use
- [PRIVACY.md](PRIVACY.md): privacy policy
- [COPYRIGHT.md](COPYRIGHT.md): copyright, the name and logo, third-party software and credits
- [SECURITY.md](SECURITY.md): reporting security problems

The logo files are in `brand/`. The wordmark is outlined from Dela Gothic One, so the files need no fonts
installed.
