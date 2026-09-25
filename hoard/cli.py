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
from .config import NewShop, clean_payhip_shop, load_config, payhip_shops, root_dir, save_config
from .downloader import build_catalog, cmd_probe, cmd_sync, cmd_verify
from .jobs import Jobs
from .library import BOOTH_JS, GR_LIBRARY, IMPORTABLE, JX_CARDS_JS, JX_INVENTORY, Library, PAYHIP_SHOP_JS, STORES, import_saved_page, open_sign_in_pages
from .paths import CONFIG_FILE, DEBUG_DIR, LIBRARY_FILE

from .safety import scrub
from .app import run_app, self_test
from .server import serve
from .setup import install_browser, migrate_from


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


SENSITIVE_NOTE = ("These files were saved with --raw: they're the pages exactly as your store showed them, with your "
                  "purchases, account name or email address, and possibly signed download links or license keys. "
                  "Only share them with someone you trust, and delete them when you're done.\n")


def reader_summary(parsed) -> dict:
    """What the reader found, without the purchases themselves: how many items, and how often each field was filled."""
    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("cards") or parsed.get("items") or []
    else:
        items = []
    fields: dict = {}
    for item in items:
        for k, v in (item.items() if isinstance(item, dict) else ()):
            fields[k] = fields.get(k, 0) + (1 if v not in (None, "", [], {}) else 0)
    files = sum(len(i.get("files") or []) for i in items if isinstance(i, dict))
    return {"items": len(items), "fields_filled": fields, **({"files": files} if files else {})}


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
        shops = payhip_shops(cfg)
        url = {"booth": "https://accounts.booth.pm/library", "gumroad": GR_LIBRARY, "jinxxy": JX_INVENTORY,
               "payhip": (shops[0] + "/b-account") if shops else "https://payhip.com/"}[store]
        page.goto(url, wait_until="domcontentloaded")
        settle(page, 2000)
        page.mouse.wheel(0, 4000)
        page.wait_for_timeout(1500)
        content = page.content()
        (DEBUG_DIR / f"{store}.html").write_text(content if raw else scrub(content), "utf-8")
        links = sorted({urlparse(h).path for h in page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")})
        (DEBUG_DIR / f"{store}_links.txt").write_text("\n".join(links), "utf-8")
        js = {"booth": BOOTH_JS, "payhip": PAYHIP_SHOP_JS}.get(store)
        if js:
            parsed = page.evaluate(js)
        elif store == "jinxxy":
            parsed = page.evaluate(JX_CARDS_JS, cfg["jinxxy"]["item_link_pattern"])
        else:
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
    s.add_argument("--trust-shop", metavar="ADDRESS", help="add the Payhip shop the page is from (its exact address)")
    s = sub.add_parser("sync", help="download everything new or changed")
    s.add_argument("--store", choices=[*STORES, "all"], default="all")
    s.add_argument("--dry-run", action="store_true", help="list what would download, download nothing")
    s.add_argument("--only", help="only products whose name or creator contains this text")
    s.add_argument("--headed", action="store_true", help="show the browser while downloading from Booth or Jinxxy")
    s.add_argument("--payhip-page", metavar="FILE", help="read Payhip products from a library page you saved")
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
            sys.exit(run_app(cfg, args.config, browser=args.browser))   # the app, in its own window
        elif args.cmd == "self-test":
            sys.exit(self_test())
        elif args.cmd == "login":
            cmd_login(cfg, args.store)
        elif args.cmd == "logout":
            cmd_logout(cfg, args)
        elif args.cmd == "refresh":
            cmd_refresh(cfg, args.store or list(STORES))
        elif args.cmd == "import":
            try:
                store, items = import_saved_page(cfg, args.store, args.file.name, args.file.read_text("utf-8", errors="replace"),
                                                 trust_shop=clean_payhip_shop(args.trust_shop) if args.trust_shop else None)
            except NewShop as e:
                sys.exit(f"{e}\nTo add it, run the import again with: --trust-shop {e.shop.split('://', 1)[1]}")
            if store == "payhip" and args.trust_shop:
                save_config(cfg, args.config)
            total = Library(LIBRARY_FILE).merge_store(store, items)
            print(f"Imported {len(items)} {STORES[store]['label']} items ({total} in the library for that store).")
        elif args.cmd == "sync":
            cmd_sync(cfg, args)
        elif args.cmd == "tags":
            build_catalog(cfg, root_dir(cfg))
        elif args.cmd == "verify":
            sys.exit(cmd_verify(cfg, root_dir(cfg)))
        elif args.cmd == "debug":
            cmd_debug(cfg, args.store, args.raw)
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


def cmd_migrate(cfg: dict, folder: Path, config_path: Path) -> None:
    """Bring over a Hoard 1.x library list and downloads folder."""
    print(migrate_from(cfg, folder, config_path))

