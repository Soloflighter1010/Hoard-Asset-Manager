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

Yes, from source: see [Installing Hoard](Installing-Hoard#from-source-windows-macos-linux). The installer and the
windowed app are for Windows. Hoard for Unity works wherever Unity 2022.3 does.

## Will it download the same file twice?

No. Hoard records what it downloaded and where, and only downloads what's new, plus files the creator has
updated. See [Downloads](Downloads).

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

No. It never checks for updates on its own. The **Updates** link at the bottom of every page opens the releases
page; install the newer version over the old one.

## Is the hidden library encrypted?

No. It's a privacy screen for Hoard: hidden items stay out of view everywhere in Hoard until you unlock them, but
the files on your disk are ordinary files. See [Your library](Library#the-hidden-library).

## Does Hoard use AI?

Hoard itself doesn't, and your data never goes to one. Most of its code, design and documentation was written by
an AI assistant, directed and tested by the maintainer:
[AI-DISCLOSURE.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/AI-DISCLOSURE.md) explains
what that means for you.
