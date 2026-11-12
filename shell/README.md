# Hoard's window (Tauri), and how Hoard is built

Hoard's releases, from 5.2.0 beta 6: its window is this Tauri app, and its server is compiled by Nuitka. (Before,
PyInstaller packed Hoard, with pywebview's window; the experiments that compared the two, tauri-nuitka-beta.1 to 5,
are on the Releases page.) Run from source, Hoard still opens in pywebview's window.

| Part | What it is |
|---|---|
| `src/main.rs` | The window. It starts Hoard's server (`hoard-server --shell`, in the app's resources), shows its page, and passes on the close button, Command-Q and the system's pickers. Links that would open a new window open in your browser |
| `../hoard/shell.py` | Hoard's side: the messages to and from the window, one JSON message a line on the server's standard input and output (the file says what each means). Hoard decides everything as in its own window |
| `../scripts/build_nuitka.py` | Compiles `../packaging/hoard_shell.py` into `../build/nuitka/server/` (hoard-server, and what it needs) |
| `tauri.conf.json` | The app: its name, icons, installers, and the server folder as its resources |
| `flatpak/` | The Flatpak: the .deb's files on the GNOME runtime, with the app ID the earlier Flatpak had (so it installs over it), and `hoard`, which opens the window or runs one of Hoard's commands |
| `updater.pub` | The public half of the key Hoard's updates are signed with. Empty: the window doesn't update itself (see Updates) |
| `installer/` | The Windows installer's sidebar (its first and last pages) and header (the others), made by `../scripts/make_installer_art.py` from the Heap and the website's fonts: run it again after the logo changes |
| `package.json` | The Tauri CLI, pinned (`package-lock.json` has each file's hash) |

## Building it

You need Python 3.10 or later with `requirements.txt` and `requirements-nuitka.txt` installed, a C compiler,
Rust, and Node. On Linux, Tauri also needs WebKitGTK (`libwebkit2gtk-4.1-dev`) and `patchelf`.

```
python scripts/build_nuitka.py                  # build/nuitka/server/
build/nuitka/server/hoard-server self-test      # (hoard-server takes Hoard's commands too)
cd shell
npm ci --ignore-scripts
npx tauri build --config '{"version": "5.2.0"}' # the app, and its installers in target/release/bundle/
```

`cargo build --release` builds the window alone (with the server folder beside it, in `target/release/server/`),
to run it from there.

## Releasing it

`.github/workflows/release.yml` builds Hoard for Windows, macOS (Apple silicon and Intel) and Linux when a version
tag is released (see the wiki's Releasing page): Windows' installer, a .dmg for each kind of Mac (and the
`.app.tar.gz` a Mac updates from), and for Linux an AppImage, a .deb and the Flatpak. Windows' programs and libraries
are signed first, then the installer; then each file the window updates from is signed for the updater. Every push
and pull request builds the same, unsigned (`.github/workflows/check.yml`).

Hoard's commands (`sync`, `verify`, `import`, ...) are `hoard-server`'s, in the app's `server` folder; in the Flatpak,
`hoard <command>`. There's no `hoard-cli` any more.

## Updates

Hoard chooses the update, as it always has (`hoard/updater.py`: its beta channel, what's new, checking only when you
ask or once a day if you've said so). The window installs it, with Tauri's updater: Hoard sends it the release's
`Hoard-update.json` and the version, and the window downloads the file for this computer, keeps it only if it matches
its signature (checked against `updater.pub`, built into the window), and installs it once Hoard has quit cleanly,
then opens the new Hoard. Windows' setup reopens Hoard itself; a Mac's app and Linux's AppImage are replaced where they
are, and the .deb is installed with `dpkg` (it asks for your password). The Flatpak never updates itself: Flatpak
does that.

The key is made once, on your own computer, and never put in the repository or pasted anywhere:

```
cd shell && npm ci --ignore-scripts
npx tauri signer generate -w ~/.tauri/hoard-updates.key   # asks for a password; keep the key and the password safe
```

Then put the private key (the whole of `hoard-updates.key`) and its password in the repository's Actions secrets,
`TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`, and the public half (`hoard-updates.key.pub`, one
line) in `updater.pub`. The workflow then signs each release's files and makes `Hoard-update.json`
(`scripts/update_manifest.py`); with only one of the two, it stops before building anything. Lose the key, and the
copies out there can't be updated by the window any more: everyone downloads the next one by hand, once.

