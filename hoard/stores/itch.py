"""Itch store adapter: library pages, downloads and recorded wishlist readers.

Shared browser, transport, limits and persistence remain in their common modules.
Compatibility service references preserve dependency overrides during extraction.
"""
from __future__ import annotations

import re
from .services import lib, dl, wish


# ----------------------------------------------------------------------------- itch.io
#
# itch.io is read through its API (itch.py), with an API key you create on itch.io: its website shows automated
# browsers a Cloudflare check they never get past. ITCH_JS reads a library page you saved yourself (itch.io/
# my-purchases), for importing: a card per project, each with a Download button leading to the project's download
# page (<creator>.itch.io/<project>/download/<key>). Items are known by itch.io's own project number either way.

lib_ITCH_LIBRARY = "https://itch.io/my-purchases"


lib_ITCH_JS = r"""
() => {
  const text = e => ((e && (e.innerText || e.textContent)) || '').replace(/\s+/g, ' ').trim();
  const LANDMARKS = 'nav, header, footer, aside, [role="navigation"], [role="banner"], [role="contentinfo"]';
  const NOT_CREATORS = new Set(['www', 'static', 'img', 'api', 'itch', 'assets', 'cdn']);
  // A creator's site (<creator>.itch.io), one of their projects (<creator>.itch.io/<project>), or a project's
  // download page (<creator>.itch.io/<project>/download/<key>)
  const parse = href => {
    let u; try { u = new URL(href, location.href); } catch (e) { return null; }
    const m = u.hostname.toLowerCase().replace(/\.$/, '').match(/^([a-z0-9][a-z0-9-]*)\.itch\.io$/);
    if (u.protocol !== 'https:' || !m || NOT_CREATORS.has(m[1])) return null;
    const segs = u.pathname.split('/').filter(Boolean);
    if (!segs.length) return { kind: 'creator', creator: m[1], url: u.origin };
    const id = m[1] + '/' + segs[0].toLowerCase(), url = u.origin + '/' + segs[0];
    if (segs.length === 1) return { kind: 'project', id, url };
    if (segs.length === 3 && segs[1] === 'download' && /^[A-Za-z0-9_-]{6,}$/.test(segs[2]))
      return { kind: 'download', id, url: url + '/download/' + segs[2] };
    return null;
  };
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    if (a.closest(LANDMARKS)) continue;
    const p = parse(a.getAttribute('href'));
    if (p && p.kind !== 'creator') { a.setAttribute('data-hoard-project', p.id); links.push({ a, ...p }); }
  }
  // Yours: every project with a download page here. On a page with no download pages at all (a layout Hoard
  // doesn't know), the project cards itch.io marks with an id, so the library still lists them.
  const withDownload = new Set(links.filter(l => l.kind === 'download').map(l => l.id));
  const owned = withDownload.size ? withDownload
    : new Set(links.filter(l => l.a.closest('[data-game_id]')).map(l => l.id));
  const cardOf = (a, id) => {   // the project's card: widen from its link while it's still about this one project
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const p = c.parentElement;
      if (p.matches('main, [role="main"]')) break;
      if ([...p.querySelectorAll('[data-hoard-project]')].some(x => x.getAttribute('data-hoard-project') !== id)) break;
      c = p;
    }
    return c;
  };
  const picture = c => {   // itch.io loads pictures as you scroll: the address waits in data-lazy_src until then
    const img = c.querySelector('a[data-hoard-project] img') || c.querySelector('img');
    const src = img ? (img.getAttribute('data-lazy_src') || img.getAttribute('data-src') || img.currentSrc || img.getAttribute('src') || '') : '';
    if (src && !src.startsWith('data:')) return src;
    const bg = c.querySelector('[data-background_image]');
    if (bg) return bg.getAttribute('data-background_image');
    const styled = [c, ...c.querySelectorAll('[style*="background-image"]')]
      .map(e => (e.getAttribute('style') || '').match(/url\(["']?([^"')]+)/)).find(Boolean);
    return styled ? styled[1] : '';
  };
  const cards = new Map();
  for (const l of links) {
    if (!owned.has(l.id)) continue;
    const old = cards.get(l.id);
    if (old) { if (l.kind === 'download' && !old.download_url) old.download_url = l.url; continue; }
    const c = cardOf(l.a, l.id);
    const mine = links.filter(x => x.id === l.id && c.contains(x.a));
    const img = c.querySelector('img');
    const name = mine.filter(x => x.kind === 'project').map(x => text(x.a)).find(Boolean)
      || text(c.querySelector('.game_title, .title')) || (img && img.alt) || l.id.split('/')[1];
    const who = l.id.split('/')[0];
    let creator = '', creatorUrl = 'https://' + who + '.itch.io';
    for (const a of c.querySelectorAll('a[href]')) {
      const p = parse(a.getAttribute('href'));
      if (p && p.kind === 'creator' && p.creator === who && text(a)) { creator = text(a); creatorUrl = p.url; break; }
    }
    creator = creator || text(c.querySelector('.game_author')).replace(/^by\s+/i, '') || who;
    const page = mine.find(x => x.kind === 'project'), dl = mine.find(x => x.kind === 'download');
    const cell = l.a.closest('[data-game_id]'), number = cell && cell.getAttribute('data-game_id');
    cards.set(l.id, { id: /^\d{1,20}$/.test(number || '') ? number : l.id, name, creator, creator_url: creatorUrl, thumbnail: picture(c),
                      url: page ? page.url : l.url.split('/download/')[0], download_url: dl ? dl.url : '' });
  }
  const next = [...document.querySelectorAll('a[rel="next"], a.next_page, .pager a, .pagination a')]
    .find(a => /next|›|»/i.test(text(a) + ' ' + (a.getAttribute('rel') || '') + ' ' + (a.className || '')));
  let nextUrl = null;
  if (next) {
    try { const u = new URL(next.getAttribute('href'), location.href); if (u.protocol === 'https:' && u.hostname === 'itch.io') nextUrl = u.href; } catch (e) {}
  }
  return { cards: [...cards.values()], next: nextUrl };
}
"""


def lib_fetch_itch(ctx, cfg, progress) -> list[dict]:
    """Everything you own on itch.io, through its API (no browser: ctx is unused)."""
    key = lib.vault.load_key(cfg, "itch")
    if not key:
        raise lib.NotLoggedIn("No itch.io API key yet")
    sess = lib.itch.session(key)
    try:
        keys = lib.itch.owned_keys(sess, float(cfg.get("request_delay", 1.0)), progress, cfg)
    finally:
        sess.close()
    items = []
    for k in keys:
        g = lib.itch.game_of(k)
        if g["id"]:
            items.append(lib.item("itch", g["id"], name=g["title"], creator=g["creator"], creator_url=g["creator_url"],
                              thumbnail=g["cover"], url=g["url"]))
    return items


def lib_itch_item(c: dict) -> dict:
    """Turn a card read from your itch.io library into a library item."""
    return lib.item("itch", c["id"], name=c["name"], creator=c["creator"], creator_url=c.get("creator_url"),
                thumbnail=c.get("thumbnail"), url=c.get("url"), download_url=c.get("download_url"))


def dl_sync_itch(cfg: dict, root: dl.Path, args, report: dl.Report) -> None:
    """Download everything new or changed in your itch.io library."""
    key = dl.vault.load_key(cfg, "itch")
    if not key:
        raise dl.NotLoggedIn("no itch.io API key yet")
    store_dir = root / dl.STORE_DIRS["itch"]
    man = dl.StoreRecords(cfg, root, dl.STORE_DIRS["itch"])
    delay = float(cfg.get("request_delay", 1.0))
    sess = dl.itch.session(key)
    try:
        keys = dl.itch.owned_keys(sess, delay)
        dl.log(f"itch.io: {len(keys)} {'item' if len(keys) == 1 else 'items'} in your library")
        for k in keys:
            g = dl.itch.game_of(k)
            name = dl.clean_text(g["title"], 300) or f"itch.io project {g['id']}"
            creator = dl.clean_text(g["creator"], 200) or "Unknown Creator"
            if not g["id"] or dl.skip_product(args, "itch", name, creator):
                continue
            if dl.removed_product("itch", name, report) or man.away(str(g["id"]), f"itch.io: {name}", report):
                continue
            dl.pause(delay)
            try:
                dl._itch_project(sess, k, g, name, creator, man, store_dir, cfg["itch"], args, report)
            except dl.NotLoggedIn:
                raise
            except Exception as e:
                report.failed_product("itch", name, f"itch.io: {creator} / {name} - {e}", str(e))
    finally:
        sess.headers.pop("Authorization", None)   # the key only lives for this sync
        sess.close()
        man.save_changes()   # every finished file recorded, however the sync ended


def dl__itch_project(sess, k: dict, g: dict, name: str, creator: str, man: dl.StoreRecords, store_dir: dl.Path, icfg: dict, args,
                  report: dl.Report) -> None:
    """Download each of one project's files that isn't here yet, or has changed."""
    files = dl.itch.uploads(sess, g["id"], k["id"])
    if not files:
        report.skipped.append(f"itch.io: {name} - no files to download")
        return
    rec = man.record(str(g["id"]), creator, name)
    is_new_asset = not rec["files"]
    rec.update(name=name, creator=creator, url=dl.store_link("itch", g["url"]), last_synced=dl.now_iso())
    folder = man.folder_of(rec)
    dl.log(f"\n[itch.io] {creator} / {name}")
    offered = {str(u["id"]) for u in files}
    got_any = False
    for u in files:
        fid = str(u["id"])
        label = dl.clean_text(u.get("display_name") or u.get("filename"), 200) or f"file {fid}"
        # what itch.io says about the file: when it changes, the creator updated it
        shown = str(u.get("md5_hash") or f"{u.get('filename')}|{u.get('size')}|{u.get('updated_at')}")
        old = rec["files"].get(fid)
        if old and old.get("shown", shown) == shown and dl.rel_to_path(folder, old["path"]).exists():
            continue
        if u.get("storage") == "external":
            report.skipped.append(f"itch.io: {name} / {label} - kept on another website, so not downloaded")
            continue
        if dl.itch.systems(u) and icfg.get("skip_game_builds", True):
            report.skipped.append(f"itch.io: {name} / {label} - a game build for {' and '.join(dl.itch.systems(u))}, so not "
                                  "downloaded (Settings, itch.io: Skip game builds)")
            continue
        if dl.left_out(args, report, "itch", name, label):
            continue
        if args.dry_run:
            dl.would_get(args, report, "itch", rec, name, creator, label, old is not None and old.get("shown", shown) != shown,
                      old is not None and old.get("shown", shown) == shown)
            continue
        fname = dl.distinct_name(dl.safe_name(u.get("filename") or label, 150), fid, rec, offered)
        target = folder / fname
        prev = next((f for f, v in rec["files"].items() if v.get("path") == fname and f != fid), None)
        is_update = old is not None or prev is not None or target.exists()
        def fetch(fid=fid, target=target, fname=fname, u=u):
            """Download one of the project's files from itch.io, deleting it when it doesn't match itch.io's
            checksum."""
            got = dl.egress.download(sess, dl.itch.download_address(fid, k["id"]), target, dl.itch.sites(), desc=fname,
                                 progress=dl.downloading(fname))
            expected = str(u.get("md5_hash") or "").lower()
            if expected and dl.md5_of(target) != expected:
                target.unlink(missing_ok=True)
                raise RuntimeError("the file didn't match itch.io's checksum, so it was deleted")
            return got
        try:
            size = dl.with_retries(report, fname, fetch)
        except dl.NotLoggedIn:
            raise
        except Exception as e:
            report.failed_product("itch", name, f"itch.io: {creator} / {name} / {fname} - {e}", f"{fname}: {e}")
            continue
        if prev:
            rec["files"].pop(prev, None)
        rec["files"][fid] = {"path": fname, "size": size, "label": label, "shown": shown, "downloaded_at": dl.now_iso()}
        dl.log(f"    {'updated' if is_update else 'saved'}: {fname}")
        (report.updated if is_update else report.new_files).append(f"itch.io: {creator} / {name} / {fname}")
        report.saved("itch", name, label)
        got_any = True
        man.checkpoint()
    if got_any and is_new_asset:
        report.new_assets.append(f"itch.io: {creator} / {name}")
    if rec["files"] and icfg.get("save_thumbnails", True) and not args.dry_run:
        dl.save_thumbnail(g["cover"], folder, "https://itch.io/")
    man.checkpoint()

LIBRARY_EXPORTS = {
    'ITCH_LIBRARY': lib_ITCH_LIBRARY,
    'ITCH_JS': lib_ITCH_JS,
    'fetch_itch': lib_fetch_itch,
    'itch_item': lib_itch_item,
}

DOWNLOADER_EXPORTS = {
    'sync_itch': dl_sync_itch,
    '_itch_project': dl__itch_project,
}

WISHLISTS_EXPORTS = {
}


from .base import Adapter

STORE = Adapter('itch', 'itch.io', 'https://itch.io/user/settings/api-keys', 'https://itch.io/', 5, wishlists=False)


def read_saved(page, cfg: dict, prep: dict) -> list[dict]:
    """Parse this store's saved library page in the caller's isolated browser."""
    items = [lib.itch_item(c) for c in page.evaluate(lib.ITCH_JS)["cards"]]
    return items


def read_tags(got) -> list:
    """Read the raw creator tags; the shared normalizer bounds and cleans them."""
    import json
    import html as html_text
    if not isinstance(got, str):
        return []
    m = re.search(r"<td>Tags</td>\s*<td>(.*?)</td>", got, re.S)
    raw = [html_text.unescape(x) for x in re.findall(r"<a[^>]*>([^<]{1,80})</a>", m.group(1))] if m else []
    return raw


# itch.io API: its key only goes to api.itch.io through the shared egress boundary.

import re
import uuid
from urllib.parse import urlencode, urlparse

import requests

from .. import __version__, egress
from ..common import QUICK_ITEMS, NotLoggedIn, pause, quick_done

API = "https://api.itch.io"
KEYS_PAGE = "https://itch.io/user/settings/api-keys"   # where you make one
SYSTEMS = (("p_windows", "Windows"), ("p_osx", "macOS"), ("p_linux", "Linux"), ("p_android", "Android"))


class KeyRefused(NotLoggedIn):
    """itch.io didn't accept the API key (mistyped, or deleted on itch.io)."""


def sites() -> list[str]:
    """The only host that ever gets the key."""
    return [urlparse(API).hostname]


def session(key: str) -> requests.Session:
    """A session that sends the key to api.itch.io, and only there (see egress)."""
    s = egress.session(f"Hoard/{__version__}")
    s.headers.update({"Authorization": f"Bearer {key}", "Accept": "application/json"})
    return s


def _refuses_api_key(text: str) -> bool:
    """Does an error itch.io gave turn away the API key itself? Not one project's download key (revoked, say), which
    only means that project can't be downloaded."""
    t = text.lower()
    if "download key" in t or "download_key" in t:
        return False
    return bool(re.search(r"\b(api[ _-]?key|invalid key|authenticat\w*|unauthori[sz]ed)\b", t))


def call(sess: requests.Session, path: str, **params) -> dict:
    """One API request. Raises KeyRefused when itch.io turns the key away."""
    r = egress.get(sess, API + path, sites(), params=params or None, timeout=60)
    if r.status_code in (401, 403):
        raise KeyRefused("itch.io didn't accept the API key")
    r.raise_for_status()
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("itch.io's answer wasn't the data Hoard asked for") from None
    if not isinstance(data, dict):
        raise RuntimeError("itch.io's answer wasn't the data Hoard asked for")
    errors = data.get("errors")
    if errors:
        text = "; ".join(str(e) for e in errors)[:300] if isinstance(errors, list) else str(errors)[:300]
        if _refuses_api_key(text):
            raise KeyRefused(f"itch.io didn't accept the API key ({text})")
        raise RuntimeError(f"itch.io said: {text}")
    return data


def profile(sess: requests.Session) -> dict:
    """The account the key belongs to."""
    user = call(sess, "/profile").get("user")
    return user if isinstance(user, dict) else {}


def owned_keys(sess: requests.Session, delay: float = 0.0, progress=lambda m: None, cfg: dict | None = None) -> list[dict]:
    """Everything you own on itch.io, bought or claimed: one download key per project. A quick refresh's cfg (issue
    #300): only the first pages, or the first products."""
    found: dict = {}
    quick = bool((cfg or {}).get("_quick"))
    for page in range(1, 2000):
        data = call(sess, "/profile/owned-keys", page=page)
        keys = [k for k in (data.get("owned_keys") or []) if isinstance(k, dict) and isinstance(k.get("game"), dict)]
        new = [k for k in keys if k.get("id") not in found][:max(0, QUICK_ITEMS - len(found)) if quick else None]
        for k in new:
            found[k.get("id")] = k
        progress(f"Library, {len(found)} items")
        try:
            per_page = int(data.get("per_page") or 50)
        except (TypeError, ValueError):
            per_page = 50
        if not new or len(data.get("owned_keys") or []) < per_page or quick_done(cfg or {}, page, len(found)):
            break
        pause(delay)
    return list(found.values())


def game_of(key: dict) -> dict:
    """The project a download key is for, with its creator."""
    game = key.get("game") if isinstance(key.get("game"), dict) else {}
    user = game.get("user") if isinstance(game.get("user"), dict) else {}
    return {"id": game.get("id") or key.get("game_id"), "title": game.get("title"), "url": game.get("url"),
            "cover": game.get("still_cover_url") or game.get("cover_url"),
            "creator": user.get("display_name") or user.get("username"), "creator_url": user.get("url")}


def uploads(sess: requests.Session, game_id, key_id) -> list[dict]:
    """A project's files, as your download key opens them."""
    data = call(sess, f"/games/{int(game_id)}/uploads", download_key_id=int(key_id))
    return [u for u in (data.get("uploads") or []) if isinstance(u, dict) and u.get("id")]


def systems(upload: dict) -> list[str]:
    """The operating systems a file is marked for, as a game build (asset files hardly ever are)."""
    traits = set(upload.get("traits") or []) if isinstance(upload.get("traits"), list) else set()
    return [name for flag, name in SYSTEMS if flag in traits or upload.get(flag) is True]


def download_address(upload_id, key_id) -> str:
    """Where a file downloads from: api.itch.io, which redirects to the file itself."""
    return f"{API}/uploads/{int(upload_id)}/download?" + urlencode({"download_key_id": int(key_id), "uuid": str(uuid.uuid4())})
