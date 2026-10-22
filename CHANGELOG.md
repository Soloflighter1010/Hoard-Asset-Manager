# Changelog

## 5.1.3

- **Projects opens with Hoard's splash,** the logo and "Opening your projects", while it reads your projects, as
  the Library does while it opens. The first time you open Projects it shows for a moment; after that, only when
  reading your projects takes a while.
- **Put in products from your library** (a project's, and New project's) opens Downloads in **Select** mode for
  that project, instead of a long list in a window: tick what goes in, then **Add to project**, the only other thing
  to do there being **Cancel**. Either way you're back at the project.
- **Logs in Projects,** as ALCOM and the Creator Companion have: what Hoard did to your projects, packages and
  repositories, and what went wrong, each with its time and level (Info, Warning, Error). Find entries by their words,
  show only some levels, and watch new ones come in. Each time Hoard starts, they're written to a log of their own in
  the logs folder (**Open logs folder**).
- Put right: putting products in a project offered what they need even when the project already had it, and could
  add a repository you already had (VRCFury's, say, added in ALCOM or the Creator Companion with its address spelled
  another way) a second time. What the project has is now only said, a repository that already gives a package is
  used for it, and a repository already there, at any spelling of its address or another address for the same
  listing, is never added again.

## 5.1.2

- Put right: a set or wishlist of about 370 to 500 products was called too big for one short link, so it couldn't
  be shared, and a link it had couldn't be updated to keep it going. Hoard now measures a set as the share server
  does, and these share, and keep their links going, again.
- Put right: Look inside and **Extract** opened a hidden product's file while your hidden library was locked. They
  ask you to unlock it first, as **Make an editable copy** does.
- **Extract takes files out more carefully.**
  - With Unity's .meta files, a folder's `.meta` comes out too, and each file's `.meta` is always beside it under
    the name Unity looks for, even when the file was renamed " (2)" because its name was taken.
  - Nothing already there is ever written over.
  - A file that can't be written (a path too long for your system, say) is left out, and Hoard says which and why;
    the rest still come out. If nothing could be, it says why instead of opening an empty folder.
  - A Unity package in a zip goes in its own folder, where it is in the zip, so two of the same name stay apart.
  - Files get the permissions any new file does, and taking a few files out of a large package is quicker.
- Put right: closing Look inside while it was taking files out showed an error, and ticking a box meanwhile could
  start a second extraction.
- Put right: a wishlist's tags and creators could show nothing after you'd set a price range on another wishlist,
  and a tag chosen on a set could carry over into a wishlist.
- Put right: **Split into sets** could make a part a little too big for its short link when the set's name was
  long and in a script such as Japanese, and could leave out a product added just before splitting. Share... and
  Split are also quicker on long sets.
- Put right: **Share...** gave no answer for a set holding a product too big for a short link on its own.
- Put right: a product a Jinxxy list sends you to on a site that isn't one of the stores (the creator's own, say)
  showed **No store link**. It shows **Buy on** that site, and opens its page there. A shared set leaves such links
  out, as its page opens only the stores' own.

## 5.1.1

- **A set too big for one short link can be split.** A short link holds about 500 products, and a longer set or
  wishlist (Booth's Loved items can run to hundreds) couldn't be shared at all. **Share...** now says when a set is
  too big, and **Split into N sets** makes new sets of its products, in its order, each as full as one short link
  holds: "Booth: Loved items (1 of 2)", "(2 of 2)", each with the set's note and photos. Share each one. The set
  itself stays as it is, and a wishlist read from a store is still brought up to date when you read it again.
- **Projects uses the whole window**, not a column down its middle.
- **A press kit**, on Hoard's website: what Hoard is, the facts, its logo and colours, and its screenshots, to download
  in one go. Every page of the site links it.
- **Look inside takes files out.** Tick the files and folders you want in a Unity package or a zip (a folder brings
  everything in it) and choose **Extract the N chosen files**, or **Extract everything**. They go in a new folder,
  named after the file, in **Extracted** beside your editable copies, in the folders their paths say, with Unity's
  `.meta` files too if you like, and the folder opens. Nothing is written outside it, whatever a package's paths say.
- **A wishlist's tags and creators are in the filters beside it**, as everything else's are: its suggested tags,
  your tags on what you have of it, and who made its products, each with how many. **Sort** orders it too: by name,
  creator or store, or as the store lists it (Recently added).
- Put right: a wishlist you'd filtered stayed on show below the list of sets after you went back to it.

## 5.1.0

- **Projects takes the whole window**, with its views as tabs along its top: Projects, Repositories, Backups, and Unity
  and folders. A project has tabs of its own: its Packages, **Add packages** (a tab now, not a window over the page:
  tick the packages you want, choose a version if you like, then **Add the chosen packages**), From your library, and
  what Hoard for Unity found in it. Rows alternate in colour, and the one under the pointer is outlined.
- **Projects' tasks run on their own**, beside the rest of Hoard's: a project's change never waits behind a sync or a
  download, and they never wait behind it. What Projects is doing shows at its top, with **Stop** (what it was
  changing is put back as it was), as well as in **Tasks**.
- **Add a project...** opens your computer's own folder picker (in Hoard's window), in your projects folder.
  **Repositories** puts **Add a repository** first, above the list.
- **Delete from this computer...**, in a project: its folder deleted, backed up into your backups folder first unless
  you untick that, once you've typed its name. Never a project that holds Hoard's own folders, or one Unity has open.
- **Hoard for Unity in every new project**, unless you leave it out; its repository is added for you if you haven't
  got it.
- **Sets and wishlists** is the Sets tab's name now, with a colour and a heart of its own beside the stores.
- **Wishlists, easier to go through.** What isn't yours yet and what is are two groups, each folding away (and
  staying folded). **Suggested tags**, from words its products' names share, narrow it down, and so does a **price
  range**, in one of its currencies.
- **Add products by link...**, in any set or wishlist: paste products' links on Booth, Gumroad, Jinxxy, Payhip or
  itch.io, and Hoard reads each one's page (as anyone sees it, without your sign-in) for its name, creator, price and
  picture. A wishlist of your own can hold what you don't own yet.
- **Check for updates automatically** checks in the background each time Hoard starts, and once a day while it's
  open (it was at most once a day). It's on to begin with in a new Hoard; one you have already keeps your choice, so
  turn it on in **Settings**, **Updates**, if it's off.
- Put right: a wishlist read again shows as it is now straight away (it showed as it was until you made a new list),
  and taking a product out of a list no longer leaves the products after it with the wrong pictures.

## 5.0.1

- **Projects is now a project manager, with your library in it.** **Projects** (at the top of either page) is your
  Unity projects, the same list as [ALCOM](https://vrc-get.anatawa12.com/en/alcom/)'s and the VRChat Creator
  Companion's. A project added in any of the three shows in all of them, and Hoard keeps the Creator Companion's
  other settings as they are. Hoard works as ALCOM does, from its own code (it doesn't need ALCOM or the Creator
  Companion installed), and only reads the Creator Companion's own database, never writing to it. See
  [Projects](https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki/Projects) in the wiki.
- **A new project, ready to use.** **New project** makes one from VRChat's avatar or world template (Unity
  2022.3.22f1, the VRChat SDK's own, or 2022.3.6f1 or 2019.4.31f1), a blank one, or an ALCOM template, with the VPM
  packages you choose, and with products from your library already in it: a .unitypackage is put straight in
  (each file of one with several variants chosen with a tick), and a VPM package in a .zip goes into `Packages`, with
  what it needs. What your products need (lilToon, Poiyomi, Modular Avatar, VRCFury, NDMF, Avatar Optimizer, the
  VRChat SDK) is offered with a tick, its repository added for you. Put in a whole set at once with **Put in a set**.
- **Presets.** **Save as a preset** keeps a project to start from again: its template, Unity, packages and products
  ("my avatar base"). **Save it for ALCOM too** writes it as an ALCOM template, so ALCOM makes the same project
  (leaving out any package inside a .zip, which ALCOM can't open).
- **A project's packages.** **Manage** lists them, with each one's update; add packages from your repositories,
  update one or all, remove one (with what only it needed), or **Put it right** when they aren't installed the way
  the project says. A package's version is a button
  ([#160](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/160)): it lists every version that works in
  the project's Unity, newest first (prereleases too when **Offer prerelease versions of packages** is on), and
  installs the one you choose, an older one included, with what it needs changed to match. **Add packages** can
  choose a version too. Every change is shown before it's made, and made as a task, so it shows in **Tasks** and
  **Stop** puts everything back as it was. Hoard chooses versions exactly as ALCOM does (its own tests are among
  Hoard's), and checks each download against the SHA-256 its repository gives.
- **Your library in your projects.** Choose products in the Library or Downloads (or right-click one), then
  **Projects**: **Put in a project...** puts them in one of your projects, and **New project with these...** starts a
  new one with them already in it; **Manage** puts more in later. Nothing already in the project is replaced (by its
  asset ID or its path).
- **What went into a project, and where**
  ([#155](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/155)). Each time Hoard puts products in a
  project, it adds them to `Hoard imports.md`, beside the project's `Assets`: each product, its file, when, and the
  folders it added (or its package), and what was left as it was. They're added to Hoard for Unity's own list of
  imports too (`ProjectSettings/Hoard/imports.json`). **Manage** lists the folders each one added, and Hoard for
  Unity 0.9.0 shows them under each product (**Put in by Hoard**, with **Select** to select them).
- **Open in Unity**, with the Unity version the project needs (found as ALCOM finds them, through Unity Hub), or
  another one you choose. **Back up** zips a project, without what Unity makes again by itself, into your backups
  folder.
- **Old project backups, kept in hand.** **Backups**, in Projects, lists every project backup with its size, marks
  the old ones (past the newest 3 of a project, and older than a month, unless you choose otherwise), and deletes
  them, or moves them to a folder on another drive, copied and checked before they go. When the drive your backups
  are on is low on room, Projects says so, with how much the old ones take.
- **Repositories** and **Unity and folders** have views of their own: add a repository (with headers for a private
  one, sent only to its own address), refresh them all, and choose where new projects and backups go, kept in the
  Creator Companion's settings.
- **What Hoard for Unity reports** about a project shows with it, as before: what it uses, which has updates, and
  its credits. A project it reported that isn't on the list shows below the list, with **Add to the list**.
- **Three styles: Standard, Treasure and Workbench**
  ([#159](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/159)). Choose how Hoard lays everything
  out, in the setup assistant or in Settings, under **Appearance**. **Standard** is Hoard as it has always looked.
  **Treasure** shows bigger pictures, each in a frame of its store's colour with the store's name on it, round
  buttons and tabs, and a product's details with its picture large and a row of what it is. **Workbench** makes the
  Library, Downloads and sets close-set lists, each product a row with a small picture, its store, whether it's
  downloaded and when it came, in your computer's own font, with lower bars and closer-set panels and tables. A
  style shows as you choose it, on both pages and from the first moment a page opens, and it's kept with your other
  settings, so it stays when Hoard starts again or updates, and in a backup. Every theme, Light or Dark, and the
  accessibility settings work with all three, in English, Japanese and Korean.
- **Kinds of tags** ([#157](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/157)). A tag can say
  what it's about: Avatar, World, Clothing, Gimmick, Script, Texture or Other, chosen beside it in **Tags**. Your
  tags in the filters are grouped by kind, and the downloads folder's `tags.json` says each tag's kind, for other
  programs.
- **Mix and match** ([#156](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/156)). In the Sets tab,
  **Mix and match...** picks an avatar and an outfit at random from what you own, one product from each of your
  Clothing tags, and only clothes tagged for that avatar if you like. Keep the picks you like, pick the rest again,
  and make a set of them.
- **Sets are shared by short link only** ([#162](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/162)).
  **Share...** makes a short link (about 70 characters, for 14 days) instead of the long link that held the whole
  set, which was too long to pass around. **Update the link** keeps it 14 days from today, so a set can stay shared
  for as long as you like; Hoard doesn't renew it by itself. Long links shared from earlier versions still open, in
  the viewer and in **Add a shared set...**.
- **Your sort stays.** The sort you choose (**Sort**, beside the store tabs) is kept when you go between the Library
  and Downloads, and next time Hoard starts. Downloads can sort by store too, as the Library does; **Largest** is
  only in Downloads, so the Library sorts by name while it's chosen. A link with its own sort still shows that one.
- **Booth wishlists: every loved item.** Reading your loved items on Booth stopped at the first 20; Hoard now turns
  every page. Each item's link opens its page for everyone (`booth.pm/en/items/...`); links kept from before, in a
  wishlist or a set, do too.
- Smaller things put right: in Projects, what you've typed in **Repositories** or **Unity and folders** and not saved
  stays when a task ends, and a save that's refused keeps it to put right. **Mix and match** never picks a product
  you kept for one slot again for another. A backup made into a folder inside the project leaves that folder out. A
  tag's remove button and a suggestion's "in N names" are translated, and backups show their date in your language.
  Workbench's list keeps its words whole (in OpenDyslexic too), and its rows fit the space the list has. A page
  whose request to Hoard couldn't be sent for a moment tries again, rather than saying Hoard isn't running.
- Faster with a large library: a product's contents are read once for each version of its file, products are found
  by key from one map, and the backups folder without listing every project.
- Secure connections are checked against the newest list of trusted certificate authorities (certifi
  2026.10.19).
- For anyone working on Hoard's pages: **the style guide**, at `/styleguide` on a running Hoard, shows every part of
  the pages with its markup, in any page, style, theme, font and text size.

## 4.4.0

- **Wishlists** ([#158](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/158)). The Sets tab now has
  your wishlists too, each product with what it costs, and those already in your library shown as yours:
  - **Read my wishlists...** reads them from Booth (your loved items, and each list of them you made), Gumroad (each
    of your wishlists), Jinxxy (your wishlist, likes and lists) and Payhip (each shop's wishlists), in each store's
    own signed-in window, as a refresh reads your library. It runs as a task.
  - **Import saved wishlist pages...** reads pages you saved from your own browser instead, on your computer.
  - Read again, a wishlist holds what the store's list does now, and a price that changed shows the old one struck
    through. A product that's cheaper than before is marked, and the task lists them.
  - **New wishlist** makes one of your own. A wishlist can be shared, like any set; Hoard for Unity doesn't list them.
  - The privacy policy (version 1.6.0) says so: Hoard reads your wishlists from the stores only when you choose to,
    and keeps them in `sets.json` with their prices.
- **The wiki in Japanese and Korean.** Every page of the wiki for using Hoard is in Japanese and Korean too, naming
  each button and setting as the app does in that language, on GitHub's wiki (linked from the sidebar) and on the
  website, at `docs/ja/` and `docs/ko/`, where each docs page links the same page in the other languages. They were
  translated with AI's help: where one says something different, the English page is right, and
  [Translation fix](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml)
  is how to say so. The pages for working on Hoard itself (Development and Releasing) stay in English. The wiki's home page
  also lists Sets and Your own packages now.
- **File lists keep their names readable with OpenDyslexic.** A downloaded product's files showed one letter a line
  with the dyslexic font, its wider letters leaving no room beside the size and buttons. The buttons now go below
  the name when they don't fit.

## 4.3.7

- **Payhip shops whose sign-in check goes round in a loop now say so, and what to do.** A tester's refresh failed on
  four shops every time: two on their own addresses ("the website kept redirecting in a loop, which is usually a
  passing problem") and two on payhip.com (": : Navigation to ... is interrupted by another navigation to
  chrome-error://chromewebdata/"). A shop on its own address sends every visit to Payhip's sign-in check on
  payhip.com and back, and when that check never finds you signed in to Payhip itself, the two go round until the
  browser gives up. That isn't a passing problem, so Payhip's row now says "Payhip kept sending the page back and
  forth between the shop and its sign-in check on payhip.com", and tells you to sign in to Payhip itself.
- **Signing in to Payhip opens payhip.com's own sign-in page first,** then a tab for each of your shops. Before, it
  opened only the shops, so you were never asked to sign in on payhip.com, which shops on their own addresses rely on.
- **A page that doesn't load says why, in the browser's own words.** When a page fails partway through its redirects,
  the browser shows its own error page, and all Hoard could say was that the navigation "is interrupted by another
  navigation to chrome-error://chromewebdata/". Hoard now reads the reason from that error page, and its log lists each
  address the page went through (without anything after a "?", which can carry sign-in tokens), so a support report
  shows where a loop goes. The stray ": :" before such messages is gone.

## 4.3.6

- **One Payhip shop that can't be read no longer stops the rest.** A shop on its own address that Payhip sent round
  in a loop of redirects (during an outage at Payhip) failed the whole Payhip refresh, with "Couldn't read the
  library: Page.goto: net::ERR_TOO_MANY_REDIRECTS ..." and nothing read from your other shops. Now Hoard reads every
  other shop, and says on Payhip's row in **Stores** which shop it couldn't read and why. Only when no shop can be
  read does the refresh fail.
- **A Payhip refresh that couldn't read every shop keeps what it had from those shops.** A shop you weren't signed in
  to had its purchases dropped from your library until the next full refresh. Now they stay.
- **Why a page didn't load, in plain words.** A store's row said what the browser said, with its log of each step.
  Now it says what happened ("the website kept redirecting in a loop", "the website didn't answer in time").
- **Why some Payhip purchases have no Open on Payhip.** Hoard only opens the links of the Payhip shops in your list,
  so a purchase from a shop on its own address you haven't added had no link, and nothing said why. Its details now
  say so, with **Add this shop**; refresh Payhip after to get its links. **Settings** explains that a shop on
  payhip.com usually lists everything you bought on Payhip, but only the shops listed there have their links opened.
- **The Windows portable zip isn't published any more.** Antivirus engines kept flagging it (never the installer),
  so each release waited on a false positive. Use **Hoard-Setup**: if you used the portable zip, run it once. Your
  settings, library and downloads carry over, and from then on Hoard updates itself. A copy from the portable zip
  now says so when there's an update. `Hoard-<version>.zip`, to run Hoard with Python from any folder, is still
  published.

## 4.3.5

- **Reading a photo site's page stays on that site.** When you add a set's photo by its page link, Hoard reads the
  page once for the picture it shows. It already went only to addresses on the public internet, never to your
  computer or your network. Now the address it reads is put back together from Hoard's own list of photo sites,
  rather than taken as pasted, and a redirect is followed only to another page on those sites, over HTTPS. GitHub's
  code scanning had flagged that the address came straight from what was pasted.

## 4.3.4

- **The Save for Hoard bookmark can be added again.** Hoard asked you to drag it from its window to your browser's
  bookmarks bar, but a link can't be dragged out of Hoard's own window into another browser. Now **get it from its
  page** (in **Stores**, under **Import saved pages**) opens the bookmark's own page on Hoard's website in your usual
  browser, where you drag it to the bookmarks bar. **Copy it** still copies it, to paste as a new bookmark's
  address. It's the same bookmark, for saving every page of your library on a Payhip shop as one file to import.

## 4.3.3

- **Credits lists link each product's public page.** Hoard for Unity's **Create Credits List**, and the credits list
  in **Projects**, linked each product with the link Hoard keeps for you as its buyer. For Jinxxy that's your own
  inventory, which nobody else can open. For Gumroad it can be your download page, which lets whoever has the link
  download the files. Now they link the product's public page on its store, the one anyone can open to see and buy
  it, else the creator's shop page, else nothing. Hoard's catalog lists that page for Hoard for Unity, which uses it
  from 0.8.3, and a refresh now updates the catalog too, so pages a refresh finds reach Unity straight away. A list
  you've already copied or saved keeps its old links: refresh your library, make the list again, and paste the new
  one where the old one is.

## 4.3.2

- **A set's photos can be added by their page link.** **Add a photo link...** took only the picture's own address
  (`https://i.imgur.com/fOJAk3L.jpeg`), not the link a photo site's Share or Copy button gives
  (`https://imgur.com/fOJAk3L`). Now it takes either: for a page on Imgur, Gyazo, ImgBB, Postimages, Bluesky, Reddit
  or X, Hoard reads the page once for the picture it shows and keeps that picture's own link (Imgur's in full, not
  its link-preview crop). Where a page's picture can't be found, it says to copy the picture's own link.
  [PRIVACY.md](PRIVACY.md), the website and the wiki list the photo site among what Hoard talks to.

## 4.3.1

- **Shared sets link each product's own page on every store.** A set links each product to its store, and for
  Gumroad and Jinxxy that was often the creator's shop rather than the product. Gumroad products now get their own
  page from your next Gumroad refresh, from every name Gumroad gives it (and Gumroad's own address for a creator on
  a domain of their own). Jinxxy's inventory only links the creator, so a refresh now opens each item's own page
  once to find its product page, then keeps it, so only new items are opened later (at most 150 in one refresh,
  with the usual pause). A page found once is kept across refreshes, for every store. Share a set again, or
  **Update the link** of its short link, after refreshing.
- **A product with no picture shows its initials in the set viewer,** on a colour from its creator's name, as
  Hoard's own tiles do, and every product there has its store's colour along its foot.

## 4.3.0

- **Short links for shared sets.** A set's link holds the set itself, so a big set's is thousands of characters
  long. **Make a short link**, in **Share...**, makes one of about 70 characters that works for 14 days. Hoard
  locks the set on your computer (AES-GCM, with a new random key) and sends only the locked copy to Hoard's share
  server, `hoard-share.furryup.link`; the key is only in the link, after its `#`, which a browser never sends
  anywhere, so the server can't read the set. **Update the link** puts the set as it is now behind the same link,
  for 14 days from then (the dialog says when the set has changed since), and **Delete the short link** deletes it
  from the server at once, as deleting the set does. The set viewer opens short links, and says when one has run
  out or been deleted; **Add a shared set...** takes them too. Nothing is uploaded unless you make a short link:
  the long link works as before. The share server is `share/` in the repository (a Cloudflare Worker, with its own
  tests); `PRIVACY.md` says what it keeps, and `TERMS.md` has a section on using it.

## 4.2.1

- **Fixed: a shared set could include your own Gumroad download pages.** A set links each product to its page on its
  store, and for Gumroad, Hoard used your purchase's own link: its download page (`gumroad.com/d/...`), which opens
  the files for whoever has it. For Jinxxy it was your inventory page. A set now links only a product's public page
  on its store, or its creator's page, never one of yours, and the set viewer on Hoard's website shows no other, so
  links shared from 4.2.0 don't show them either. A link already shared still holds what was in it, so if you shared
  a set with Gumroad products, delete those posts and share the set again. Gumroad products get their own page from
  your next Gumroad refresh (until then, their creator's page).
- **Fixed: Jinxxy products had no pictures in shared sets.** Their pictures are on Jinxxy's image host,
  `jinxxy-c.jinxxy-cdn.com`, which a set now takes, and the viewer shows.
- **Sets:**
  - The tiles are square.
  - Sets are chosen as products are, with **Select**, Ctrl or Shift. Right-click one for **Open**, **Share...**,
    **Download the N not downloaded**, **Choose a picture...**, **Rename** and **Delete**. With several chosen, you
    can download what's not downloaded, or delete them.
  - **Select** stays on the right in a set, **Note and photos** is open to begin with, and the share dialog's buttons
    wrap at large text sizes instead of running off its edge. The wording is plainer throughout.
- **The set viewer** shows a set's products as tiles, in as many columns as fit.

## 4.2.0

- **Sets, reworked: any products, downloaded or not, in a tab like a store's.** **Sets** is a tab beside the stores,
  in the Library and in Downloads (and in the bar at the top of every page). Each set is a big tile, with its own
  picture or four of its products'; open one and it's a folder of its products: the ones there as their usual tiles
  (to open, select and right-click as anywhere), then the rest, yours but not downloaded (**Download the N not
  downloaded** gets them all) or not yours yet (with **Buy on** its store). Make a set there, or choose products in
  the Library as well as in Downloads and use **Sets** in the selection bar or right-click (**Take out of** the set
  that's open, too): a set no longer needs its products downloaded. A set remembers what each product is (its name,
  creator, store page and picture), and has a **Note** and up to 8 **Photos**. Downloads' Sets list in the sidebar is
  now the tab.
- **Your own pictures for sets and Local items.** **Choose a picture...** on a set, or in a Local item's details,
  takes a picture from your computer for its tile (made at most 640 pixels across). A set's is kept in Hoard's
  app-data folder; a Local item's in Hoard's own folder for it, as its `_thumbnail`, so Hoard for Unity shows it too,
  and nothing in a folder of yours listed where it is is written. **Take the picture off** goes back to its own.
- **Share a set as a link.** **Share...** makes a link to the set viewer on Hoard's website, which shows the set's
  products with their pictures and a link to buy each, your note and your photos. The set is in the link itself,
  after its `#`, which a browser never sends anywhere: nothing is uploaded, and Hoard keeps no copy. Each picture
  loads from its store's own image host, and your photos from the photo site they're on (Imgur, Gyazo, X,
  Bluesky, Reddit, Postimages, ImgBB or Discord), so Hoard hosts nothing. Your own products (Local) and hidden ones
  are never in a link. **Add a shared set...** pastes one in: what you own already shows as yours, and the rest
  says where to buy it.
- **Fixed: Enter in the name box (New set, Rename set) cancelled instead of saving.** Enter now confirms (and
  waits while a Japanese or Korean input method is still putting a word together).

Fixes from an audit of everything since 4.0 (docs/audit-2026-10-14.md):

- **Fixed: Disk space's From more than one store could delete the copy you chose to keep.** A copy is removed by its
  product key, which leaves numbers and (labels) out, so Booth's "Hair Pack 1" and "Hair Pack 2" share one; and
  Downloads stacked them together, though the Library keeps them apart. With Gumroad's "Hair Pack 1" too, keeping
  Booth's removed and deleted all three. Downloads now stacks each download as its own product, and a copy is offered
  for removal only when nothing you keep, and no other product, shares its key. Where one store has two copies in a
  product, each says its name.
- **Fixed: a backup made while the hidden library was locked named the hidden products.** It left their hidden mark
  out, but listed them in the library list (name, creator, link), the archive and removed choices, tags and sets.
  They're left out of all of it now, and restoring a backup made while locked leaves the hidden products' tags, sets
  and choices here as they are.
- **Fixed: previous versions of a file in a subfolder** (a Gumroad product's "Textures/body.png", say) weren't listed,
  so they couldn't be restored, and stayed behind when the product was deleted or moved to another library folder.
  They're listed, restored, deleted and moved like the rest.
- **Fixed: support reports could still name your products.** A log's names were hidden only in a few kinds of line
  (a store's "creator / product" line, "saved:", the summary a sync ends with). Moving, restoring and deleting a
  product, an editable copy, the integrity check's paths, Local, a task's name and a path in another library folder
  went in as written, and products the library list doesn't have (Local's, for one) weren't known by name at all.
  Every name Hoard knows, products, creators and downloaded files, from the library list and every library folder, is
  now hidden wherever it is in a report, the same name always with the same placeholder. What's left in a path in a
  library folder (a product deleted since, say) is hidden too, and other library folders show as `<LIBRARY_1>`.
- **Fixed: Look inside had no limit on the previews it keeps.** A small, made-up package could fill the disk with them
  (a 1 MB one left a GB). A file's previews are kept up to 64 MB (past that, its other files show their kind), and
  the cache to 512 MB in all.

## 4.1.1

- **Fixed: menus and the tour could open off the screen** with a larger **Text size** (Settings, Accessibility).
  Text size enlarges the whole page, and the right-click menu, the selection bar's menus and the tour's card and ring
  were placed by the window's own measurements, which the larger page scales again: at 130% a menu opened near the
  window's edge, or the tour's card for Sync, landed partly or wholly past it. They're placed in the page's own scale
  now, at every text size, and the tour's card is sized to the window too.
- **Fixed: the selection tick covered the Library's downloaded mark** when pointing at a tile. The mark moves beside
  the tick whenever the tick shows, as it does when you choose something.
- **Fixed: right-clicking a tile near the end of the grid could open no menu.** Choosing the tile brings up the
  selection bar, which can move the page a little, and that closed the menu as it opened. Only scrolling you do
  closes it now.

## 4.1.0

- **Easier reading, from the start.** **Font: OpenDyslexic** (Settings, Accessibility), a typeface many people with
  dyslexia find easier to read, bundled so it works offline (Latin letters; Japanese and Korean keep their fonts),
  and **More space between letters, words and lines**. The page is served with them, so it never shows in the
  other font first.
- **Setup asks what makes Hoard easier to use**, right after the language: text size, font, light or dark, store
  colours for colour blindness, more spacing, reduce motion and pause animated pictures. Each shows as you choose
  it, and is saved at once.
- **A tour of Hoard, on your own library.** Hoard does a lot more than download, and a short tour now shows it, one
  thing at a time: a ring round the part of the page it's about, and a card beside it. It uses your own things (it
  asks you to search for a word from one of your items, open it, choose two, look inside its package, tag it), and
  each step that asks you to try something goes on by itself once you have. It goes from the Library on to
  Downloads: stores, search, details, choosing several, Archive and the rest, Sync, Look inside, What it needs, tags,
  sets, updates, Disk space, Local, Projects, Tasks and Settings. A step about something you don't have yet (nothing
  downloaded, say) is passed by. The Library offers it once, after setup or after updating, and **Settings** has
  **Take the tour** any time.
- **Choosing several items, reworked** (Library and Downloads):
  - **Without a mode:** tick a tile's box (it shows when you point at the tile), Ctrl-click (Cmd-click on a Mac), or
    Shift-click to take in everything from the last one. **Ctrl+A** chooses everything shown, **Esc** lets go, and a
    plain click still opens an item. **Select** stays, for touch screens: then every tap chooses.
  - **A compact bar:** the count, the main thing to do (**Download** in the Library), then menus: **Tags** (add or
    take off a tag), **Sets** (a new set of them, or add them to one), **Move** (to another library folder) and
    **More** (archive, hide, remove, delete their downloaded files), with **Select all shown** and **Done**. It stays
    on one line, where it used to run to two.
  - **Right-click** a tile (or press the menu key) for the same, in one menu. Right-clicking one you haven't chosen
    chooses just it.
- **Duplicates across stores** (Downloads, Disk space, **From more than one store**): products you have from several
  stores, each downloaded. Choose which store's copy to keep, for each or for all at once (**Keep the copy from**
  Booth, say, **In every one**), then **Remove** the others: they leave your library, so syncing never downloads them
  again unless you **Restore** them (Library, Removed), and their downloaded files are deleted.

## 4.0.4

- **Make a set from a project.** Each project in **Projects** has **Make a set**: a set of the products it uses (all of
  them or partly; not ones imported once and gone since), named for the project, so you can import them together in
  another project with Hoard for Unity's **Import set**.
- **Fixed: What it needs could show what it said before your downloads changed**, until Hoard was restarted: what
  it had worked out was kept by where the list of downloads was in memory, which a new list can be given.

## 4.0.3

- **What it needs no longer names other products.** Telling the product another one really needs (an outfit's base
  avatar) from files creators share and reuse across their products wasn't reliable enough, so for now it lists the
  shaders and tools a product uses, and says when it also uses files from other products, without naming them. Hoard
  for Unity's warning before importing lists the shaders and tools only, and **Import set** imports a set in name
  order.

## 4.0.2

- **What it needs names fewer products that aren't needs.** Products that only carry files many of your products
  share (a creator's free extras, each with the same files), or a few files of another product by the same creator
  (most often their own textures or materials used again), are counted with what Hoard doesn't know instead of being
  listed. Hoard for Unity's warning before importing follows.
- **The box for naming a set** (New set, Rename set) has Hoard's look rather than the browser's own grey box.

## 4.0.1

- **New set, in Select.** Making a set of the products you've selected was the last choice in the **Choose a set**
  list, easy to miss. **Select** now has a **New set** button of its own; **Add to set** shows once you have sets.
- **The set list in a product's details** looks like Hoard's other lists, at the height of **Add** beside it.
- **Fixed: a task's progress jumped back to the top with every new line**, in Tasks. It stays where you've scrolled
  to, and while you're at the end it follows the newest lines.
- **Hoard for Unity 0.8.1** leaves Poiyomi's `OptimizedShaders` folders out of how much of a product is in a
  project, and works that out again only when a change in the project can alter it.

## 4.0.0

- **Look inside a download.** In Downloads, each `.unitypackage` and `.zip` in a product's files has **Look inside**:
  every file a Unity package holds, in its folders, with its size and the preview picture Unity keeps for it, and
  **Search in it** to find one wherever it is. A `.zip` lists its files, and what each Unity package in it holds.
  Nothing is extracted or imported, and a second look is instant.
- **Hoard for Unity 0.8: packages that came in a .zip.** Many products, on Booth especially, come as a `.zip` with
  the `.unitypackage` inside. Hoard for Unity now lists each such package under its `.zip`, counts it towards
  **In this project**, and **Import** unpacks just that package (into the project's `Library` folder, checked as it's
  unpacked) and opens Unity's import dialog as usual.
- **What it needs.** A product's details in Downloads list what its packages use that isn't in them: shaders and
  tools (lilToon, Poiyomi Toon with the version its materials were made with, Modular Avatar, VRCFury, NDMF, Avatar
  Optimizer, the VRChat SDK) with **Get it**, other products you've downloaded, such as the base avatar an outfit is
  made for, with **View**, and a count of anything else. Hoard reads each package once, in the background while
  nothing else is running: the IDs its materials and prefabs name, less its own, are what it needs from elsewhere.
  It knows the tools' IDs from their own published releases. Hoard for Unity 0.8 says what's missing from the
  project, and asks before importing without it.
- **Backup and restore.** **Make a backup** (in Settings) saves what you've set up in one file, in Documents ›
  Hoard backups: your settings, tags, sets, archive choices and library list (without its download links), and
  your hidden items with their PIN while they're unlocked. Never your sign-ins, keys or downloads. **Restore a
  backup...** checks everything in it as Settings would, saves how things are now first so you can go back, and
  puts it in place: on a new computer, sign in to your stores and copy your downloads folder, and the rest is back.
- **Sets.** Group products you use together, such as an avatar, its outfits and hair, and the shaders they need: in
  Downloads, **Sets** in the sidebar (**New set**), **Add to set** for the products you've selected, or a product's
  details. Choose a set to see just its products. In Hoard for Unity 0.8, the **Sets** pill shows one, and **Import
  set** imports its packages one after another through Unity's import dialog, what's needed first (an outfit's
  avatar before the outfit), leaving out packages already all in the project and saying which tools it still needs.
- **Previous versions.** When an update replaces a file, the old one is kept in `_Previous versions` in the product's
  folder, and a product's details in Downloads list it with **Restore**, which puts it back (and keeps the one it
  replaces, so you can change your mind). Hoard keeps the last one of each file; choose none, or up to 5, in
  Settings (**Previous versions**). Deleting a product's downloaded files deletes them too, and moving it takes
  them along.
- **Easier to get around.**
  - A product's picture in its details is shorter, so its name and buttons show without scrolling; click it to
    see it full size.
  - In Downloads, a product's files come straight after what you can do with them.
  - Settings has a row of its parts at the top (Folders, Stores, Downloading, Look, Sign-ins, Updates, Backup,
    Troubleshooting), to jump to one.
  - A longer message stays up long enough to read.
- **Fixed: Japanese and Korean were missing from the portable download** (`Hoard-<version>.zip`, for macOS and Linux
  without the installer) since 3.3.0, so it was always in English. Every build is now checked for all of Hoard's files.

## 3.3.2

- **Notifications are in Hoard's language.** When the routine check finds something while Hoard runs in the
  background, the notification from your system is in Japanese or Korean too, not only English.
- **Fixed: in Japanese and Korean, a message Hoard has no translation for could come out half translated**, with
  words swapped for marks ("All 12 files / 3 downloads…"). It now stays whole, in English, until it's translated.
- **Fixed: products with no name to go by** (one that's only marks, such as "★★") **stacked into one tile** with
  every other such product by the same creator.
- **"1 file", not "1 files"**, when moving a product, rescanning or adding to Local.
- **The links to Hoard's website** (in the READMEs, the Hoard for Unity README and the site's own link previews) go
  to https://hoard.furryup.link/ directly; the old address forwarded without HTTPS.

## 3.3.1

- **Fixed: in Japanese and Korean, the Stores panel said how your sign-ins are kept in English** ("encrypted by
  your Windows account", or your Mac's Keychain, Linux keyring or folder), in the middle of the translated
  sentence. It's translated now.

## 3.3.0

- **Hoard in Japanese and Korean (日本語, 한국어).** Settings, Appearance has a new **Language** choice: **Match my
  computer** (the language your system or browser asks for, English if it's neither), **English**, **日本語** or
  **한국어**. Both pages, Settings, the panels and dialogs, and Hoard's own messages on the page are translated.
  Product names, creators, tags and files stay as they are. Korean uses Malgun Gothic, Apple SD Gothic Neo or Noto
  Sans KR when you have them, and breaks lines between words. The translations were made with AI help, and
  Hoard says so beside the Language setting and in setup: if something reads oddly, there's a new **Translation
  fix** issue form for telling us. The task log, Hoard for Unity and the website are still in English for now.
- **The setup assistant starts by asking your language**, with the question written in all three, so you can
  set Hoard up in yours from the first screen.
- **The README in Japanese and Korean** ([README.ja.md](README.ja.md), [README.ko.md](README.ko.md)), linked from
  the top of the English one.
- **Fixed: Updates, in Downloads, showed "undefined"** when nothing needed updating. It says **Nothing to update**.

## 3.2.0

- **Themes, and Light or Dark.** Settings has a new **Appearance** section: choose **Match my computer**, **Light**
  or **Dark**, and one of ten themes, each with a light and a dark version: **Hoard** (as before), **Dragonfire**,
  **Frost Cave**, **Geode**, **Mossy Ruins**, **Synthwave**, **Sakura**, **Midnight & Paper** (true black for OLED
  screens, and white), **High contrast** and **Spooky Hoard**. The pages open in your theme from the first moment.
  Every theme keeps text easy to read, at the same contrast as Hoard's own colours. Where a theme's accent is close
  to a store's colour, that store's colour shifts a little so the two can't be mistaken for each other.
- **Text on gold buttons is darker in the light theme**, so **Sync**, **Download** and the like are easier to read.
  Warnings in the light theme are a little darker too.

## 3.1.1

- **The logo glows while an update to Hoard is waiting**, and gives a little shake now and then. Choose it to open
  Updates in Settings. With reduced motion (Settings, or your system's), it only glows.
- **There are a few things to find in Hoard.**
- **Fixed: a stacked tile with a tall picture grew to the picture's height** instead of staying square.

## 3.1.0

- **Disk space, in Downloads.** A new view lists your downloads biggest first, with how much they take, and two
  ways to narrow it down:
  - **Same file kept twice**: files you have more than once, in two products (a bundle and the product also sold
    on its own, the same package bought from two stores) or in two library folders, with how much you'd free.
    Open one to see where else its files are. It's worked out from the fingerprints Hoard's download check
    already keeps, so it reads nothing; files the check hasn't seen yet are counted, with **Check now**.
  - **Not in any Unity project**: downloads none of your projects use (as Hoard for Unity reports them).
  Choose **Select** to move several to another library folder, archive them, or delete their downloaded files.
- **Select in Downloads can archive, and delete downloaded files, for several at once**, in any view.
- **A notification when the routine check finds something.** With Hoard open in the background, your system
  tells you how many new products and updates the routine check found (never their names), once: the same again
  isn't news. Turn it off in Settings, under **Routine check**. On Linux it needs `notify-send` or `gdbus`; the
  Flatpak asks to talk to the notification service for it.
- **Copies on two stores stack.** A product you have on two stores is one tile now, in the Library and in
  Downloads (which stacks copies too, with **Stack copies** beside Sort): by the same name and creator, or, when a
  creator's shops have different names, by the same name and a picture that looks the same, though each store
  saved it its own way. The page works out how pictures look once, and Hoard keeps it (`picture-looks.json`).
  Pictures several creators use stack names that are nearly the same, too. Names still need the same numbers and
  (variants), so "Hair Pack 1" and "Hair Pack (Pink)" stay apart.
- **The setup assistant asks what closing Hoard's window does**: keep Hoard running, minimized to the taskbar
  (the Dock on a Mac), or quit it. It's the same choice as **Closing Hoard** in Settings.
- **Hoard for Unity 0.6.0**: right-click files in the Project window and choose **Hoard › Which Product Is This
  From?**, and products in your project with a newer download are marked, to import the update. See its
  changelog.

## 3.0.3

- **Fixed: in Hoard's window, Settings' Add a folder... filled the whole row**, pushing the box for a folder's path
  and its **Add** button out of the panel (a sliver of them showed at the edge). It's as wide as its label now, with
  the box and **Add** beside it. **Install update**, in Settings' Updates, had the same problem when an update was
  waiting.

## 3.0.2

- **Downloads only shows the store tabs you have something in.** A store with nothing downloaded in the view
  you're in has no tab, as in the Library; Local's tab still shows when you open Local with nothing in it yet.
- **The store tabs in Downloads show how many things are in each**, as the Library's tabs do.
- **Downloads can unlock your hidden items.** Choosing **Hidden** in Downloads asks for your PIN there, as the
  Library does, instead of sending you to the Library first; **Lock now** locks them again from Downloads too.
  Setting, changing and resetting the PIN stay in the Library.
- **Sync is the last button in the header on both pages.** In Downloads, **Download new** sat after the gold
  **Sync**; it's now before it, so Sync is in the same place on every page.
- **Projects' Credits dropdown looks like the others**: the same arrow, height and text size as Sort and the
  dropdowns in Settings, instead of the system's own.
- **Settings and Add to Local start with the same size of text as Stores and Tags.**

## 3.0.1

- **Fixed: the store tabs' counts went to 0 after a while.** The tabs (Everything, Booth, Gumroad...) count what's
  in the view you're in: the Library, Archive, Removed or Hidden. They were only redrawn when your library was read
  again, so if that happened while you were looking at another view (when a routine check or a task finished,
  say), they kept counting that view: every tab read 0 back in the Library, while the heading still said how many
  things you have. They now follow the view you're in.

## 3.0.0

Hoard 3.0 is the biggest update since Hoard began. It's an app on **Windows, macOS and Linux** now, with a new look
built around your stores' colours. Signing in works with Google, Discord or X. Downloads queue up, retry
themselves, show their speed and time left, and can't hang; you choose what downloads, down to each file, and any
task can be force stopped. One routine check keeps your library up to date and asks before downloading anything.
And Hoard can keep working in the background while its window is closed.

Coming from 2.8.4, everything carries over by itself: your library, tags, sign-ins, settings and downloads. See
**Upgrading from 2.8** at the end.

### Hoard on every computer

- **Hoard for macOS.** `Hoard-3.0.0-macos-apple-silicon.pkg` (M-series Macs) and `Hoard-3.0.0-macos-intel.pkg`
  install **Hoard** in Applications, opening in its own window like the Windows app. macOS 11 or newer. They
  aren't signed by Apple yet, so macOS won't open them at first: choose **Done**, then **System Settings ›
  Privacy & Security › Open Anyway**.
- **Hoard for Linux, as a Flatpak.** `Hoard-3.0.0-linux-x86_64.flatpak` installs from your software centre or with
  `flatpak install --user`, on the GNOME runtime from Flathub. Its sandbox allows the network, its window, your
  keyring (for sign-ins) and your home folder and drives (for your downloads), and nothing else. It uses the same
  `~/.local/share/Hoard` as Hoard run from source, so your library carries over and Hoard for Unity finds it.
- **Updates say which file to get.** On the Mac and in the Flatpak, **Settings › Updates** names the new version's
  package for your computer. The Windows app still updates itself.
- **Betas, for testers.** Betas of the next version now come out here, as pre-releases ("Hoard 3.1.0 beta 1").
  Turn on **Get beta updates** in **Settings › Updates** to be offered each one, and the finished version when
  it's out. Everyone else only ever sees releases.
- **Hoard always installs into `%LOCALAPPDATA%\Programs\Hoard` on Windows** (issue #21): a folder only your account
  can change, which Hoard's sign-in protection counts on. A Hoard installed somewhere else by an older setup moves
  there when it updates; you can delete the old folder afterwards.

### Signing in, your way

- **Sign in with Google, Discord or X** (issue #21). Those sign-in services refuse a browser that a program is
  driving, which Hoard's sign-in window was. Now signing in opens your chosen browser as itself (Edge, Chrome or
  Hoard's own) on that store's own sign-in folder, so you sign in however you normally do: a password, a passkey,
  or Google, Discord or X. Close the window when you're done (on a Mac, quit the browser with Command-Q), and
  Hoard reads the store as before. Your sign-in is saved and protected exactly as it was. A link from a sign-in
  email still opens in that window when you paste it into Hoard. If you need the old window,
  `"automated_sign_in": true` in `config.json` brings it back.
- **Signing in installs Hoard's browser if it needs to,** showing its progress, then opens the sign-in window.
  Signing in to Payhip before you've added your shops says it's done, and to add them (a shop's address is in your
  purchase email) or import their saved pages.
- **Save a whole Payhip shop in one go.** Importing Payhip meant saving every page of every shop's library by
  hand. The **Save for Hoard** bookmark (in Stores, under Import saved pages: drag it to your browser's bookmarks
  bar) reads every page of a shop's library in your usual browser, as you, and saves them as one file to import.
  It reads only that shop's own library pages, and sends nothing anywhere. Run it on each shop, then import the
  files together.
- **Sign-ins on a Mac work in the background too.** Store reads now use the same full Chromium as the sign-in
  window, so they can read sign-ins that the Keychain protects.
- **Setup is sturdier.** On Windows, a browser holding its sign-ins open no longer makes the setup assistant's
  status fail, and the Library takes over the store counts if you close the assistant while signing in.
  Settings, sign-in messages, logs and support reports all say which browser Hoard is really using, including when
  it falls back to its own.
- **The first setup goes through to the end** (issue #21). The first time Hoard opens, the setup assistant can't be
  skipped or closed half-way: a step that isn't done yet keeps you on it (Hoard's browser not installed, say, or
  no store picked), and going on without signing in to any store, or without a Payhip shop, asks first. Run again
  from Settings, it can still be left at any step.

### A new look

- **Folder tabs and the glow.** The store tabs are folder tabs: the one you're looking at is raised, and the page
  glows up from the bottom in its store's colour. On **Everything**, the colours of the stores you use drift
  slowly through the glow (and stay still when you ask your system for less motion).
- **One panel for Tags, Stores, Settings and Tasks** (issue #84). Each opens in a panel over the middle of the
  page, one at a time: choosing another swaps it in, and the buttons along the top stay in reach. **×**, Escape or
  a click on the page around it closes it.
- **Browse for folders.** Choosing the downloads folder (in setup and Settings) and adding your own packages have a
  **Browse** button that opens your system's own folder or file picker, instead of typing a full path.
- **Stores offers Sign in or Sign out, whichever applies,** instead of both for every store, and the panels use more
  of the window's width.
- **Panels work from the keyboard.** A panel takes the keyboard when it opens, Tab goes round inside it instead of
  wandering through the dimmed page, and closing it hands the keyboard back to the button you opened it with.
- **Questions in Hoard's own dialog.** "Delete its downloaded files too?" and the like ask in a dialog that matches
  the rest of Hoard, with buttons that say what they do, instead of the browser's plain pop-up.
- **Store tabs stay in sight.** In a smaller window, or at a larger text size, Sort and the tile size go up a row
  of their own instead of covering the later store tabs. In a very narrow window the tabs scroll, and fade at the
  edge where there are more.
- **Local is a place of its own** in the top bar: choosing it highlights Local, not Downloads.
- **Easier to read in the light theme:** gold links and buttons are a darker gold, at least 4.5:1 against the
  background.
- **The download panel sits beside an asset's details** (issue #85) instead of over them, so you can keep using
  them while it shows. In a narrow window the details end above it.
- **Settings save as you change them.** There's no **Save** button any more: a box or a list is saved straight
  away, and a folder or the Payhip shops when you leave the field. While a job runs, only the settings it depends
  on (where files go, the browser, the stores and the Payhip shops) wait for it to finish.
- **A sidebar that folds.** **Hide filters** folds it to a thin strip, and each section (your tags, suggestions,
  Show, creators) folds by its heading. Hoard remembers both.
- **Tasks**, next to Library and Downloads, shows what's running with its progress, what's waiting, and what
  finished: how it went, how long it took, any problems, and its full progress. It keeps the last 60, between
  runs too.
- **A splash while your library opens,** with the Hoard logo and "Opening your hoard", so the page never shows
  half-loaded. It doesn't animate when you ask for less motion.
- **The window remembers its size and place,** and whether it was maximised. A window that would open off-screen
  comes back to the middle.
- **Large text fits.** With **Largest** text, panels sized to the window no longer run off its edge: Settings,
  Stores, the sidebar, details, the selection bar, dialogs, the setup card and the download panel.
- Sort, tile size and what's running sit up beside the tabs, out of the way.
- **Buttons line up.** Every button is one of two heights, gold and plain alike, with its text centred; the bar's
  buttons stay on one row with the search box down to narrower windows; tickboxes are gold everywhere.
- **What's new, in Hoard.** **Settings › Updates › What's new in Hoard** shows every change, version by version,
  with the version you're running marked; betas too when you tick **Include beta updates**.

### Accessibility

- **Store colours you can tell apart** (issue #112). Settings, under **Accessibility**, has **Store colours**:
  **Standard**, **Easier to tell apart (colour blindness)**, a set chosen to stay distinct with the common kinds of
  colour blindness and clear on light and dark backgrounds, or **My own**, a colour you pick for each store.
- **The glow can be turned off** (issue #112): untick **Coloured glow behind the page** for a plain background.

### Your library

- **See what you've downloaded.** Downloaded products have a small download mark on their pictures (with a label
  for screen readers), and **Downloaded** under **Show** filters to **Downloaded** or **Not downloaded yet**, with
  live counts.
- **New, and Recently added** (issue #18). Anything that appears in your library after a refresh has a **New**
  badge for a week (change it in Settings, under **New in your library**: a day to a month, or never), and **New**
  under **Show** filters to them. **Recently added** sorts the newest first. What was already there when Hoard
  first read a store isn't counted as new.
- **Check for updates to what you've downloaded.** In Downloads, **Check for updates** (under **Updates**) reads
  your stores without downloading anything and lists every download whose store has newer files: files the
  creator added or changed since you downloaded it. **Update all**, or **Update** one from its details, which can
  also check just that one. In the Library, such products say **Update available**.
- **Downloads has Archive, Removed and Hidden views,** with the sidebar's counts following the view you're in.
- **Payhip products are credited to the right creator** (issue #25). If you sell on Payhip too, your own shop's
  library page lists everything you've bought anywhere on Payhip, without saying who made each one, and Hoard
  credited them all to you. Now they show as **Unknown creator**, and a product a shop's page lists from a
  different shop is credited to the shop it's from. Products from shops at `payhip.com/<name>` keep their creator and link even when your own
  shop is at payhip.com too (issue #97).
- While your hidden library is locked, hidden products' names stay out of job progress and the Tasks list, and
  locking it closes any hidden product's details you had open.
- **Remove a download completely** (issue #81). Removing something you've downloaded asks whether to delete its
  downloaded files too, so it no longer lingers in Downloads. **Delete downloaded files** is in every download's
  details, in the Library and in Downloads, and for a selection: a product still in your library stays there, to
  download again. Only the files Hoard downloaded go; anything of your own in the folder stays.
- **Local: your own packages** (issue #80). Packages you make, to move textures and materials between projects or
  to hand to commissioners, live beside what you bought: **Add your own** takes a folder or file on this computer,
  with who it's for. You choose each time whether Hoard copies it in (checked like a download) or lists it where
  it is (never written to; **Rescan** picks up changes). Tagged, searched and imported into Unity like the rest.
- **Add a folder of folders to Local** (issue #109). In **Add your own**, **Folders inside it** makes each folder
  one, two or three levels down a package of its own, named for its folder; from two levels down, the folder above
  is who made it. Hoard lists what it would add first, and adding the same folder again only adds what's new.
- **Clearer buttons in an item's details** (issue #108). There's one thing to do, in gold: **Download** when you
  don't have a copy yet, **Show in Downloads** when you do (with **See the update** when there's one), or **Open on
  Payhip** for Payhip's. The store's own pages are named for the store (**Open on Gumroad**, **Store page**), and
  **Archive**, **Hide** and **Remove** sit under **Organise**.
- **Copies stack** (issue #111). Copies of the same product on one store (bought more than once, or in several
  versions) show as one tile marked ×3, say. Hoard knows them by their picture: the same image, byte for byte, not
  the same name, so "Hair Pack 1" and "Hair Pack 2" stay apart. A picture several creators share (a store's default
  banner) stacks nothing. Choose a stack to see every copy. Untick **Stack copies**, beside **Sort**, to show each
  on its own.
- **Projects** (issue #86). Every Unity project you open Hoard's window in (Hoard for Unity 0.4.0) shows up under
  **Projects**: each product it uses, all of it or part, which have updates waiting, and its credits list (the
  same one the Unity window makes, with your changes there), ready to copy in any style. Downloads says which
  projects use each product.

### Downloads you can leave running

- **Choose what downloads** (issue #107). **Download new**, **Download everything new**, a store's **Download** and
  **Update all** first list what they'd get: what's in your library with nothing on disk yet, and the updates the
  last check found. Untick anything you don't want this time. Where Hoard knows a product's files before
  downloading (an update's new and changed files, and a Booth product's files), **Choose files** lets you untick
  them one by one. Only the stores switched on in Settings are included.
- **Always skip** (issue #107) leaves a product out of every download and sync, automatic ones included, until you
  choose **Stop skipping**. Choosing it by name still downloads it.
- **Download several at once** (issue #106): select products in the Library and choose **Download**. They download
  as one job, across stores.
- **Jobs wait their turn** (issue #49). Start a sync, download, refresh or sign-in while something is running, and
  it joins the queue instead of being refused with "Hoard is busy". So does taking something out of Local,
  rescanning it, or deleting a removed product's downloaded files. Take one off the queue in Tasks.
- **Failed downloads are tried again** (issue #19): twice, after a short wait, before they count as failed (change
  it in Settings, under **Failed downloads**). A store saying a file isn't there, or isn't yours, isn't retried.
- **Progress, speed and time left.** While a file downloads, the download panel and Tasks show a progress bar, how
  much has come in of how much, how fast it's coming, and how long is left. (Files that come through the browser,
  from Jinxxy and sometimes Booth, show how much and how fast; the browser doesn't say how big they are.)
- **Nothing can hang a sync any more:**
  - A download that stops coming in, without the store hanging up, is given up on after 2 minutes and tried
    again, whichever way it comes.
  - When a store's browser closes by itself part way through (Jinxxy, or Booth through the browser), Hoard opens
    it again and carries on. Before, every product after it failed at once: 258 in one sync. If it keeps closing,
    the rest of that store waits for next time, with one message saying so.
  - A browser that stops answering is ended 20 seconds after you choose **Stop**, so the job finishes. A job with
    no progress for 5 minutes says so, and the log notes where it was waiting.
- **Stop is quick and sure:** it works part way through a file, within a few seconds, and always reaches the
  download it's meant to end.
- **Force stop, for any task.** The running task in **Tasks** has **Force stop** beside it, whatever it is: a
  refresh, a sign-in, installing the browser, as well as downloads and syncs. It closes the store's browser (or the
  sign-in window, or the browser download) at once, so the task ends straight away. What finished is kept, and a
  file part way through resumes next time where it can. It asks first.
- **Your tasks go first** (issue #110). Start something while an automatic one runs and it stops safely to make way
  (Tasks says so), then carries on after yours.
- **Jinxxy files download straight from Jinxxy,** with your sign-in, the way Booth's do, so a download that's
  interrupted picks up where it stopped and progress shows its size and speed. If Jinxxy turns that away, Hoard
  downloads through the browser instead.
- **A resumed download is never joined onto a different file:** if the creator uploaded a new file under the same
  name since, it starts again from the beginning.
- **One product goes straight to its download.** **Download a copy** (Library) and **Update** (Downloads) open just
  that product's page on Jinxxy, and just that purchase's download page on Gumroad, instead of reading through
  the whole store to find it.
- **Booth's free items download.** Booth lists them without their files, so Hoard now opens each one's page and
  downloads from its buttons.
- **Gumroad products that are only pictures download.** Some download pages have no files, just pictures in the
  page (a set of PNG textures, say). Hoard saves those into a **Page images** folder, in page order.
- **Jinxxy downloads into OneDrive work:** OneDrive's cloud files are no longer mistaken for shortcuts.
- **A download you delete completely leaves Downloads** on the next rescan and can be downloaded again. One with
  only some files missing stays, marked.
- Removing a browser store's sign-in folder while Hoard is closed clears that store's list from the Library at the
  next start, without touching your downloads or imported pages.
- **Make an editable copy** (issue #82). Want to change a texture? Open a download and make an editable copy: its
  files go to a folder of their own (**Hoard Edits**, beside your downloads), which Hoard never checks or replaces,
  so a sync can't undo your edits. Only files that still match what Hoard downloaded are copied, and a read-me in
  the copy says what it is.
- **Library folders on other drives.** When your downloads drive fills up, add a folder on another drive (an
  external disk, say) in Settings, under **Library folders**: **Add a folder…** picks it and adds it. Hoard reads
  it as part of your library, and Downloads gives each folder a tab of its own, with how many downloads it holds.
  Downloads, Hoard for Unity, the routine checks and syncing all cover it. New downloads still go to your downloads
  folder, and a product already in another folder is updated where it is. To move a product, open its details and
  choose **Move here** (or select several and move them together): Hoard copies its files, checks every one, and only then deletes them where they were. When
  a folder's drive isn't connected, its products are left alone, not downloaded again; removing a folder in
  Settings only stops Hoard reading it.
- **One routine check, which asks before downloading** (issues #83 and #113). Every 6 or 12 hours, once a day, a
  week or a month (or off, until you choose), while Hoard is open it reads your stores (not Payhip), checks your
  downloads are there and unchanged (by size and SHA-256 fingerprint, reading only files that changed since the last
  check), and checks for updates. When it finds something new, it asks: **Choose what to download** shows the list
  **Download new** does, or **Not now**. It never downloads by itself. If you'd turned on **Sync automatically**,
  it keeps that timing. Downloads shows when your downloads were last checked and what was found, with **Check
  now**; Tasks names any changed or missing files.

### Working in the background, and closing safely

- **Closing the window minimizes Hoard to the taskbar** (the Dock on a Mac), and downloads, syncs and automatic
  syncs carry on; click it there to bring the window back. **Quit Hoard** in Settings stops it. It's on unless you
  turn it off in Settings, and then the close button quits.
- **Quitting while Hoard is working asks first:** **Stop it, then close** (Hoard closes once what's running has
  stopped), **Minimize, and keep working**, or **Close now**, which ends everything at once. Before, closing
  gave a download 5 seconds to stop.

### Logs and support reports

- **A log for each time Hoard starts,** kept for 30 days (and the newest 10 however old), instead of one log that
  grew for ever. **Open logs folder**, in Settings under Troubleshooting, shows them, and a support report
  includes this run's log and the one before.
- **Support reports give away even less.** Product and creator names in the summary at the end of a sync are now
  hidden like the rest; Windows paths written with doubled separators and downloaded file names in progress lines
  are replaced too, with the same placeholder everywhere in the report. A name with "secret" or "token" in it is
  no longer mangled as if it were a password. `PRIVACY.md` says where reports really go: `Hoard\Support Reports`
  in your Documents folder.

### Security

- **The September 2026 code-scanning findings are fixed.** None is known to have been exploitable (Hoard's server
  already needed each run's own access key, and imported pages were already opened with scripts off), but every
  guard is now one the scanner can follow, with a test for each:
  - Imported store pages are cleaned with an HTML parser instead of patterns, so no way of writing a script tag or
    an event handler slips through, and a `<style>` inside an SVG can't carry markup.
  - The pages' Content-Security-Policy hashes are found the same way.
  - Pictures from your downloads folder are served only from checked paths inside it, as a fixed list of types;
    fonts only from Hoard's own.
  - No response header can carry a line break.
  - Jinxxy links are recognised by their address's host, over https, not by "jinxxy.com" appearing anywhere in
    it.
  - Support reports hide names without patterns that could take very long on an unusual line.
- **Safer releases.** Every file on a release is built on GitHub from this project's code, with signed build
  provenance and a checksum file, and is scanned by VirusTotal before the release is published. The release notes
  link each file's report.
- **Signed for Windows.** `Hoard.exe`, `hoard-cli.exe` and the installer are code-signed, so Windows and Defender
  know they're Hoard's. See `CODE_SIGNING.md`.

### Fixed

- **Store pictures didn't load in the Mac app** (2.10, issue #93): every tile showed its initials. The app's Python looked
  for the system's trusted certificates where they were on the computer that built it, so every picture's secure
  connection failed, without a word. Hoard now always trusts the same certificate bundle its downloads use, still
  checking every certificate, and notes in its log, once, why a picture couldn't be fetched. The build's own check
  of each app now makes sure it has certificates to trust, and on a Mac that its window's parts are there.
- **The Library no longer asks your keyring on every load.** Whether there's an itch.io key, and how sign-ins are
  protected, were looked up each time the page loaded: on Linux that started gdbus and secret-tool every time,
  on a Mac the Keychain's security tool, and a locked keyring could ask to be unlocked again and again. Hoard now
  remembers the answers, and updates them when you add or remove the key.
- **Command-Q quits Hoard on a Mac** (and Quit in its menu or the Dock), asking first only while something is
  running. It went through the same step as the window's close button, so with the window going to the Dock on
  close, Hoard couldn't be quit that way.
- Downloads' tiles no longer crowd the heading above them, which they cut into when no filter was chosen.
- **A sync that read none of your stores said Done,** in green. It now fails and says which stores it couldn't read
  (each store's row in Stores says why), and doesn't try to download. A sync that read only some is **Partly done**,
  and so is a download where some files failed.
- The download panel could cover the last tiles. The page now has room to scroll them clear of it, and after a job
  that went well it closes by itself a few seconds later (Tasks keeps the result).
- The top bar could stay two rows tall after the window was made wider again, and differed between Library and
  Downloads. It now fits its contents, and is laid out the same on both pages.
- The setup assistant ticked every store, so someone who'd never used Payhip was asked for Payhip shops. The first
  time, only the stores you already have items from are ticked.
- A library with many products of the same name (on different stores or by different creators) was slow to open:
  finding each product's copies on other stores took time that grew with the square of how many shared the name.
  It's now worked out once per store.
- Your own folders listed where they are now have a picture: a copy of one of their images, kept in Hoard's
  `Local` folder (made again on **Rescan**).
- Sign-ins kept on another drive (`advanced_signin_location`) that wasn't plugged in when Hoard started made every
  store's list vanish, as if you'd signed out. Hoard now leaves the lists alone when that whole folder is missing.
- "Hoard is busy" just after starting: checking the catalog's seal no longer holds up the first thing you choose.
- The store tabs no longer make the page bounce as the pointer moves along them.
- The pages' scripts run in strict mode again.
- A PIN test could fail when its digits happened to appear inside a random hash.
- **One itch.io project's revoked download key** no longer counts as your API key being refused, which stopped every
  itch.io download and asked you to sign in again.
- **Booth:** one dropped connection no longer sends every later file through the browser (the file resumes
  instead), and a new file in a product you have counts as new, not updated.
- **Jinxxy:** pictures several products share are kept instead of being deleted (and downloaded again) every sync,
  and a file whose button moves on the page is still the file downloaded.
- A product both hidden and removed stays hidden while the hidden library is locked; reading your Jinxxy inventory
  only follows Jinxxy's own pages.
- Adding a folder with your downloads folder inside it (your whole Documents folder, say) to Local is refused, and
  one file name your system can't take no longer stops a copy part way.
- A Gumroad product downloaded from the Library gets its picture; removing one product no longer deletes a picture
  another uses.
- Requests Hoard can't make sense of get a clear error instead of a dropped connection, and the pages run faster:
  your hidden, archived and removed choices are read once until they change.

### Hoard for Unity 0.3.0 to 0.5.2

Released alongside, through VCC (Hoard's listing:
https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json):

- **Create Credits List** (issues #51 and #79). The **Create Credits List** button lists the creators of the
  Hoard assets fully in your project, ready to paste where you share your avatar or world: as a list with store
  links, as Markdown, or grouped by creator. Untick any you don't want credited and add others by hand; **Copy** or **Save as...**. Your changes travel with
  the project.
- **Animated pictures play** in the list and the details. Unity can't read GIFs, so the window decodes them itself.
- **A picture for more products:** when a product's saved picture is a kind Unity can't show (WebP or AVIF), the
  window uses one of the product's own images instead.
- **Your own packages** from Hoard's Local are listed and imported, with who they're for (0.4.0).
- **Projects in Hoard** (issue #86): the window tells Hoard what each project uses (0.4.0).
- **Library folders on other drives**: products kept in another of Hoard's library folders are listed and
  imported like any other (0.5.0).
- **Only what's in Assets counts as in your project** (issue #114, 0.5.1): a package's own copy of something VCC
  installs under `Packages/` (Poiyomi, VRCFury, the VRChat SDK) no longer makes a product look imported, and only
  files count, not the folders a creator's products share (0.5.2).
- **Nothing is cut off in a narrow window** (0.5.1): long names end in "…", and the toolbar's buttons move to a
  second row instead of off its edge.
- **Importing a package with scripts is remembered** (0.5.2), a damaged `imports.json` is kept aside rather than
  written over, a library folder that's a whole drive works, and "Checking packages" no longer gets stuck.

### A website, and thanks

- **Hoard has a website:** https://soloflighter1010.github.io/Hoard-Asset-Manager/ with downloads for your
  computer, Hoard for Unity, and a **What's new** page that follows this changelog. VCC's listing address hasn't
  changed.
- **Thank you to the testers** who tried every beta of 3.0 on their own libraries and told us what broke:
  puzzlella, dx_nacca, kyrmeso, xionite02, vixendavali, djfin, loafevr, doctorlucymoth, surfur, hallowokin,
  cheapthrill, petra.synth and xkittygoddessx.

### Upgrading from 2.8

- **On Windows,** update from **Settings › Updates** as usual, or install `Hoard-Setup-3.0.0.exe` over your copy.
  If your Hoard was installed somewhere other than `%LOCALAPPDATA%\Programs\Hoard`, the update installs it there;
  you can delete the old folder afterwards. Your settings, library, sign-ins and downloads stay where they are.
- **Settings has no Save button:** changes save as you make them.
- **Logs:** each start of Hoard has its own log now. Use **Open logs folder** in Settings to find them.
- **Payhip sellers:** after your next refresh, products bought from other creators show as **Unknown creator**
  instead of your own shop's name.
- **Signing in with Google, Discord or X:** sign in to that store again, choosing it on the store's own sign-in
  page.

## 2.11.1

- **Fixed: Payhip products bought from other creators were credited to you** (issue #25). If you sell on Payhip
  too, your own shop's library page lists everything you've bought on Payhip, from every shop, and doesn't say
  who made each one. Hoard credited them all to the shop whose page it was: yours. Now they show as Unknown
  creator. And a product another shop's library page lists from a different shop is now credited to the shop it's
  from (its link says which), not to the shop whose page it was.
- **The release's VirusTotal check no longer looks stuck.** It waited for each file's scan in turn, without a word,
  which with several new files could run for most of an hour. Now it sends every file first, waits for all the
  scans together, and says how they're getting on. It gives up after 40 minutes, naming the files still being
  scanned, and running it again picks up where VirusTotal got to.

## 2.11.0

Sign in with Google, Discord or X.

- **Sign in with Google, Discord or X works** (issue #21). Google and the others refuse to sign in from a browser
  a program is driving, which Hoard's sign-in window was. Now signing in opens your chosen browser as itself (Edge,
  Chrome or Hoard's own), on that store's own sign-in folder, so you can sign in however you normally do. Close the
  window when you're done (on a Mac, quit the browser with Command-Q) and Hoard reads the store, as before. Your
  sign-in is saved and protected exactly as it was. A link from a sign-in email still opens in that window when
  you paste it into Hoard. `"automated_sign_in": true` in `config.json` brings back the old window if you need it.
- **Fixed: Stop could miss the download it was meant to end.** Stop was acted on by whichever part of Hoard wrote
  to the log next, which wasn't always the download. Only the download itself acts on it now.
- **Every release is scanned by VirusTotal before it's published.** The release notes link each file's report.

## 2.10.0

Hoard is now an app on macOS and Linux too: a package for the Mac, and a Flatpak for Linux, each opening in Hoard's
own window, like the Windows app.

- **Hoard for macOS.** `Hoard-2.10.0-macos-apple-silicon.pkg` (M-series Macs) and
  `Hoard-2.10.0-macos-intel.pkg` install **Hoard** in Applications. macOS 11 or newer. They aren't signed by
  Apple yet, so macOS won't open them at first: choose **Done**, then **System Settings › Privacy & Security ›
  Open Anyway**.
- **Hoard for Linux, as a Flatpak.** `Hoard-2.10.0-linux-x86_64.flatpak` installs from your software centre or
  with `flatpak install --user`, on the GNOME runtime from Flathub. Its sandbox allows the network, its window,
  your keyring (for sign-ins), and your home folder and drives (for your downloads folder), and nothing else. It
  uses the same `~/.local/share/Hoard` as Hoard run from source, so your library carries over and Hoard for
  Unity finds it. The manifest follows Flathub's rules, ready to submit there.
- **Updates say which file to get.** On the Mac and in the Flatpak, **Settings › Updates** names the new
  version's package for your computer (the Windows app still updates itself).
- Every file on a release has signed build provenance and a checksum file, and every pull request builds the
  Mac app and the Flatpak, with their self-tests, as a release would.

## 2.9.2

The downloader fix: a store browser that closes or stops answering no longer fails, or holds up, a whole sync.
Downloading one product goes straight to it. And Hoard can carry on in the background, and close safely while
it's working.

- **Fixed: a Jinxxy sync failed every product after the browser closed.** When Hoard's browser for a store
  closed by itself part way through (Jinxxy, or Booth through the browser), every product after it failed at once
  ("Target page, context or browser has been closed"): 258 of them in one sync. Now Hoard opens the browser again
  and tries that product once more, then carries on; if it keeps closing, the rest of that store is left for next
  time with one message saying so.
- **Fixed: a sync could stop moving, and Stop couldn't end it.** Some of what Hoard asks a store's browser has no
  time limit, so a browser that stopped answering held the job, and every job after it, until Hoard was closed.
  Now Stop ends such a browser after 20 seconds, so the job finishes; and a job with no progress for 5 minutes
  says so. Either way, Hoard's log notes where it was waiting, so the cause can be found.
- **Downloading one product goes straight to it.** **Download a copy** (Library) and **Update** (Downloads) used
  to read through the whole store to find the product: on Jinxxy, opening every item's page, one after another,
  until the name matched. Now they open just that item's page on Jinxxy, and just that purchase's download page on
  Gumroad. (Booth's files are only on its library pages, and itch.io is read through its API, as before.)
- **Keep Hoard running in the background.** A new setting, **Keep Hoard running when its window is closed**:
  closing the window hides it, and downloads, syncs and automatic syncs carry on. Open Hoard again to bring the
  window back; **Quit Hoard** in Settings stops it.
- **Fixed: Booth's free items weren't downloaded.** Booth lists your free downloads without their files ("no
  files listed in your library"); Hoard now opens each such item's page and downloads from its buttons there.
- **Fixed: a Gumroad product that is only pictures downloaded nothing.** Some download pages list no files: the
  product is pictures in the page itself (a set of PNG textures, say). Hoard now saves those into a **Page
  images** folder, in page order, each typed by what it is. Pictures beside real files (previews, instructions)
  still aren't downloaded.
- **A log for each time Hoard starts,** kept for 30 days (the newest 10 however old), instead of one log that
  every run added to. **Open logs folder** in Settings (Troubleshooting) opens where they are, and a support
  report includes this run's log and the one before.
- **Closing Hoard while it's working asks first:** **Stop it, then close** (Hoard closes once what's running has
  stopped), **Keep working in the background**, or **Close now**, which closes at once, ending any store browser,
  for when stopping takes too long. **Quit Hoard** in Settings asks the same. Before, closing gave a download 5
  seconds to stop.
- **The first setup goes through to the end (#21).** The first time Hoard opens, the setup assistant can't be
  skipped or closed; a step that isn't done yet (Hoard's browser not installed, no store picked) keeps you on it,
  and going on without signing in to any store, or without a Payhip shop, asks first. Run again from Settings, it
  can still be left at any step.
- **Hoard always installs into `%LOCALAPPDATA%\Programs\Hoard` (#21),** a folder only your account can change,
  which Hoard's sign-in protection counts on. The installer no longer offers another folder, and a Hoard installed
  elsewhere by an older setup is installed there when it updates (the old folder can then be deleted).

## 2.9.1

- **Fixed: the page bounced when the pointer went along the store tabs.** A tab rising under the pointer made the
  whole row of tabs taller, so everything below it moved down and back. Only the tab moves now.

## 2.9.0

Folder tabs, floating windows, and jobs that wait their turn; downloads that can't stall.

- **The store tabs are folder tabs:** the one you're looking at is raised, and the page glows up from the bottom in
  its store's colour. On **Everything**, the colours of the stores you're signed in to drift slowly through the
  glow (still, when motion is reduced). Sort, tile size and what's running moved up beside the tabs.
- **Tags, Stores and Settings are windows** that float over the page: move one by its title bar, resize it from
  its corner, keep several open side by side. A click elsewhere no longer closes them; **×** or Escape does
  (the one in front). Each opens where you left it.
- **Settings save as you change them.** No more **Save**: a box or a list is saved straight away, a folder or the
  Payhip shops when you leave the field. While a job runs, only where files go, the browser, the stores and the
  Payhip shops wait for it to finish; everything else changes at once.
- **The sidebar folds.** **Hide filters** folds it to a thin strip, and each section (your tags, suggestions,
  Show, creators) folds by its heading. Both are remembered.
- **Tasks** (next to Library and Downloads) shows what's running with its progress, what's waiting, and what
  finished, with how it went, how long it took, any problems and its full progress (the last 60, kept between
  runs).
- **Jobs wait their turn (#49).** Start a sync, download, refresh or sign-in while something is running, and it's
  queued instead of refused ("Hoard is busy"); it starts when its turn comes. Take one off the queue in Tasks.
- **Failed downloads are tried again (#19),** twice unless you choose otherwise in Settings (**Failed downloads**),
  after a short wait, before they count as failed. A store saying the file isn't there, or isn't yours, isn't
  tried again.
- **New, and Recently added (#18).** Something that appears in your library after a refresh has a **New** badge for
  a week (**New in your library** in Settings: a day to a month, or never), and **New** under **Show** filters to
  them. **Recently added** sorts the newest first. What was already there when Hoard first read a store isn't new.
- While your hidden library is locked, hidden products' names are left out of job progress and the Tasks list.
- **Downloads that stall no longer hang Hoard.** A file the store stopped sending part way through, without hanging
  up, used to wait for ever when it came through the browser (Jinxxy, and Booth when it turns direct downloads
  away): the download never finished, its item stayed busy, and every job after it waited, with **Stop** unable to
  reach it. Now a download with nothing new for 2 minutes is given up on and tried again, whichever way it comes.
- **Stop works part way through a file,** within a few seconds.
- **Download progress, speed and time left.** While a file downloads, the download panel and Tasks show it with a
  progress bar, how much has come in of how much, how fast it's coming (smoothed over the last few seconds) and
  how long is left. A file coming through the browser (Jinxxy, and Booth when it turns direct downloads away)
  shows how much and how fast; the browser doesn't say how big it is, so there's no time left for those.

### Fixed since 2.8.6

- **Fixed: support reports showed product and creator names from the end of a sync.** The list of what was
  updated, skipped and failed that ends each sync in `hoard.log` went into reports as it was. Those names are now
  hidden like the rest, and a name with "secret" or "token" in it is no longer mangled as if it were a password.
- **Fixed: sign-ins kept on another drive** (`advanced_signin_location`) that wasn't plugged in when Hoard
  started made every store's list disappear, as if you'd signed out. Hoard now leaves the lists alone when that
  whole folder is missing.
- **Fixed: "Hoard is busy" just after starting.** The check of the catalog's seal no longer holds up the first
  thing you choose when there's nothing to reseal.
- The pages' script runs in strict mode again (the splash's code had been put before `"use strict"`, which
  switched it off), and `PRIVACY.md` says where support reports really go: `Hoard\Support Reports` in your
  Documents folder.

## 2.8.6
UI Improvements
A UI and usability update focused on knowing what's downloaded, smoother startup, better window behavior and accessibility.

- Downloaded status in the Library. Downloaded assets now show a small download indicator on their thumbnails, with an accessible label for screen readers. A new Downloaded filter provides `Downloaded` and `Not downloaded yet` options with live counts. Filters work with the existing filter system, can be cleared normally, survive reloads through the URL, and stay in sync with the item's actual on-disk status.

- Splash screen while the Library loads. The Library and Downloads pages now show a full-window Hoard splash with the logo and "Opening your hoard" while the initial library is being read. The splash stays visible for at least 1.2 seconds, appears immediately on the first page, only fades in on later page loads when loading takes longer, and is removed after loading finishes, an error, or a 20-second safety timeout. Reduced-motion settings disable the animation.

- Remember window size and position. Hoard now remembers the window's size, position and maximized state between launches. Invalid or damaged saved settings are ignored safely, off-screen windows are repositioned to the center, and the previous normal size and position are preserved when maximizing or minimizing.

- Improved large-text layouts. Fixed an accessibility issue where the Largest text setting could cause panels sized relative to the window to extend beyond the visible area. Window-based sizing now accounts for the active zoom level across Settings, Stores, the sidebar, details panel, selection bar, dialogs, setup card and download panel.

- **Check for updates to what you've downloaded.** In Downloads, **Check for updates** (under **Updates**) reads
  your stores without downloading anything, and lists each download whose store has newer files: files the
  creator added or changed since you downloaded it. **Update all**, or **Update** one from its details (which also
  have **Check for updates** for just that one). In the Library, such items say **Update available**.

## 2.8.5

- **Security: the September 2026 code-scanning findings.** Nothing here is known to have been exploitable (the
  server already needed this run's access key, and imported pages were already opened with scripts off), but each
  guard is now one CodeQL can follow, with tests for each:
  - Imported store pages are cleaned with an HTML parser instead of patterns, so no way of writing a script tag
    (`<SCRIPT>`, `</script >`, a tag split over lines) or an event handler slips through, and `<style>` inside SVG
    can't carry markup.
  - The page scripts' Content-Security-Policy hashes are found the same way, however the tags are written.
  - Images from the downloads folder are served from a path rebuilt from a checked path inside the folder, with a
    type from a fixed list; fonts from Hoard's own list of names.
  - No response header can carry a line break.
  - Jinxxy links are recognised by their host (`jinxxy.com` or a subdomain, over https), not by the text
    "jinxxy.com" somewhere in the address.
  - Support reports hide asset and creator names without patterns that could take very long on an unusual line.

- **Store sign-ins and setup.** On macOS, background store reads now use the same full Chromium as the sign-in window so Keychain-encrypted cookies can be read. On Windows, an open browser's locked cookie database no longer makes setup status fail; the Library takes over count updates if the setup assistant is closed during sign-in. Settings, sign-in messages, logs and support reports now show which browser Hoard actually uses, including fallback to its own browser.
- **Downloads and library.** Jinxxy browser downloads now accept OneDrive cloud files without treating them as symlinks. Fully deleted downloads leave Downloads on rescan and can be downloaded again; partially missing ones remain marked. Downloads gains Archive, Removed and Hidden views, with sidebar counts following the current view. Removing a browser store's sign-in folder while Hoard is closed clears that store's refreshed Library list at startup without deleting downloaded files or imported lists.
- **Privacy and interface.** Support reports now redact Windows user paths with doubled separators and downloaded filenames in progress lines, using consistent placeholders throughout the ZIP. Locking Hidden clears any open hidden-item details. Downloads Settings now includes the update controls. A PIN test no longer fails if its digits happen to occur inside a random hash.

## 2.8.4

- **Local support reports.** Settings, store errors and failed downloads can now create a sanitized support ZIP without using the command line. The report is built locally, keeps raw diagnostics and tracebacks private, replaces local paths, credentials, tokens, purchase names and creator names with placeholders, and is never uploaded automatically.

## 2.8.3

Faster with large libraries, in both pages and behind them. (There's no 2.8.2: a release by that name was
published by mistake without its files.)

- **Only the cards near the screen are drawn.** Both pages drew every card on each filter click or search
  keystroke; now they draw the first 120 and add more as you scroll.
- **Tags that match a word are found through a word index,** instead of trying every such tag on every name:
  20,000 names with 300 matching tags take about 0.1 s instead of 28 s, every time the library loads.
- **The Downloads index is rebuilt without holding anything up.** A sync no longer pauses after each download while
  the Downloads page asks for the index, and the Library page never waits for it.
- **The library and downloads lists are gzipped** when they're large: 28 times smaller, which helps when Hoard is
  opened from another device.

## 2.8.1

- **Hoard for Unity loads large libraries quickly,** and recognises your own catalog: see its 0.2.0 changelog.
- **The catalog is sealed again when Hoard starts,** if it isn't sealed with this computer's key. The Unity window
  reads `catalog.json`, and one sealed by a Hoard with a different key (Hoard on another computer, an earlier
  install, or Hoard run on Microsoft Store Python) showed there as "made on another computer" until the next
  download. Hoard rebuilds it in the background, and not while a job is running (that job rebuilds it anyway).
- **Fixed: a blank page from files with Windows line endings.** Browsers check a page's script against Hoard's
  security policy after turning CRLF line endings into LF, and Hoard didn't, so a page file saved with CRLF (a
  checkout whose git settings override `.gitattributes`) had its script refused.
- **Microsoft Store Python:** when Hoard runs on it, the log and `verify` say so. Windows keeps a Store app's
  AppData separately, so that Hoard's settings, sign-ins and sealing key aren't the installed app's.

## 2.8.0

- **Sync automatically.** In **Settings**, choose every 6 or 12 hours, once a day or once a week (it's off unless
  you do). While Hoard is open, it syncs by itself that often, counting from your last sync, whoever started
  it: it reads your stores and downloads anything new or updated. Payhip is left out, since it needs you there
  for its bot check. It waits for any other job, and when you're offline it tries again 15 minutes later
  instead of marking every store as unreachable. An open page shows its progress, and **Stop** stops it.
- **The open item stays marked.** While an item's details are open, its tile is outlined in gold, in both
  views, and screen readers hear it as the current item.
- **Owned twice, striped.** Something you own on more than one store has a spine striped in both stores'
  colours, and its label says where else you own it.
- **Accessibility settings,** in **Settings**, for both views:
  - **Text size:** Normal, Larger, Large or Largest.
  - **Pause animated pictures:** animated product pictures show as a still of their first frame.
  - **Reduce motion:** no sliding panels, lifting tiles or animated progress, as when your computer asks for
    less motion (which Hoard already followed).

## 2.7.0

- **Hoard updates itself.** **Settings** has a new **Updates** section. **Check now** asks GitHub whether there's
  a newer version. In the Windows app installed with `Hoard-Setup`, **Update to** then downloads the new
  installer, checks it, closes Hoard, installs it and opens Hoard again. Your settings, library, sign-ins and
  downloads stay as they are. Hoard only runs an installer whose SHA-256 matches both the release's
  `SHA256SUMS-windows.txt` and the checksum GitHub lists for the file, and it won't update in the middle of a
  refresh or download. The portable zip and Hoard run with Python say there's a newer version and link to it.
- **Check for updates automatically,** off unless you turn it on: Hoard asks GitHub once a day, when it starts,
  and shows **Update to** at the bottom of the page when there's a new version. A check sends GitHub nothing but
  the request itself (GitHub sees your IP address, as with any website). The privacy notes say so.

## 2.6.0

- **itch.io signs in with an API key.** Its website shows automated browsers a Cloudflare check that never lets
  them through, so signing in to itch.io in Hoard's window couldn't work. Now **Add API key** on itch.io's row
  in **Stores** shows where to make a key on itch.io, checks it with itch.io, and keeps it protected by your
  operating system (your Windows account, your Mac's Keychain or your Linux keyring), never in `config.json`.
  Hoard reads your itch.io library and downloads your files through itch.io's API, as itch.io's own app does:
  no browser, downloads that resume, and each file checked against itch.io's checksum. The key is only ever
  sent to itch.io's API. **Sign out** deletes it. From the command line: `login itch`.
- itch.io items are known by itch.io's own project number, so a page you import and the API agree.

## 2.5.2

- **Hoard's own browser, in the Windows app:** installing it now works. The app looked for the browser inside its
  own program folder, while installing put it in your user account's usual folder
  (`%LOCALAPPDATA%\ms-playwright`), so setup went on saying it "isn't installed". Both now use that folder: a
  browser you'd already downloaded is found straight away, and updating Hoard never removes it.

## 2.5.1

- **Hoard's own browser:** when **Settings** names Microsoft Edge or Google Chrome and it isn't installed, Hoard
  now uses its own browser instead. Setup offered to install it for that case, but afterwards still said the
  chosen browser "isn't installed", and signing in failed. Installing it is now also written to `hoard.log`.

## 2.5.0

Payhip becomes a library Hoard reads, saved pages can be imported in bulk, and itch.io joins.

- **Payhip is listed, not downloaded.** Payhip's check for automated browsers made downloading from it
  unreliable, so Hoard now lists everything you bought there, with each product's download page, and you
  download the files from Payhip yourself. **Sync**, **Download** and **Download everything new** leave Payhip
  out. Files Hoard downloaded from Payhip before stay where they are, in Downloads and in the catalog.
  `sync --payhip-page` is gone, with the page Hoard used to write listing Payhip products to download yourself.
  Refreshing Payhip with no shops listed no longer opens a window just to say so: it suggests importing.
- **Import saved pages in bulk.** A store's library often spans several pages, and Payhip keeps one per shop,
  so one saved page couldn't hold everything. **Import pages** (in **Stores**) now takes any number of saved
  pages at once, **Import a folder** takes a whole folder of them, and files or folders can be dropped on the
  window. They're read together, offline, and each page gets its own result, shown at the end: one that can't
  be read doesn't stop the rest. Pages from Payhip shops you haven't added are asked about once, together. On
  the command line, `import` takes several files and folders, and `--trust-shop` can be given more than once.
- **itch.io,** a new store. Sign in, and Hoard reads your itch.io library (what you bought, and what you
  claimed from bundles or "name your own price" pages) and downloads each project's files from its download
  page. If you set Hoard up before this version, turn itch.io on in **Settings** first: Hoard keeps the stores
  you chose. Game builds (files the creator marked for Windows, macOS, Linux or Android) are skipped unless you
  turn off **Skip game builds** in **Settings**, so a library with games in it doesn't fill your drive. A download
  page's address holds a key that opens it for anyone, so it's kept like a sign-in: only in Hoard's private
  library list, and taken out of troubleshooting files. If Hoard reads your itch.io library wrong, `debug itch`
  saves what it read (scrubbed of your details) for a report.
- **Hoard for Unity 0.1.3** shows itch.io's assets too. It's a separate release: see its own changelog.

## 2.4.2

Fixes from an outside review of 2.3.1. What was found and what changed, finding by finding, is in
`docs/security-review-2.3.1-response.md`.

- **Only Hoard's own window can use Hoard:** every request for your library, your downloads, their pictures or
  an action now needs a key that's new each time Hoard starts, even from your own computer. Other programs,
  and other people's accounts on a shared computer, could reach Hoard's address and, for example, point its
  downloads folder somewhere else. Hoard opens its window with a one-time link that the page trades for the
  key. Started as a server from the command line (`--no-open`, `--port` or `--host`), Hoard prints an
  address that includes it.
- **Payhip:** when Payhip blocks the automated browser, the page listing products for you to download yourself
  only links to Payhip and your own shops, whatever a product's record says (a record could have held a
  `javascript:` link), and it's written the same careful way as every other file.
- **Resumed downloads:** a half-finished file is only continued with the part that follows it, and only counts
  as finished when the store says the file ends there. Otherwise it's downloaded again from the start rather
  than stitched together from two different versions, and a file is only put in place once it's as long as
  the store said.
- **An emptied downloads folder:** `catalog.json` and `tags.json` no longer go on listing products that aren't
  there any more (the Unity window showed them).
- **Stop:** the file that had just finished downloading when you pressed Stop is recorded, instead of being
  downloaded again next time.
- **Faster with large libraries:** product pictures are found without going through the whole library
  (1,000 pictures in a 100,000-item library: 10 seconds before, 0.05 now); opening the Library no longer copies
  the whole list through JSON (0.7 seconds to 3 milliseconds at 100,000 items); and during a sync each store's
  record is saved at most every 10 seconds, instead of after every product and file (a 5,000-product sync
  with nothing new rewrote a 1.4 MB file 5,000 times).
- The list of files Hoard has sealed never drops an entry (past 20,000 it could, in principle).
- **Hoard for Unity 0.1.2:** a `.unitypackage` whose headers claim impossible sizes is refused before anything
  is set aside for it. It's a separate release: see its own changelog.

## 2.4.1

The 2.4.0 Windows app, released again: 2.4.0's release couldn't take the installer, and its version number can't
be reused. Nothing else changed: what's new is under 2.4.0 in CHANGELOG.md.

## 2.4.0

Hoard is a Windows app now: no command prompt, no Python to install.

- **An installer:** `Hoard-Setup-<version>.exe` installs Hoard for you only (no administrator prompt), with a
  Start menu entry, an optional desktop icon and an uninstaller. Updating is running the newer setup. Your
  data is never touched by installing, updating or uninstalling. A portable zip of the same app is there too.
- **Its own window,** using Microsoft Edge WebView2 (part of Windows). Closing it quits Hoard cleanly: a download
  in progress stops (and resumes next time), and store browsers close. Links to store pages open in your web
  browser. Without WebView2, Hoard says so and opens in your browser, with **Quit Hoard** in Settings.
- **One copy at a time:** opening Hoard again brings its window to the front.
- **No console:** anything Hoard would print goes to `logs\hoard.log` in its app-data folder, handy when
  reporting a problem.
- **The command line** is `hoard-cli.exe` in Hoard's folder (`hoard-cli sync`, `hoard-cli verify`, ...). New:
  `self-test`, which checks a copy of Hoard has everything it needs.
- From source, `Hoard.bat` also starts Hoard without leaving a console open.
- Built on GitHub for every release from hash-locked dependencies (`requirements-app.txt`), checked with the
  self-test, with signed build provenance.

## 2.3.1

- **Sync button:** next to Stores and Settings (and in Downloads). It reads what you own from each store
  you use, then downloads anything new, as one job with progress and **Stop**.
- **Fixed: Gumroad downloads failed.** Since 2.1.1, every download that redirects to a file host, which
  is every Gumroad file, was refused. The checked download path counted redirects it wasn't even
  following. Booth hid the problem by falling back to its browser route. Hoard's tests now cover the
  real HTTPS path, which would have caught it.
- **Fixed: Jinxxy downloads could look like they never finished,** which also kept **Sign out** and
  other jobs waiting. Visible download buttons get a normal click again, with the patience they had
  before 2.2.0, and waiting for a download to start now shows progress and can be stopped. A second
  download started by the same click is cancelled, and a button's class names no longer count when
  deciding which buttons never to click.
- **Fixed: an old version number after updating over an old install** (and, worse, possibly old code in
  any file whose size hadn't changed). Python reused compiled copies because every release's files had
  the same date. Release files now carry the release's own date, the launchers always start from the
  files, and Hoard notices and clears stale copies itself.
- **Fixed:** the filter chips overlapped the first row of the grid, and the heading counted archived
  items in the main library.

## 2.3.0

- **Recovery words for a forgotten PIN.** When you set your hidden library's PIN, Hoard shows 6 recovery
  words, once, and asks you to type two of them back. If you forget your PIN, choose **Forgot your
  PIN?** and enter the words to set a new one; your hidden items stay hidden. Capitals, numbering and
  the first four letters of each word are all fine, and a misspelt word is pointed out. The words
  are kept only as a slow, salted hash, and wrong ones count toward the same waits as wrong PINs.
- Already have a PIN? Unlock **Hidden** and choose **Create a recovery phrase**. **New recovery phrase**
  replaces an old one.
- The words come from the standard BIP-39 list, but they only unlock Hoard's hidden library. They
  aren't a crypto wallet phrase, and Hoard never asks for a wallet's recovery words.

## 2.2.0

Tidy your library, and keep some of it private.

- **Remove:** open an item (or choose several with **Select**) and remove it. Removed items stay out of
  your library even after a refresh, and aren't downloaded. Restore them from **Removed**, or delete
  them from Hoard for good. That's also how to clean up a library page imported by mistake.
- **Archive:** put older products that may no longer work into **Archive**, out of your main library.
  Gumroad's own archived purchases start there too. **Unarchive** moves them back.
- **Hidden library:** **Hide** things you'd rather not see by default, such as NSFW assets, behind a
  PIN. Hidden items are left out of everything (library, Downloads, counts, tags, search) until you
  unlock them in that browser, for 15 minutes past your last use. Wrong guesses wait longer each time.
  A forgotten PIN can only be cleared by deleting the hidden items, never by showing them. It's a
  privacy screen, not encryption: the files on your disk are ordinary files.
- **Payhip, large libraries:** refreshing Payhip now opens a window and waits while you complete
  Payhip's automated-browser check, instead of giving up. Libraries of up to 3,000 products are read
  page by page.
- **Payhip, one shop for everything:** a shop on payhip.com lists your purchases from every shop, so
  adding one is often enough. Shops on their own domains that turn up are offered in **Stores** to
  review and add, never trusted automatically.
- **Payhip downloads:** Hoard uses each file's own download button, names files from the name Payhip
  shows, includes files on a product's other content pages, and never touches **Reset download
  credits** (or any other reset, credit, limit or delete control, on any store).

## 2.1.1

A security release answering the independent audit of 2.1.0. Every finding is fixed; the details are in
docs/security-audit-2.1.0-response.md.

- **Downloads take one checked path.** Downloads of your files went through a different, less careful
  route than product pictures, which would have followed a redirect to your own computer or network.
  Now every store request and download goes through one path. Redirects are followed one hop at a
  time, and each hop must be https to a public internet address. Store cookies only go to the store's
  own sites; the servers hosting its files get none.
- **Store traffic is https only.**
- **Files can't be redirected on disk.** Downloads are created exclusively without following links, and
  only moved into place if they're still the file that was written. Pictures are served the same way.
- **Imported pages run nothing:** scripts are off, and event handlers are stripped too.
- **Shops from imported pages need your say-so.** Hoard shows the exact address and asks before
  adding it. Internationalised look-alike names are refused.
- **No more overwriting** when two products' or files' names clean up alike.
- **Troubleshooting files are scrubbed by default:** no email addresses, license keys, tokens, signed
  links or screenshots, and a summary instead of your purchases. `--raw` saves everything, marked
  sensitive.
- Also: time limits and a connection cap for Hoard's server; manifests are read with size and type
  checks everywhere; a custom sign-in folder needs an explicit advanced setting and can't be on a
  network share; the import picker accepts the same file again after you decline.

## 2.1.0

A setup assistant, so nobody needs a command line or has to guess what to do first.

- **The setup assistant** opens the first time you start Hoard, and any time from Settings. It covers
  the browser Hoard signs in with, which stores you use, your Payhip shops, signing in to each store,
  where downloads go, and bringing over Hoard 1.x.
- **No more `playwright install`:** if Hoard needs its own browser, one button installs it, with
  progress. On Windows, Hoard uses Microsoft Edge, which is already there. If a store is ever read
  without the browser installed, the message says what to do instead of showing Playwright's error.
- **Signing in without your saved passwords:** Hoard's window is its own browser, so it doesn't have
  what your usual browser saved. The assistant shows where to copy your password from (Chrome, Edge,
  Firefox, Safari, password managers) and other ways in: password reset, Google or Discord sign-in, and
  passkeys on Windows Hello or your phone.
- **Links from emails:** when a store emails a sign-in or "is this you?" link, paste it into the
  assistant and it opens in Hoard's window, rather than signing in your usual browser. Only links on
  that store's own site are accepted.
- **Stores you don't use are hidden**, from the tabs, the Stores panel, the grid and **Refresh all**.
- New `install-browser` command, for the command line.

## 2.0.2

Fixes from real Booth and Payhip library pages.

- **Booth downloads:** nothing downloaded, because Booth now draws its download buttons with a script. The
  addresses sit in placeholders, not links, so every item looked like it had no files. Hoard now reads
  them; the "Open in Browser" and Booth Library Manager variants of each file are skipped.
- **Booth's free downloads** are now included, with a switch in Settings.
- **Payhip shops:** Payhip keeps your purchases in each shop you bought from, on the shop's own address,
  with no single library. Add your shops in Settings under **Payhip shops**, and Hoard reads each one's
  library page and downloads from it. Signing in to Payhip opens a tab per shop. Importing a shop's
  saved page adds that shop for you.
- Only the shops you list count as Payhip's own sites, for links and downloads alike. Any other address
  is still refused.

## 2.0.1

Fixes for new testers' reports.

- **Jinxxy, new accounts:** items showed as "Navigation", by your own account name. With only one item in
  the inventory, the reader took the whole page as that item's card, sidebar and all. Cards now stop
  before the page's menus and sidebars, your own "Profile" link is never read as a creator, and page
  headings such as "Navigation" or "Product Details" are never read as names.
- **Jinxxy, pictures:** downloaded items got Jinxxy's default site banner as their picture, because it
  came from the page's share image. Hoard now takes the product's own picture beside its title. Copies of
  the banner saved by earlier versions are removed on the next sync and replaced with the real pictures.
- **Booth downloads:** when Booth turns away Hoard's direct download, as sites often do with anything
  that isn't a real browser, Hoard now downloads through the signed-in browser instead, as if you'd
  clicked the download button. The direct route is still tried first, since it's faster and resumes
  where it stopped.
- **Signing out** of a store now also removes that store's items and their cached pictures from your
  library, so whoever signs in next never sees them. Your downloaded files stay where they are.
- Store readers are now tested in a real browser, against pages copied from the layouts that broke, on
  every change.

## 2.0.0

Hoard and Hoard Downloader are now one app, and nothing needs a command prompt or a settings file.

### One app
- **Library** and **Downloads** are two views of the same app, with one set of sign-ins, tags and settings.
- Download from the page: **Download** on each store, **Download everything new**, or **Download a copy**
  on a single item. Progress shows as it goes, and **Stop** pauses safely; it carries on next time.
- Items you already have say **On disk**, with a link straight to them in Downloads.
- A **Settings** panel: the downloads folder, which stores to include (and Booth gifts, archived Gumroad
  purchases), saving images for offline use, and the browser used for store sign-ins.
- On Windows, store sign-ins use Microsoft Edge, which every PC has and Windows Update keeps patched, so
  setup no longer downloads a separate 150 MB browser. Hoard's own browser is used only if Edge is missing.

### Where things live
- Settings, the library list and cached images moved into Hoard's app-data folder, next to your sign-ins
  and tags. Downloads go to a `Hoard` folder in Documents unless you choose another in Settings.
- Coming from 1.x: sign-ins and tags carry over by themselves. `Hoard.bat migrate <old folder>` brings
  over the library list and downloads folder.
- One release zip, `Hoard-<version>.zip`, replaces the three. Start it with `Hoard.bat` (or `./run.sh`).

### Command line
- Every command from both tools, as `Hoard.bat <command>` (or `./run.sh <command>`): `sync`, `verify`,
  `login`, `refresh` and the rest. See docs/COMMAND-LINE.md. `browse` is gone: that's the Downloads view.

### Under the hood
- The code is one package, `hoard/`, with each piece in exactly one place. The security code used to be
  copied into two or three files, kept identical by tests; now there's one copy, and a test checks it.
- Fixed: recognising which store a saved library page came from only worked for pages saved from the exact
  library address, because a second definition silently replaced the first.

## 1.6.2

Stops edited links from sending you anywhere but the store.

- Links you can open (**Open on Booth**, **Open download page**, a creator's page) must now be https
  addresses on the item's own store, checked when data is read, when it's written, and in the pages. Before,
  any https address was accepted, so a program editing a record could point a button at a lookalike
  sign-in page. Downloads never came from stored links, and still don't.
- Data files (manifests, `catalog.json`, `tags.json`, `asset.json` and Hoard's library list) are sealed with a
  keyed signature. When something else edits one, the tools tell you, keep a copy, and don't use its links
  until the store is read again.
- New `verify` command in Hoard Downloader: checks every data file and rebuilds the catalog files.
- The catalog files are now format version 3 (docs/DATA-FORMATS.md). Using one download folder from two
  computers? Copy `integrity.key` between them (see the README).

## 1.6.1

Hardens tags and the downloader's data files. docs/security-review-2026-09.md lists each finding.

- Paths read from `_manifest.json` must stay inside their folder, through symlinks too, so a tampered
  manifest can't make a sync write anywhere else. Records that don't are ignored.
- File, folder and item names no longer carry invisible characters such as right-to-left overrides,
  which could make one kind of file look like another.
- Data files are written through a temporary file and swapped in, so a planted symlink can't redirect a
  write and nothing reads half a file.
- Data files are read with size limits and checked entry by entry. A damaged manifest, library list or
  tag file is kept aside under a new name and the tool carries on, instead of stopping.
- Tags may only use letters, digits, spaces and `- _ . + & '`. Existing tags that used anything else are
  converted, not lost. The tag file is private to your account and has size limits.
- `catalog.json`, `tags.json` and `asset.json` now carry `format` and `version`, and each entry is
  checked against the promises in the new docs/DATA-FORMATS.md before it's written.
- Requests to the tools are limited in size, and malformed ones are refused.
- Fixed: on Linux without a keyring, Hoard's page stopped updating after the first refresh.

## 1.6.0

Security release, answering two independent reviews. docs/security-review-2026-09.md lists every finding
and what was done.

### Your sign-ins
- Each store's sign-in is now kept separately. Existing sign-ins are split between stores automatically on
  first run, keeping only each store's own cookies.
- On Linux, sign-ins are only saved when a keyring can encrypt them, and Hoard checks after you sign in that
  they really were. Computers without a desktop can opt out with `"allow_unprotected_signins": true`.
- Sign out now asks the store to end the session where it can, deletes that store's sign-in, checks nothing
  is left, and tells you what it did.
- A copied Gumroad session cookie in `config.json` or `HOARD_GUMROAD_SESSION` is no longer read. Sign in
  with `login gumroad` instead.

### Network and pages
- Product images are fetched over a connection that goes only to the public address that was checked, so
  DNS rebinding can't point it at your network. Store download links are only followed on the store's own
  website.
- Only raster images are kept (no SVG), and everything the tools serve apart from the page is sandboxed.
- Using the tools from other devices now needs HTTPS (`--tls-cert`, `--tls-key`), or `--plain-http` to
  say the connection is already encrypted, such as over Tailscale.

### Installation and releases
- Setup limits who can change the program folder to your account.
- Every Python package is pinned to an exact version and checked against its hash when installed.
  `requests` is now at least 2.32.4.
- GitHub Actions are pinned to exact commits with minimal permissions, and release zips carry signed
  build provenance once the repository is public (`gh attestation verify`).
- Security tests run on every change. SECURITY.md now explains what Hoard protects against and what no
  desktop app can.

## 1.5.0

Tag manager.

### Both tools
- Your own tags, alongside the suggested ones. Tag an item from its details, or many items at once with
  **Select** (including **Select all shown** after filtering).
- A **Tags** panel to create, rename, merge and delete tags, and to keep or hide suggestions. Keeping a
  suggestion makes it your tag on every item whose name has that word, including ones you buy later, and
  any tag can match names that way.
- Hoard and Hoard Downloader share your tags, so tagging in one shows in the other. Tags added to a
  product apply to every copy you own on other stores.
- The sidebar lists your tags first, then suggestions.

### Hoard Downloader
- `asset.json` and `catalog.json` include your tags (`tags`) next to the suggestions (`suggested_tags`),
  and `tags.json` now lists your tags under `tags` and suggestions under `suggested`.

## 1.4.0

Works offline.

### Both tools
- The typefaces are bundled, so the pages look right without an internet connection, and they no longer
  load anything from Google Fonts. Nothing is fetched from outside your computer just to show a page.
- A notice appears when you're offline, saying what still works.
- A store that can't be reached is now reported as "couldn't reach", with your saved data left
  unchanged, instead of a raw browser error.

### Hoard
- After each refresh, every product image is saved, so your whole library shows its images offline.
  Turn this off with `"offline_images": false` in `config.json`.
- Refresh and Sign in say you're offline instead of trying. Signing out still works offline.

### Hoard Downloader
- Stores that can't be reached are skipped with a clear message, and the rest still sync.

## 1.3.0

Ready for a public release: safer pages, clear policies and documented code.

### Both tools
- A footer with the version and links to the project on GitHub, updates, problem reports, the privacy
  policy, the terms of use and the AI disclosure.
- Links from store pages and imported pages only open when they're ordinary web addresses. A crafted
  listing can't turn a link into a script.
- Product images are only fetched from public internet addresses, never from your home network or from
  files on your computer.
- The pages are sent with a strict Content-Security-Policy and headers that stop other websites from
  embedding them or reading their responses.
- With `--host 0.0.0.0`, other devices on your network need the access key the tool prints when it
  starts. Actions still only work from the computer running the tool.
- Outbound links no longer tell the store which page you came from.

### Project
- New documents: privacy policy, terms of use, copyright and credits, security policy and AI disclosure.
  Each release zip includes them.
- A developer guide in `docs/ARCHITECTURE.md`, and every function in the code now has a docstring.
- Dependency versions are capped at their current major versions.

## 1.2.1

Maintenance release; Hoard and Hoard Downloader work the same as in 1.2.0.
- Release builds no longer depend on a third-party GitHub Action, and the release for an existing
  version can be built again from the Actions tab.

## 1.2.0

Safer sign-ins, in both tools.
- Sign-ins moved out of the program folder into your user account's private app-data folder, so sharing,
  syncing or committing the program folder can't carry them. The first run moves existing sign-ins
  automatically and removes the old copy. Both tools now share one set of sign-ins.
- Saved sign-ins are encrypted by the operating system on every platform. On Linux and macOS the
  browser previously used a fixed, publicly known key, which made them readable to anything that could
  read the files. macOS users need to sign in again once.
- The two tools can no longer use the sign-ins at the same moment, which could damage them.
- Sign out of a store, or of every store, from the Hoard Downloader menu, Hoard's Stores panel, or the
  `logout` command.
- A Gumroad session cookie for headless use now comes from the `HOARD_GUMROAD_SESSION` environment
  variable. Keeping it in `config.json` still works but shows a warning.

## 1.1.0

### Hoard Downloader
- Downloads Booth purchases and gifts. Files come straight from Booth, interrupted downloads resume,
  and new versions a creator uploads are downloaded and listed as updated.
- Downloads Payhip purchases in a visible browser window, waiting while you complete Payhip's bot check.
  If Payhip won't let it in, it can read your library from a page you saved, and lists the rest in
  `Payhip/_download-yourself.html`; files you save there are recorded on the next sync.
- Stores you haven't signed in to are skipped instead of reported as failures.
- The menu has a single **Sign in to a store** entry covering all four stores.
- The downloads browser shows Booth and Payhip.

### Hoard
- No changes; version raised to match Hoard Downloader.

## 1.0.0

First release.

### Hoard
- One searchable page for everything you own on Booth, Gumroad, Jinxxy and Payhip, with store,
  tag and creator filters and links to each item's download page.
- Sign in and refresh each store from the page. A failed refresh keeps that store's previous list.
- Products you own on more than one store are pointed out, with a view of every copy.
- Booth items list their files with direct download links; Booth gifts and archived Gumroad
  purchases are labelled.
- Import a library page saved from your own browser, for stores that block automated browsers
  (Payhip today).

### Hoard Downloader
- Downloads everything you own on Gumroad and Jinxxy into one folder per product, with a separate
  manifest per store so nothing is fetched twice. Interrupted Gumroad downloads resume.
- Re-running only fetches new or changed files, and the summary lists files a creator has updated.
- Suggests tags from words shared across asset names.
- Includes a read-only library browser with thumbnails, search, filters, and buttons to open folders.
