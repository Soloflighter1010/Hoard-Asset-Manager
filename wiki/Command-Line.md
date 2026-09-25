Everything Hoard does from its window also works as a command, for scripts, scheduled tasks and computers
without a desktop (a NAS, say).

## Running a command

- **The installed app:** `hoard-cli.exe` in Hoard's folder, `%LOCALAPPDATA%\Programs\Hoard`. It isn't on your
  `PATH`, so give its full path:

  ```
  "%LOCALAPPDATA%\Programs\Hoard\hoard-cli.exe" sync
  ```

- **The portable zip:** `hoard-cli.exe` in the folder you extracted.
- **From source:** `Hoard.bat <command>` on Windows, `./run.sh <command>` on macOS and Linux.

The examples below say `hoard-cli`; use whichever of these fits. Without a command, Hoard opens in its window
(`--browser`: in your web browser instead).

## Commands

| Command | What it does |
|---|---|
| `login <store>` | Sign in to a store (`booth`, `gumroad`, `jinxxy`, `payhip`) in a browser window, or add an itch.io API key (`itch`) |
| `logout <store>` | Sign out of a store in Hoard, or of every store with `all` |
| `refresh [--store <store>]` | Read what you own from the stores (repeat `--store` for several; default: all) |
| `import <file or folder>... [--store <store>] [--trust-shop <address>]` | Add library pages you saved from your own browser (`.mhtml` or `.html`): any number of files, and folders of them. A Payhip shop that isn't in your list is only added with `--trust-shop` and its exact address (repeat it for several). Exits with 1 if any page wasn't imported |
| `sync` | Download everything new or changed, from every store but Payhip, which Hoard only lists (options below) |
| `tags` | Rebuild `catalog.json` and `tags.json` from what's downloaded |
| `verify` | Check whether any data file was changed outside Hoard, then rebuild the catalog files. Exits with 1 if anything was changed |
| `self-test` | Check this copy of Hoard has everything it needs |
| `migrate <folder>` | Bring over the library list and downloads folder from Hoard 1.x |
| `install-browser` | Download Hoard's own browser (only needed without Microsoft Edge) |
| `debug <store> [--raw]` | Save a store's library page and a summary of what Hoard read from it, for troubleshooting. Personal details are removed; `--raw` keeps everything, with a screenshot |
| `probe jinxxy [--raw]` | Record what the Jinxxy site loads, for troubleshooting (scrubbed the same way) |

`sync` options:

- `--store <store>`: only one store, `booth`, `gumroad`, `jinxxy` or `itch` (default: all of them)
- `--dry-run`: list what would download, and download nothing
- `--only <text>`: only products whose name or creator contains the text
- `--headed`: show the browser while downloading from Booth or Jinxxy

Every command also takes `--config <file>`, to use a different settings file (default: `config.json` in Hoard's
app-data folder).

## Examples

See what a sync would fetch, without downloading anything:

```
hoard-cli sync --dry-run
```

Download only one creator's products from Booth:

```
hoard-cli sync --store booth --only "Kitsu Studio"
```

Import every page you saved in a folder (every shop's Payhip library pages, say):

```
hoard-cli import "D:\Saved pages\Payhip"
```

Check nothing has been tampered with (useful in a script: it exits with 1 if something was):

```
hoard-cli verify
```

## Syncing on a schedule

- **Windows:** in **Task Scheduler**, create a task that runs
  `%LOCALAPPDATA%\Programs\Hoard\hoard-cli.exe` with the argument `sync`, as your own account.
- **macOS and Linux:** a cron job or systemd timer running `./run.sh sync` in Hoard's folder.

Sign in to your stores first, in the app or with `login`. `sync` never opens Payhip (Hoard only lists what you
bought there), so it needs nobody at the computer. If Hoard is busy with a store at the same moment, the command
says so rather than getting in its way.

## Running Hoard as a server

Started with `--no-open`, `--port` or `--host`, Hoard runs as a server until you stop it with **Ctrl+C**, and
prints the address to open it at. That address includes an access key that's new each time: see
[Using Hoard on other devices](Using-Hoard-on-Other-Devices).

The complete reference is
[docs/COMMAND-LINE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/COMMAND-LINE.md).
