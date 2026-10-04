# Changelog

## 0.5.1

- **Products only count as in your project for what's in Assets** (Hoard's issue #114). Many packages carry their
  own copy of something VCC installs under `Packages/` (Poiyomi, VRCFury, the VRChat SDK), and Unity finds those
  files there too. So a product you hadn't imported could show as **In this project**, and land in the credits
  list. Now only files under `Assets/` count, and **Select** only selects those.
- **Nothing is cut off in a narrow window.** Long names end in "…" instead of being cut through a letter, with the
  whole name when you point at one; a file's name keeps its end ("CyclopsBe….unitypackage") rather than wrapping
  part way through a word; and when the window is too narrow for one row of buttons, Create Credits List, Reload
  and Folder... move to a second row instead of off its edge.

## 0.5.0

- **Library folders on other drives.** Hoard 3.0 can keep your downloads in more than one folder: its downloads
  folder, and folders you add on other drives. Products in those folders are listed and imported like any other.
  As with your own packages listed where they are, the window only uses another folder when Hoard sealed the
  catalog on this computer, and never through a link. Needed for a catalog from Hoard 3.0 that has products in
  another folder (version 4); a library all in one folder still works with earlier versions.

## 0.4.0

- **Your own packages** (Hoard's issue #80). Hoard 3.0 keeps packages you make under **Local**, copied into its
  downloads folder or listed where they are. The window lists them under **Local**, shows who they're for, and
  imports them like any download. A Local item listed where it is has its own folder outside the downloads
  folder; the window only uses it when Hoard sealed the catalog on this computer, and still never through a link.
- **Projects in Hoard** (Hoard's issue #86). The window tells Hoard what this project uses: a few seconds after
  anything changes, it writes a small report (the project's name and folder, each product in it and how much of
  it, and the credits settings) to `projects/` in Hoard's own folder, and only when something in it changed.
  Hoard 3.0's **Projects** lists every project with its assets, their updates and its credits list.

## 0.3.1

- **Create Credits List** (issue #79). The toolbar's **Credits** button is now **Create Credits List**, and the
  list only takes products fully in the project: one with a package whose files are all there. A product that's
  only partly there, or that the import log says was imported but whose files are gone, is no longer credited.
  Ones you added by hand stay.

## 0.3.0

A credits list for your project, and animated pictures.

- **Credits** (issue #51). The **Credits** button in the window's toolbar lists the creators of the Hoard assets
  this project uses, ready to paste where you share your avatar or world: as a list with store links, as
  Markdown, or grouped by creator. An asset counts when its files are in the project, or when it was imported
  through Hoard and hasn't been removed since. Untick any you don't want credited, and add assets that didn't
  come through Hoard by hand. **Copy** puts the list on the clipboard; **Save as...** writes a text file (in the
  project's own folder by default, never part of an upload). What you change is kept in
  `ProjectSettings/Hoard/credits.json`, so it travels with the project.
- **Animated pictures show, and play.** Hoard saves a store's animated picture as `_thumbnail.gif`, which the
  window didn't look for, and Unity can't read GIFs itself. The window now decodes GIFs (every frame, at the size
  it shows them, checked against how a browser shows them) and plays them in the list and the details.
- **A picture for more products.** When a product's saved picture is a kind Unity can't show (WebP or AVIF), the
  window uses one of the product's own images instead: one named like a preview, else any, as Hoard's own pages
  do.
- Pictures are kept within a memory budget as well as a count, so a library of long animations can't fill the
  editor's memory.

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
