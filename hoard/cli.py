"""Hoard's command line: `python -m hoard` opens Hoard; commands such as `sync` or `verify` run on their own."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .browser import (PlaywrightMissing, ProfileBusy, SigninsUnprotected, _playwright, check_saved_signin, launch,
                      profile_dir, sign_out, signin_protection, start_afresh)
from .common import log
from .config import clean_payhip_shop, load_config, payhip_shops, root_dir, save_config
from .downloader import build_catalog, cmd_probe, cmd_sync, cmd_verify, file_rules, remembered_files
from .jobs import Jobs
from . import itch, vault
from .library import (DOWNLOADABLE, IMPORTABLE, Library, STORES, import_saved_pages, open_sign_in_pages,
                      saved_pages_in)
from .paths import CONFIG_FILE, DEBUG_DIR, LIBRARY_FILE

from .safety import scrub
from .kept_pages import open_library, read_found, reader_summary
from .app import run_app, self_test
from .server import serve
from .setup import install_browser, migrate_from


# ----------------------------------------------------------------------------- CLI

def cmd_login(cfg, store):
    """Open Hoard's browser at a store's sign-in page and wait while you sign in. For itch.io: ask for an API key."""
    if store == "itch":
        return cmd_itch_key(cfg)
    with _playwright()() as p:
        said = start_afresh(p, cfg, store)   # (a sign-in made with another browser: signed out of with it first)
        if said:
            print(said)
        ctx = launch(p, cfg, False, store)
        open_sign_in_pages(ctx, cfg, store)
        input(f"Sign in to {STORES[store]['label']} in the browser window, then press Enter here... ")
        ctx.close()
    check_saved_signin(cfg, store)
    print(f"Saved in {profile_dir(cfg, store)}, {signin_protection(cfg)}. Never share that folder.")


def cmd_refresh(cfg, stores):
    """Refresh stores from the command line, printing progress as it goes."""
    lib = Library(LIBRARY_FILE)
    jobs = Jobs(cfg, lib)
    last = [""]

    def show(**kw):
        """Update the job's state, printing each new message once."""
        jobs.state.update(kw)
        if jobs.state["message"] != last[0]:
            last[0] = jobs.state["message"]
            print(" ", last[0])
    jobs._set = show
    jobs._refresh(stores)
    for s in stores:
        info = lib.data["stores"].get(s, {})
        print(f"{STORES[s]['label']:<8} {info.get('error') or str(info.get('count', 0)) + ' items'}")


SENSITIVE_NOTE = ("These files were saved with --raw: they're the pages exactly as your store showed them, with your "
                  "purchases, account name or email address, and possibly signed download links or license keys. "
                  "Only share them with someone you trust, and delete them when you're done.\n")


def cmd_itch_key(cfg) -> None:
    """Ask for an itch.io API key (typed without showing), check it with itch.io, and keep it."""
    import getpass
    print(f"Make an API key on itch.io ({itch.KEYS_PAGE}), then paste it here. It isn't shown as you type.")
    key = vault.clean_key(getpass.getpass("itch.io API key: "))
    if not key:
        sys.exit("That doesn't look like an itch.io API key. Copy the whole key from itch.io.")
    sess = itch.session(key)
    try:
        who = itch.profile(sess)
    except itch.KeyRefused:
        sys.exit("itch.io didn't accept that key. Check you copied all of it, and that it hasn't been deleted.")
    finally:
        sess.close()
    vault.save_key(cfg, "itch", key)
    print(f"Signed in to itch.io as {who.get('display_name') or who.get('username') or 'you'}. The key is kept "
          f"{vault.key_protection(cfg)}. Run: refresh --store itch")


def cmd_debug_itch(cfg) -> None:
    """For troubleshooting itch.io: what its API returned, counted rather than listed (no purchases, no key)."""
    key = vault.load_key(cfg, "itch")
    if not key:
        sys.exit("There's no itch.io API key yet. Run: login itch")
    sess = itch.session(key)
    try:
        keys = itch.owned_keys(sess)
        first = next((k for k in keys if itch.game_of(k)["id"]), None)
        files = itch.uploads(sess, itch.game_of(first)["id"], first["id"]) if first else []
    finally:
        sess.close()
    summary = {"library": reader_summary([itch.game_of(k) for k in keys]),
               "first_project_files": reader_summary(files),
               "file_fields": sorted({f for u in files for f in u}), "systems": [itch.systems(u) for u in files]}
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    (DEBUG_DIR / "itch_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
    print(f"itch.io's API lists {len(keys)} items, and {len(files)} files for the first. Saved in {DEBUG_DIR}.")


def cmd_debug(cfg, store, raw: bool = False):
    """Save what a store's library page looks like and what the reader found, for troubleshooting.

    By default, what's saved is scrubbed (email addresses, form values such as license keys, tokens, and every
    URL's query values, which is where signed download links keep their secrets), there's no screenshot, and the
    reader's findings are a summary rather than your purchases. raw=True saves everything as it is.
    """
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    with _playwright()() as p:
        ctx = launch(p, cfg, False, store)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        open_library(page, cfg, store)
        content = page.content()
        (DEBUG_DIR / f"{store}.html").write_text(content if raw else scrub(content), "utf-8")
        links = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (DEBUG_DIR / f"{store}_links.txt").write_text("\n".join(links), "utf-8")
        parsed = read_found(page, cfg, store)
        if parsed is None:
            parsed = {"note": "Gumroad is read from page data, not the layout"}
        summary = reader_summary(parsed)
        (DEBUG_DIR / f"{store}_summary.json").write_text(json.dumps(summary, indent=2), "utf-8")
        if raw:
            page.screenshot(path=str(DEBUG_DIR / f"{store}.png"), full_page=True)
            (DEBUG_DIR / f"{store}_parsed.json").write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
            (DEBUG_DIR / "SENSITIVE-README.txt").write_text(SENSITIVE_NOTE, "utf-8")
        print(f"Page: {urlparse(page.url).scheme}://{urlparse(page.url).netloc}{urlparse(page.url).path}")
        ctx.close()
    print(f"The reader found {summary['items']} items. Saved in {DEBUG_DIR}.")
    if raw:
        print("These files are exactly what the store showed you, including your purchases and account details. "
              "Only share them with someone you trust.")
    else:
        print("Email addresses, form values, tokens and signed links were removed, and there's no screenshot. "
              "If someone helping you needs the page exactly as it is, run again with --raw.")

def cmd_import(cfg: dict, args, batch: int = 20) -> int:
    """Import library pages saved from your own browser: files, and folders of them. Returns 1 when any page
    wasn't imported, so a script can tell."""
    trust = []
    for given in args.trust_shop or []:
        shop = clean_payhip_shop(given)
        if not shop:
            sys.exit(f"{given} isn't a Payhip shop's address. Use the shop's own address, such as myshop.store or "
                     "payhip.com/MyShop.")
        trust.append(shop)
    files = saved_pages_in(args.paths)
    if not files:
        sys.exit("There are no saved pages (.mhtml, .mht, .html or .htm) there.")
    shops_before, lib = payhip_shops(cfg), Library(LIBRARY_FILE)
    items_by_store: dict[str, int] = {}
    totals: dict[str, int] = {}
    problems, new_shops = [], {}
    receipts_added = 0
    for start in range(0, len(files), batch):   # a batch at a time, so a large folder isn't all in memory at once
        pages = []
        for f in files[start:start + batch]:
            try:
                pages.append((f.name, f.read_text("utf-8", errors="replace")))
            except OSError as e:
                problems.append(f"{f.name}: couldn't be opened ({e.strerror or e})")
        results = import_saved_pages(cfg, pages, args.store, trust, progress=lambda n, _total, name, done=start:
                                     print(f"Reading {name} ({done + n} of {len(files)})"))
        found: dict[str, list] = {}
        for r in results:
            if "items" in r:
                found.setdefault(r["store"], []).extend(r["items"])
                items_by_store[r["store"]] = items_by_store.get(r["store"], 0) + len(r["items"])
            elif "receipts" in r:   # a Gumroad receipt: kept, and read by Gumroad's refresh
                receipts_added += r["added"]
            elif "confirm_shop" in r:
                new_shops.setdefault(r["confirm_shop"], []).append(r["filename"])
            else:
                problems.append(f"{r['filename']}: {r['error']}")
        for store, items in found.items():
            totals[store] = lib.merge_store(store, items)
    if payhip_shops(cfg) != shops_before:
        save_config(cfg, args.config)
    if items_by_store:
        print("Imported " + ", ".join(f"{n} {STORES[s]['label']} {'item' if n == 1 else 'items'}" for s, n in items_by_store.items()) + ". "
              + "Your library now has " + ", ".join(f"{n} from {STORES[s]['label']}" for s, n in totals.items()) + ".")
    if receipts_added:
        print(f"Added {receipts_added} Gumroad {'receipt' if receipts_added == 1 else 'receipts'}. Read "
              f"{'it' if receipts_added == 1 else 'them'} with: refresh --store gumroad")
    for shop, names in new_shops.items():
        address = shop.split("://", 1)[1]
        problems.append(f"{', '.join(names)}: from the Payhip shop {address}, which isn't in your list. If it's the "
                        f"shop you bought from, import again with: --trust-shop {address}")
    if problems:
        print(f"{len(problems)} {'page wasn' if len(problems) == 1 else 'pages weren'}'t imported:")
        for line in problems:
            print(f"  - {line}")
    return 1 if problems else 0


def cmd_receipts(cfg: dict, args) -> int:
    """Gumroad receipts (receipts.py): list them, add View content links or receipt files, or remove one."""
    from . import receipts
    if args.action == "list":
        rows = receipts.listing()
        for r in rows:
            how = r["error"] or ("in your Gumroad library too" if r["in_library"] else r["creator"] if r["read"] else "")
            print(f"{r['ref']}  {r['name'] or 'Not read yet'}" + (f"  ({how})" if how else ""))
        print(f"{len(rows)} {'receipt' if len(rows) == 1 else 'receipts'}." if rows else
              "No Gumroad receipts yet. Add one with: receipts add <receipt.eml or View content link>")
        return 0
    if args.action == "remove":
        which = (args.what or [""])[0]
        gone = receipts.remove(cfg, which) if re.fullmatch(r"[0-9a-f]{12}|all", which) else None
        if gone is None:
            sys.exit("There's no such receipt. See them with: receipts list")
        Library(LIBRARY_FILE).forget_downloads("gumroad", set(gone["tokens"]), receipts.token_of)
        print("Removed." if which != "all" else "Removed every receipt.")
        return 0
    found, problems = [], []
    for given in args.what or []:
        path = Path(given)
        if path.is_file():
            try:
                got = receipts.find(path.name, path.read_text("utf-8", errors="replace"))
            except OSError as e:
                problems.append(f"{path.name}: couldn't be opened ({e.strerror or e})")
                continue
            if not got:
                problems.append(f"{path.name}: there's no Gumroad receipt in it")
            found += got
        else:
            got = receipts.find("", given)
            if not got:
                problems.append(f"{given[:80]}: not a file, nor a Gumroad View content link (gumroad.com/d/...)")
            found += got
    done = receipts.add(cfg, found) if found else {"added": 0, "already": 0, "emails_kept": True}
    print(f"Added {done['added']} Gumroad {'receipt' if done['added'] == 1 else 'receipts'}"
          + (f" ({done['already']} kept before)" if done["already"] else "") + ". Read them with: refresh --store gumroad")
    if not done["emails_kept"]:
        problems.append("this computer has no keyring to protect the receipts' emails, so they weren't kept")
    for line in problems:
        print(f"  - {line}")
    return 1 if problems else 0


def cmd_logout(cfg: dict, args) -> None:
    """Sign out of one store, or of every store, in Hoard."""
    with _playwright()() as p:
        log(sign_out(p, cfg, args.store))
    log("Hoard doesn't keep store passwords, so there's nothing else to remove.")


def main(argv=None) -> None:
    """Open Hoard, or run one command from the command line (for power users and computers without a desktop)."""
    ap = argparse.ArgumentParser(prog="hoard", description="Everything you've bought for VRChat, in one place. "
                                 "Run it without a command to open Hoard.")
    ap.add_argument("--version", action="version", version=f"Hoard {__version__}")
    ap.add_argument("--config", type=Path, default=CONFIG_FILE, help="settings file (default: in Hoard's app-data folder)")
    ap.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to also use Hoard from other devices on your network")
    ap.add_argument("--port", type=int, default=0, help="port for Hoard's page (default: any free port)")
    ap.add_argument("--tls-cert", help="with --host: your HTTPS certificate file (PEM)")
    ap.add_argument("--tls-key", help="with --host: the certificate's private key file (PEM)")
    ap.add_argument("--plain-http", action="store_true",
                    help="with --host: serve plain HTTP, only when the network is already encrypted (a VPN such as Tailscale)")
    ap.add_argument("--no-open", action="store_true", help="run Hoard as a server only, without opening it")
    ap.add_argument("--browser", action="store_true", help="open Hoard in your web browser instead of its own window")
    ap.add_argument("--shell", action="store_true", help=argparse.SUPPRESS)   # (its Tauri shell's window: hoard/shell.py)
    sub = ap.add_subparsers(dest="cmd", metavar="command")
    s = sub.add_parser("login", help="sign in to a store in a browser window (itch.io: with an API key)")
    s.add_argument("store", choices=list(STORES))
    s = sub.add_parser("logout", help="sign out of a store in Hoard, or of every store")
    s.add_argument("store", choices=[*STORES, "all"])
    s = sub.add_parser("refresh", help="read what you own from the stores")
    s.add_argument("--store", choices=list(STORES), action="append", help="repeat for several; default: all")
    s = sub.add_parser("import", help="add library pages you saved from your own browser (.mhtml or .html), or folders of them")
    s.add_argument("paths", type=Path, nargs="+", metavar="file-or-folder")
    s.add_argument("--store", choices=list(IMPORTABLE), help="only needed if the store can't be worked out")
    s.add_argument("--trust-shop", metavar="ADDRESS", action="append",
                   help="add the Payhip shop a page is from (its exact address); repeat for several")
    s = sub.add_parser("receipts", help="Gumroad purchases outside your Gumroad library, added by their receipts")
    s.add_argument("action", choices=["list", "add", "remove"])
    s.add_argument("what", nargs="*", metavar="file-link-or-ref",
                   help="add: receipt emails (.eml), saved pages or View content links; remove: a receipt's ref (from list), or all")
    s = sub.add_parser("sync", help="download everything new or changed")
    s.add_argument("--store", choices=[*DOWNLOADABLE, "all"], default="all")
    s.add_argument("--dry-run", action="store_true", help="list what would download, download nothing")
    s.add_argument("--only", help="only products whose name or creator contains this text")
    s.add_argument("--headed", action="store_true", help="show the browser while downloading from Booth or Jinxxy")
    sub.add_parser("tags", help="rebuild catalog.json and tags.json from what's downloaded")
    sub.add_parser("verify", help="check whether any data file was changed outside Hoard, and rebuild the catalog")
    s = sub.add_parser("debug", help="save a store's library page, for troubleshooting (scrubbed of personal details)")
    s.add_argument("store", choices=list(STORES))
    s.add_argument("--raw", action="store_true", help="save the page as it is, with a screenshot (contains your details)")
    sub.add_parser("self-test", help="check this copy of Hoard has everything it needs (used by the build)")
    sub.add_parser("install-browser", help="download Hoard's own browser (only needed without Microsoft Edge)")
    s = sub.add_parser("migrate", help="bring over the library list and downloads folder from Hoard 1.x")
    s.add_argument("folder", type=Path, help="the folder you ran Hoard 1.x from")
    s = sub.add_parser("probe", help="record what the Jinxxy site loads, for troubleshooting (scrubbed of personal details)")
    s.add_argument("store", choices=["jinxxy"])
    s.add_argument("--raw", action="store_true", help="save pages as they are, with screenshots (contains your details)")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    try:
        if args.cmd is None and (args.no_open or args.host not in ("127.0.0.1", "localhost", "::1") or args.port):
            # a server: for other devices, a fixed port, or no page (stop it with Ctrl+C where it runs)
            serve(cfg, args.host, args.port, not args.no_open, args.tls_cert, args.tls_key, args.plain_http,
                  config_path=args.config)
        elif args.cmd is None:
            sys.exit(run_app(cfg, args.config, browser=args.browser, shell=args.shell))   # the app, in its own window
        elif args.cmd == "self-test":
            sys.exit(self_test())
        elif args.cmd == "login":
            cmd_login(cfg, args.store)
        elif args.cmd == "logout":
            cmd_logout(cfg, args)
        elif args.cmd == "refresh":
            cmd_refresh(cfg, args.store or list(STORES))
        elif args.cmd == "import":
            sys.exit(cmd_import(cfg, args))
        elif args.cmd == "receipts":
            sys.exit(cmd_receipts(cfg, args))
        elif args.cmd == "sync":   # the files to leave out, as in the app (issue #225: Settings, and each product's)
            args.rules, args.remembered = file_rules(cfg), remembered_files(cfg)
            cmd_sync(cfg, args)
        elif args.cmd == "tags":
            build_catalog(cfg, root_dir(cfg))
        elif args.cmd == "verify":
            sys.exit(cmd_verify(cfg, root_dir(cfg)))
        elif args.cmd == "debug":
            cmd_debug_itch(cfg) if args.store == "itch" else cmd_debug(cfg, args.store, args.raw)
        elif args.cmd == "install-browser":
            install_browser(print)
            print("Hoard's browser is installed.")
        elif args.cmd == "migrate":
            cmd_migrate(cfg, args.folder, args.config)
        elif args.cmd == "probe":
            cmd_probe(cfg, args)
    except KeyboardInterrupt:
        log("\nStopped. Anything half-downloaded resumes next time.")
    except (ProfileBusy, SigninsUnprotected) as e:
        log(f"\n{e}")
    except PlaywrightMissing as e:
        sys.exit(str(e))


def cmd_migrate(cfg: dict, folder: Path, config_path: Path) -> None:
    """Bring over a Hoard 1.x library list and downloads folder."""
    print(migrate_from(cfg, folder, config_path))

