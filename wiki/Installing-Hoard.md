Hoard is a Windows app. It also runs from source on Windows, macOS and Linux.

## Windows

1. Download **`Hoard-Setup-<version>.exe`** from the
   [latest release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest) and run it.
   It installs for you only, with no administrator prompt, into `%LOCALAPPDATA%\Programs\Hoard`, and adds
   Hoard to the Start menu (a desktop icon is optional).
2. Windows may say **"Windows protected your PC"**, because Hoard isn't code-signed yet (a certificate costs
   money every year). Choose **More info**, then **Run anyway**. To be sure the file is genuine first, see
   [Checking a download](#checking-a-download).
3. Open **Hoard** from the Start menu. It opens in its own window, and a short setup assistant walks you
   through the rest: see [Getting started](Getting-Started).

Closing the window quits Hoard. A download in progress stops, and carries on from where it was next time.

**Prefer no installer?** `Hoard-<version>-windows.zip` is the same app. Extract it anywhere of your own (a
folder in your user folder is best) and run `Hoard.exe`.

**Hoard's window** uses Microsoft Edge WebView2, which is part of Windows 11 and kept up to date on Windows 10.
Without it, Hoard says so and opens in your web browser instead; quit it from **Settings**, then **Quit Hoard**.

### Updating

In **Settings**, under **Updates**, choose **Check now**. When there's a newer version, **Update to** it: Hoard
downloads its installer from the release on GitHub, checks it, closes (a download in progress resumes next time),
installs it and opens again. It only runs an installer whose SHA-256 matches both the release's
`SHA256SUMS-windows.txt` and the checksum GitHub lists for the file; one that doesn't is deleted. Hoard won't
update in the middle of a refresh or download: wait for it, or **Stop** it.

**Check for updates automatically** (off unless you turn it on) makes Hoard ask GitHub once a day, when it
starts; a newer version then shows as **Update to** at the bottom of the page. A check sends GitHub nothing but
the request itself: see [Security and privacy](Security-and-Privacy).

Hoard installs updates itself only when it was installed with `Hoard-Setup`. The portable zip, and Hoard run
with Python, say there's a newer version and link to it. You can always run the newer setup yourself too.
There's no need to uninstall first, and an update replaces the program files completely, so nothing from the
old version lingers.

Your settings, library, sign-ins and tags live in Hoard's app-data folder (`%LOCALAPPDATA%\Hoard`) and your
files in your downloads folder, so installing, updating and uninstalling never touch them.

### Uninstalling

Use **Settings › Apps** in Windows, like any other app. That removes the program only. To remove everything
Hoard keeps, see [Where Hoard keeps things](Where-Hoard-Keeps-Things#deleting-everything).

### Checking a download

Every release is built by GitHub Actions straight from this repository, with a signed record of how it was
built. With the [GitHub CLI](https://cli.github.com/):

```
gh attestation verify Hoard-Setup-<version>.exe -R Soloflighter1010/Hoard-Asset-Manager
```

Each release also lists checksums: `SHA256SUMS-windows.txt` for the installer and the Windows zip, and
`SHA256SUMS.txt` for the source zip. In PowerShell, `Get-FileHash .\Hoard-Setup-<version>.exe` prints the one
to compare.

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
