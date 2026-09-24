# Hoard from the command line

Everything Hoard does from its window also works as a command, for scripts, scheduled tasks and
computers without a desktop (a NAS, say). On Windows, run commands with `Hoard.bat`; on Linux and macOS,
with `./run.sh`. Without a command, Hoard opens.

| Command | What it does |
|---|---|
| `login <store>` | Sign in to a store (`booth`, `gumroad`, `jinxxy` or `payhip`) in a browser window |
| `logout <store>` | Sign out of a store in Hoard, or of every store with `all` |
| `refresh [--store <store>]` | Read what you own from the stores (repeat `--store` for several; default: all) |
| `import <file> [--store <store>]` | Add a library page you saved from your own browser (`.mhtml` or `.html`) |
| `sync` | Download everything new or changed (options below) |
| `tags` | Rebuild `catalog.json` and `tags.json` from what's downloaded |
| `verify` | Check whether any data file was changed outside Hoard, then rebuild the catalog files. Exits with 1 if anything was changed |
| `migrate <folder>` | Bring over the library list and downloads folder from Hoard 1.x |
| `debug <store>` | Save a store's library page and what Hoard read from it, for troubleshooting |
| `probe jinxxy` | Record what the Jinxxy site loads, for troubleshooting |

`sync` options:

- `--store <store>`: only one store (default: all)
- `--dry-run`: list what would download, and download nothing
- `--only <text>`: only products whose name or creator contains the text
- `--headed`: show the browser while downloading from Booth or Jinxxy
- `--payhip-page <file>`: read your Payhip products from a library page you saved, when Payhip blocks the
  automated browser

Options for every command:

- `--config <file>`: use a different settings file (default: `config.json` in Hoard's app-data folder)

## Using Hoard from other devices

Hoard only serves your own computer unless you start it with `--host 0.0.0.0`. Because your library and
its access key would then cross your network, that needs one of:

- **HTTPS:** add `--tls-cert cert.pem --tls-key key.pem`, a certificate for this computer (the free tool
  mkcert makes one your devices will trust).
- **An encrypted network:** if your devices reach this computer over a VPN such as Tailscale or WireGuard,
  add `--plain-http`.

Other devices then open the address Hoard prints, which includes an access key. Signing in, refreshing,
downloading, signing out, changing tags or settings and opening folders still only work on the computer
running Hoard. `--port` picks the port (by default Hoard uses any free one), and `--no-open` starts Hoard
without opening its page.

## Settings file

Hoard's window has a Settings panel for everyday choices. A few rarer ones only live in `config.json` in
Hoard's app-data folder (`%LOCALAPPDATA%\Hoard` on Windows, `~/Library/Application Support/Hoard` on
macOS, `~/.local/share/Hoard` on Linux):

| Setting | Default | Meaning |
|---|---|---|
| `allow_unprotected_signins` | `false` | Linux without a keyring only: keep sign-ins protected by folder permissions alone |
| `request_delay` | `1.0` | Seconds between page loads on a store |
| `payhip.shops` | `[]` | The Payhip shops you've bought from (also in Settings). Payhip keeps purchases per shop |
| `booth.include_free` | `true` | Also read Booth's free downloads (also in Settings) |
| `payhip.bot_check_wait` | `180` | Seconds to wait for you to complete Payhip's bot check |
| `jinxxy.item_link_pattern` | | Which links on Jinxxy's inventory page are your items |
| `tags.min_count`, `tags.max_share` | `3`, `0.4` | When a word becomes a suggested tag |
| `tags.blocklist` | `[]` | Words never to suggest (the Tags panel's **Hide** does the same) |
