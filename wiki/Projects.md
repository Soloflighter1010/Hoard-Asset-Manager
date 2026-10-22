# Projects

**Projects** (at the top of either page) is your Unity projects: make one ready to use, with the packages and the
products from your library it needs, open it in Unity, and change its packages. It's new in Hoard 5.0. From 5.1 it
takes the whole window, with its views as tabs along its top: **Projects**, **Repositories**, **Backups**, **Unity and
folders**, and (from 5.1.3) **Logs**. Rows alternate in colour, and the one under the pointer is outlined.

It's the same list of projects as [ALCOM](https://vrc-get.anatawa12.com/en/alcom/)'s and the VRChat Creator
Companion's. A project you add or take off in any of the three is added or taken off in all of them, and Hoard keeps
the Creator Companion's other settings as they are. Hoard does what ALCOM does from its own code, so it doesn't need
ALCOM or the Creator Companion installed: it chooses the same package versions, and makes the same projects.

## The list

Each project shows its kind (avatars or worlds), its Unity version, and when you last opened it. **★** makes it a
favourite, at the top of the list. **Open in Unity** opens it; **Manage** shows its packages and more. A project whose
folder has gone (moved, or on a drive that isn't connected) says so, with **Take off the list**.

**Add a project...** lists one you already have: in Hoard's own window it opens your computer's folder picker, in your
projects folder (in a web browser, you type the folder's full path). **Take off the list** leaves its folder as it is;
to delete a project from your computer, see [Managing a project](#managing-a-project).

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

[Hoard for Unity](Hoard-for-Unity) is in a new project to begin with (its repository is added for you if you haven't
got it); click it to leave it out. **Add packages** opens a view of its own: every VPM package from your repositories
that works in the project's Unity, in groups by the repository it comes from (VRChat's own first, your package folders
last; each folds away, and what you find opens its group), to tick (with a version, if you'd rather not have the newest), then **Add the
chosen packages**. **Put in products from your library** opens Downloads in **Select** mode, for this project: tick
the products you want, then **Add to project**, and you're back at the new project as you left it, with them in
(**Cancel** goes back without them). A product with several packages (one for PC, one for Quest, a few variants)
asks which this project needs. **Put in a set** puts in what's downloaded of one of your [sets](Sets).
What the products need ([What it needs](Downloads#the-downloads-view): lilToon, Poiyomi Toon, Modular Avatar, VRCFury,
NDMF, Avatar Optimizer, the VRChat SDK) is offered beside them, to add with a click; the repository it comes from is
added for you, unless a repository you have already gives it (one added in ALCOM or the Creator Companion too, under
any spelling of its address), which is used instead, so no repository is ever added twice. What the project already
has isn't offered again: it's said, as **Already in the project**.

**Make the project** makes it as a task (see [Projects' tasks](#projects-tasks)): the template, its packages, then
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

**Manage** shows a project, with tabs of its own: **Packages** (in columns: each package, the version installed, any
update, and the repository it comes from), **Add
packages**, **From your library**, and, when [Hoard for Unity](Hoard-for-Unity#projects-in-hoard) has reported on it,
what it found. From there:

- **Add packages** (its tab: tick them, then **Add the chosen packages**), **Update** one or all of them, or
  **Remove** one (with what only it needed).
- **Another version of a package**: choose a package's version (the button with its number on it) to see every
  version that works in the project's Unity, newest first, and install any of them, an older one too. The packages
  it needs change to match. **Add packages** can choose a version as well, instead of the newest.
- **Put it right**, when the project's packages aren't installed the way it says (after cloning it from Git, say).
- **Put in products from your library**, later: Downloads opens in **Select** mode for this project, with nothing to
  do there but **Add to project** or **Cancel**. What's chosen is shown before it goes in, with what it needs.
  Nothing already in the project is replaced: a file that's there (with the same asset ID, or at the same path) is
  left as it is.
- **What went in, and where.** Each time Hoard puts products in a project (making it, or later), it adds them to
  `Hoard imports.md`, beside the project's `Assets` folder: each product, its file, when, and the folders it added
  (or the package, in `Packages`), with anything left as it was because the project already had it. Unity doesn't
  use that file, and deleting it changes nothing. Hoard also adds them to `ProjectSettings/Hoard/imports.json`, the
  list [Hoard for Unity](Hoard-for-Unity) keeps of what it imported, so it knows they're in the project.
- **Open in Unity**, with the version the project uses; when that one isn't installed, another you have (which
  may change the project to its own version).
- **Open folder**, and **Back up**: everything in the project but what Unity makes again by itself (`Library`,
  `Temp`, `Logs`, `obj`) in a zip, in your backups folder. Packages from repositories can be left out, since they're
  downloaded again.
- What [Hoard for Unity](Hoard-for-Unity#projects-in-hoard) reports about it: the products it uses, which have
  updates, and its credits.
- **Delete from this computer...**: the project's folder is deleted, and it's taken off the list. It's backed up into
  your backups folder first, unless you untick that (without a backup, it can't be got back), and only once you've
  typed its name. Hoard won't delete a project Unity has open, or one that holds its own folders (the downloads
  folder, or your backups folder).

Every change to packages is shown before it's made: what's installed, what's removed and why, and anything old the
new packages replace. It's made as a task (see [Projects' tasks](#projects-tasks)); **Stop** puts everything back as
it was. If Unity has the project open,
Hoard says so: close it first, so nothing it has open is replaced under it.

Each package download is checked against the SHA-256 its repository lists for it, and downloads are kept where ALCOM
keeps them, so neither downloads one twice.

## Projects' tasks

Making a project, changing its packages, putting products in it, backing it up or deleting it, and refreshing the
repositories are Projects' tasks, and they run on their own, beside the rest of Hoard's: a project's change never
waits behind a sync or a download, and they never wait behind it. Projects' tasks wait their turn after each other.
What Projects is doing shows at its top, with **Stop**, and in **Tasks**. **Stop** stops a task at its next step, and
puts back what it was changing; it never closes a store's browser that a download is using.

## Repositories

Where packages come from: VRChat's own (Official and Curated) and any you add, the same list ALCOM and the Creator
Companion use. **Add a repository**, at the top, takes its address; for a private one, **For a private repository** takes the
headers it asks for, sent only to its own address. **Refresh them all** fetches the newest listing of each.

## Unity and folders

The Unity versions Hoard found, the way ALCOM finds them (the ones Unity Hub installed or was told about), and the
folders new projects and backups go in. **Offer prerelease versions of packages** lists packages' prereleases too.
These are kept in the Creator Companion's settings, so ALCOM and the Creator Companion use them too.

## Backups

**Backups** (beside **Repositories**) lists every project backup in your backups folder, newest first, with its size,
and how much room the drive it's on has left. A backup is **old** when it's past the newest few of its project (3
unless you choose 1, 2, 5 or 10) and older than a month (or a week, 2 weeks, 3 or 6 months, or a year). **Delete the old
ones**, or **Move the old ones...** to a folder on another drive with more room; or tick the ones you want, then **Delete
the chosen ones** or **Move the chosen ones...**.

- When the drive your backups are on runs low on room (less than 10 GB, or a tenth of the drive, free) and there are
  old backups, the top of Projects says so, with **Delete or move them**.
- Moving copies each backup, checks the copy is whole, and only then deletes it where it was, as a task. The ones you
  moved are listed under **Moved to**, to delete later too.
- Only zips named as a backup is (`<project>-<date>T<time>.zip`, as Hoard and ALCOM name them), directly in your
  backups folder or the folder you moved them to, are ever listed, deleted or moved. Anything else there is left as it
  is.

## Logs

**Logs** shows what Hoard did to your projects, packages and repositories since it started, and what went wrong, as
ALCOM's Logs page and the Creator Companion's Logs tab show theirs: each entry's time, its level (**Info**,
**Warning** or **Error**) and what happened, the newest at the bottom. That's every step of Projects' tasks and how
each ended; a project opened in Unity, put on the list or taken off it; a repository added or removed, or one that
couldn't be read; **Unity and folders** saved; presets saved or deleted; backups deleted; and anything Projects
couldn't do.

- **Find in the log** finds entries by their words. Untick **Info**, **Warnings** or **Errors** to leave those out
  (which ones you show is kept, in this browser).
- New entries come in as they happen. **Follow new entries** keeps the newest in view; turn it off to read back
  without being moved.
- Each time Hoard starts, Projects' log is written to a file of its own, `projects-<date>_<time>.log`, in Hoard's logs
  folder (**Open logs folder**), beside Hoard's own logs; the newest 30 are kept, as ALCOM keeps its own. **Logs**
  shows this run's; earlier runs' are in those files.

ALCOM and the Creator Companion keep logs of what they do: ALCOM's in `vrc-get/gui-logs` in the Creator Companion's
folder, the Creator Companion's in its `Logs` folder. Hoard leaves those alone.

## Where it's kept

The project list, repositories and these settings are the Creator Companion's, in its folder: `%LOCALAPPDATA%\VRChatCreatorCompanion`
on Windows, `~/.local/share/VRChatCreatorCompanion` on macOS and Linux. Hoard reads the Creator Companion's database
there (`vcc.liteDb`) and never writes to it. Favourites, when you opened a project from Hoard, and what you put in
each from your library are Hoard's own, in `vpm-projects.json`, with which backups count as old and where you last moved
some; presets are in `vpm-presets.json` (see
[Where Hoard keeps things](Where-Hoard-Keeps-Things)).
