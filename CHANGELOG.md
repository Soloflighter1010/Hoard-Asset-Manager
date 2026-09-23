# Changelog

## 1.1.0

### Hoard Downloader
- Downloads Booth purchases and gifts. Files come straight from Booth, interrupted downloads resume,
  and new versions a creator uploads are downloaded and listed as updated.
- Downloads Payhip purchases in a visible browser window, waiting while you complete Payhip's bot check.
  If Payhip won't let it in, it can read your library from a page you saved, and lists the rest in
  `Payhip/_download-yourself.html`; files you save there are recorded on the next sync.
- Stores you haven't signed in to are skipped instead of reported as failures.
- The menu has a single **Sign in to a store** entry covering all four stores.
- The downloads browser shows Booth and Payhip.

### Hoard
- No changes; version raised to match Hoard Downloader.

## 1.0.0

First release.

### Hoard
- One searchable page for everything you own on Booth, Gumroad, Jinxxy and Payhip, with store,
  tag and creator filters and links to each item's download page.
- Sign in and refresh each store from the page. A failed refresh keeps that store's previous list.
- Products you own on more than one store are pointed out, with a view of every copy.
- Booth items list their files with direct download links; Booth gifts and archived Gumroad
  purchases are labelled.
- Import a library page saved from your own browser, for stores that block automated browsers
  (Payhip today).

### Hoard Downloader
- Downloads everything you own on Gumroad and Jinxxy into one folder per product, with a separate
  manifest per store so nothing is fetched twice. Interrupted Gumroad downloads resume.
- Re-running only fetches new or changed files, and the summary lists files a creator has updated.
- Suggests tags from words shared across asset names.
- Includes a read-only library browser with thumbnails, search, filters, and buttons to open folders.
