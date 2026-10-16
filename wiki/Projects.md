# Projects

**Projects** (at the top of either page) is your Unity projects: make one ready to use, with the packages and the
products from your library it needs, open it in Unity, and change its packages. It's new in Hoard 5.0, a beta for
now: turn on **Get beta updates** in **Settings › Updates** to try it.

It's the same list of projects as [ALCOM](https://vrc-get.anatawa12.com/en/alcom/)'s and the VRChat Creator
Companion's. A project you add or take off in any of the three is added or taken off in all of them, and Hoard keeps
the Creator Companion's other settings as they are. Hoard does what ALCOM does from its own code, so it doesn't need
ALCOM or the Creator Companion installed: it chooses the same package versions, and makes the same projects.

## The list

Each project shows its kind (avatars or worlds), its Unity version, and when you last opened it. **★** makes it a
favourite, at the top of the list. **Open in Unity** opens it; **Manage** shows its packages and more. A project whose
folder has gone (moved, or on a drive that isn't connected) says so, with **Take off the list**.

**Add a project** lists one you already have, by its folder's full path. **Take off the list** leaves its folder as it
is.

Projects you've opened Hoard's window in ([Hoard for Unity](Hoard-for-Unity)) that aren't on the list show below it,
with what they use and their credits, and **Add to the list**.

## A new project

**New project** makes one in your projects folder, from:

- **VRChat Avatars** or **VRChat Worlds**: VRChat's templates (the same as ALCOM's), for Unity 2022.3.22f1 (the
  VRChat SDK's own version), 2022.3.6f1 or 2019.4.31f1. The VRChat SDK is installed in it from VRChat's repository.
- **Blank**: an empty project, for any Unity you have.
- An ALCOM template (`.alcomtemplate`) you have, which ALCOM keeps in the Creator Companion's folder, in
  `vrc-get/templates`.

A Unity version marked ✕ isn't installed on this computer: the project is made either way, and Unity Hub installs
that version to open it. The name is checked as you type, as ALCOM checks it (a name Windows can't use as a folder
name, one already there).

**Add packages** adds VPM packages from your repositories. **Put in products from your library** chooses products
you've downloaded, and which of their files: a product with several packages (one for PC, one for Quest, a few
variants) asks which this project needs. **Put in a set** puts in what's downloaded of one of your [sets](Sets).
What the products need ([What it needs](Downloads#the-downloads-view): lilToon, Poiyomi Toon, Modular Avatar, VRCFury,
NDMF, Avatar Optimizer, the VRChat SDK) is offered beside them, to add with a click; the repository it comes from is
added for you.

**Make the project** makes it as a task (in **Tasks**, where **Stop** stops it): the template, its packages, then
your products. A `.unitypackage` goes straight into the project (as ALCOM puts one in, without opening Unity), a VPM
package in a `.zip` goes into `Packages`, and whatever those packages need is installed with them.

### From anywhere in your library

Products don't have to be chosen in Projects. In the Library or Downloads, choose some (tick them, Ctrl- or
Shift-click, or **Select**) or right-click one, then **Projects**:

- **Put in a project...** chooses a project from the list and shows what goes in, with what the products need (to
  leave out with a tick), before it's put in. Nothing already in the project is replaced.
- **New project with these...** opens **New project** with them already in it.

A product with several packages to choose from (one for PC and one for Quest, say) asks which; one that isn't
downloaded, or has no Unity or VPM package, is left out, and Hoard says which.

### Presets

**Save as a preset** keeps the template, Unity version, packages and products as a preset, to start a project from
again (**Start from a preset**): your usual avatar base, say. **Save it for ALCOM too** writes the preset as an ALCOM
template, so ALCOM can make the same project. ALCOM can't open a package inside a `.zip`, so those are left out of it
(Hoard says which).

## Managing a project

**Manage** shows a project's packages, each with its version and any update. From there:

- **Add packages**, **Update** one or all of them, or **Remove** one (with what only it needed).
- **Put it right**, when the project's packages aren't installed the way it says (after cloning it from Git, say).
- **Put in products from your library**, later. Nothing already in the project is replaced: a file that's there
  (with the same asset ID, or at the same path) is left as it is.
- **Open in Unity**, with the version the project uses; when that one isn't installed, another you have (which
  may change the project to its own version).
- **Open folder**, and **Back up**: everything in the project but what Unity makes again by itself (`Library`,
  `Temp`, `Logs`, `obj`) in a zip, in your backups folder. Packages from repositories can be left out, since they're
  downloaded again.
- What [Hoard for Unity](Hoard-for-Unity#projects-in-hoard) reports about it: the products it uses, which have
  updates, and its credits.

Every change to packages is shown before it's made: what's installed, what's removed and why, and anything old the
new packages replace. It's made as a task; **Stop** puts everything back as it was. If Unity has the project open,
Hoard says so: close it first, so nothing it has open is replaced under it.

Each package download is checked against the SHA-256 its repository lists for it, and downloads are kept where ALCOM
keeps them, so neither downloads one twice.

## Repositories

Where packages come from: VRChat's own (Official and Curated) and any you add, the same list ALCOM and the Creator
Companion use. **Add a repository** takes its address; for a private one, **For a private repository** takes the
headers it asks for, sent only to its own address. **Refresh them all** fetches the newest listing of each.

## Unity and folders

The Unity versions Hoard found, the way ALCOM finds them (the ones Unity Hub installed or was told about), and the
folders new projects and backups go in. **Offer prerelease versions of packages** lists packages' prereleases too.
These are kept in the Creator Companion's settings, so ALCOM and the Creator Companion use them too.

## Where it's kept

The project list, repositories and these settings are the Creator Companion's, in its folder: `%LOCALAPPDATA%\VRChatCreatorCompanion`
on Windows, `~/.local/share/VRChatCreatorCompanion` on macOS and Linux. Hoard reads the Creator Companion's database
there (`vcc.liteDb`) and never writes to it. Favourites, when you opened a project from Hoard, and what you put in
each from your library are Hoard's own, in `vpm-projects.json`; presets are in `vpm-presets.json` (see
[Where Hoard keeps things](Where-Hoard-Keeps-Things)).
