# Security

## Reporting a problem

Please don't report security problems in a public issue. Instead, open the repository's **Security**
tab on GitHub and choose **Report a vulnerability**. That report is visible only to the maintainer.

Include what you found, how to reproduce it, and which version you used. Expect a first reply within a
week. Fixes are released as a new version, and the changelog credits you unless you'd rather it didn't.

## Supported versions

Only the latest release receives security fixes. The tools don't update themselves, so check the
releases page now and then.

## What Hoard protects against, and what it can't

Hoard is built to keep your store sign-ins and library safe from:

- other people and other accounts on the same computer
- someone who copies Hoard's folders, a backup or a synced folder to another computer
- websites you visit, including store pages and pages you import, trying to reach Hoard or your network
- other devices on your network, and anyone watching network traffic
- tampered or swapped release downloads and dependencies

It can't fully protect against:

- **Malware already running as you.** Anything running as your user account can do what you can,
  including using a signed-in store while Hoard has it open. Hoard limits how much there is to take:
  it never keeps store passwords, keeps each store's sign-in separate, and holds copied cookies only in
  memory for the length of a download. Keep your computer clean; no desktop app can do this part for you.
- **Someone with administrator access to your computer,** or control of the operating system itself.
- **The stores themselves.** Problems in their websites or accounts are theirs to fix.

## How Hoard protects you

**Your sign-ins**
- Hoard never sees or stores your store passwords. You sign in on the store's own page, in a browser
  window that belongs to Hoard alone, and only the store's session cookies are kept.
- Each store's sign-in is kept separately, in your user account's private app-data folder, never in
  the program folder. One store's pages never share a browser with another store's sign-in.
- The saved cookies are encrypted by your operating system: your Windows account, the macOS Keychain,
  or a Linux keyring (the Secret Service or KWallet). On Linux, Hoard won't save sign-ins at all without
  a keyring, and after you sign in it checks that the cookies really were encrypted with it. Only if you
  set `"allow_unprotected_signins": true` (meant for computers without a desktop) are they kept
  protected by folder permissions alone.
- One program at a time can use a store's sign-in.
- **Sign out** asks the store to end the session where Hoard can (Gumroad has a sign-out address;
  for the others Hoard uses the store's own sign-out button), deletes that store's saved sign-in, checks
  that no copy of it is left anywhere, and tells you what it did.
- A copied session cookie in a settings file or environment variable is never read.

**The tools' pages**
- Served only to your own computer by default. To use them from other devices you need HTTPS (your
  own certificate) or to say the connection is already encrypted, such as over Tailscale; other devices
  also need an access key. Signing in, refreshing, signing out, changing tags and opening folders only
  work on the computer running the tool.
- Sent with a strict Content-Security-Policy, so only the page's own script can run, and with headers
  that stop other websites from embedding the page or reading its responses. Everything else Hoard
  serves (data, images, fonts) is sandboxed, so it can never run as a page.
- Text and links from store pages, and from pages you import, are treated as untrusted: text is escaped,
  and only plain web addresses become links. Product images are only fetched from public internet
  addresses, and the connection goes to exactly the address that was checked, so a name that changes
  its answer (DNS rebinding) can't redirect it to your network. Only ordinary raster images (JPEG, PNG,
  WebP, GIF, AVIF) are kept; SVG never is.
- Imported pages are read in a browser with scripts removed and all network access blocked.

**Files and data**
- File and folder names from stores are cleaned before anything is saved, including invisible
  characters such as right-to-left overrides, which could make a program's name look like a picture's.
  Downloads only go inside the download folder you chose, and the downloader only follows a store's
  download links when they point at that store's own website.
- Every path read back from a data file (`_manifest.json` and the rest) must be a plain relative path
  that stays inside its folder, even through a symlink. Anything else is ignored, so a tampered record,
  say on a shared drive, can't make a sync write elsewhere.
- Data files are read with size limits and checked entry by entry. A damaged one is kept aside under a
  new name, never silently overwritten, and the tool carries on.
- Files are written through a new temporary file and swapped into place, so a symlink planted where a
  file goes is replaced rather than followed, and nothing reads half a file.
- Tags may only contain letters, digits, spaces and a little punctuation, so they're safe wherever they
  end up. Your tag file is private to your account and has hard limits on its size.
- `catalog.json`, `tags.json` and `asset.json` promise clean text, plain relative paths and store-only
  links, and are checked against that before they're written ([docs/DATA-FORMATS.md](docs/DATA-FORMATS.md)).

**Links and seals**
- Hoard never downloads from a link stored in a data file. Every download address comes from the
  store itself, at the time of the sync.
- Every link you can open (**Open on Booth**, **Open download page**, a creator's page) must be an https
  address on that item's own store, checked when data is read, when it's written, and again in the page.
  An edited record can't send you to a lookalike sign-in page.
- Each data file the tools write (manifests, `catalog.json`, `tags.json`, `asset.json`, Hoard's library
  list) is sealed with a keyed signature (HMAC-SHA256) using a random key private to your user account.
  If something else edits a file, the tools notice when they next read it: they keep the data but not its
  links, tell you, keep a copy of the changed file, and fetch the links from the store again on the next
  sync or refresh. Removing the seal doesn't hide an edit.
- `python asset_dl.py verify` checks every data file in the download folder and rebuilds the catalog files.
- The seal can't stop malware already running as you, which could read the key too (see above).
- Setup limits who can change the program folder to your account (plus Windows itself and
  administrators), so no other account can swap in code that would run with your sign-ins. For the
  same reason, keep Hoard in a folder of your own, such as one inside your user folder.

**Dependencies and releases**
- Every Python package is pinned to an exact version and checked against a recorded hash when Setup
  installs it. That also fixes which Chromium build gets installed.
- Release zips are built by GitHub Actions from the tagged source, using actions pinned to exact
  commits, and contain only listed files, so personal files can't slip in.
- Each release includes `SHA256SUMS.txt`. Once the repository is public, each zip also carries a signed
  build provenance record. Check a download with the GitHub CLI:
  `gh attestation verify Hoard-1.6.0.zip -R Soloflighter1010/Hoard-Asset-Manager`
- Automated security tests (`tests/`) run on every change.
