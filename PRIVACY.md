# Privacy Policy

Last updated: 23 September 2026 (version 1.4.0)

**The short version:** Hoard runs entirely on your own computer. They don't send
anything to me or to anyone else. There are no accounts, no analytics, no tracking and no ads.

## Who this is from

Hoard is an open-source project maintained by Soloflighter1010 ("I" below). I don't run any servers for
Hoard, and I never receive any of your information.

## What Hoard keeps on your computer

| What | Why | Where |
|---|---|---|
| Your store sign-ins (the cookies and site data a store sets when you sign in in Hoard's browser window, one folder per store; never your passwords) | To read your purchase list and download your files without asking you to sign in every time | Hoard's private sign-in folder: `%LOCALAPPDATA%\Hoard\sign-ins` on Windows, `~/Library/Application Support/Hoard/sign-ins` on macOS, `~/.local/share/Hoard/sign-ins` on Linux. Encrypted by your operating system where it can be. |
| Your library list: names, creators, links and image links for the items you own | To show your library | `library.json` in Hoard's app-data folder |
| Product images, saved after each refresh (turn off in Settings) | So the library loads quickly and works offline | `cache/thumbs` in Hoard's app-data folder |
| Downloaded files and their records (`_manifest.json`, `catalog.json`, `tags.json`, `asset.json`) | So nothing is downloaded twice, and for search and tags | The download folder you choose |
| Your tags | So you can sort and find things your way, in Hoard | `tags.json` in the same private `Hoard` folder as your sign-ins |
| What Hoard would print: which stores it read, what it downloaded, and any errors (no passwords, cookies or page contents) | So there's something to look at if Hoard misbehaves | `logs\\hoard.log` in Hoard's app-data folder (it keeps two runs' worth) |
| The window's own storage (its layout choices) | So the window remembers how you left it | `window` in Hoard's app-data folder |
| What you've archived, hidden or removed, and your hidden library's PIN (only as a salted, slow hash, never the PIN itself) | So those choices last, even after refreshing | `marks.json` in the same private `Hoard` folder |
| Your settings | So Hoard remembers your choices | `config.json` in Hoard's app-data folder |
| The last 60 finished jobs (refreshes, syncs, downloads): what each did, how it went, and its progress, which names products and creators | So the Tasks window can show them after Hoard restarts | `tasks.json` in Hoard's app-data folder (Clear in Tasks empties it) |
| Troubleshooting files, only when you run `debug` or `probe` | So you can see why a store isn't being read | `debug` in Hoard's app-data folder |
| Local error history and support reports | So errors can be investigated and a sanitized report can be shared by you | `diagnostics/incidents.jsonl` in app-data; reports you create go to `Documents\\Hoard\\Support Reports` (see below) |

None of this leaves your computer unless you share it yourself.

## Hoard for Unity

The Unity package reads Hoard's `catalog.json`, its seal key and your downloaded files, all on your own
computer, and contacts nobody. It keeps a list of what you imported through it in the Unity project
(`ProjectSettings/Hoard/imports.json`) and a cache of package contents in the project's `Library` folder.

## Who Hoard talks to

- **The stores you sign in to:** Booth (and pixiv, which Booth uses for sign-in), Gumroad, Jinxxy, Payhip
  and itch.io. Hoard reads your purchases there and downloads your files (from every store but Payhip, which
  it only reads), as your own browser would, and each store handles those visits under its own privacy
  policy. For itch.io that's its API (`api.itch.io`), with the API key you gave Hoard, and the file hosts its
  downloads come from. Pages you import instead are read on your computer, and nothing is sent anywhere for them.
  With **Sync automatically** turned on in **Settings** (it's off unless you do), Hoard does this by itself
  while it's open, as often as you chose.
- **The image hosts those stores use,** to fetch product images.
- **GitHub,** where Hoard is published: when you open a link in Hoard's footer or in the documentation, and
  when Hoard checks for a newer version. It checks when you choose **Check now** in **Settings**, and once a
  day when it starts only if you've turned on **Check for updates automatically** (off unless you do). A
  check asks GitHub's API (`api.github.com`) for the list of Hoard's releases; GitHub sees your IP address and
  that it's Hoard (and which version) asking, as with any website, and nothing else is sent. Updating
  downloads the new installer from GitHub.

That's all. The pages' typefaces come with Hoard, so showing a page never contacts anyone. Hoard
has no telemetry or automatic crash reporting: errors and crash details stay on your computer until you choose to share a sanitized report, and it works offline except for refreshing, signing in, downloading
and checking for updates.

## Using Hoard on your network

If you start a tool with `--host 0.0.0.0`, other devices on your network can view your library, but only
over HTTPS (or a VPN you've said is encrypted) and only with the access key the tool prints when it
starts. Those devices can't sign in, refresh, sign out, change tags or open folders; only the computer
running the tool can.

## Sharing troubleshooting files

The normal way to report a problem is **Settings → Create support report** (or **Create report** next to a failed store or download). Hoard builds the ZIP locally and sanitizes it before saving it to `Hoard\\Support Reports` in your Documents folder, so it's easy to find and attach. If your Documents folder is synced (OneDrive, iCloud and the like), the reports are synced with it, as anything else there would be. Hoard never uploads them itself. It includes technical details, error information and sanitized logs, but not your sign-ins, library file, downloaded files, passwords, cookies or API keys. Review the preview and the ZIP before attaching it to a public GitHub issue.

The command-line `debug` and `probe` files are still available for deeper troubleshooting. They can contain purchase details and should be reviewed carefully before sharing them.

## Deleting your information

- **Sign-ins and library list:** choose **Sign out of every store** in the Stores panel. It also removes every store's items from your library.
- **Everything else:** delete the Hoard program folder, your downloads folder, and the `Hoard` folder in your
  app-data folder (see the table above).

## Changes to this policy

Any change is recorded in this file's history on GitHub and mentioned in `CHANGELOG.md`.

## Contact

Open an issue on GitHub (don't include personal information), or for security matters follow
[SECURITY.md](SECURITY.md).
