# Hoard for Unity

The VRChat assets you've downloaded with [Hoard](https://github.com/Soloflighter1010/Hoard-Asset-Manager), inside
Unity. Open **Window › Hoard** to:

- **Browse and search** everything Hoard has downloaded, by name, creator, store or tag, with thumbnails
  (animated GIFs play).
- **See what's already in this project.** Hoard reads the asset GUIDs inside each `.unitypackage` (without
  extracting anything) and marks products **In this project** or **Partly in project**. **Select** finds
  their assets in your Project window.
- **Import without downloading again.** **Import** opens Unity's own import dialog on the copy Hoard already
  downloaded, so you choose exactly what comes in. Other files (textures, archives) open in Explorer.

- **Credit the creators.** **Create Credits List** lists the Hoard assets fully in this project, as a list, Markdown or
  grouped by creator, to copy or save. Untick any you don't want credited, or add assets that didn't come
  through Hoard.

- **Projects in Hoard.** The window tells Hoard what this project uses, so Hoard's **Projects** lists every
  project with its assets, their updates and its credits list.

Imports made this way are recorded in `ProjectSettings/Hoard/imports.json`, so a project remembers where its
assets came from. The credits list's settings are kept beside it, in `credits.json`.

## What it needs

- The Hoard app (version 2.3.1 or newer), with some downloads. Hoard doesn't need to be running.
- Unity 2022.3, the version VRChat uses.

**Installing:** in VCC, add the listing from https://soloflighter1010.github.io/Hoard-Asset-Manager/ (**Add to
VCC**), then add **Hoard** to your project. Without VCC, import the `.unitypackage` from a
[release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases) into your project.

It finds Hoard's downloads folder the same way the app does. If yours is somewhere else, choose **Folder...**
in the window's toolbar.

## Safe by design

- **Read-only toward your Hoard library.** It reads `catalog.json` and never changes, moves or deletes
  anything in your downloads folder.
- **Checks Hoard's seal.** `catalog.json` is sealed by Hoard. If something else has edited it, importing
  pauses and store links are hidden until Hoard rebuilds it (choose **Sync** in Hoard).
- **Checks every entry** against Hoard's documented rules: plain paths inside your downloads folder only,
  never through a link or junction, and store links only to the product's own store.
- **Editor only.** Nothing from this package is included in avatar or world uploads.

MIT licensed. Not affiliated with VRChat, Booth, Gumroad, Jinxxy, Payhip or itch.io.
