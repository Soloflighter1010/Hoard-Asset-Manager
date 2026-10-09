The **Library** shows everything you own on the stores you use, whether or not you've downloaded it.
**Downloads** (the other tab) shows what's on your computer: see [Downloads](Downloads).

## Finding things

- **Search** matches names, creators, stores, variants and tags.
- **The store tabs** above the grid narrow it to one store, with a count for each. The tab you're looking at is
  raised, and the page glows up from the bottom in that store's colour (on **Everything**, the colours of the
  stores you're signed in to drift through it).
- **Filters** on the left: your tags, suggested tags, **Show** (**Downloaded**, **Not downloaded yet** and
  **New**) and creators (**Find a creator** to search a long list). Filters combine; **Clear filters** starts
  again. Each section folds away by its heading, and **Hide filters** folds the whole sidebar to a thin strip;
  both stay as you left them.
- **Sort** by name, creator, store or **Recently added** (the newest first), beside the store tabs.
- **Stack copies:** copies of the same product show as one tile with a count on it (×3): bought more than once,
  in several versions, or on two stores (from 3.1). Hoard knows copies by:
  - **the same picture**, byte for byte, when no other creator uses it: "Hair Pack 1" and "Hair Pack 2" stay
    apart, as their pictures differ;
  - **the same name by the same creator**, on any store (case, spacing, punctuation and 【store】 [labels] aside,
    but not numbers or (variants));
  - **the same name, and a picture that looks the same**, when a creator's shops have different names (say,
    their Gumroad and Jinxxy). Each store saves a picture its own way, so Hoard compares how the pictures look:
    the page works that out once and Hoard keeps it in `picture-looks.json`. Two creators' products with the same
    name and different pictures stay apart;
  - **a picture several creators use and a name nearly the same** (a word more or less, the same numbers).

  A picture several creators use for different names (a store's default banner) stacks nothing. Choose a stack to
  see every copy. Downloads stacks the same copies, and lists the others in a copy's details. Untick **Stack
  copies**, beside **Sort** on either page, to show each on its own; Hoard remembers. While you're choosing
  several, and in Disk space, each copy shows.
- **New:** something that appeared in your library after a refresh has a **New** badge for a week (**New in your
  library** in Settings). What was already there when Hoard first read a store isn't new.

Your search, filters and sort are kept in the page's address, so going back returns you to the same view.

## An item's details

Click an item to open its details. The item stays outlined in gold in the grid while its details are open, so
you can see where it is.

Something you own on more than one store has a striped spine along the bottom of its tile, in both stores'
colours (the tile's label says so too, for screen readers).

In the details:

- **One thing to do, in gold:** **Download** when you don't have a copy yet (Hoard downloads it into your downloads
  folder), or **Show in Downloads** when you do, with **See the update** when its store has newer files. Payhip
  products have **Open on Payhip** instead: Hoard lists them and doesn't download them.
- **Open on** the store (its download page) and **Store page** open the product on its store, in your web browser.
  These buttons only ever go to that item's own store.
- **Organise:** **Archive**, **Hide**, **Remove** and **Delete downloaded files**. See below.
- **You also own this on ...**: Hoard spots the same product bought on more than one store. **Show all copies**
  lists them together.
- **Tags:** add your own tags, or click a suggestion. See [Tags](Tags).
- **Files** lists what the store offers, each with its own download link.
- **Archive**, **Remove** and **Hide**: see below.

## Choosing several at once

Choose **Select**, then click items, or **Select all shown** after filtering (say, by a creator). Then tag them,
**Download** them (one job, across stores; Payhip's are left out, as Hoard doesn't download from Payhip), or
archive, remove or hide them all at once.

## Archive, Removed and Hidden

The views on the left keep things out of your way:

- **Archive** is for older products you want out of sight but still yours. Gumroad's archived purchases start
  there.
- **Removed** is for things that don't belong in your library. They stay out, even after a refresh, and they
  aren't downloaded. **Delete for good** takes them out of Hoard's list entirely. When you remove something you've
  downloaded, Hoard asks whether to delete its downloaded files too; say no and they stay (Downloads lists them
  under Removed), and you can choose **Delete downloaded files** later, in either view. Only the files Hoard
  downloaded are deleted: anything of your own in the same folder stays, and so does the folder.
  **Delete downloaded files** works on anything you've downloaded, too, from its details or for a selection: a
  product still in your library stays there, as not downloaded, so you can download it again later.
- **Hidden** puts products behind a PIN. See the next section.

These choices apply in the Library and in Downloads alike.

## The hidden library

Hidden items stay out of view everywhere (Library, Downloads, counts and tags) until you unlock them.

- **Setting your PIN:** the first time you hide something, Hoard asks for a PIN, then shows **6 recovery
  words, once**. Write them down: they're how you reset a forgotten PIN without losing anything.
- **Unlocking** applies to the window or browser you unlock it in, and lasts 15 minutes after you last use it.
  **Lock now** locks it straight away, and restarting Hoard locks everything.
- **Wrong PINs:** after five wrong tries, each further try waits longer (30 seconds, doubling, up to an hour),
  even if Hoard restarts.
- **Forgot your PIN?** Enter your recovery words and choose a new PIN. Hidden items stay hidden, and every
  browser is locked.
- **Change PIN** needs your current one. **New recovery phrase** (while unlocked) replaces your recovery words,
  and the old ones stop working.
- **Lost your recovery words too?** The only way out deletes the hidden items from Hoard's list, without ever
  showing them. Your downloaded files aren't touched.

It's a privacy screen for Hoard, not encryption: the files on your disk are still ordinary files that anyone
who can open your folders can find. The recovery words only unlock Hoard's hidden library: they aren't a
crypto wallet phrase, and Hoard never asks for one.

## Offline

Hoard saves every product picture after each refresh, so your whole library, its search and its pictures work
without a connection. Refreshing, signing in, downloading and store links need one. Turn picture saving off in
[Settings](Settings) if you'd rather not keep them.
