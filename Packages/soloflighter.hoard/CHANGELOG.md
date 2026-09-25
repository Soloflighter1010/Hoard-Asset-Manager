# Changelog

## 0.2.0

Fast with large libraries, and no more "made on another computer" for your own catalog.

- **Loads in the background.** The catalog is read and checked, and each product's packages, picture and search
  text worked out, on a background thread, with folders that many products share checked once. The window says
  "Loading your library..." meanwhile, and stays usable when you choose **Reload**. A 3,000-product library
  loads in about a fifth of a second.
- **Draws only what's on screen.** The list used to lay out every product, and read and decode every picture, on
  each repaint. Now it draws the rows you can see, pictures are read in the background for those rows only and
  decoded a few at a time, and at most 256 are kept in memory. Whether a product is in the project is
  remembered, and only worked out again when its package has been read or the project changes.
- **Your own catalog is recognised.** The seal on `catalog.json` is checked with any of this account's Hoard
  keys, including the separate one Windows keeps for Hoard run on Microsoft Store Python, which made a catalog
  look "made on another computer". Hoard 2.8.1 also seals the catalog again when it starts, so if the message
  shows for a real reason, opening Hoard and choosing **Reload** clears it.

## 0.1.3

Knows itch.io, which Hoard 2.5.0 downloads from: its assets show in the window (as "itch.io"), can be picked in
the store filter, and link to their pages on itch.io. Earlier versions left them out of the list, since the
catalog promises never to show a store they don't know.

## 0.1.2

Safer reading of `.unitypackage` files, which anyone could have made: a package whose headers claim a file name
longer than any real path is refused before anything is set aside for it (one claiming an 8 GB name could make
the editor try to allocate it), and a package that would unpack to more than 64 GB is refused instead of being
read to the end. Either counts as "not a package", as a damaged one always has.

## 0.1.1

Published the way VRChat's template-package does: each release now also has a `.unitypackage`, for projects
without VCC, and the VCC listing has moved to https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json
(the earlier `vpm/index.json` address keeps working). No changes inside Unity.

## 0.1.0

First version: **Window › Hoard** browses what the Hoard app has downloaded, shows which products are already
in this project (from the GUIDs inside each `.unitypackage`), and imports a `.unitypackage` through Unity's own
import dialog. Imports are recorded in `ProjectSettings/Hoard/imports.json`.
