The first time you open Hoard, a setup assistant walks you through everything. It takes a few minutes, and
you can run it again any time from **Settings**, then **Set up Hoard again**.

The first time, the assistant goes through to the end: it can't be skipped or closed, a step that isn't done
(Hoard's browser not installed yet, no store picked) keeps you on it, and going on without signing in to any
store, or without a Payhip shop, asks first. Run again from Settings, it can be skipped or closed at any step.

## The setup assistant, step by step

1. **Welcome to Hoard.** What's about to happen. Hoard runs only on your computer and never sees your
   passwords.
2. **The browser Hoard signs in with.** Hoard reads your stores through a browser it controls, kept apart from
   the one you browse with: Microsoft Edge on Windows, and Hoard's own browser elsewhere (or on Windows without
   Edge). If that isn't installed yet, **Install Hoard's browser** downloads it (about 150 MB, once).
3. **Used Hoard before?** If you used Hoard 1.x, **Bring it over** copies your library list and downloads
   folder. New to Hoard? Skip it.
4. **Which stores have you bought from?** Booth, Gumroad, Jinxxy, Payhip and itch.io. Tick the ones you use
   (the first time, only stores you already have items from are ticked). Hoard only shows and
   reads the stores you pick. You can change this later in [Settings](Settings). Hoard keeps copies of your
   files from all of them but Payhip, which it lists: you download from Payhip yourself.
5. **Your Payhip shops** (only if you picked Payhip). Payhip keeps your purchases in each shop you bought
   from, not in one library, so add each shop's address, one per line. Rather not sign in to Payhip? Leave
   this empty, save each shop's library page from your usual browser, and import them all from **Stores**
   afterwards. See [Stores](Stores#payhip).
6. **Sign in to your stores.** Each store opens in Hoard's own window. Sign in there as usual, then close the
   window, and Hoard reads what you own.
7. **Where should downloads go?** A `Hoard` folder in your Documents unless you choose another. Pick a drive
   with room to spare: VRChat assets add up.
8. **When you close Hoard's window** (in Hoard's own window, from 3.1): **Keep Hoard running**, minimized to the
   taskbar (the Dock on a Mac), so downloads, syncs and the routine check carry on, or **Quit Hoard**. It's the
   same choice as **Closing Hoard** in [Settings](Settings), where you can change it later. Hoard in your web
   browser doesn't ask: closing the tab is the browser's.
9. **Hoard's ready.** When you choose **Finish**, Hoard reads what you own from your stores.

## Signing in without your saved passwords

Hoard's window is its own browser, so it doesn't have the passwords your usual browser saved. Copy yours from
there and paste it into the store's page in Hoard's window. It goes straight to the store: Hoard doesn't read
or keep it.

- **Chrome:** type `chrome://password-manager` in the address bar and search for the store.
- **Edge:** go to `edge://settings/passwords`.
- **Firefox:** go to `about:logins`.
- **Safari or iPhone:** open the Passwords app.
- **A password manager** such as Bitwarden or 1Password: open it and search for the store.

Other ways in:

- **Forgot the password?** Use the store's own "Forgot password" link in Hoard's window. The new password
  works everywhere.
- **Signed up with Google, Discord or X?** Use the same button in Hoard's window: it's the browser's own window,
  which they accept (from 2.11). If one still says the browser isn't supported, set a password for your store
  account in your usual browser, then sign in here with that.
- **Passkeys** on Windows Hello or your phone work in Hoard's window too.
- **A sign-in or confirmation link by email?** Paste it into the assistant's box instead of clicking it, and
  Hoard opens it in its own window, where it belongs.

## After setup

- **Sync** (top right) reads what you own from each store, then downloads anything new, in one go. See
  [Downloads](Downloads).
- **Library** shows everything you own; **Downloads** shows what's on your computer. See
  [Your library](Library).
- **Stores** is where you sign in again, refresh one store, or sign out. See [Stores](Stores).
- **Tags** organises things your way. See [Tags](Tags).
- Want your assets in Unity? See [Hoard for Unity](Hoard-for-Unity).
