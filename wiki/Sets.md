# Sets

A set groups products you use together: an avatar, its outfits and hair, and the shaders and tools they need.
From 4.2, a set can hold anything in your library, downloaded or not, and products you don't own yet: a set
someone shared with you lists what it needs, and where to buy each.

## The Sets tab

**Sets** is a tab beside the stores, in the [Library](Library) and in [Downloads](Downloads) (and **Sets** in the bar
at the top of every page opens it in the Library). Each set is a big tile: the picture you chose for it (see
[Its picture](#its-picture)), or four of its products' pictures, with how many products it has and how many are
downloaded, yours to download, or still to buy.

Open a set and it's a folder of its products. **Sets** above its name goes back to every set.

- **The ones on this page** are their usual tiles: open one for its details, or select several and use the
  selection bar or right-click as anywhere (**Sets**, **Take out of** this set, takes them out). In a set, these
  are all of its products here, whichever view (Library, Archive...) they're in.
- **The rest** come after them, each with its picture and where it is. In the Library: **Not yours yet**, with
  **Buy on** its store (opens the product's page in your browser), and **Your own, in Local**. In Downloads, also
  **Yours, not downloaded**, which opens it in the Library. **×** takes one out of the set.

A set also has **Share...**, **Download the N not downloaded** (every product of it that's yours and not downloaded,
at once, as **Download** does in the Library), **Choose a picture...**, **Rename** and **Delete** (deleting a set
leaves its products as they are), and under **Note and photos** a **Note** (what it's for, or how to put it
together) and **Photos** (below).

## Making a set

- **New set**, in the Sets tab, then add products to it.
- Choose products in the **Library** or in **Downloads** (tick their boxes, Ctrl- or Shift-click, or **Select**
  on a touch screen), then **Sets** in the selection bar (or right-click): **New set from these...**, or **Add to**
  a set you have. In the Library that works whether they're downloaded or not.
- A product's details, in the Library or in Downloads, list its sets: **Add** puts it in another, **×** takes it
  out, and a set's name opens it in the Sets tab.
- **Make a set** in **Projects** makes one of the products a Unity project uses.

A set remembers what each product is when it's added (its name, creator, store page and picture), so it can be
shown and shared whether or not the product is in your library now. Products are known by the same key tags use
(their store and name, without versions or labels), so a product stays in its set when it's updated or moved to
another library folder.

## Sharing a set

**Share...** makes a link to the set viewer on Hoard's website, such as
`https://hoard.furryup.link/set.html#H1.…`, with **Copy the link**, **Copy the code** (just the part after `#`)
and **Open it**. Anyone who opens the link sees the set's name, your note and photos, and each product with its
picture and a link to its store page. Pasting the link (or the code) into **Add a shared set...** in their Sets
tab adds the set to their Hoard: what they own already shows as theirs, and what they don't says where to buy it.

- **Nothing is uploaded.** The set is in the link itself, after the `#`, which a browser never sends anywhere:
  the viewer reads it in the page, and Hoard's website never sees it. Hoard keeps no copy of shared sets, and
  there's no account.
- **What's in a link:** the set's name, note and photo links, and each product's store, name, creator, store page
  and picture address. Not your library, your downloads, your tags or anything else of yours.
- **What's never in one:** your own products (**Local**) and hidden products, whether the hidden library is
  locked or not. Sharing says how many were left out.
- **Pictures:** each product's picture loads from its store's own image host (Booth's, Gumroad's and so on), so
  Hoard hosts nothing. Store pages are only links to the stores' own websites.
- A set of 20 products makes a link of about 2,000 characters. Links that long work in browsers and most chat
  apps; a very big set may be too long for a single Discord message, so share it in a file, or in two sets.

## Its picture

**Choose a picture...** in a set takes a picture from your computer for its tile: a PNG, JPEG, WebP or GIF, made at
most 640 pixels across. Hoard keeps it in `set-pictures` in its app-data folder; it isn't shared with the set (a
link holds no pictures) or kept in backups. **Take the picture off** goes back to its products' pictures. Your own
packages can have a picture of your choosing too: see [Your own packages](Your-Own-Packages#its-picture).

## Photos

A set can have up to 8 of your own photos of it (an avatar wearing the outfit, say), shown in the viewer with the
set. Hoard doesn't host pictures: put them on a photo site, then **Add a photo link...** with the link to the
picture itself. Links from these sites are accepted: Imgur (`i.imgur.com`), Gyazo (`i.gyazo.com`), X
(`pbs.twimg.com`), Bluesky (`cdn.bsky.app`), Reddit (`i.redd.it`), Postimages (`i.postimg.cc`), ImgBB
(`i.ibb.co`), Discord (`cdn.discordapp.com`, `media.discordapp.net`), and the stores' own image hosts. The
viewer shows pictures only from those sites. Discord's links stop working after a while, so for a set you'll
share for long, use another site.

## In Hoard for Unity

Hoard for Unity's **Sets** pill lists your sets, and **Import set** imports the downloaded products in one go
(see [Hoard for Unity](Hoard-for-Unity)). Products a set has that aren't downloaded aren't in Unity yet:
**Download the N not downloaded** in the Sets tab brings them in, and buying the ones that aren't yours.

## Where sets are kept

In `sets.json` in Hoard's app-data folder (see [Where Hoard keeps things](Where-Hoard-Keeps-Things)), and in
backups (**Settings**, **Backup**). A backup made while your hidden library is locked leaves hidden products out
of every set.
