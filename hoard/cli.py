"""Hoard's command line: `python -m hoard` opens Hoard; commands such as `sync` or `verify` run on their own."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from . import __version__
from .browser import ProfileBusy, SigninsUnprotected, _playwright, check_saved_signin, launch, profile_dir, settle, sign_out, signin_protection
from .common import log
from .config import load_config, root_dir, save_config
from .downloader import build_catalog, cmd_probe, cmd_sync, cmd_verify
from .jobs import Jobs
from .library import BOOTH_JS, GR_LIBRARY, IMPORTABLE, JX_CARDS_JS, JX_INVENTORY, Library, PAYHIP_CARDS_JS, STORES, import_saved_page, open_sign_in_pages, payhip_library_url
from .paths import CONFIG_FILE, DEBUG_DIR, LIBRARY_FILE
from .safety import read_json_file
from .server import serve


# ----------------------------------------------------------------------------- CLI

def cmd_login(cfg, store):
    """Open Hoard's browser at a store's sign-in page and wait while you sign in."""
    with _playwright()() as p:
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
        jobs.state.update(kw)
        if jobs.state["message"] != last[0]:
            last[0] = jobs.state["message"]
            print(" ", last[0])
    jobs._set = show
    jobs._refresh(stores)
    for s in stores:
        info = lib.data["stores"].get(s, {})
        print(f"{STORES[s]['label']:<8} {info.get('error') or str(info.get('count', 0)) + ' items'}")


def cmd_debug(cfg, store):
    """Save what a store's library page looks like and what the reader found, for troubleshooting."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    with _playwright()() as p:
        ctx = launch(p, cfg, False, store)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if store == "payhip":
            try:
                url = payhip_library_url(page, cfg)
            except Exception as e:
                print(f"Finding the library failed: {e}")
                url = "https://payhip.com/"
        else:
            url = {"booth": "https://accounts.booth.pm/library", "gumroad": GR_LIBRARY, "jinxxy": JX_INVENTORY}[store]
        page.goto(url, wait_until="domcontentloaded")
        settle(page, 2000)
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
        (DEBUG_DIR / f"{store}.html").write_text(page.content(), "utf-8")
        page.screenshot(path=str(DEBUG_DIR / f"{store}.png"), full_page=True)
        links = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (DEBUG_DIR / f"{store}_links.txt").write_text("\n".join(links), "utf-8")
        js = {"booth": BOOTH_JS, "payhip": PAYHIP_CARDS_JS}.get(store)
        if js:
            parsed = page.evaluate(js)
        elif store == "jinxxy":
            parsed = page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"])
        else:
            parsed = "(Gumroad is read from page data, not the layout)"
        (DEBUG_DIR / f"{store}_parsed.json").write_text(json.dumps(parsed, indent=2, ensure_ascii=False), "utf-8")
        print(f"Page: {page.url}")
        ctx.close()
    print(f"Saved {store}.html, {store}.png, {store}_links.txt and {store}_parsed.json in {DEBUG_DIR}.")
    print("They can contain your name and purchases; skim them before sharing.")


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
    ap.add_argument("--no-open", action="store_true", help="start Hoard without opening its page")
    sub = ap.add_subparsers(dest="cmd", metavar="command")
    s = sub.add_parser("login", help="sign in to a store in a browser window")
    s.add_argument("store", choices=list(STORES))
    s = sub.add_parser("logout", help="sign out of a store in Hoard, or of every store")
    s.add_argument("store", choices=[*STORES, "all"])
    s = sub.add_parser("refresh", help="read what you own from the stores")
    s.add_argument("--store", choices=list(STORES), action="append", help="repeat for several; default: all")
    s = sub.add_parser("import", help="add a library page you saved from your own browser (.mhtml or .html)")
    s.add_argument("file", type=Path)
    s.add_argument("--store", choices=list(IMPORTABLE), help="only needed if the store can't be worked out")
    s = sub.add_parser("sync", help="download everything new or changed")
    s.add_argument("--store", choices=[*STORES, "all"], default="all")
    s.add_argument("--dry-run", action="store_true", help="list what would download, download nothing")
    s.add_argument("--only", help="only products whose name or creator contains this text")
    s.add_argument("--headed", action="store_true", help="show the browser while downloading from Booth or Jinxxy")
    s.add_argument("--payhip-page", metavar="FILE", help="read Payhip products from a library page you saved")
    sub.add_parser("tags", help="rebuild catalog.json and tags.json from what's downloaded")
    sub.add_parser("verify", help="check whether any data file was changed outside Hoard, and rebuild the catalog")
    s = sub.add_parser("debug", help="save a store's library page, for troubleshooting")
    s.add_argument("store", choices=list(STORES))
    s = sub.add_parser("migrate", help="bring over the library list and downloads folder from Hoard 1.x")
    s.add_argument("folder", type=Path, help="the folder you ran Hoard 1.x from")
    s = sub.add_parser("probe", help="record what the Jinxxy site loads, for troubleshooting")
    s.add_argument("store", choices=["jinxxy"])
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    try:
        if args.cmd is None:
            serve(cfg, args.host, args.port, not args.no_open, args.tls_cert, args.tls_key, args.plain_http,
                  config_path=args.config)
        elif args.cmd == "login":
            cmd_login(cfg, args.store)
        elif args.cmd == "logout":
            cmd_logout(cfg, args)
        elif args.cmd == "refresh":
            cmd_refresh(cfg, args.store or list(STORES))
        elif args.cmd == "import":
            store, items = import_saved_page(cfg, args.store, args.file.name, args.file.read_text("utf-8", errors="replace"))
            total = Library(LIBRARY_FILE).merge_store(store, items)
            print(f"Imported {len(items)} {STORES[store]['label']} items ({total} in the library for that store).")
        elif args.cmd == "sync":
            cmd_sync(cfg, args)
        elif args.cmd == "tags":
            build_catalog(cfg, root_dir(cfg))
        elif args.cmd == "verify":
            sys.exit(cmd_verify(cfg, root_dir(cfg)))
        elif args.cmd == "debug":
            cmd_debug(cfg, args.store)
        elif args.cmd == "migrate":
            cmd_migrate(cfg, args.folder, args.config)
        elif args.cmd == "probe":
            cmd_probe(cfg, args)
    except KeyboardInterrupt:
        log("\nStopped. Anything half-downloaded resumes next time.")
    except (ProfileBusy, SigninsUnprotected) as e:
        log(f"\n{e}")


def cmd_migrate(cfg: dict, folder: Path, config_path: Path) -> None:
    """Bring a Hoard 1.x setup across: its library list and its downloads folder. (Sign-ins and tags already
    live in Hoard's app-data folder, so they carry over by themselves.)"""
    folder = folder.expanduser().resolve()
    places = [folder, folder / "Hoard", folder / "HoardDownloader", folder.parent / "Hoard", folder.parent / "HoardDownloader"]
    done = []
    old_list = next((p / "library.json" for p in places if (p / "library.json").is_file()), None)
    if old_list:
        new = Library(LIBRARY_FILE)
        if new.data["items"]:
            print(f"Hoard already has a library list here ({len(new.data['items'])} items), so {old_list} wasn't copied.")
        else:
            new.data = Library(old_list).data   # checked and cleaned as it's read
            new.save()
            done.append(f"your library list ({len(new.data['items'])} items)")
    old_cfg = next((p / "config.json" for p in places if (p / "asset_dl.py").is_file() and (p / "config.json").is_file()), None)
    if old_cfg:
        old = read_json_file(old_cfg, 1024 * 1024)
        value = str(old.get("root") or "downloads") if isinstance(old, dict) else "downloads"
        root = Path(value).expanduser()
        root = root if root.is_absolute() else (old_cfg.parent / root).resolve()
        if root.is_dir():
            cfg["root"] = str(root)
            for store in STORES:
                if isinstance(old.get(store), dict):
                    cfg[store].update({k: v for k, v in old[store].items() if k in ("enabled", "include_gifts", "include_archived")
                                       and isinstance(v, bool)})
            save_config(cfg, config_path)
            done.append(f"your downloads folder ({root})")
        else:
            print(f"The downloads folder in {old_cfg} ({root}) doesn't exist, so it wasn't used.")
    if done:
        print("Brought over " + " and ".join(done) + ". Your sign-ins and tags were already shared, so everything's here.")
    else:
        print(f"Found no Hoard 1.x library list or downloader settings in or next to {folder}.")

