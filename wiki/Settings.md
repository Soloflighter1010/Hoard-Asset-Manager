Everyday choices are in **Settings** (top right). A few rarer ones only live in `config.json`.

## The Settings panel

Settings opens in a panel over the page, like Tags, Stores and Tasks; one of them is open at a time. **×**,
Escape or a click on the page around it closes it. Each change is **saved as you make it**: a box or a list
straight away, a folder or the Payhip shops when you leave the field. The title bar says **Saved**.


- **Downloads folder:** where downloaded files are saved. A `Hoard` folder in your Documents unless you choose
  another: **Browse…** opens your system's folder picker (in Hoard's own window), or type the path. **Default**
  puts it back. Changing it doesn't move files you've already downloaded, so move those
  yourself if you want them in the new place.
- **Library folders:** your downloads folder and any folders on other drives (an external disk, say) that Hoard
  reads as part of your library, each with how many downloads it holds and the space free on its drive (or that
  its drive isn't connected), and **Open**. **Add a folder…** picks one and adds it (in Hoard's window), or type a
  path and choose **Add**. **Remove** only stops Hoard reading a folder: its files stay. Each folder gets a tab in
  Downloads. See [Downloads](Downloads#library-folders-on-other-drives).
- **Stores:** which stores Hoard shows and reads, with a few options:
  - Booth: **Include gifts** and **Include free downloads**.
  - Gumroad: **Include archived purchases**.
  - itch.io: **Skip game builds** (on unless you turn it off): files the creator marked as a program for
    Windows, macOS, Linux or Android aren't downloaded. See [Stores](Stores#itchio).
- **Payhip shops:** the shops you've bought from on Payhip, one per line, such as `myshop.store` or
  `payhip.com/ShopName`. Importing a shop's saved page adds it for you. Hoard lists what you bought there, and
  you download it from Payhip yourself. See [Stores](Stores#payhip).
- **Offline:** **Save product images, so the library works offline**.
- **New in your library:** how long something that appeared in your library after a refresh keeps its **New**
  badge: a day, 3 days, a week (unless you choose otherwise), 2 weeks or a month, or never. See
  [Library](Library#finding-things).
- **Failed downloads:** a file download that fails (a dropped connection, a busy server) is tried again after a
  short wait: twice unless you choose otherwise, once, 3 times, or not at all. A store saying the file isn't
  there, or isn't yours, isn't tried again.
- **Previous versions** (4.0): how many old copies of a file to keep when an update replaces it: the last one unless
  you choose otherwise, none, or the last 2, 3 or 5. See [Downloads](Downloads#previous-versions).
- **Routine check:** **Off** (only when you ask) unless you choose every 6 hours, every 12 hours, once a day, once a
  week or once a month, while Hoard is open. It reads your stores (not Payhip), checks your downloads and checks
  for updates, then asks which of what it found to download. It replaces **Sync automatically** and **Check your
  downloads**: a sync you'd turned on keeps its timing. See [Downloads](Downloads#downloading).
  **Tell me when it finds something to download** (on unless you turn it off, from 3.1) shows a notification from
  your system when it finds new products or updates while Hoard is open in the background.
- **Appearance** (from 3.2):
  - **Language** (from 3.3): **Match my computer**, **English**, **日本語** (Japanese) or **한국어** (Korean). Match
    my computer uses the first of these your system or browser asks for, and English if it asks for none of them.
    The page reloads in the language you choose. Your product names, creators, tags and files are never
    translated. The task log, Hoard for Unity and the website are in English. The Japanese and Korean were made
    with AI help, so some wording may be off: [tell us](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml) when something reads wrong.
  - **Match my computer**, **Light** or **Dark**: Hoard follows your computer's light or dark setting, or stays the
    one you choose.
  - **A theme**, each in a light and a dark version: **Hoard** (the cave and its gold), **Dragonfire**, **Frost
    Cave**, **Geode**, **Mossy Ruins**, **Synthwave**, **Sakura**, **Midnight & Paper** (true black, for OLED
    screens, and white), **High contrast** and **Spooky Hoard**. In a theme whose accent is close to a store's
    colour, that store's colour shifts a little, so the two aren't mistaken for each other. **Store colours** (below)
    still apply in every theme.
- **Accessibility:**
  - **Text size:** **Normal**, **Larger**, **Large** or **Largest**. Everything on the page grows with the text.
  - **Pause animated pictures:** animated product pictures (GIFs and the like) show as a still of their first
    frame. Turn it off and they move again.
  - **Reduce motion:** no sliding panels, lifting tiles or animated progress. Hoard also does this when your
    computer's own settings ask for less motion.
  - **Coloured glow behind the page:** the stores' colours rising from the bottom of the window. Turn it off for a
    plain background.
  - **Store colours:** **Standard**; **Easier to tell apart (colour blindness)**, a set of colours chosen to stay
    distinct with the common kinds of colour blindness, clear on light and dark backgrounds; or **My own**, a colour
    for each store (and Local) that you pick. Choose **Standard** again to go back.

  These apply to both views straight away.
- **Updates:** **Check for updates automatically** (off unless you turn it on): once a day, when Hoard starts,
  it asks GitHub whether there's a newer version. **Check now** asks straight away, and **Update to** installs
  it (in the app installed with `Hoard-Setup`). See [Installing Hoard](Installing-Hoard#updating). While an
  update is waiting (from 3.1.1), the Hoard logo at the top glows (and shakes now and then, unless motion is
  reduced): choose it to come straight here.
  **Get beta updates** (off unless you turn it on) is for testers: betas of the next version count as updates
  too, and you're offered the finished version when it's out. Betas may have problems. **What's new in Hoard**
  shows the changelog, version by version, with the one you're running marked; tick **Include beta updates** there
  to see betas' changes too.
- **Browser for store sign-ins:** **Automatic** (Microsoft Edge on Windows, Hoard's own browser elsewhere),
  **Microsoft Edge**, **Google Chrome** or **Hoard's own browser**. After changing it, you may need to sign in to
  your stores again.

While Hoard is refreshing or downloading, the downloads folder, the browser, the stores and the Payhip shops
can't change (the job is using them): a change to one of those is put back, and you can make it again once the
job has finished. Everything else changes straight away.

Also here:

- **Backup** (4.0): **Make a backup** saves what you've set up in Hoard to one file in your Documents, in
  `Hoard backups`: your settings (the downloads folder and other library folders as places), tags, sets, archive and
  removed choices, and your library list without its download links. Hidden items, with the PIN and recovery words
  that hide them (as their slow hashes, never the words or PIN themselves), go in only while your hidden library is
  unlocked. It never holds your store sign-ins, your itch.io key, the key Hoard seals its records with, or anything
  you downloaded: on a new computer, copy the downloads folder yourself and sign in to your stores again. **Restore a
  backup...** asks what's in the file, saves a backup of how things are now first (marked "before restoring"), then
  puts the file's settings, tags, sets and choices in place, each checked as if you'd made it here. A folder that
  isn't on this computer is left as it is, and the library list fills in only stores that have nothing listed yet.
  A backup with hidden items replaces yours only once your hidden library is unlocked.
- **Set up Hoard again:** the setup assistant, step by step. See [Getting started](Getting-Started).
- **Closing the window minimizes Hoard to the taskbar** (in Hoard's own window; on unless you turn it off): the
  close button minimizes the window to the taskbar (the Dock on a Mac), and downloads, syncs and the routine check
  carry on. Click it there, or open Hoard again, to bring the window back. Turn it off and the close button quits
  (asking first while something's running). On a Mac, **Command-Q** always quits, as **Quit Hoard** does.
- **Quit Hoard:** stops Hoard. While something is running (or waiting its turn), it asks first, as closing the
  window does: see [Closing Hoard while it's working](Downloads#closing-hoard-while-its-working).

## Settings only in config.json

`config.json` is in Hoard's app-data folder: `%LOCALAPPDATA%\Hoard` on Windows,
`~/Library/Application Support/Hoard` on macOS, `~/.local/share/Hoard` on Linux. Quit Hoard before editing it,
and keep it valid JSON.

| Setting | Default | Meaning |
|---|---|---|
| `allow_unprotected_signins` | `false` | Linux without a keyring only: keep sign-ins protected by folder permissions alone |
| `automated_sign_in` | `false` | Sign in to stores in a window Hoard drives, as before 2.11, instead of the browser's own window. Google, Discord and X refuse to sign in there, so only use it if the browser's own window gives you trouble |
| `profile_dir` with `advanced_signin_location` | `""`, `false` | Keep sign-ins somewhere other than Hoard's private folder. Used only when `advanced_signin_location` is `true`, never on a network share; how well they're protected then depends on that drive |
| `routine_hours` | `null` | Hours between routine checks while Hoard is open: `0` (off), `6`, `12`, `24`, `168` or `720` (**Routine check** in Settings). `null` until you choose: then it's `auto_sync_hours` if you'd turned that on, else `0` (off) |
| `auto_sync_hours`, `integrity_check_days` | | Before 3.0: how often to sync by itself, and to check your downloads. `auto_sync_hours` is read only to set the routine check's first timing |
| `display.text_size` | `100` | Text size in percent: `100`, `115`, `130` or `150` (**Accessibility** in Settings) |
| `download_skip` | `[]` | Products to always skip when downloading, by tag key (**Always skip** in the list **Download new** shows; see [Downloads](Downloads)) |
| `display.glow` | `true` | The coloured glow behind the page (**Accessibility** in Settings) |
| `display.colours` | `"standard"` | Store colours: `"standard"`, `"colourblind"` or `"custom"` (**Store colours** in Settings) |
| `display.theme` | `"hoard"` | The theme: `hoard`, `dragonfire`, `frost`, `geode`, `moss`, `synthwave`, `sakura`, `midnight`, `contrast` or `spooky` (**Appearance** in Settings) |
| `display.mode` | `"system"` | `"system"` (match your computer), `"light"` or `"dark"` (**Appearance** in Settings) |
| `display.language` | `"system"` | `"system"` (match your computer), `"en"`, `"ja"` or `"ko"` (**Appearance** in Settings) |
| `display.custom_colours` | `{}` | Your own store colours, as `#rrggbb` by store (`booth`, `gumroad`, `jinxxy`, `payhip`, `itch`, `local`), used when `colours` is `"custom"` |
| `check_for_updates` | `false` | Ask GitHub once a day, when Hoard starts, whether there's a newer version (the **Updates** checkbox in Settings) |
| `beta_updates` | `false` | Count betas (pre-releases tagged `v<version>-beta.<n>`) as updates too (**Get beta updates** in Settings) |
| `close_to_taskbar` | `true` | Closing Hoard's window minimizes it to the taskbar, and Hoard carries on (**Closing the window minimizes Hoard to the taskbar** in Settings) |
| `local_copy` | `true` | Whether **Add your own** offers to copy into Hoard (`true`) or to list where it is (`false`). Set by your last choice |
| `edits_root` | `""` | Where **Make an editable copy** puts copies; empty means **Hoard Edits** beside your downloads folder. Never inside the downloads folder. See [Changing a download](Downloads#changing-a-download-make-an-editable-copy) |
| `request_delay` | `1.0` | Seconds between page loads on a store |
| `new_days` | `7` | Days something new in your library is marked **New**: `0` (never), `1`, `3`, `7`, `14` or `30` (**New in your library** in Settings) |
| `keep_previous` | `1` | How many previous versions of each file an update replaces are kept: `0`, `1`, `2`, `3` or `5` in Settings (**Previous versions**), up to `10` here |
| `download_retries` | `2` | How many more times a failed file download is tried: `0` to `3` in Settings (**Failed downloads**), up to `5` here |
| `payhip.bot_check_wait` | `180` | Seconds to wait for you to complete Payhip's bot check |
| `jinxxy.item_link_pattern` | | Which links on Jinxxy's inventory page are your items |
| `tags.min_count`, `tags.max_share` | `3`, `0.4` | When a word becomes a suggested tag: in at least this many names, and in no more than this share of them |
| `tags.blocklist` | `[]` | Words never to suggest (the Tags panel's **Hide** does the same) |

The command line's `--config <file>` uses a different settings file. See [Command line](Command-Line).
