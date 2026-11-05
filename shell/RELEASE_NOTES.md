**An experiment, beside Hoard's own releases.** This is Hoard {version}, built another way: its window is a
[Tauri](https://tauri.app) app instead of pywebview, and its server is compiled by [Nuitka](https://nuitka.net)
instead of packed by PyInstaller. It's here to compare with the usual build: how big it is, how quickly it starts,
and what antivirus makes of it. Everything else is the same Hoard.

- **Your library, settings and sign-ins are shared** with the usual Hoard (the same app-data folder). Only one Hoard
  runs at a time: quit the other one first.
- **It isn't offered by Hoard's updates,** and doesn't update itself: a newer one is put up here.
- **Not in it:** hoard-cli (the server, hoard-server, takes the same commands), the Flatpak (Linux has an AppImage and
  a .deb instead) and the Mac's .pkg (a .dmg instead).
- **The Mac's isn't signed,** as the usual one isn't: open it with right-click, Open, the first time.

Something different from the usual Hoard, or wrong? Say so in Discord or an issue, and say it's this build.

| File | For |
|---|---|
| `Hoard-Tauri-Setup-{version}.exe` | Windows (installs for you alone, no administrator needed) |
| `Hoard-Tauri-{version}-macos-apple-silicon.dmg` | Macs with Apple silicon |
| `Hoard-Tauri-{version}-macos-intel.dmg` | Macs with Intel |
| `Hoard-Tauri-{version}-linux-x86_64.AppImage` | Linux, any distribution |
| `Hoard-Tauri-{version}-linux-amd64.deb` | Debian and Ubuntu |
