# Changelog

## 0.6.0

- **Which product is this from?** Right-click files or folders in the Project window (or use the **Assets** menu)
  and choose **Hoard › Which Product Is This From?**. The window lists the products whose packages carry them,
  most files first, with **Show** to find each one in the list. Files no package Hoard downloaded carries are
  said to be from none.
- **Updates for what's in your project.** A product in this project shows **Update to import** when Hoard has
  downloaded a newer package of it than the one you imported (a package downloaded later than the one in the
  project, or than when you last imported it through Hoard), and **Update in Hoard** when Hoard's last check for
  updates found new or changed files you haven't downloaded yet. Its details have **Import update**, or say to
  download the update in Hoard first. **Updates** in the toolbar shows just those.

## 0.5.3

- **A product counts only by the files that are its own.** Products often carry the same files: a creator's shared
  shader, textures or materials in each of their hairs, say, or a bundle and the product also sold on its own.
  Having one of them made every other product carrying those files show as **Partly in project**, in this window,
  in Hoard's Projects view and on the way to the credits list. Files more than one of your products carry are
  left out of the count now, so only what you imported shows. A product that has nothing of its own (the same
  package bought from another store, or a product that's all inside a bundle) still counts by all its files.

## 0.5.2

- **Importing a package with scripts is remembered.** Unity reloads its scripts part way through such an import, and
  the window forgot what it was importing, so the import was never noted in `imports.json`. It's kept through the
  reload now. If `imports.json` can't be written (read-only, say), Import is no longer greyed out for the rest of the
  session, and a damaged `imports.json` is kept beside the new one (`imports.json.unreadable-…`) instead of being
  written over. Its times are written the same way whatever your computer's language.
- **A product's folders don't count as its files.** A package lists the folders it puts things in, and a creator's
  folder is shared by all their products, so having one of them made the others show as **Partly in project**. Only
  files count now (the window reads each package once more, the first time).
- **A library folder that's a whole drive** (`E:\`) works: everything in it showed as missing.
- **"Checking packages: N to go" no longer sticks.** A package queued just as the last one finished could be left
  waiting for good, and with it the project report and the credits list.
- **Choosing Folder... while the library is loading** loads that folder, instead of being ignored; a library that
  can't be read says why, instead of "Loading your library..." for good. Choosing the default folder again (written
  with `/` rather than `\`) no longer pins it.
- **Credits:** a creator whose name's case differs between stores is one line in **By creator**; you can type a
  space in the title; typing saves once you pause rather than on every key; and a read-only `credits.json` is said
  in the Console instead of breaking the window.
- Faster: how much of a package is in the project is worked out once rather than on every redraw; pictures are read
  two at a time however fast you scroll, and none are left behind in memory; an unwritable package cache is tried
  again once a minute, not on every editor tick. `\u` escapes in Hoard's files must be four hex digits.

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
