Hoard is an app for Windows, macOS and Linux (an AppImage, a .deb or a Flatpak). It also runs from source on all
three.

From 5.2.0 beta 6, Hoard is built a new way (its window with Tauri, its server compiled by Nuitka), and its files
are new: this page is about those. Hoard 5.1, the latest release until 5.2.0, is installed as it always was; each
section says what's different for it.

## Moving to the new Hoard

Hoard 5.1.4 and 5.2.0 beta 5 are the last Hoards built the way they had been (with PyInstaller). The versions
after them install as a new app. So Hoard can't update itself to them, and the old one has to go first, or you'd
have two Hoards. When one is out, Hoard says so under its bar.

1. Uninstall the Hoard you have:
   - **Windows:** Windows Settings › Apps › Installed apps › Hoard › Uninstall.
   - **macOS:** quit Hoard, then move it from Applications to the Bin.
   - **Linux (Flatpak):** nothing to uninstall: the new Flatpak installs over the old one (it's the same app to
     Flatpak). If you'd rather have the AppImage or the .deb, remove the Flatpak in your software centre, or run
     `flatpak uninstall io.github.soloflighter1010.Hoard`.
   - **From source:** there's nothing to uninstall.
2. Download the new Hoard for your computer from
   [its release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases), and install it as below.

Your library, settings, sign-ins and downloads stay where they are: uninstalling removes only the program, and the
new Hoard finds them as the old one did.

## Windows

1. Download **`Hoard-<version>-windows-setup.exe`** from
   [the release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases) and run it.
   It installs for you only, with no administrator prompt, into `%LOCALAPPDATA%\Hoard`, and adds Hoard to the Start
   menu. The folder is one only your account can change, which keeps your store sign-ins safe.
2. Windows may say **"Windows protected your PC"** for a while after a release. Hoard is code-signed (every program
   and library in it): choose **More info** and the publisher shows as Hoard's maintainer. A new publisher earns
   Microsoft's trust as people install it, so the warning fades with time. Choose **Run anyway**. To be sure the
   file is genuine first, see [Checking a download](#checking-a-download).
3. Open **Hoard** from the Start menu. It opens in its own window, and a short setup assistant walks you
   through the rest: see [Getting started](Getting-Started).

Hoard 5.1's installer is **`Hoard-Setup-<version>.exe`**, from the
[latest release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest), and it installs into
`%LOCALAPPDATA%\Programs\Hoard`.

Closing the window quits Hoard. While it's downloading, it asks first: stop and close, keep going in the
background, or close at once (a download stopped part way carries on from where it was next time).

**Hoard's window** uses Microsoft Edge WebView2, which is part of Windows 11 and kept up to date on Windows 10.

### Updating

In **Settings**, under **Hoard updates**, choose **Check now**. When there's a newer version, **Update to** it: Hoard
closes (a download in progress resumes next time), its window downloads the new version's installer, installs it
and opens Hoard again. The installer is kept only if it carries the signature of Hoard's own key, built into
Hoard's window, so nothing else can be installed in its place. Hoard won't update in the middle of a refresh or
download: wait for it, or **Stop** it.

**Check for updates automatically** (on unless you turn it off, from 5.1; a Hoard you had before keeps your choice)
makes Hoard ask GitHub, in the background, each time it starts and once a day while it's open; a newer version then
shows as **Update to** at the top of the page, beside Hoard's version. A check sends GitHub nothing but
the request itself: see [Security and privacy](Security-and-Privacy).

You can always run the newer installer yourself too, over this one. An update replaces the program files, so
nothing from the old version lingers. (Hoard 5.1 installs updates the same way when it was installed with
`Hoard-Setup`, checking the installer against the release's checksums instead.)

Your settings, library, sign-ins and tags are kept in the same folder as the program (`%LOCALAPPDATA%\Hoard`), and
your files in your downloads folder, but installing, updating and uninstalling only ever touch the program's own
files.

### Uninstalling

Use **Settings › Apps** in Windows, like any other app. That removes the program only (its option to delete the
app's data removes only its window's own cache). To remove everything Hoard keeps, see
[Where Hoard keeps things](Where-Hoard-Keeps-Things#deleting-everything).

### Checking a download

Every release is built by GitHub Actions straight from this repository, with a signed record of how it was
built. With the [GitHub CLI](https://cli.github.com/):

```
gh attestation verify Hoard-<version>-windows-setup.exe -R Soloflighter1010/Hoard-Asset-Manager
```

The same works for every file on a release (`Hoard-<version>-macos-apple-silicon.dmg`,
`Hoard-<version>-linux-x86_64.AppImage`, and so on).

Each release also lists checksums: `SHA256SUMS-windows-x86_64.txt` for the installer,
`SHA256SUMS-macos-apple-silicon.txt` and `SHA256SUMS-macos-intel.txt` for the Macs' files,
`SHA256SUMS-linux-x86_64.txt` for the AppImage and the .deb, `SHA256SUMS-flatpak.txt` for the Flatpak, and
`SHA256SUMS.txt` for the source zip. In PowerShell, `Get-FileHash .\Hoard-<version>-windows-setup.exe` prints the
one to compare; on a Mac, `shasum -a 256 <file>`; on Linux, `sha256sum <file>`.

Every file is also scanned by VirusTotal before a release is published: the release notes link each file's
report. Hoard's Mac app isn't signed by Apple, and a newly signed program has little reputation yet, so an engine or
two may occasionally flag one by mistake; the
report shows which, and each release is checked by hand before it's published anyway.

## macOS

Hoard runs on macOS 11 (Big Sur) or newer.

1. Download the disk image for your Mac from
   [the release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases):
   **`Hoard-<version>-macos-apple-silicon.dmg`** for a Mac with an M-series chip, or
   **`Hoard-<version>-macos-intel.dmg`** for an Intel Mac. (Apple menu › **About This Mac** says which: "Chip Apple
   M…" or "Processor … Intel".)
2. Open it, and drag **Hoard** to **Applications**.
3. Open Hoard from Applications. Hoard isn't signed by Apple yet (that costs money every year), so the first time,
   macOS says it **can't be opened** or **can't check it for malicious software**. Choose **Done** (not Move to
   Trash), then open **System Settings › Privacy & Security**, scroll down to the message about Hoard and choose
   **Open Anyway**. To be sure the file is genuine first, see [Checking a download](#checking-a-download). It opens
   in its own window, and a short setup assistant walks you through the rest: see [Getting started](Getting-Started).

Hoard 5.1 is a package instead, **`Hoard-<version>-macos-apple-silicon.pkg`** or **`...-macos-intel.pkg`**, from
the [latest release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest): open it, then allow
it in **Privacy & Security** as above, and it installs Hoard in Applications.

The first time Hoard's browser signs in to a store, macOS asks whether it may use the Keychain. Choose
**Always Allow**. Hoard's browser (Chromium, about 150 MB) is downloaded once, into
`~/Library/Caches/ms-playwright`.

**Updating:** **Settings › Hoard updates**, then **Update to** the newer version, as on Windows: Hoard's window
downloads it, keeps it only if it carries Hoard's signature, replaces the app in Applications and opens it again.
(Hoard 5.1 says which package to download, and you open it as above.) **Uninstalling:** drag **Hoard** from
Applications to the Bin. Your settings, library, sign-ins and tags are in `~/Library/Application Support/Hoard`, and
stay unless you delete them (see [Where Hoard keeps things](Where-Hoard-Keeps-Things#deleting-everything)).

## Linux

Hoard for Linux is for x86_64 (Intel and AMD) computers, three ways:

- **The AppImage** (`Hoard-<version>-linux-x86_64.AppImage`): one file that runs on most Linux systems. Make it
  executable (in its Properties, or `chmod +x Hoard-<version>-linux-x86_64.AppImage`) and open it. It updates
  itself.
- **The .deb** (`Hoard-<version>-linux-amd64.deb`), for Debian, Ubuntu and their relatives: open it with your
  software centre, or `sudo apt install ./Hoard-<version>-linux-amd64.deb`. It updates itself, asking for your
  password to install the update.
- **The Flatpak** (`Hoard-<version>-linux-x86_64.flatpak`), below: sandboxed, and the way Hoard 5.1 comes.

Hoard's window uses WebKitGTK, which the .deb installs with it, the AppImage carries inside it, and the Flatpak
gets with its runtime. Each keeps its settings, library, sign-ins and tags in
`~/.local/share/Hoard`, like every Linux Hoard, so a library from another carries over and Hoard for Unity finds it.
Your sign-ins need a keyring: GNOME Keyring, KeePassXC with its Secret Service turned on, or KWallet.

### The Flatpak

Most desktop Linux systems have Flatpak already; if yours doesn't, see [flatpak.org/setup](https://flatpak.org/setup/).

1. Download **`Hoard-<version>-linux-x86_64.flatpak`** from
   [the release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases).
2. Open it with your software centre (GNOME Software, KDE Discover), or install it from a terminal:

   ```
   flatpak install --user Hoard-<version>-linux-x86_64.flatpak
   ```

   Hoard runs on the GNOME runtime, which Flatpak gets from [Flathub](https://flathub.org/). If it says it
   can't find `org.gnome.Platform`, add Flathub once and try again:
   `flatpak remote-add --if-not-exists --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
3. Open **Hoard** from your applications menu (or `flatpak run io.github.soloflighter1010.Hoard`). It opens in
   its own window, and a short setup assistant walks you through the rest: see [Getting started](Getting-Started).

The Flatpak may use the network, show its window, your keyring (for your sign-ins) and your home folder and
removable drives (for your downloads folder), and nothing else. Hoard's browser (Chromium, about 150 MB) is
downloaded once, into `~/.var/app/io.github.soloflighter1010.Hoard/cache`.

**Updating:** when **Settings › Hoard updates** says there's a newer version, download that version's `.flatpak` and
install it as above; it replaces the old one. **Uninstalling:** `flatpak uninstall io.github.soloflighter1010.Hoard`
(or your software centre). That leaves your settings and library; see
[Where Hoard keeps things](Where-Hoard-Keeps-Things#deleting-everything) to remove those too.

## From source (Windows, macOS, Linux)

1. Install [Python 3.10 or newer](https://www.python.org/downloads/).
2. Download `Hoard-<version>.zip` from the
   [latest release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest) and extract it
   somewhere of your own.
3. Run `Hoard.bat` (Windows) or `./run.sh` (macOS and Linux).

The first run sets up a private Python environment in that folder, checking every package against a fingerprint
recorded in advance, so a tampered package won't install. On Windows, setup also makes the folder changeable
only by your account.

From source, Hoard opens in your web browser rather than its own window. Quit it from **Settings**, then
**Quit Hoard**, or just close its pages: it stops by itself a few minutes after the last one closes.

Store sign-ins use Microsoft Edge on Windows, and Hoard's own browser elsewhere or without Edge: a copy of
Chromium at a fixed version, about 150 MB, downloaded once.

- **macOS** asks once whether Hoard's browser may use the Keychain. Choose **Always Allow**.
- **Linux** needs a keyring to protect your sign-ins: GNOME Keyring, KeePassXC with its Secret Service turned
  on, or KWallet. See [Stores](Stores#signing-in) for computers without a desktop. If the browser won't
  start, run `.venv/bin/python -m playwright install-deps chromium` in Hoard's folder.

## Coming from Hoard 1.x

Your sign-ins and tags carry over by themselves. The setup assistant's **Used Hoard before?** step brings over
your library list and downloads folder: choose the folder you ran 1.x from. From the command line, that's
`hoard-cli migrate <folder>`.
