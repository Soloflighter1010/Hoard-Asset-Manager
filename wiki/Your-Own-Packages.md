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
| Its picture | One of its images (one named like a preview first) | A copy of one of its images in `Local`, made again on **Rescan** |
| Disk space | Takes as much again | Only that picture |

A single file can only be copied in; to list something where it is, choose its folder. Links (shortcuts) inside
a folder are left out, and a folder that is itself a link can't be listed.

Copying a large folder takes a while: it runs as a task, so Tasks shows how far it's got.

### A folder of folders

Already keep your things in folders, say one per creator with a folder per product inside? Under **Folders inside
it**, choose **Each folder inside it is a package**, or two or three levels down. Each folder that far down becomes
a package of its own, named for its folder; from two levels down, the folder above it is who made it (type a name
under **Made by** to use it for all of them instead). Hoard lists what it would add before you choose **Add**.
Files in the folders above are left out (the list says how many), Hoard's own downloads folder is never one of
them, and up to 500 can be added at once. They're copied or listed together, as you choose, and **For** applies
to them all.

## Using it

- Local items are in Downloads under **Local**, with your tags, search and **Make an editable copy**.
- **Hoard for Unity** lists them under **Local** (0.4.0 and newer), and imports their `.unitypackage` files like
  any download. Its credits list includes them when they're in the project.
- An item listed where it is is only trusted from Hoard's own sealed records on this computer: if
  `Local/_manifest.json` is changed by anything else, Hoard and Hoard for Unity stop using the folders it names
  until you add them again.
