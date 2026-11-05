# Hoard's Tauri window (the Tauri and Nuitka build)

An experiment beside Hoard's own releases: the same Hoard, with its window from this Tauri app instead of
pywebview, and its server compiled by Nuitka instead of packed by PyInstaller. It's here to compare with the usual
build: how big it is, how quickly it starts, and what antivirus makes of it.

| Part | What it is |
|---|---|
| `src/main.rs` | The window. It starts Hoard's server (`hoard-server --shell`, in the app's resources), shows its page, and passes on the close button, Command-Q and the system's pickers. Links that would open a new window open in your browser |
| `../hoard/shell.py` | Hoard's side: the messages to and from the window, one JSON message a line on the server's standard input and output (the file says what each means). Hoard decides everything as in its own window |
| `../scripts/build_nuitka.py` | Compiles `../packaging/hoard_shell.py` into `../build/nuitka/server/` (hoard-server, and what it needs) |
| `tauri.conf.json` | The app: its name, icons, installers, and the server folder as its resources |
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

`.github/workflows/tauri-nuitka.yml` builds it for Windows, macOS (Apple silicon and Intel) and Linux on every push
to its branch. `RELEASE` holds the experiment's number, n: while `tauri-nuitka-beta.<n>` isn't published, a push
releases it (a draft, VirusTotal's scan, then a pre-release, never Latest, tagged on that push's commit). After that,
pushes only build, with the files kept with the run; put the next number in `RELEASE` for the next one. Hoard's
updates only look at version tags (`v...`), so nobody is offered this build; it says so in Hoard's updates
(`hoard/updater.py`).
