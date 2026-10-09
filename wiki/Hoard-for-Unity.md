**Hoard for Unity** brings what Hoard has downloaded into the Unity editor, so you can import an asset without
hunting for it or downloading it again.

## What it does

Open **Hoard › Open Hoard** (Hoard has its own menu in Unity's menu bar, from 0.7.0; before, it was
**Window › Hoard**) to:

- **Browse and search** everything Hoard has downloaded, by name, creator, store or tag, with thumbnails.
  Animated ones (GIFs) play, from 0.3.0. **Pause GIFs** keeps them still (0.7.0).
- **The app's look** (0.7.0): Hoard's colours and logo, a tab for each store, the products as tiles (a slider
  sets their size, the arrow keys move between them, **/** searches), and the chosen one's details beside them.
- **See what's already in this project.** It reads the asset GUIDs inside each `.unitypackage`, without extracting
  anything, and marks products **In this project** or **Partly in project**. Only what's under `Assets/` counts:
  a package's own copy of something VCC installs under `Packages/` (Poiyomi, say) doesn't, from 0.5.1. Only files
  count, not the folders a package puts them in, from 0.5.2: a creator's folder is all their products' folder.
  From 0.5.3, a product counts only by the files that are its own: a shader or texture several products carry
  (a creator's shared files, or a bundle and the product sold alone) doesn't make the others **Partly in project**.
  A product with nothing of its own (the same package from another store) still counts by all its files.
  **Select** finds their assets in your Project window.
- **Import without downloading again.** **Import** opens Unity's own import dialog on the copy Hoard already
  downloaded, so you choose exactly what comes in. Other files (textures, archives) open in Explorer.
- **Find which product a file came from** (0.6.0). Select files or folders in the Project window, right-click and
  choose **Hoard › Which Product Is This From?** (also in the **Assets** menu). The window lists the products
  whose packages carry them, most files first, with **Show** to find each in the list. It looks at up to 20,000
  files at a time, and says when Hoard is still reading packages.
- **Import updates** (0.6.0). A product in this project shows **Update to import** when Hoard has downloaded a
  newer package of it than the one you have: one downloaded more than an hour after a package that's all in the
  project, or after you last imported the product through Hoard. Its details have **Import update**, which opens
  Unity's import dialog on it. A product whose creator updated it since Hoard last downloaded (what Hoard's last
  **Check for updates** found, in `asset-updates.json` in Hoard's own folder) shows **Update in Hoard**: download
  the update in Hoard (**Downloads**, **Updates**), then import it here. **Updates** above the tiles shows just
  those products.

Imports made this way are recorded in `ProjectSettings/Hoard/imports.json`, so a project remembers where its
assets came from (from 0.5.2, a package with scripts too, though Unity reloads its scripts part way through). If
the file is damaged, it's kept beside the new one as `imports.json.unreadable-<time>` rather than written over.

## Credits

Creators often ask to be credited when you use their assets. **Create Credits List** in the window's bar lists the
Hoard assets this project uses, ready to paste into an avatar or world description, a post or a store page:

- **What's in it:** each product fully in the project, with all the files of one of its packages there (0.3.1
  and newer; 0.3.0 also took products only partly there, or imported through Hoard and removed since). Untick any you don't want credited. Assets that didn't come through Hoard can be added by
  hand, with a link if you like.
- **Styles:** a list (name, creator, store and store link), Markdown (names linked to their store pages), or
  grouped by creator (one line a creator, however their name's case differs between stores).
- **Copy** puts it on the clipboard. **Save as...** writes a text file, in the project's own folder unless you
  choose otherwise; outside `Assets`, it's never part of an upload.

What you change (the title, style, unticked assets and ones added by hand) is kept in
`ProjectSettings/Hoard/credits.json`, beside the import log, so it travels with the project and its version
control. The list is made from what's on your computer; nothing is sent anywhere.

## Projects in Hoard

Each project you open Hoard's window in shows up in Hoard under **Projects** (at the top of the page), from
0.4.0. For each one, Projects lists:

- every product of yours it uses, and how much of it: **In the project**, **Partly in the project**, or
  **Imported, not found now** (Hoard imported it there, but its files aren't found any more);
- which of them have an update waiting (after **Check for updates** in Downloads), each linked to its download;
- its credits list, the same one **Create Credits List** makes in Unity, with what you changed there, in any of
  the three styles, ready to copy.

In Downloads, a product says which projects use it. The window tells Hoard what a project uses a few seconds after
anything changes (an import, a deleted folder, the credits settings), by writing a small report to `projects/` in
Hoard's own folder. Hoard doesn't need to be running. **Forget this project** in Projects takes one out until you
open its window again.

## What it needs

- The Hoard app, 2.3.1 or newer, with some downloads. Hoard doesn't need to be running.
- Unity 2022.3, the version VRChat uses.
- For assets from itch.io, which Hoard downloads from 2.5.0: the package's 0.1.3 or newer. Earlier ones leave
  them out, since they only show stores they know.
- For your own packages (Hoard's **Local**, from 3.0) and **Projects** in Hoard: 0.4.0 or newer, with Hoard 3.0.
- For products in Hoard's other library folders (on other drives, from 3.0): 0.5.0 or newer. Older versions say
  the catalog is from a newer Hoard while any product is in another folder.
- For animated pictures and the credits list: 0.3.0 or newer. Pictures Hoard saved as WebP or AVIF can't be
  shown in Unity; the window uses one of the product's own images instead when there is one.

## Installing

**With the VRChat Creator Companion (VCC):**

1. Open [Hoard's website](https://soloflighter1010.github.io/Hoard-Asset-Manager/#unity) and choose **Add to VCC**.
   Or, in VCC, go to **Settings › Packages › Add Repository** and paste
   `https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json`.
2. Add **Hoard** to your project, like any other package. VCC offers updates when there's a new version.

**Without VCC:** download the `.unitypackage` from a Hoard for Unity release (its tags start `unity-v`) on the
[releases page](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases), and import it into your
project.

It finds Hoard's downloads folder the same way the app does. If yours is somewhere else, choose **Folder...** in
the window's bar.

## Safe by design

- **Read-only toward your Hoard library.** It reads `catalog.json`, and from 0.6.0 what Hoard's last check for
  updates found (`asset-updates.json`), and never changes, moves or deletes anything in your downloads folder. The one thing it writes outside the project is the small report for **Projects**,
  in `projects/` in Hoard's own folder (0.4.0).
- **Checks Hoard's seal.** Hoard seals `catalog.json`. If something else has edited it, importing pauses and store
  links are hidden until Hoard rebuilds it: choose **Sync** in Hoard, or run `hoard-cli verify`.
- **Checks every entry** against Hoard's documented rules: plain paths inside your downloads folder only, never
  through a link or junction, and store links only to the product's own store. The one exception is a Local item
  you listed where it is, and a product in another of Hoard's library folders, whose folder is used only when
  Hoard sealed the catalog on this computer.
- **Checks every package it reads.** A `.unitypackage` whose headers claim impossible sizes is treated as not a
  package, before anything is read into memory for it (0.1.2).
- **Editor only.** Nothing from this package is included in avatar or world uploads, and it contacts nobody.

It keeps a cache of what's inside each package in the project's `Library` folder, so it doesn't read the same
package twice.

## If the window says...

- **"catalog.json was changed by something other than Hoard"**: see the seal note above. If you share one
  downloads folder between computers, copy `integrity.key` as described in
  [Where Hoard keeps things](Where-Hoard-Keeps-Things#one-downloads-folder-two-computers).
- **Nothing to show:** check the folder (**Folder...** in the bar) is your Hoard downloads folder, and that Hoard has
  downloaded something (its **Downloads** tab lists it).

The package's own notes are in
[Packages/soloflighter.hoard/README.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/Packages/soloflighter.hoard/README.md),
and its changes in its
[CHANGELOG](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/Packages/soloflighter.hoard/CHANGELOG.md).
