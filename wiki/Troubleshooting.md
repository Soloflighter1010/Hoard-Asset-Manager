Look for the message you're seeing. If it isn't here, see [Reporting a problem](#reporting-a-problem).

## Opening Hoard

### "Hoard didn't recognise this page"

The page doesn't have this run's access key. That happens with an old bookmark, an address copied from before
Hoard restarted, or a one-time link opened twice. Open Hoard again from the Start menu (it brings its window to
the front), or, if you started it as a server, open the address it printed. See
[Using Hoard on other devices](Using-Hoard-on-Other-Devices#the-access-key).

### "Hoard is already running, but isn't answering"

Another copy of Hoard is open but not responding. Close it (in Task Manager, end **Hoard**), or restart your
computer, then open Hoard again.

### "Hoard's window couldn't open on this PC"

Hoard's window needs Microsoft Edge WebView2. Hoard opens in your web browser instead, and everything works
there; quit it from **Settings**, then **Quit Hoard**. To get the window back, install the WebView2 Runtime from
Microsoft, then open Hoard again.

### "Hoard isn't running. Open it again."

The page lost Hoard's server: Hoard was quit or closed. Open Hoard again.

### "Windows protected your PC"

Windows says this about apps that aren't code-signed yet. Choose **More info**, then **Run anyway**. To check the
file first, see [Installing Hoard](Installing-Hoard#checking-a-download).

## Signing in

### Signing in with Google, Discord or X doesn't work

Some stores' sign-in buttons refuse browsers they don't know. Set a password for your store account in your usual
browser, then sign in with that in Hoard's window. See
[Getting started](Getting-Started#signing-in-without-your-saved-passwords) for finding saved passwords.

### "Not signed in to Booth", or "session expired"

The store ended Hoard's sign-in, as stores do from time to time. In **Stores**, choose **Sign in** on that store
again.

### "The other Hoard tool is using your ... sign-in right now"

Only one program at a time can use a store's sign-in: a second copy of Hoard, or a `hoard-cli` command, is using
it. Wait for that to finish, or close it.

### Sign-ins aren't saved (Linux)

Hoard only keeps sign-ins it can protect, and that needs a keyring: GNOME Keyring, KeePassXC with its Secret
Service turned on, or KWallet. Install and unlock one, then sign in again. See [Stores](Stores#signing-in).

### "Hoard's browser isn't installed yet"

Open **Settings**, choose **Set up Hoard again**, and choose **Install Hoard's browser** (about 150 MB, once). If
the message names a browser you chose in **Settings**, choose another there instead. On Linux, if the browser
still won't start: `.venv/bin/python -m playwright install-deps chromium` in Hoard's folder.

## Stores

### A store isn't read correctly

Stores change their websites, and a reader can stop working until Hoard is updated.

1. Check you're on the [latest version](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases/latest).
2. Meanwhile, you can usually import pages you saved yourself: see
   [Stores](Stores#importing-saved-pages).
3. Run `hoard-cli debug <store>` (or `hoard-cli probe jinxxy`). It saves the library page and a summary of what
   Hoard read into the `debug` folder in Hoard's app-data folder, with personal details removed.
4. [Open an issue](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues) and attach it, **after reading
   it**: it still shows what you've bought, and GitHub issues are public.

### Payhip keeps showing a bot check

Complete it in the window Payhip opens in, and Hoard carries on (it waits up to 3 minutes). If Payhip still won't
let Hoard in, save each shop's library page from your usual browser and import them all instead. See
[Stores](Stores#payhip).

### Payhip shows nothing, or only some of what I bought

Payhip keeps purchases in each shop, each on pages of 15, so Hoard only sees the shops you've added, or the
pages you've imported. Import every page of every shop's library (**Import a folder** takes them all at once),
or add your shops in **Settings** under **Payhip shops** and refresh.

### "Hoard doesn't download from Payhip"

That's right: Hoard lists what you bought on Payhip, and you download it from Payhip. Open the product in your
library and choose **Open download page**. See [Stores](Stores#payhip).

### Some pages weren't imported

When importing ends, Hoard lists each page it couldn't use, and why:

- **"couldn't tell which store this page is from":** the page wasn't saved from a store's library, or was saved
  as text only. Save the library page itself as **Webpage, Single File**, or import it from that store's row
  in **Stores** (**Import pages**), which tells Hoard the store.
- **"no ... items in that page":** the page was saved before it finished loading. Scroll to the bottom first,
  then save it again.
- **A Payhip shop you didn't add:** Hoard only adds a shop when you confirm it. Import the page again and choose
  **OK** when Hoard asks, or add the shop in **Settings**.

### itch.io: "didn't accept the API key"

The key was mistyped or cut short when it was copied, or it was deleted on itch.io. Make a new one on itch.io
(Settings, API keys), then choose **Change API key** on itch.io's row in **Stores**. See [Stores](Stores#itchio).

### itch.io skips some of my files

Files the creator marked as a program for Windows, macOS, Linux or Android are game builds, skipped unless you
turn off **Skip game builds** under itch.io in **Settings**. Files kept on another website (the summary says
so) are downloaded from there, by you. A project from a bundle only counts once you've claimed it on itch.io.

### "Booth turned the direct download away"

Nothing to do: Hoard carries on through its browser, by itself.

### "Couldn't reach booth.pm, so Booth wasn't refreshed"

You're offline, or the store is down. Your saved library and downloads are unchanged; try again later.

## Downloads

### "The download stopped at ... bytes; the next sync resumes it"

The connection ended before the file was complete. Nothing is lost: the next sync picks up where it stopped.

### A download keeps failing, or is skipped

The summary at the end of each download gives the reason for everything that failed or was skipped. On Gumroad,
"no download page" means a refund or a membership that ended, and files Gumroad only streams can't be downloaded.
Products you removed from your library are skipped on purpose.

### A record "was changed by something other than Hoard"

Something edited one of Hoard's records. Hoard kept a copy of the changed file, stopped trusting its links, and
fetches them from the store again on the next sync. Run `hoard-cli verify` to check everything. If you share the
downloads folder between computers, copy `integrity.key`: see
[Where Hoard keeps things](Where-Hoard-Keeps-Things#one-downloads-folder-two-computers).

### "Hoard's saved list was saved by Hoard on another computer"

Your library list came from another computer's Hoard (a copied app-data folder, say). Its links and pictures are
hidden until you refresh your stores. To keep them, copy that computer's `integrity.key` too.

### A file "is damaged" and was "kept as ...damaged-..."

Hoard couldn't read that file, set it aside rather than overwriting it, and carried on. A refresh or sync
rebuilds what it held.

## The hidden library

- **Forgot your PIN?** Choose **Forgot your PIN?** and enter your 6 recovery words to set a new one. Nothing is
  lost.
- **Lost the words too?** The only way out deletes the hidden items from Hoard's list, without showing them.
- **"Too many wrong tries. Try again in ... seconds."** After five wrong tries, each further try waits longer
  (30 seconds, doubling, up to an hour), even if Hoard restarts.

See [Your library](Library#the-hidden-library).

## Reporting a problem

1. Note your version (bottom of every page) and what you did.
2. Look in `logs/hoard.log` in Hoard's app-data folder (see
   [Where Hoard keeps things](Where-Hoard-Keeps-Things)) for the error.
3. [Open an issue](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues) with both. Leave out anything
   personal: issues are public.

Found a security problem? Report it privately instead: see
[Security and privacy](Security-and-Privacy#reporting-a-security-problem).
