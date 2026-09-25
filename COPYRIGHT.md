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

## Store names

Booth and pixiv, Gumroad, Jinxxy, Payhip and VRChat are trademarks of their owners. They appear only to
say which stores Hoard works with.

## Your assets

Everything Hoard download belongs to its creators. Hoard doesn't grant you any rights to those files
beyond what each creator's license already gives you.

## Thanks

The Gumroad reader follows the data shapes in Gumroad's open-source code (antiwork/gumroad), and the Booth
reader was informed by ribeKim's booth-library-manager.
