# Security

## Reporting a problem

Please don't report security problems in a public issue. Instead, open the repository's **Security**
tab on GitHub and choose **Report a vulnerability**. That report is visible only to the maintainer.

Include what you found, how to reproduce it, and which version you used. Expect a first reply within a
week. Fixes are released as a new version, and the changelog credits you unless you'd rather it didn't.

## Supported versions

Only the latest release receives security fixes. The tools don't update themselves, so check the
releases page now and then.

## How Hoard protects you

**Your sign-ins**
- Kept in your user account's private app-data folder, never in the program folder, and encrypted by the
  operating system: your Windows account, the macOS Keychain, or the Linux keyring. On a Linux machine
  without a keyring, the folder is locked to your user account instead.
- Used by one tool at a time, and removable at any time with **Sign out**.

**The tools' pages**
- Served only to your own computer by default. On your network, other devices need an access key, and
  signing in, refreshing, signing out and opening folders stay limited to the computer running the tool.
- Sent with a strict Content-Security-Policy, so only the page's own script can run, and with headers
  that stop other websites from embedding the page or reading its responses.
- Text and links from store pages, and from saved pages you import, are treated as untrusted: text is
  escaped, only plain web addresses become links, and product images are only fetched from public
  internet addresses, never from your home network or your own computer.
- Imported pages are read in a browser with scripts removed and all network access blocked.

**Files**
- File and folder names from stores are cleaned before anything is saved, and downloads only go inside
  the download folder you chose.

**Releases**
- Release zips are built by GitHub Actions from the tagged source and contain only listed files, so
  personal files can't slip in. Each release includes `SHA256SUMS.txt` for checking your download.

## Out of scope

Problems in the stores' own websites, and anyone who already has access to your signed-in computer
account.
