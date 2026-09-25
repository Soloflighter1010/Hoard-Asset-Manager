In plain words, here's what protects you. The technical details are in
[SECURITY.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/SECURITY.md), and what Hoard keeps
is in [PRIVACY.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/PRIVACY.md).

## Your store accounts

- **Hoard never sees your passwords.** You sign in on the store's own page. Hoard only keeps the "stay signed
  in" pass the store hands out, the same thing your browser keeps.
- **That pass is locked by your computer.** It's encrypted with your Windows account, your Mac's Keychain or your
  Linux keyring, so copying Hoard's files to another computer doesn't give anyone access.
- **Each store is kept separate.** Your Booth sign-in and your Gumroad sign-in never mix.
- **Signing out really signs you out**, and that store's items leave your library. See
  [Stores](Stores#signing-out).

## Your computer

- **Only Hoard's own window can use Hoard.** Every request for your library, downloads, pictures or an action
  needs a key that's new each time Hoard starts, even from your own computer, so other programs and other
  people's accounts on a shared computer can't use it. Hoard opens its window with a one-time link that the page
  trades for the key, so the key never shows up where another program could read it.
- **Sharing with your other devices is off** until you switch it on, and then needs a secure connection and the
  key. See [Using Hoard on other devices](Using-Hoard-on-Other-Devices).
- **Websites can't use Hoard against you.** Other sites can't read Hoard's pages, press its buttons, or show it
  inside their own pages.
- **Nothing from a store can run on your computer.** Names, links and pictures from stores are shown as plain
  text and ordinary images, never as code. Saved pages you import are read with scripts switched off.
- **Downloads only go where they should.** Every store request is checked at each step: secure connections only,
  never to your computer or home network, and your store sign-in only ever goes to that store, never to the
  servers that host its files.

## Your files

- **Downloads stay in your downloads folder,** whatever a store sends or a record says.
- **File names can't pretend to be something else.** Invisible characters that could make a program's name look
  like a picture's are removed.
- **Store buttons only go to the real store.** An **Open on Booth** button can only ever open booth.pm.
- **Tampering gets noticed.** Hoard seals every record it writes. See
  [Where Hoard keeps things](Where-Hoard-Keeps-Things#seals).
- **A half-finished download is never stitched to the wrong file.** See [Downloads](Downloads#resuming).

## Hoard itself

- **What gets installed is checked.** Every package is compared against a fingerprint recorded in advance.
- **Releases are built in the open,** by GitHub from the source code, with checksums and a signed record of the
  build. See [Installing Hoard](Installing-Hoard#checking-a-download).
- **Every change is security-tested** automatically before it's released.

## Your privacy

- **Nothing is sent to the developer.** No accounts, no tracking, no analytics, no ads. Hoard only talks to the
  stores you use, the servers that host their pictures, and GitHub when it checks for updates (when you ask,
  or daily if you turn that on).
- **Updates are checked before they run.** Hoard only runs an installer whose SHA-256 matches both the
  release's `SHA256SUMS-windows.txt` and the checksum GitHub lists for the file.
- **It works offline** for everything except refreshing, signing in and downloading.
- **Hoard doesn't use AI,** and your data never goes to one. (It was largely written with an AI assistant: see
  [AI-DISCLOSURE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/AI-DISCLOSURE.md).)

## What no app can protect you from

- **Malware already on your computer.** A virus running as you could use your signed-in stores just as you can.
  Keep your computer up to date and scanned.
- **Someone with administrator access** to your computer.
- **Problems on the stores' own websites.**

The hidden library is a privacy screen for Hoard, not encryption: see [Your library](Library#the-hidden-library).

## Reporting a security problem

Please don't open a public issue. On the repository's
[Security tab](https://github.com/Soloflighter1010/Hoard-Asset-Manager/security), choose **Report a
vulnerability**: only the maintainer sees it. How past reviews were handled is in
[docs/security-review-2.3.1-response.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/security-review-2.3.1-response.md).
