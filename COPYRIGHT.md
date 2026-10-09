# Copyright and credits

## Hoard

Hoard is copyright (c) 2026 Soloflighter1010 and released under the MIT license
([LICENSE](LICENSE)).

## The Hoard name and logo

The name "Hoard" and the logo (the tile pile and the "hoard" wordmark, in `brand/` and in Hoard) are
the project's identity. You're welcome to use them to refer to Hoard, for example in an article, a video
or a link to the project. Please don't use them for a fork or another product in a way that suggests it's
the official Hoard.

The wordmark is drawn from the Dela Gothic One typeface (SIL Open Font License 1.1).

## Typefaces

Hoard include the Dela Gothic One and Zen Maru Gothic typefaces (in `fonts/`), converted to WOFF2
without other changes. Both are licensed under the SIL Open Font License 1.1, and their license texts
come with them: `fonts/DelaGothicOne-OFL.txt` and `fonts/ZenMaruGothic-OFL.txt`.

## Software Hoard uses

These aren't included in the release zip. Setup installs them from their official
sources:

| Software | License |
|---|---|
| Playwright for Python | Apache License 2.0 |
| Chromium, downloaded by Playwright | BSD-style license, plus the licenses of its components |
| requests | Apache License 2.0 |
| tqdm | MPL 2.0 and MIT |

## The Windows app

The installed app includes [pywebview](https://github.com/r0x0r/pywebview) (BSD 3-Clause) for its window,
with [pythonnet](https://github.com/pythonnet/pythonnet) and clr-loader (MIT), and is built with
[PyInstaller](https://pyinstaller.org) (GPL 2.0 with an exception that allows distributing the programs it
builds under their own licenses). The installer is made with [Inno Setup](https://jrsoftware.org/isinfo.php)
(the Inno Setup License, free for any use). The window is drawn by Microsoft Edge WebView2, part of Windows.

## The recovery word list

`hoard/recovery_words.txt` is the BIP-39 English word list, as published in Trezor's python-mnemonic
project: Copyright (c) 2013-2016 Pavol Rusnak, under the MIT License. Hoard uses it only to make the
recovery phrase for its hidden library.

## The Unity project and the listing page

The Unity project layout, the release and listing workflows and the listing page (`Website/`) are adapted
from VRChat's [template-package](https://github.com/vrchat-community/template-package). The listing is built
by VRChat's [package-list-action](https://github.com/vrchat-community/package-list-action).
`Packages/com.vrchat.core.bootstrap` is VRChat's, under the VRChat Distro License in its folder; it's part of
the Unity project for working on the package, not part of Hoard for Unity itself.
`Website/vendor/fluent-web-components-2.6.1.min.js` is Microsoft's Fluent UI web components, MIT licensed (its
notice is beside it), bundled so the listing page loads nothing from other sites.

## Pictures in the screenshots

The screenshots in this README and on the website (`site/img/`) show real products from the maintainer's own library,
with their creators' own pictures (also in `site/img/credits/`). Every picture belongs to its creator, is shown only as
it appears in Hoard, and isn't covered by Hoard's MIT license. Thank you to these creators:

| Product | Creator | Where to get it |
|---|---|---|
| Substance Painter Files for the Nepterran (VRChat Furry Avatar) | 3Rr0r_418 | [The creator's shop](https://3rr0r418.store) |
| EDJ - Virtual DJ Equipment | Electro's Assets for VRChat | [Get it on Booth](https://booth.pm/en/items/3552518) |
| The Vixine - Flatcap | Hecka.Space | [Get it on Jinxxy](https://jinxxy.com/Hecka/Flatcap) |
| VRChatWorld用 ClockCounter | Mofcosmos | [Get it on Booth](https://booth.pm/en/items/4874440) |
| Aster Dragon Wings (VRChat Asset) | Morghus | [Get it on Gumroad](https://morghus.gumroad.com/l/asterwings) |
| \[VRChat想定\]ワードクロック(Word clock) | nyakomake | [Get it on Booth](https://booth.pm/en/items/2990166) |
| AVIA X2 Headphones 【PACIFIA WARES】 (Raver Pack \[2 Colors\]) | PACIFIA 🞮 Virtual Shop | [Get it on Booth](https://booth.pm/en/items/4962763) |
| PIXON400 Camera 【PACIFIA WARES】\[For VRCLens\] (FULL PACK \[All 6 Colors\]) | PACIFIA 🞮 Virtual Shop | [Get it on Booth](https://booth.pm/en/items/4928549) |
| FREE Plumbob With Moods and Audiolink \| VRChat Accessory | Perfecto | [Get it on Gumroad](https://perfectodoart.gumroad.com/l/FreePlumbob) |
| Mobile Studio \[VRChat\] | Pointless Creations | [Get it on Gumroad](https://pointlesscreations.gumroad.com/l/MobileStudio) |
| Round Glasses - Fat Pack Compatibility Update | Shep Shep | [Get it on Gumroad](https://shepshep.gumroad.com/l/rglass) |
| Spiri'vali Headphones | Shep Shep | [Get it on Gumroad](https://shepshep.gumroad.com/l/tdxvv) |
| VRChat Studio Lights | SherbDrgn | [Get it on Gumroad](https://sherbertdragon.gumroad.com/l/StudioLights) |
| The cat condo | SOShop | [Get it on Booth](https://booth.pm/en/items/4142963) |
| 【VRChat】撮影スタジオ / Photography Studio | tofumarket | [Get it on Booth](https://booth.pm/en/items/3856844) |
| 【VRchat対応ワールド】Moonlit Perch | udon-cat-works | [Get it on Booth](https://booth.pm/en/items/6340105) |
| VioTech Plasma Cannon w/ Remote Fireworks | Violentpainter | [Get it on Gumroad](https://violentpainter.gumroad.com/l/viotech-plasma-cannon) |
| The Deep Dusk (VRCWorld) | wispywoo | [Get it on Booth](https://booth.pm/en/items/4189273) |
| アズキドチェス(Ahzkwid Chess) | Wmup | [Get it on Booth](https://booth.pm/en/items/1707240) |
| Hologram Projector (VRChat) | Zekk | [Get it on Gumroad](https://zekk.gumroad.com/l/HologramProjector) |
| VirtualLens2 | ろじらぼ | [Get it on Booth](https://booth.pm/en/items/2280136) |
| 結晶化 光の輪 Ring V09 (\[TypeA\]) | 雪械重工 | [Get it on Booth](https://booth.pm/en/items/3138614) |

The same list, with each picture, is on the website's
[Picture credits](https://hoard.furryup.link/credits.html) page. Made one of these and
want it changed or taken out? [Open an issue](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues).

## Store names

Booth and pixiv, Gumroad, Jinxxy, Payhip and VRChat are trademarks of their owners. They appear only to
say which stores Hoard works with.

## Your assets

Everything Hoard download belongs to its creators. Hoard doesn't grant you any rights to those files
beyond what each creator's license already gives you.

## Thanks

The Gumroad reader follows the data shapes in Gumroad's open-source code (antiwork/gumroad), and the Booth
reader was informed by ribeKim's booth-library-manager.
