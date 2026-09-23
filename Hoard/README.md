# Hoard

Everything you own on **Booth**, **Gumroad**, **Jinxxy** and **Payhip**, in one searchable page.
Nothing is downloaded: it reads each store's purchase list with your login and links you back to
each store's download page.

## Setup

**Windows:** double-click `Setup.bat` once (it installs a private Python environment and the browser
used for store sign-ins, about 150 MB), then double-click `Hoard.bat`. Keep its window open
while you use the library.

**Linux / macOS:** run `./setup.sh`, then `./run.sh`.

The library opens at http://127.0.0.1:8766. Open **Stores**, choose **Sign in** for each store,
sign in in the browser window that opens, then close that window. The store refreshes on its own.
After that, **Refresh all stores** picks up new purchases.

Everything also works from a terminal by passing a command to the launcher:
`"Hoard.bat" login booth`, `"Hoard.bat" refresh`, `"Hoard.bat" import page.mhtml`.

### Your sign-ins

Sign-ins are encrypted by your operating system and kept in a private folder outside this one, shared
with Hoard Downloader, so you sign in once for both. **Sign out** on a store's row in **Stores**, or
**Sign out of every store** at the bottom, removes Hoard's copy; your library list stays. The main
README's "Your sign-ins" section has the details.

While one tool is using your sign-ins (a download running, say), the other waits: a refresh then says
the sign-ins are in use, and you can try again when the other tool has finished.

## Using the library

- Search matches names, creators and tags. Press `/` to jump to the search box.
- Filter by store, suggested tags (words shared by several item names) and creator.
  The address bar keeps your filters, so you can bookmark a view.
- Click an item for its links. **Open download page** goes to that item on its store.
  Booth items also list their files, each with its own download link.
- When you own the same product on more than one store, its details say so, and
  **Show all copies** lists them side by side. The corner mark on each tile shows the store.
- Gifts (Booth) and archived purchases (Gumroad) are labelled on their tiles.

## How each store is read

| Store | Where it reads | Notes |
|---|---|---|
| Booth | Your library and gifts pages | File links open in your normal browser, so be signed in to Booth there too. |
| Gumroad | Your library, including archived purchases | Read from Gumroad's page data, so it's the most reliable. |
| Jinxxy | Your inventory page | No buyer API; reads the page the way you see it. |
| Payhip | Your customer library | Needs your account in **Customer** mode (Account menu, Use Payhip as). Only purchases attached to your account appear; for older email-only purchases, open the download link from the receipt and choose **Get Started** to add it. |

### When a store blocks the automatic refresh

Some stores (Payhip, for one) put up a bot check for the automated browser. When that happens,
**Stores** says so and your previous list is kept. Import the page from your normal browser instead:

1. Open your library on that store in your usual browser and scroll to the bottom so everything loads.
2. Press Ctrl+S and save it as **Webpage, Single File** (`.mhtml`). "HTML only" works too, but the
   single file keeps the thumbnails.
3. In **Stores**, choose **Import page** on that store's row, or drop the file anywhere on the library.

The file is read on your computer; nothing is fetched from the store. If your library has several
pages, import each one; imports add to what's there rather than replacing it. **Refresh all stores**
leaves imported stores alone, and that store's own **Refresh** button still tries the automatic way.
From the terminal: `"Hoard.bat" import "Payhip library.mhtml"`. Booth and Jinxxy pages can be
imported the same way if they ever block it too.

### Fixing a reader

Jinxxy and Payhip were written without access to a signed-in page. If either finds nothing or
reads names wrong, run:

```
"Hoard.bat" debug jinxxy      (or payhip, booth)
```

That saves a screenshot, the page, its links and what the reader extracted into `debug/`.
For Payhip you can also set `payhip.library_url` in `config.json` to your library's address.
The debug files show your purchases, so skim them before sharing.

A refresh that fails, or suddenly finds nothing, keeps that store's previous list and shows why in
**Stores**, so a bad refresh never empties your library.

## Files

- `library.json`: your combined library (refresh rewrites it per store)
- `.cache/thumbs/`: store images, fetched once and kept for offline browsing
- Your sign-ins aren't here; see "Your sign-ins" above.

`--port` changes the port. `--host 0.0.0.0` lets other devices on your network browse it;
signing in and refreshing still only work on the PC running it.
