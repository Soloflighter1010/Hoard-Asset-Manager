## Is Hoard free?

Yes. It's open source under the [MIT license](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/LICENSE),
with no accounts, ads or tracking.

## Does Hoard see my store passwords?

No. You sign in on each store's own page, in Hoard's window, and Hoard only keeps the "stay signed in" pass the
store hands out, encrypted by your operating system. See [Security and privacy](Security-and-Privacy).

## Is it allowed?

Hoard reads your own purchases, signed in as you, the way your browser would, and waits between pages to stay
polite. It's unofficial: not affiliated with or endorsed by any of the stores. Downloading doesn't change what
you're allowed to do with an asset, so follow each creator's license and each store's terms.

## Does it work on a Mac or Linux?

Yes. There's a package for macOS 11 or newer (Apple Silicon and Intel), and a Flatpak for Linux (x86_64), each
opening in Hoard's own window: see [Installing Hoard](Installing-Hoard#macos). It also runs from source anywhere
with Python 3.10 or newer. Hoard for Unity works wherever Unity 2022.3 does.

## Will it download the same file twice?

No. Hoard records what it downloaded and where, and only downloads what's new, plus files the creator has
updated. See [Downloads](Downloads).

## Which stores does Hoard work with?

Booth, Gumroad, Jinxxy, Payhip and itch.io. Hoard lists what you own on all of them, and downloads from all but
Payhip, where you download the files yourself from each product's download page. See [Stores](Stores).

## Can I choose which files of a product to download?

Yes. Before one product downloads, Hoard asks **What files do you want to save?**: **Download everything**, or
**Choose files** to untick what you don't want (a Quest version, say, or the PSDs). It remembers what you left out
and asks again next time, and rules in **Settings** (**Files to leave out**) leave a kind of file out of every
download. See [Downloads](Downloads#which-files-to-save).

## Can Hoard put my assets into my Unity projects?

Yes. **Projects** lists the same projects as ALCOM and the VRChat Creator Companion: it makes new ones, adds VPM
packages, and puts in products from your library (a `.unitypackage` goes in without opening Unity), with what they
need. Hoard for Unity, a package in the project, shows which of your products it uses, with their credits. See
[Projects](Projects) and [Hoard for Unity](Hoard-for-Unity).

## What are sets and wishlists?

A set groups products you use together (an avatar and its outfits, say), to download, put in a project, or share by
a short link that only someone with the link can open. A wishlist is a set of what you'd like: read from your stores'
wishlists or added by a product's link, with its price, and Hoard says when one gets cheaper. See [Sets](Sets).

## I removed a product. Will it come back?

No. A removed product stays out of your library, and out of every download and sync, after each refresh, even when
the store renames it. The **Removed** view lists them, to put back whenever you like. See
[Your library](Library#archive-removed-and-hidden).

## Where do my files go?

A `Hoard` folder in your Documents, in `<Store>/<Creator>/<Product>` folders, unless you choose another folder in
[Settings](Settings).

## Can I move my downloads folder?

Yes. Move the whole folder (Hoard's records inside it move with it), then choose its new place in
[Settings](Settings). Changing the setting alone doesn't move any files.

## Can two computers share one downloads folder?

Yes, a NAS for example: copy `integrity.key` between them. See
[Where Hoard keeps things](Where-Hoard-Keeps-Things#one-downloads-folder-two-computers).

## Can I use Hoard on my phone?

You can browse your library and downloads from another device, once you've set it up on the computer running
Hoard: see [Using Hoard on other devices](Using-Hoard-on-Other-Devices).

## Does Hoard update itself?

When you ask it to. In **Settings**, **Updates**: **Check now** asks GitHub whether there's a newer version, and
in the installed Windows app **Update to** downloads it, checks it, closes Hoard, installs it and opens Hoard
again. With **Check for updates automatically** on, Hoard checks in the background each time it starts and once a
day while it's open, and shows **Update to** at the bottom of the page when there's a new version. From 5.1 it's on
to begin with in a new Hoard (one you had before keeps your choice). See
[Installing Hoard](Installing-Hoard#updating).

## Can Hoard tell me about new things on my phone?

Yes, through Apprise: in **Settings**, **Notifications through Apprise**, add an address for Discord, Telegram,
ntfy, email or many more, then tick what to send. Only counts are sent, never a product's name. See
[Settings](Settings).

## Why does my antivirus or Windows warn about Hoard?

Windows warns about programs from a publisher it doesn't know well yet, and Hoard drives a real browser and
downloads files, which some security software watches closely. Hoard is code-signed and open source, and every
release is scanned by VirusTotal before it's published. See
[Troubleshooting](Troubleshooting#security-software-stops-hoard-or-its-browser).

## Is the hidden library encrypted?

No. It's a privacy screen for Hoard: hidden items stay out of view everywhere in Hoard until you unlock them, but
the files on your disk are ordinary files. See [Your library](Library#the-hidden-library).

## Does Hoard use AI?

Hoard itself doesn't, and your data never goes to one. Most of its code, design and documentation was written by
an AI assistant, directed and tested by the maintainer:
[AI-DISCLOSURE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/AI-DISCLOSURE.md) explains
what that means for you.
