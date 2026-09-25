Hoard reads your purchases from **Booth**, **Gumroad**, **Jinxxy**, **Payhip** and **itch.io**, signed in as you
or from pages you save yourself, and keeps copies of your files from all of them but Payhip. Everything here
happens in the **Stores** panel (top right).

## The Stores panel

Each store you use has a row:

- **Sign in** opens the store's sign-in page in Hoard's own window. Sign in as usual, then close the window.
- **Refresh** reads what you've bought. Nothing is downloaded.
- **Download** keeps local copies of everything new from that store. See [Downloads](Downloads). Payhip has
  none: Hoard lists what you bought there, and you download it from Payhip (see [Payhip](#payhip)).
- **Import pages** (Booth, Jinxxy, Payhip and itch.io) adds library pages you saved from your usual browser,
  any number at once: for when a store blocks the automatic refresh, or you'd rather not sign in. See
  [Importing saved pages](#importing-saved-pages).
- **Sign out** signs you out of that store in Hoard.

At the top, **Refresh all stores** and **Download everything new** do every store at once. **Sync** (top
right, outside the panel) does both in one go: it reads what you own, then downloads anything new.

Hoard only shows and reads the stores you use. Switch stores on or off in [Settings](Settings).

## Signing in

You sign in to each store once, in a browser window that belongs to Hoard alone, never your everyday browser.
The Library and Downloads share those sign-ins.

- **Hoard never sees your password.** You type it into the store's own page. Hoard only keeps the "stay
  signed in" pass the store hands out, the same thing your browser keeps. For help finding your saved
  passwords, see [Getting started](Getting-Started#signing-in-without-your-saved-passwords).
- **Each store is kept separate,** in its own folder, and encrypted by your operating system: your Windows
  account, your Mac's Keychain, or your Linux keyring. Copying Hoard's files to another computer doesn't give
  anyone access.
- **One program at a time** can use a store's sign-in. If Hoard is busy with a store (or the command line is
  using it), wait for that to finish.
- **Linux without a keyring:** Hoard won't save sign-ins unless it can protect them. Install and unlock GNOME
  Keyring, KeePassXC (with its Secret Service on) or KWallet, then sign in again. On a computer with no desktop
  at all, such as a NAS, you can allow it with `"allow_unprotected_signins": true` in Hoard's `config.json`;
  they're then protected only by being readable by your user account alone.

## Signing out

**Sign out** asks the store to end the session where Hoard can, deletes that store's saved sign-in, checks no
copy of it is left anywhere, and tells you what it did. That store's items leave your library too, so the next
person to sign in on this computer never sees what you bought. Your downloaded files stay where they are.

**Sign out of every store** does the same for all of them.

## Booth

- Hoard reads your library, your gifts and your free downloads. Gifts and free downloads can be switched off
  in [Settings](Settings).
- Files come from each item's download buttons. If Booth turns Hoard's direct download away, Hoard carries on
  through its browser instead, by itself.
- Booth signs you in through pixiv.

## Gumroad

- Hoard reads your library, including purchases you archived on Gumroad. Those start in your **Archive** (see
  [Your library](Library#archive-removed-and-hidden)); leave them out altogether in [Settings](Settings).
- A purchase with no download page (refunded, or a membership that ended) is skipped and listed in the
  summary. So are files Gumroad only streams.

## Jinxxy

- Hoard reads your inventory, then downloads each file by clicking its download button in the browser,
  because that's the only way Jinxxy hands files out.
- Jinxxy shows its own banner where a product has no picture. Hoard doesn't keep that banner as the
  product's picture.

## Payhip

Hoard **lists** what you bought on Payhip, and doesn't download it: Payhip's check for automated browsers made
downloading unreliable. Open a product in your library and choose **Open download page** to get its files from
Payhip. (Files earlier versions of Hoard downloaded from Payhip stay where they are, in [Downloads](Downloads).)

Payhip has no single library: your purchases live in each shop you bought from, on that shop's own library page
(`<shop>/b-account`), and a page shows 15 products at a time. There are two ways to read them:

- **Import the pages** (the easy way). In your usual browser, open each shop's library page (the shop's
  address followed by `/b-account`, such as `myshop.store/b-account`), sign in there if it asks, and save it
  with **Ctrl+S** as **Webpage, Single File**, and each of its pages if it has several. Then choose **Import pages** on Payhip's row, or **Import a
  folder** with all of them in it. See [Importing saved pages](#importing-saved-pages). A shop that isn't in
  your list yet is added when you confirm it: Hoard asks once for all of them, showing each address.
- **Sign in and refresh.** Add your shops in **Settings** under **Payhip shops**, one per line: a shop's
  address is either its own domain (`myshop.store`) or `payhip.com/ShopName`. **Sign in** then opens a tab for
  each shop. Payhip checks for automated browsers, so refreshing happens in a visible window: if a check
  appears, complete it there and Hoard carries on. It waits up to 3 minutes.

A shop on payhip.com lists your purchases from every shop, so one is often enough. Shops on their own domains
that turn up in your library are offered in **Stores**: choose **Review** to add the ones that are yours.

## itch.io

- Hoard reads your itch.io library: what you bought, and what you claimed from bundles or "name your own
  price" projects. A bundle's projects only count once you've claimed them on itch.io.
- Each project's files come from its download page, by clicking each file's Download button in Hoard's
  browser, as you would. A file is downloaded again when itch.io shows a new version of it (a new name or size).
- **Game builds are skipped:** files the creator marked as a program for Windows, macOS, Linux or Android. That
  keeps the games in your library from filling your drive, and VRChat assets are hardly ever marked that way.
  To download them too, turn off **Skip game builds** under itch.io in [Settings](Settings). Files a creator
  keeps on another website (a Google Drive link, say) are skipped as well, and listed in the summary.
- A download page's address holds a key that opens it for anyone, so Hoard keeps it like a sign-in: only in
  its private library list, and never in the catalog or troubleshooting files.

## Importing saved pages

Instead of signing in, or when a store blocks the automatic refresh:

1. Open your library on the store's website, in your usual browser.
2. Scroll to the bottom, so everything has loaded.
3. Press **Ctrl+S** and save it as **Webpage, Single File** (`.mhtml`), or as a web page (`.html`). If your
   library has more pages (or, on Payhip, more shops), save each one.
4. In **Stores**, choose **Import pages** and pick them all, or **Import a folder** and pick the folder you saved
   them in. You can also drop the files, or their folder, on Hoard's window.

Hoard reads them all together and shows what came of each page: how many items it found, and why a page
couldn't be read (a page from somewhere else, say), without that stopping the rest. Importing adds to what's
there, so importing a page again, or the pages in any order, is fine.

Imported pages are read with scripts switched off and nothing allowed to load, so a saved page can't do
anything on your computer. A Payhip shop named inside an imported page is only added to your shops after you
confirm its exact address.

From the command line: `hoard-cli import <files or folders>`, as in [Command line](Command-Line).

## When a store can't be reached

Hoard says so ("Couldn't reach booth.pm, so Booth wasn't refreshed") and leaves your saved library and
downloads exactly as they were. Try again when you're connected.

Stores change their websites now and then, and a store's reader can stop working until Hoard is updated. If
one isn't read correctly, see [Troubleshooting](Troubleshooting#a-store-isnt-read-correctly).
