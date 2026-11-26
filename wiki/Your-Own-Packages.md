Hoard keeps what you make beside what you buy. Packages you put together to move textures and materials between
projects, or to hand to the people you make things for, live under **Local**: tagged, searched and imported into
Unity like your downloads.

## Adding something

Open **Local** (in the bar at the top, or the **Local** tab in Downloads) and choose **Add your own**:

1. Choose **Folder…** or **File…** to pick it, or type its full path (for example `D:\Packages\My Textures`). (In a
   web browser rather than Hoard's own window, there's no picker: type the path.)
2. Give it a name (the folder's name if you leave it empty), who made it (**You** unless you say), and, if you
   like, who or what it's for: a commission, a project, a friend.
3. Choose how Hoard keeps it. Hoard offers what you chose last time.

| | **Copy it into Hoard** | **List it where it is** |
|---|---|---|
| Where the files are | A copy in `Local` inside your downloads folder | Where they already are |
| Changing the original later | Doesn't change the copy | Is what Hoard lists (choose **Rescan** to pick up files you added or removed) |
| Routine checks ([Checking your downloads](Downloads#checking-your-downloads)) | Checked like a download | Left alone: it's your working folder |
| What Hoard writes there | Its copy, and `asset.json` beside it | Nothing, ever |
| **Remove from Local** | Deletes Hoard's copy (only the files it copied) | Only forgets it; nothing in the folder is touched |
| Its picture | One you choose, else one of its images (one named like a preview first) | One you choose, else a copy of one of its images in `Local`, made again on **Rescan** |
| Disk space | Takes as much again | Only that picture |

A single file can only be copied in; to list something where it is, choose its folder. Links (shortcuts) inside
a folder are left out, and a folder that is itself a link can't be listed. A folder with your downloads folder
inside it (your whole Documents folder, say) can't be added: it would bring Hoard's own downloads into Local. A file
whose name your system can't take is left out, and the rest are still added.

Copying a large folder takes a while: it runs as a task, so Tasks shows how far it's got.

### The Local sync folder

Choose a folder in [Settings](Settings), under **Local sync folder** (5.2.0), and whatever you put in it is added
here by itself: a folder in it is listed where it is, a file in it is copied in. A file over 100 MB or a folder
over 1 GB isn't added (Settings says which). It has to be on a drive of this computer: not a network drive or a NAS.
Take something out of the sync folder and its tile says so; it's only taken out of Local when you choose **Remove
from Local**.

On Windows, the sync folder has Hoard's own icon in File Explorer, and right-clicking any file or folder offers **Add
to Hoard** (on Windows 11, under **Show more options**): a file is copied into the sync folder, a folder is listed
here where it is. Right-click the sync folder for **Sync with Hoard now** or **Open in Hoard**. Settings' **Show it in
File Explorer** turns them off.

### Make a Unity package

**Make a Unity package** (5.2.0), in a Local item's details, makes a `.unitypackage` of it without opening Unity, in
**Unity packages** in your folder for editable copies, and shows it in its folder. Its files go under
`Assets/<its name>/`. A file with its own `.meta` beside it (copied out of a Unity project) keeps it, so whatever
refers to it still finds it; one without gets a new ID, and Unity gives it its usual import settings. Hoard says
which got a new ID, and what it left out (hidden files, those ending in `~`, and stray `.meta` files). Nothing is
written into the item's own folder. More in
[the notes behind it](https://github.com/Soloflighter1010/Hoard-Asset-Manager/blob/main/docs/UNITYPACKAGE-FROM-LOCAL.md).

### A folder of folders

Already keep your things in folders, say one per creator with a folder per product inside? Under **Folders inside
it**, choose **Each folder inside it is a package**, or two or three levels down. Each folder that far down becomes
a package of its own, named for its folder; from two levels down, the folder above it is who made it (type a name
under **Made by** to use it for all of them instead). Hoard lists what it would add before you choose **Add**.
Files in the folders above are left out (the list says how many), Hoard's own downloads folder is never one of
them, and up to 500 can be added at once. They're copied or listed together, as you choose, and **For** applies
to them all. Adding the same folder again later only adds the folders that are new: those already in Local are
marked in the list and left as they are. (Packages added with a beta of 3.0, before beta 6, aren't recognised this way.)

### From KonoAsset

Switching from [KonoAsset](https://github.com/siloneco/KonoAsset)? Choose **Bring in from KonoAsset...** in
Settings, under Bring in from another tool (or, the first time, in the setup assistant's last step), and choose KonoAsset's data folder: the one with
`metadata`, `data` and `images` in it (KonoAsset's Settings say where it is). KonoAsset needn't be running, or
installed. Before anything changes, Hoard says what bringing it in will do; then **Bring in** or **Cancel**.

- An asset whose BOOTH item is in your Hoard library is matched to that product. The rest become Local products,
  listed where they are: their files stay in KonoAsset's `data` folder, and KonoAsset's picture is the one chosen
  for each.
- Its tags become your tags, and so do its category and the avatars a wearable fits. An avatar is marked as an
  avatar and a world object as a world, unless you've said what it is.
- Its memo becomes the product's note (see [Library](Library#an-items-details)), with what it needs listed after
  it ("Needs: ..."), and a Local product's BOOTH page. A note you've written already stays.
- An asset with no files that isn't in your library is left out, and named.

Hoard only reads KonoAsset's folder: nothing in it is written, moved or deleted. It remembers what it brought in
(`konoasset.json` in its app-data folder), so bringing in again later adds only what's new. It reads KonoAsset's
lists as KonoAsset 1.0 and later write them.

### From BB's Library Manager

Switching from [BB's Library Manager](https://github.com/BunBnnuy/BBLM)? Choose **Bring in from BB's Library
Manager...** in Settings, under Bring in from another tool, and choose its root folder: the one with a folder for each
product in it, each with its `meta.json` (its Settings say where it is). It needn't be running, or installed. Before
anything changes, Hoard says what bringing it in will do; then **Bring in** or **Cancel** (5.2.0 beta 13).

- A product whose BOOTH item is in your Hoard library is matched to that product, and one whose folder is in Local
  already (added with **Add your own**, say) to that one. The rest become Local products, listed where they are:
  their files stay in its folder, its `thumbnail.png` is the picture chosen for each, and the page each came from is
  its page on a store (see [Changing it](#changing-it)). BB's Library Manager's own `meta.json` and picture aren't
  among their files. One named like a product in Local gets "BBLM" and its id after its name.
- Its tags become your tags, and a product it marks for adults is marked 18+, unless you said it isn't (**It isn't
  for adults**: your word wins).
- A product still downloading in it, one with no files that isn't in your library, and one that can't be listed
  (with why) are left out, and named.

Hoard only reads its folder: nothing in it is written, moved or deleted. It remembers what it brought in
(`bblm.json` in its app-data folder), so bringing in again later adds only what's new; a product taken out of Local,
or whose folder moved with its root, comes in again. **Stop**, in Tasks, stops it between products, and nothing is
brought in.

## Its picture

An item's tile shows one of its own images to begin with. To show another, open it and choose **Choose a
picture...**: any PNG, JPEG, WebP or GIF on your computer, made at most 640 pixels across (a still picture, saved as a
PNG or JPEG). Hoard keeps it in `local-pictures` in its app-data folder and copies it, as `_thumbnail.png` or
`.jpg`, into its own folder for the item: beside its copy, or in `Local/_linked/...` for one listed where it is, so
nothing in your folder is written. Hoard for Unity shows it too. **Rescan** keeps it. **Take the picture off** (or,
for an item listed where it is, **Use one of its own pictures**) goes back to one of its own. An item with a
`_thumbnail` image of its own shows that one: change that file instead.

## Changing it

**Edit...**, in an item's details, changes its name, who made it, its note, and its page on a store (5.2.0 beta 13):
a product's page on Booth, Gumroad, Jinxxy, Payhip or itch.io, such as a free BOOTH item you downloaded yourself.
Renamed, its tags, its note, your choices for it (hidden, 18+) and its places in your sets go with it. Its files and
its folder aren't touched. Its details then open that page (**Open on Booth**, or its store's). Each item in Local
has a name of its own: one another item has is refused.

With a page, **Fill in from its page** reads it, as anyone can see it, and fills in its name, who made it, the tags its
creator gave it (as suggestions), and its picture. A product its store marks for adults is marked 18+. Hoard asks
whether to, as soon as you give an item a page.

## Using it

- Local items are in Downloads under **Local**, with your tags, search and **Make an editable copy**. Once one has a
  page on a store, Local has a tab for each store, and one for those with no page (5.2.0 beta 13).
- **Hoard for Unity** lists them under **Local** (0.4.0 and newer), and imports their `.unitypackage` files like
  any download. Its credits list includes them when they're in the project.
- An item listed where it is is only trusted from Hoard's own sealed records on this computer: if
  `Local/_manifest.json` is changed by anything else, Hoard and Hoard for Unity stop using the folders it names
  until you add them again.
