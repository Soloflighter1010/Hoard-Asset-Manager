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
3. Extract it somewhere you can write to, such as `D:\Tools` (not Program Files).
4. Double-click `Setup.bat` in each tool's folder once. It sets up a private Python environment in
   that folder and downloads the browser used for store sign-ins (about 150 MB).
5. Double-click `Hoard.bat` or `Hoard Downloader.bat`.

On Linux or macOS, run `./setup.sh` and then `./run.sh` in each tool's folder.

**Updating:** extract the new zip over the old folder. Your settings (`config.json`) and library data
aren't in the zip, and your sign-ins are kept elsewhere, so everything stays.

Each tool has its own README with the details: [Hoard](Hoard/README.md),
[Hoard Downloader](HoardDownloader/README.md).

## Your sign-ins

You sign in to each store once, in a browser window that belongs to Hoard alone (never your everyday
browser). Here's how those sign-ins are kept safe:

- **Kept out of the program folder.** They live in your user account's private app-data folder, so
  zipping, sharing, syncing or committing the program folder never carries them. Both Hoard tools share
  them, so you sign in once for both.

  | Windows | macOS | Linux |
  |---|---|---|
  | `%LOCALAPPDATA%\Hoard\sign-ins` | `~/Library/Application Support/Hoard/sign-ins` | `~/.local/share/Hoard/sign-ins` |

- **Encrypted by your operating system.** Windows ties them to your Windows account. On macOS they're
  protected by the Keychain (macOS asks once whether Hoard's browser may use it; choose Always Allow).
  On Linux they use your desktop keyring. A Linux machine with no keyring, like a headless NAS, can't
  encrypt them, so there the folder is locked to your user account instead.
- **One program at a time.** The two tools never use your sign-ins at the same moment, which keeps the
  saved cookies from getting damaged.
- **Easy to remove.** Sign out of one store, or of every store, from the Hoard Downloader menu or
  Hoard's Stores panel. That only removes Hoard's copy; your store account isn't affected.

Anyone who gets that folder while you're logged in to your computer could use your store accounts, so
never copy it anywhere. Versions before 1.2 kept sign-ins in a `.browser-profile` folder next to the
program; the first run of 1.2 moves them to the private folder automatically and removes the old one.

## Privacy

- The tools talk to the stores you use and to nothing else. The library pages run on your own PC at
  `127.0.0.1`; the only other thing they load is the page typeface from Google Fonts.
- Everything they save (your library list, downloads, thumbnails) stays in the tool's folder or the
  download folder you choose.

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

## Making a release

Bump `__version__` in `HoardDownloader/asset_dl.py` and `Hoard/library.py`, add a section to
`CHANGELOG.md`, then push a tag such as `v1.0.1`. GitHub Actions builds the three zips and publishes
the release with that version's changelog. `python scripts/build_release.py` builds the same zips
locally into `dist/`.

## Thanks

The Gumroad reader follows the data shapes in Gumroad's open-source code (antiwork/gumroad), and the
Booth reader was informed by ribeKim's booth-library-manager.

## Brand

The logo files are in `brand/`: the mark on its own, and the full logo for dark and light
backgrounds. The wordmark is outlined from Dela Gothic One, so the files need no fonts installed.

## License

MIT. See [LICENSE](LICENSE).
