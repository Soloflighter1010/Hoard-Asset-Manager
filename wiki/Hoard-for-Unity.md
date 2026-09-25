**Hoard for Unity** brings what Hoard has downloaded into the Unity editor, so you can import an asset without
hunting for it or downloading it again.

## What it does

Open **Window › Hoard** to:

- **Browse and search** everything Hoard has downloaded, by name, creator, store or tag, with thumbnails.
- **See what's already in this project.** It reads the asset GUIDs inside each `.unitypackage`, without extracting
  anything, and marks products **In this project** or **Partly in project**. **Select** finds their assets in
  your Project window.
- **Import without downloading again.** **Import** opens Unity's own import dialog on the copy Hoard already
  downloaded, so you choose exactly what comes in. Other files (textures, archives) open in Explorer.

Imports made this way are recorded in `ProjectSettings/Hoard/imports.json`, so a project remembers where its
assets came from.

## What it needs

- The Hoard app, 2.3.1 or newer, with some downloads. Hoard doesn't need to be running.
- Unity 2022.3, the version VRChat uses.
- For assets from itch.io, which Hoard downloads from 2.5.0: the package's 0.1.3 or newer. Earlier ones leave
  them out, since they only show stores they know.

## Installing

**With the VRChat Creator Companion (VCC):**

1. Open the [listing page](https://soloflighter1010.github.io/Hoard-Asset-Manager/) and choose **Add to VCC**.
   Or, in VCC, go to **Settings › Packages › Add Repository** and paste
   `https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json`.
2. Add **Hoard** to your project, like any other package. VCC offers updates when there's a new version.

**Without VCC:** download the `.unitypackage` from a Hoard for Unity release (its tags start `unity-v`) on the
[releases page](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases), and import it into your
project.

It finds Hoard's downloads folder the same way the app does. If yours is somewhere else, choose **Folder...** in
the window's toolbar.

## Safe by design

- **Read-only toward your Hoard library.** It reads `catalog.json` and never changes, moves or deletes anything
  in your downloads folder.
- **Checks Hoard's seal.** Hoard seals `catalog.json`. If something else has edited it, importing pauses and store
  links are hidden until Hoard rebuilds it: choose **Sync** in Hoard, or run `hoard-cli verify`.
- **Checks every entry** against Hoard's documented rules: plain paths inside your downloads folder only, never
  through a link or junction, and store links only to the product's own store.
- **Checks every package it reads.** A `.unitypackage` whose headers claim impossible sizes is treated as not a
  package, before anything is read into memory for it (0.1.2).
- **Editor only.** Nothing from this package is included in avatar or world uploads, and it contacts nobody.

It keeps a cache of what's inside each package in the project's `Library` folder, so it doesn't read the same
package twice.

## If the window says...

- **"catalog.json was changed by something other than Hoard"**: see the seal note above. If you share one
  downloads folder between computers, copy `integrity.key` as described in
  [Where Hoard keeps things](Where-Hoard-Keeps-Things#one-downloads-folder-two-computers).
- **Nothing to show:** check the folder in the toolbar is your Hoard downloads folder, and that Hoard has
  downloaded something (its **Downloads** tab lists it).

The package's own notes are in
[Packages/soloflighter.hoard/README.md](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/Packages/soloflighter.hoard/README.md),
and its changes in its
[CHANGELOG](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/Packages/soloflighter.hoard/CHANGELOG.md).
