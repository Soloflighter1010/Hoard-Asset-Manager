# Hoard for Unity

The VRChat assets you've downloaded with [Hoard](https://github.com/Soloflighter1010/Hoard-Asset-Manager), inside
Unity. Open **Hoard › Open Hoard** (Hoard's own menu in Unity's menu bar) to:

- **Browse and search** everything Hoard has downloaded, by name, creator, store or tag, as tiles in the app's
  look: a tab for each store, the pictures with their store's colour along the foot (animated GIFs play, or
  stay still with **Pause GIFs**).
- **See what's already in this project.** Hoard reads the asset GUIDs inside each `.unitypackage` (without
  extracting anything) and marks products **In this project** or **Partly in project**, by the files that are each
  product's own (a creator's shared shader in your project doesn't make all their products look imported). **Select** finds
  their assets in your Project window.
- **Import without downloading again.** **Import** opens Unity's own import dialog on the copy Hoard already
  downloaded, so you choose exactly what comes in. A package that came in a `.zip` is listed under it, and
  **Import** unpacks just that package (into the project's `Library` folder) first. Other files (textures, archives)
  open in Explorer.
- **Find where a file came from.** Right-click files in the Project window: **Hoard › Which Product Is This From?**
- **Import updates.** Products in this project with a newer download show **Update to import**; ones whose creator
  updated them since Hoard last downloaded show **Update in Hoard**. **Updates** above the tiles lists just those.

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

**Installing:** in VCC, add the listing from https://hoard.furryup.link/ (**Add to
VCC**), then add **Hoard** to your project. Without VCC, import the `.unitypackage` from a
[release](https://github.com/Soloflighter1010/Hoard-Asset-Manager/releases) into your project.

It finds Hoard's downloads folder the same way the app does. If yours is somewhere else, choose **Folder...**
in the window's bar.

## Safe by design

- **Read-only toward your Hoard library.** It reads `catalog.json` (and what Hoard's last check for updates
  found) and never changes, moves or deletes anything in your downloads folder.
- **Checks Hoard's seal.** `catalog.json` is sealed by Hoard. If something else has edited it, importing
  pauses and store links are hidden until Hoard rebuilds it (choose **Sync** in Hoard).
- **Checks every entry** against Hoard's documented rules: plain paths inside your downloads folder only,
  never through a link or junction, and store links only to the product's own store.
- **Editor only.** Nothing from this package is included in avatar or world uploads.

MIT licensed. Not affiliated with VRChat, Booth, Gumroad, Jinxxy, Payhip or itch.io.
