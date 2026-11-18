# Preparing a new Unity project ahead of time

Research for #377, written 18 November 2026. It says what Hoard could do so that a new
VRChat project opens readier than one Unity builds from nothing on its first open,
and what it shouldn't do. **No timings were taken for this note:** Unity can't run
where it was written. The "How to measure" section says how to take them on a real
computer before anything is built.

## What a new project's first open spends its time on

Roughly in this order, for a project Hoard has just made from a template:

1. **VPM packages.** The VRChat SDK and anything else from a repository, downloaded and
   unpacked into `Packages/`. **Hoard already does this** when it makes the project
   (it resolves and installs them before the project is handed to Unity), so the
   Creator Companion's resolver has nothing left to fetch on the first open.
2. **Unity's own packages** (`Packages/manifest.json`), fetched by the Package Manager
   into `Library/PackageCache`. Unity keeps a cache of these per computer and user, so
   after the first project with a given version they're copied rather than downloaded.
3. **Importing every asset** (`Assets/` and every package) into the import artifacts
   under `Library/`. For a VRChat project most of these belong to the SDK and are the
   same in every project.
4. **Compiling scripts** into `Library/ScriptAssemblies` (and Bee's build files).
5. **Compiling shaders**, mostly as each one is first used, into `Library/ShaderCache`.
   This continues after the project is open, so no preparation removes all of it.

Steps 3 to 5 are what make a first open slow, and all of them live in `Library/`.

## The ways to do those steps before Unity is opened

| Way | What it saves | Safe? | Verdict |
| --- | --- | --- | --- |
| Import in the background with the installed Unity, in batch mode | Steps 2 to 4 (and the shaders it compiles while importing) | Yes, with care: see below | **Worth building** |
| A local Unity Accelerator (cache server) | Step 3, for assets already imported in any project using it | Yes, but it's a separate install and a project setting | Document; maybe offer later |
| Copying another project's `Library/` folder | Steps 3 to 5, when it matches | **No** | Don't |
| A template with a `Library/` already in it | Same as copying | **No** (the same risks, made once and shipped) | Don't |

### Import in the background (batch mode)

Unity's command line opens a project without its window:
`Unity -batchmode -quit -projectPath "<project>" -logFile "<log>"`
([Unity: command-line arguments](https://docs.unity3d.com/2019.3/Documentation/Manual/CommandLineArguments.html)).
Opening a project this way does the same first import a normal open does, then quits.
The next open, with its window, starts from a finished `Library/`.

It is the user's own Unity, on their computer, with their own licence, doing what it
does on any open, so there's nothing in it against Unity's or VRChat's terms. What
has to be right:

- **Only one Unity at a time per project.** Unity refuses to open a project another
  Unity has open. While Hoard prepares a project, *Open in Unity* must wait (or stop
  the preparation first), and Hoard must not start one while Unity has the project
  open (it already tells which projects Unity has open).
- **Licensing.** Batch mode needs the editor's licence to be active on the computer,
  as it is once Unity Hub has signed in. A machine where it isn't fails with a licence
  error in the log; Hoard should say so and leave the project as it was, not retry.
- **It takes as long as a normal first open,** and uses the CPU and disk as heavily.
  It saves the waiting, not the work: run it as a Projects task, with Stop, and only
  when asked ("Get it ready now") or as an option on New project.
- **Its log** goes to the project's own `Logs/` folder, so a failure can be read and
  sent in a support report.
- **Editor scripts that ask questions.** Some packages show dialogs on their first
  import. In batch mode there's nobody to answer, so they take their defaults or
  fail. This needs testing with the VRChat SDK and the most common packages before
  it's offered.

### A local Unity Accelerator

The Accelerator is Unity's cache server for Asset Import Pipeline v2: an editor that
imports an asset uploads the result, and another editor that would import the same
asset downloads it instead
([Unity: Unity Accelerator](https://docs.unity3d.com/2022.1/Documentation/Manual/UnityAccelerator.html)).
Projects using the same namespace share entries, so the SDK's import results could be
reused between a user's own projects. It's turned on per project in **Project Settings
→ Editor → Cache Server**.

It's a separate program to install and keep running, it applies to every project that
uses it, and the documentation notes that anyone with access to the computer it runs
on can read what it stores. Hoard shouldn't install it. If someone already runs one,
Hoard could offer to point new projects at it. That is small, but it only helps people
who have set it up, so it isn't a priority.

### Copying a `Library/` folder (and templates with one)

Unity's manual calls `Library/` a cache of the project's own assets, which it can
rebuild from `Assets/` and `ProjectSettings/`. It doesn't support sharing it between
projects. Unity's issue tracker has reports of errors and corrupted projects from
sharing `Library/` content, and it holds paths and machine-specific build state.
([Unity: Importing assets](https://docs.unity3d.com/Manual/ImportingAssets);
[Unity issue tracker: errors with a symlinked Library folder](https://issuetracker.unity3d.com/issues/console-errors-appear-when-reimporting-unityengine-dot-ui-when-the-library-folder-is-symlinked)).
A project that opens with a wrong `Library/` can look fine and break later. That cost
falls on the user, not Hoard, so Hoard won't do it, even for a "same version, same
packages" template.

## How to measure, before building it

On a Windows computer with Unity 2022.3 and the VRChat SDK, for an avatar and a world
template:

1. Time the first open of a project Hoard just made (from *Open in Unity* to the editor
   being idle), three times, with a new project each time.
2. Run the batch-mode command above on another new project, timing it, then time its
   first open with the window.
3. With an Accelerator running and the project pointed at it, make two projects and
   time the second one's first open.

The saving that matters is (1) minus the open in (2). If it's under a minute, the
background preparation isn't worth its complexity.

## Recommendation

- **Build:** a "Get it ready" Projects task that imports a new project in batch mode,
  with the safeguards above, offered on New project and in a project's details:
  [#390](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/390).
- **Maybe later:** pointing new projects at an Accelerator the user already runs.
- **Never:** copying `Library/` between projects or shipping one in a template.
