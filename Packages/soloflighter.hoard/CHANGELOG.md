# Changelog

## 0.1.1

Published the way VRChat's template-package does: each release now also has a `.unitypackage`, for projects
without VCC, and the VCC listing has moved to https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json
(the earlier `vpm/index.json` address keeps working). No changes inside Unity.

## 0.1.0

First version: **Window › Hoard** browses what the Hoard app has downloaded, shows which products are already
in this project (from the GUIDs inside each `.unitypackage`), and imports a `.unitypackage` through Unity's own
import dialog. Imports are recorded in `ProjectSettings/Hoard/imports.json`.
