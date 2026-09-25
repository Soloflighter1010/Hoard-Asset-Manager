Hoard reads your purchases from **Booth**, **Gumroad**, **Jinxxy** and **Payhip**, signed in as you. Everything
here happens in the **Stores** panel (top right).

## The Stores panel

Each store you use has a row:

- **Sign in** opens the store's sign-in page in Hoard's own window. Sign in as usual, then close the window.
- **Refresh** reads what you've bought. Nothing is downloaded.
- **Download** keeps local copies of everything new from that store. See [Downloads](Downloads).
- **Import page** (Booth, Jinxxy and Payhip) adds a library page you saved from your usual browser, for when a
  store blocks the automatic refresh. See [Importing a saved page](#importing-a-saved-page).
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

Payhip has no single library: your purchases live in each shop you bought from.

- **Add your shops** in **Settings** under **Payhip shops**, one per line. A shop's address is in your purchase
  email: either its own domain (`myshop.store`) or `payhip.com/ShopName`.
- A shop on payhip.com lists your purchases from every shop, so one is often enough. Shops on their own
  domains that turn up in your library are offered in **Stores**: choose **Review** to add the ones that are
  yours.
- **Payhip checks for automated browsers.** Refreshing and downloading from Payhip happen in a visible window,
  so if a check appears, complete it there and Hoard carries on. It waits up to 3 minutes.
- **If Payhip still won't let Hoard in:**
  - To read your purchases, save your library page from your usual browser and use **Import page** (below).
    From the command line, `hoard-cli sync --store payhip --payhip-page <saved file>` reads it and downloads.
  - Products Hoard couldn't download are listed in `Payhip/_download-yourself.html` in your downloads folder,
    each with its download page and the folder its files belong in. Save the files there yourself, and the
    next sync records them. That page only ever links to Payhip and your own shops.

## Importing a saved page

If a store blocks the automatic refresh:

1. Open your library on the store's website, in your usual browser.
2. Scroll to the bottom, so everything has loaded.
3. Press **Ctrl+S** and save it as **Webpage, Single File** (`.mhtml`), or as a web page (`.html`).
4. In **Stores**, choose **Import page** on that store's row, or drop the file on Hoard's window.

Imported pages are read with scripts switched off and nothing allowed to load, so a saved page can't do
anything on your computer. A Payhip shop named inside an imported page is only added to your shops after you
confirm its exact address.

## When a store can't be reached

Hoard says so ("Couldn't reach booth.pm, so Booth wasn't refreshed") and leaves your saved library and
downloads exactly as they were. Try again when you're connected.

Stores change their websites now and then, and a store's reader can stop working until Hoard is updated. If
one isn't read correctly, see [Troubleshooting](Troubleshooting#a-store-isnt-read-correctly).
