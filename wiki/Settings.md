Everyday choices are in the **Settings** panel (top right). A few rarer ones only live in `config.json`.

## The Settings panel

- **Downloads folder:** where downloaded files are saved. A `Hoard` folder in your Documents unless you choose
  another; **Default** puts it back. Changing it doesn't move files you've already downloaded, so move those
  yourself if you want them in the new place.
- **Stores:** which stores Hoard shows and reads, with a few options:
  - Booth: **Include gifts** and **Include free downloads**.
  - Gumroad: **Include archived purchases**.
  - itch.io: **Skip game builds** (on unless you turn it off): files the creator marked as a program for
    Windows, macOS, Linux or Android aren't downloaded. See [Stores](Stores#itchio).
- **Payhip shops:** the shops you've bought from on Payhip, one per line, such as `myshop.store` or
  `payhip.com/ShopName`. Importing a shop's saved page adds it for you. Hoard lists what you bought there, and
  you download it from Payhip yourself. See [Stores](Stores#payhip).
- **Offline:** **Save product images, so the library works offline**.
- **Sync automatically:** **Off** (only when you choose **Sync**), or every 6 hours, every 12 hours, once a day or
  once a week, while Hoard is open. Payhip is left out. See [Downloads](Downloads#downloading).
- **Accessibility:**
  - **Text size:** **Normal**, **Larger**, **Large** or **Largest**. Everything on the page grows with the text.
  - **Pause animated pictures:** animated product pictures (GIFs and the like) show as a still of their first
    frame. Turn it off and they move again.
  - **Reduce motion:** no sliding panels, lifting tiles or animated progress. Hoard also does this when your
    computer's own settings ask for less motion.

  These apply to both views straight away.
- **Updates:** **Check for updates automatically** (off unless you turn it on): once a day, when Hoard starts,
  it asks GitHub whether there's a newer version. **Check now** asks straight away, and **Update to** installs
  it (in the app installed with `Hoard-Setup`). See [Installing Hoard](Installing-Hoard#updating).
- **Browser for store sign-ins:** **Automatic** (Microsoft Edge on Windows, Hoard's own browser elsewhere),
  **Microsoft Edge**, **Google Chrome** or **Hoard's own browser**. After changing it, you may need to sign in to
  your stores again.

Then **Save**. Settings can't change while Hoard is busy refreshing or downloading.

Also here:

- **Set up Hoard again:** the setup assistant, step by step. See [Getting started](Getting-Started).
- **Quit Hoard:** stops Hoard. A download in progress resumes next time.

## Settings only in config.json

`config.json` is in Hoard's app-data folder: `%LOCALAPPDATA%\Hoard` on Windows,
`~/Library/Application Support/Hoard` on macOS, `~/.local/share/Hoard` on Linux. Quit Hoard before editing it,
and keep it valid JSON.

| Setting | Default | Meaning |
|---|---|---|
| `allow_unprotected_signins` | `false` | Linux without a keyring only: keep sign-ins protected by folder permissions alone |
| `profile_dir` with `advanced_signin_location` | `""`, `false` | Keep sign-ins somewhere other than Hoard's private folder. Used only when `advanced_signin_location` is `true`, never on a network share; how well they're protected then depends on that drive |
| `auto_sync_hours` | `0` | Hours between automatic syncs while Hoard is open: `0` (off), `6`, `12`, `24` or `168` (**Sync automatically** in Settings) |
| `display.text_size` | `100` | Text size in percent: `100`, `115`, `130` or `150` (**Accessibility** in Settings) |
| `check_for_updates` | `false` | Ask GitHub once a day, when Hoard starts, whether there's a newer version (the **Updates** checkbox in Settings) |
| `request_delay` | `1.0` | Seconds between page loads on a store |
| `payhip.bot_check_wait` | `180` | Seconds to wait for you to complete Payhip's bot check |
| `jinxxy.item_link_pattern` | | Which links on Jinxxy's inventory page are your items |
| `tags.min_count`, `tags.max_share` | `3`, `0.4` | When a word becomes a suggested tag: in at least this many names, and in no more than this share of them |
| `tags.blocklist` | `[]` | Words never to suggest (the Tags panel's **Hide** does the same) |

The command line's `--config <file>` uses a different settings file. See [Command line](Command-Line).
