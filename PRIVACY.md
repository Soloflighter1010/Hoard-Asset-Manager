# Privacy Policy

Last updated: 23 September 2026 (version 1.4.0)

**The short version:** Hoard and Hoard Downloader run entirely on your own computer. They don't send
anything to me or to anyone else. There are no accounts, no analytics, no tracking and no ads.

## Who this is from

Hoard is an open-source project maintained by Soloflighter1010 ("I" below). I don't run any servers for
Hoard, and I never receive any of your information.

## What the tools keep on your computer

| What | Why | Where |
|---|---|---|
| Your store sign-ins (the cookies and site data a store sets when you sign in in Hoard's browser window, one folder per store; never your passwords) | To read your purchase list and download your files without asking you to sign in every time | Hoard's private sign-in folder: `%LOCALAPPDATA%\Hoard\sign-ins` on Windows, `~/Library/Application Support/Hoard/sign-ins` on macOS, `~/.local/share/Hoard/sign-ins` on Linux. Encrypted by your operating system where it can be. |
| Your library list: names, creators, links and image links for the items you own | To show your library | `library.json` in the Hoard folder |
| Product images, saved after each refresh (turn off with `"offline_images": false`) | So the library loads quickly and works offline | `.cache/thumbs` in the Hoard folder |
| Downloaded files and their records (`_manifest.json`, `catalog.json`, `tags.json`, `asset.json`) | So nothing is downloaded twice, and for search and tags | The download folder you choose |
| Your tags | So you can sort and find things your way, in both tools | `tags.json` in the same private `Hoard` folder as your sign-ins |
| Your settings | So the tools remember your choices | `config.json` in each tool's folder |
| Troubleshooting files, only when you run `debug` or `probe` | So you can see why a store isn't being read | `debug/` or `probe-output/` in the tool's folder |

None of this leaves your computer unless you share it yourself.

## Who the tools talk to

- **The stores you sign in to:** Booth (and pixiv, which Booth uses for sign-in), Gumroad, Jinxxy and
  Payhip. The tools read your purchases and download your files there, as your own browser would, and
  each store handles those visits under its own privacy policy.
- **The image hosts those stores use,** to fetch product images.
- **GitHub,** only when you open a link in a tool's footer or in the documentation.

That's all. The pages' typefaces come with the tools, so showing a page never contacts anyone. The tools
have no telemetry, no crash reporting and no automatic update checks, and they work offline except for
refreshing, signing in and downloading.

## Using the tools on your network

If you start a tool with `--host 0.0.0.0`, other devices on your network can view your library, but only
over HTTPS (or a VPN you've said is encrypted) and only with the access key the tool prints when it
starts. Those devices can't sign in, refresh, sign out, change tags or open folders; only the computer
running the tool can.

## Sharing troubleshooting files

If you attach `debug` or `probe` output to a GitHub issue, it becomes public. Those files can show your
purchases and your account name, so remove anything you don't want public before attaching them.

## Deleting your information

- **Sign-ins:** choose **Sign out of every store** in Hoard's Stores panel or in the Hoard Downloader menu.
- **Everything else:** delete the tool folders, your download folder, and the `Hoard` folder in your
  app-data folder (see the table above).

## Changes to this policy

Any change is recorded in this file's history on GitHub and mentioned in `CHANGELOG.md`.

## Contact

Open an issue on GitHub (don't include personal information), or for security matters follow
[SECURITY.md](SECURITY.md).
