# Changelog

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
