# A Unity package from a Local item, without Unity

Research for #382, written 19 November 2026, with what was built from it:
**Make a Unity package** on a Local item (`hoard/makepackage.py`).

## The format

A `.unitypackage` is a gzipped tar. Each asset is a folder named by its GUID, holding:

- `pathname`: where the asset goes in the project, such as `Assets/My Hoodie/Textures/hoodie.png`;
- `asset`: the file itself (a folder has none);
- `asset.meta`: Unity's meta file, with the asset's GUID and how it's imported;
- optionally `preview.png`, the thumbnail Unity's import window shows.

Hoard reads these already (`hoard/vpm/unitypackage.py`, for putting products into a
project), so writing one is the same format the other way round. The tests make a
package and read it back with that importer.

## What can be made without Unity, and what can't

| File | Without Unity | Why |
| --- | --- | --- |
| Any file with its own `.meta` beside it (copied out of a Unity project) | **Exact** | The `.meta` is kept as it is: the same GUID, so whatever refers to it still finds it, and the same import settings. |
| A file without a `.meta` (a texture, a model, a sound straight from a creator) | **Works, with a new GUID** | Hoard writes a `.meta` with only `fileFormatVersion` and a new `guid`. Unity fills in its default import settings when it imports the file, as it does for a file dropped into a project. Nothing could refer to it by GUID yet, so nothing breaks. |
| A Unity asset without its `.meta` (a `.prefab`, `.mat`, `.unity` or `.asset` from someone's project, with the `.meta` lost) | **Imports, but may be broken inside** | Its own GUID is new, so other assets that referred to it by the old GUID won't find it. What it refers to inside (by GUID) holds only if those assets came with their `.meta` files. Hoard can't rebuild lost GUIDs: the `.meta` files have to come with them. |
| Folders | **Works** | Each folder gets a folder `.meta` (its own when there is one), so the tree goes in as one. |
| Hidden files, files ending in `~` | **Left out** | Unity ignores these in a project, so a package shouldn't carry them. |
| A `.meta` with nothing beside it | **Left out** | It belongs to nothing. |
| Two files carrying the same GUID (two copies of one asset) | **Second gets a new GUID** | A package can't hold one GUID twice. |

Hoard says which files got a new GUID and which were left out, every time.

## What Unity does with it

It is imported like any package: the import window lists the files under
`Assets/<the item's name>/`, and Unity imports them. Files with their own `.meta` keep
their GUIDs and settings. The rest get Unity's defaults for their type, which can be
changed in the Inspector afterwards, as for any new file.

**Not tested in Unity here:** Unity can't run where this was written. Hoard's own
importer reads the packages back, but before release a tester should import one in
Unity 2022.3 that has:

- a folder with its `.meta` files from a project, to check the references hold;
- a folder of plain textures and models with no `.meta` files, to check the default
  settings are filled in.

## What Unity's own export does that this doesn't

- **Dependencies:** *Export Package... → Include dependencies* adds what the chosen
  assets refer to elsewhere in the project. A Local item has no project around it,
  so the package holds exactly the item's files.
- **Previews:** Unity puts in thumbnails for its import window. Hoard doesn't, and
  the import window shows the file-type icons instead.
- **Size:** Hoard won't pack an item over 2 GB. Export a package that big from Unity.

## Where it goes

In **Unity packages**, in your folder for editable copies (Settings → Hoard's
folders). It's named after the item, with "(2)" added beside one that's already
there, and Hoard opens the folder to show it. Hoard never writes into a Local item's
own folder.
