"""Booth store adapter: library pages, downloads and recorded wishlist readers.

Shared browser, transport, limits and persistence remain in their common modules.
Compatibility service references preserve dependency overrides during extraction.
"""
from __future__ import annotations

import re
from .services import lib, dl, wish


# ----------------------------------------------------------------------------- Booth

lib_BOOTH_JS = r"""
() => {
  const idOf = h => { const m = (h || '').match(/\/items\/(\d+)/); return m ? m[1] : null; };
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const out = new Map();
  for (const a of document.querySelectorAll('a[href*="/items/"]')) {
    const id = idOf(a.href);
    if (!id || out.has(id)) continue;
    let c = a;
    while (c.parentElement && c.parentElement !== document.body) {
      const ids = new Set([...c.parentElement.querySelectorAll('a[href*="/items/"]')].map(x => idOf(x.href)).filter(Boolean));
      if (ids.size > 1) break;
      c = c.parentElement;
    }
    const name = [...c.querySelectorAll('a[href*="/items/"]')].map(text).sort((x, y) => y.length - x.length)[0]
      || text(c.querySelector('.font-bold'));
    let creator = '', creatorUrl = '';
    for (const s of c.querySelectorAll('a[href]')) {
      let u; try { u = new URL(s.href); } catch (e) { continue; }
      if (/\.booth\.pm$/.test(u.hostname) && !['accounts.booth.pm', 'www.booth.pm'].includes(u.hostname)
          && !/\/items\//.test(u.pathname) && text(s)) { creator = text(s); creatorUrl = u.origin + '/'; break; }
    }
    if (!creator) creator = text(c.querySelector('.text-text-gray600'));
    const img = c.querySelector('a[href*="/items/"] img') || c.querySelector('img');
    const thumb = img ? (img.getAttribute('data-original') || img.getAttribute('data-src') || img.currentSrc || img.src || '') : '';
    // Files. Booth now draws each file's buttons from placeholders that carry the address in data-href
    // (2026); older pages used plain links. "Download" is the file itself; "Open in Browser" (?browse=1) and the
    // Booth Library Manager links (/deeplink) are other ways to the same file, so they're skipped.
    const FILE_SEL = '[data-href*="/downloadables/"], a[href*="/downloadables/"]';
    const addr = el => el.getAttribute('data-href') || el.getAttribute('href') || '';
    // (however Booth names its buttons, which it has changed before: only the other routes are left out, issue #267)
    const fileId = el => {
      const h = addr(el), m = h.match(/\/downloadables\/(\d+)(?:[?#]|$)/), t = (el.getAttribute('data-test') || '').toLowerCase();
      return m && !/[?&]browse=/.test(h) && !/brows|other|deeplink|manager/.test(t) ? m[1] : null;
    };
    const seen = new Set(), files = [];
    for (const d of c.querySelectorAll(FILE_SEL)) {
      const fid = fileId(d);
      if (!fid || seen.has(fid)) continue;
      seen.add(fid);
      let r = d;   // the file's row: widen from its button while the row is still about this one file
      while (r.parentElement && r.parentElement !== c) {
        const p = r.parentElement;
        const ids = new Set([...p.querySelectorAll(FILE_SEL)].map(x => (addr(x).match(/\/downloadables\/(\d+)/) || [])[1]).filter(Boolean));
        if (ids.size > 1 || p.querySelector('a[href*="/items/"], img')) break;
        r = p;
      }
      const row = r.cloneNode(true);
      row.querySelectorAll('.js-download-button, button, [data-href], a[href*="/downloadables/"]').forEach(x => x.remove());
      const name = (row.textContent || '').replace(/\s+/g, ' ').replace(/ダウンロード|Download|Open in Browser|Other Downloads/gi, '').trim();
      files.push({ name: name || 'File', url: new URL(addr(d), location.href).href });
    }
    const order = c.querySelector('a[href*="/orders/"]');
    out.set(id, { id, name, creator, creator_url: creatorUrl, thumbnail: thumb, url: a.href,
                  order_url: order ? order.href : '', files });
  }
  return [...out.values()];
}
"""


def lib_booth_item(b: dict, gift: bool, library_url: str) -> dict:
    """Turn a card read from Booth's library page into a library item."""
    return lib.item("booth", b["id"], name=b["name"], creator=b["creator"], creator_url=b["creator_url"],
                thumbnail=b["thumbnail"], url=b["url"], download_url=b["order_url"] or library_url,
                files=b["files"], gift=gift)


def lib_booth_cards(page, cfg: dict, delay: float, progress=lambda m: None) -> list[tuple[dict, bool, str]]:
    """Every card in your Booth library, and your gifts and free downloads if you keep those, page by page: each as
    (the card BOOTH_JS read, whether it's a gift, the library page it's on). Reading the library for the list and
    for downloading both use this. Raises NotLoggedIn when Booth sends the browser to sign in."""
    cards: dict[str, tuple[dict, bool, str]] = {}
    sources = [("", False)] + ([("/gifts", True)] if cfg["booth"].get("include_gifts", True) else []) \
        + ([("/free_downloads", False)] if cfg["booth"].get("include_free", True) else [])
    quick = bool(cfg.get("_quick"))   # (a quick refresh, issue #300: the start of each)
    for path, gift in sources:
        base, here = f"https://accounts.booth.pm/library{path}", 0
        for page_no in range(1, 500):
            lib.goto(page, f"{base}?page={page_no}")
            page.wait_for_timeout(400)
            u = lib.urlparse(page.url)   # a sign-in page means the session ended, whatever its status code
            if u.hostname != "accounts.booth.pm" or "sign_in" in u.path or lib.has_password_field(page):
                raise lib.NotLoggedIn("Not signed in to Booth")
            if not u.path.startswith("/library"):
                break
            new = 0
            for b in page.evaluate(lib.BOOTH_JS):
                if b["id"] not in cards and not (quick and here >= lib.QUICK_ITEMS):
                    cards[b["id"]] = (b, gift, base)
                    new += 1
                    here += 1
            progress(f"{'Gifts' if gift else 'Library'} page {page_no}, {len(cards)} items")
            if not new or lib.quick_done(cfg, page_no, here):   # past the last page (or, quickly, far enough)
                break
            lib.pause(delay)
    return list(cards.values())


def lib_fetch_booth(ctx, cfg, progress) -> list[dict]:
    """Every item in your Booth library and gifts, page by page."""
    page = ctx.new_page()
    try:
        return [lib.booth_item(b, gift, base) for b, gift, base in lib.booth_cards(page, cfg, float(cfg.get("request_delay", 0.8)), progress)]
    finally:
        page.close()


# ----------------------------------------------------------------------------- Booth
#
# Booth lists every purchase and gift at accounts.booth.pm/library, with a link for each file.
# The list is read in the browser with your saved login; the files then come straight from
# Booth over HTTP, so big downloads resume if they're interrupted.

dl_BOOTH_LIBRARY = "https://accounts.booth.pm/library"


def dl_booth_library(page, cfg: dict) -> list[dict]:
    """Every purchase (and, if enabled, gift) in your Booth library, one dict per item (as the library reads it)."""
    return [{**b, "gift": gift} for b, gift, _base in dl.booth_cards(page, cfg, float(cfg.get("request_delay", 1.0)))]


def dl_booth_file_location(sess: dl.requests.Session, url: str) -> str:
    """Booth answers a file link with a redirect to a short-lived download address."""
    r = dl.egress.get(sess, url, dl.STORE_SITES["booth"], follow=False, timeout=60, headers={"Referer": dl.BOOTH_LIBRARY})
    if r.status_code in (301, 302, 303, 307, 308):
        loc = dl.urljoin(url, r.headers.get("Location", ""))
        if "sign_in" in loc or dl.urlparse(loc).path.startswith("/users"):
            raise dl.NotLoggedIn("Booth session expired")
        return loc
    if r.ok and not r.headers.get("Content-Type", "").startswith("text/html"):
        return url
    if r.ok:
        raise dl.NotLoggedIn("Booth sent a web page instead of the file; the session may have expired")
    raise RuntimeError(f"booth.pm answered HTTP {r.status_code} instead of sending the file")


def dl_booth_filename(label: str, location: str, fallback: str) -> str:
    """A safe local name for a Booth file: the name Booth shows, or the one in its download address."""
    name = (label or "").strip()
    if not dl.re.search(r"\.[A-Za-z0-9]{1,12}$", name):  # Booth shows the file name; if not, use the download address
        name = dl.unquote(dl.Path(dl.urlparse(location).path).name) or name or fallback
    return dl.safe_name(name, 150)


dl_BOOTH_ITEM_FILES_JS = r"""
() => {
  // A Booth item's own page (booth.pm/.../items/<id>): each file's download link, booth.pm/downloadables/<id>.
  // Items in the library's "free downloads" list only have their files here.
  const text = e => ((e && e.innerText) || '').replace(/\s+/g, ' ').trim();
  const fileName = /[^\s\/\\]+\.[A-Za-z][A-Za-z0-9]{0,11}(?=\s|$)/;   // (an extension starts with a letter: not "Ver1.2")
  const LINKS = 'a[href*="/downloadables/"], [data-href*="/downloadables/"]';
  const idOf = e => { const m = (e.getAttribute('href') || e.getAttribute('data-href') || '').match(/\/downloadables\/(\d+)/); return m && m[1]; };
  const out = new Map();
  for (const e of document.querySelectorAll(LINKS)) {
    let u; try { u = new URL(e.getAttribute('href') || e.getAttribute('data-href') || '', location.href); } catch (x) { continue; }
    const m = u.pathname.match(/^\/downloadables\/(\d+)\/?$/);   // not a deeplink for Booth's app, not "open in browser"
    if (!m || u.searchParams.has('browse') || !/(^|\.)booth\.pm$/.test(u.hostname) || out.has(m[1])) continue;
    // the file's name: in its own row (widened from the link while the row is about this file only)
    let row = e;
    while (row.parentElement && row.parentElement !== document.body
           && [...row.parentElement.querySelectorAll(LINKS)].every(x => idOf(x) === m[1])) row = row.parentElement;
    const f = text(row).match(fileName);
    const name = f ? f[0] : '';
    out.set(m[1], { name, url: 'https://booth.pm/downloadables/' + m[1] });
  }
  return [...out.values()];
}
"""


def dl_booth_item_files(page, url: str) -> list[dict]:
    """The files on a Booth item's own page (a free download), or on a purchase's order page, for an item the library
    lists without them."""
    dl.pace.before(url)
    page.goto(url, wait_until="domcontentloaded")
    dl.settle(page)
    u = dl.urlparse(page.url)   # (an item page is public: only a move to the sign-in page means the session ended)
    if "sign_in" in u.path or (u.hostname == "accounts.booth.pm" and page.locator("input[type=password]").count()):
        raise dl.NotLoggedIn("Not signed in to Booth")
    return [f for f in page.evaluate(dl.BOOTH_ITEM_FILES_JS) if dl.store_url(f.get("url"), ["booth.pm"])]


dl_BOOTH_CLICK_JS = """url => { const a = document.createElement('a'); a.href = url; a.rel = 'noreferrer';
  document.body.appendChild(a); a.click(); a.remove(); }"""


def dl_booth_browser_download(page, url: str, folder: dl.Path, label: str, fid: str, timeout_s: float,
                           name_for=lambda n: n) -> tuple[str, int]:
    """Download one Booth file through the signed-in browser, just as clicking its download button would.

    Returns (file name, size). Raises NotLoggedIn when Booth answers with its sign-in page instead.
    """
    started: list = []

    def on_download(download):
        """Note the download the click started."""
        started.append(download)

    page.on("download", on_download)
    try:
        page.evaluate(dl.BOOTH_CLICK_JS, url)
        deadline = dl.time.time() + timeout_s
        while not started and dl.time.time() < deadline:
            page.wait_for_timeout(250)
            if "sign_in" in page.url or dl.urlparse(page.url).path.startswith("/users"):
                raise dl.NotLoggedIn("Booth session expired")
    finally:
        page.remove_listener("download", on_download)
    if not started:
        raise RuntimeError("Booth didn't start the download")
    download = started[0]
    fname = name_for(dl.booth_filename(label, download.suggested_filename or download.url, f"file-{fid}"))
    dl.wait_for_browser_download(download, fname)
    target = dl.save_browser_download(download, folder, fname)
    return fname, target.stat().st_size


def dl_booth_fetch(page, sess, f: dict, folder: dl.Path, fid: str, route: dict, timeout_s: float,
                name_for=lambda n: n) -> tuple[str, int]:
    """Download one Booth file. The direct route is fastest and resumes where it stopped; if Booth turns it away
    (sites often screen out anything that isn't a real browser), that file goes through the browser, and once it has
    turned it away twice running, the rest of the run does. A dropped connection isn't Booth turning it away: it's
    raised to be tried again (with_retries), so the file resumes where it stopped. Signed out shows in the browser."""
    if route["direct"]:
        try:
            loc = dl.booth_file_location(sess, f["url"])
            fname = name_for(dl.booth_filename(f["name"], loc, f"file-{fid}"))
            got = dl.egress.download(sess, loc, folder / fname, dl.STORE_SITES["booth"], desc=fname, progress=dl.downloading(fname))
            route["refused"] = 0
            return fname, got
        except (dl.requests.ConnectionError, dl.requests.Timeout):
            raise
        except (dl.NotLoggedIn, RuntimeError, dl.requests.RequestException, dl.egress.UnsafeRequest) as e:
            route["refused"] = route.get("refused", 0) + 1
            if route["refused"] >= 2:
                route["direct"] = False
                dl.log(f"    Booth turned the direct download away again ({e}), so Hoard downloads through the browser from now on.")
            else:
                dl.log(f"    Booth turned the direct download away ({e}), so Hoard downloads this file through the browser.")
    return dl.booth_browser_download(page, f["url"], folder, f["name"], fid, timeout_s, name_for)


def dl_sync_booth(cfg: dict, root: dl.Path, args, report: dl.Report) -> None:
    """Download everything new or changed in your Booth library and gifts."""
    bcfg = cfg["booth"]
    man = dl.StoreRecords(cfg, root, "Booth")
    delay = float(cfg.get("request_delay", 1.0))
    timeout_s = float(bcfg.get("download_start_timeout", 90))
    route = {"direct": True}
    with dl._playwright()() as p:
        ctx = dl.launch_context(p, cfg, not args.headed, "booth")
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            items = dl.booth_library(page, cfg)
            sess = dl.session_from_context(ctx, "booth.pm")
            dl.log(f"Booth: {len(items)} items in your library")
            try:
                for n, b in enumerate(items, 1):
                    dl.tick(f"Booth: item {n} of {len(items)}")   # Stop is noticed here, even when items fail fast
                    name = (b["name"] or f"Booth item {b['id']}").strip()
                    creator = (b["creator"] or "Unknown Creator").strip()
                    if dl.skip_product(args, "booth", name, creator):
                        continue
                    if dl.removed_product("booth", name, report) or man.away(b["id"], f"Booth: {name}", report):
                        continue
                    rec = man.record(b["id"], creator, name)
                    is_new_asset = not rec["files"]
                    rec.update(name=name, creator=creator, url=b["url"], gift=b["gift"] or None, last_synced=dl.now_iso())
                    folder = man.folder_of(rec)
                    dl.log(f"\n[Booth] {creator} / {name}")
                    if not b["files"] and (not b.get("order_url") or not rec["files"] or dl.chosen_here(args)):
                        # none on its library card: a free item's are on its own page (looked at every time, as
                        # before); a purchase's on its order page (issue #267: Booth's library card has stopped listing
                        # them before), looked at when nothing of it is downloaded yet, or it was chosen, so a sync of
                        # a big library doesn't open every order
                        for where, what in ((b.get("order_url"), "order"), (b.get("url"), "item")):
                            if b["files"] or not dl.store_url(where, ["booth.pm"]):
                                continue
                            try:
                                b["files"] = dl.booth_item_files(page, where)
                            except dl.NotLoggedIn:
                                raise
                            except Exception as e:
                                dl.log(f"    couldn't read the {what}'s page for its files: {e}")
                    if not b["files"]:
                        report.skipped.append(f"Booth: {name} - no files listed in your library or on its page")
                        continue

                    got_any, on_disk = False, None
                    for f in b["files"]:
                        if not dl.store_url(f["url"], ["booth.pm"]):
                            report.skipped.append(f"Booth: {name} - a file link that isn't on booth.pm was ignored")
                            continue
                        m = dl.re.search(r"/downloadables/(\d+)", f["url"])
                        fid = m.group(1) if m else f["url"]
                        old = rec["files"].get(fid)
                        if old and dl.rel_to_path(folder, old["path"]).exists():
                            continue
                        guess = dl.booth_filename(f["name"], "", f"file-{fid}")
                        replaces = next((k for k, v in rec["files"].items() if v.get("path") == guess), None)
                        if not old and not replaces and (folder / guess).exists():  # already on disk, e.g. downloaded by hand
                            rec["files"][fid] = {"path": guess, "size": (folder / guess).stat().st_size, "label": f["name"]}
                            continue
                        if dl.left_out(args, report, "booth", name, f["name"] or guess):
                            continue
                        if args.dry_run:
                            dl.would_get(args, report, "booth", rec, name, creator, f["name"] or guess, bool(replaces), old is not None)
                            continue
                        if on_disk is None:   # what's in its folder, listed once a product (each file saved is added)
                            on_disk = {x.name for x in folder.iterdir()} if folder.is_dir() else set()
                        try:
                            offered = {(dl.re.search(r"/downloadables/(\d+)", x["url"]) or [None, x["url"]])[1] for x in b["files"]}
                            fname, got = dl.with_retries(report, f["name"] or guess, lambda f=f, fid=fid, offered=offered: dl.booth_fetch(
                                page, sess, f, folder, fid, route, timeout_s,
                                name_for=lambda n, fid=fid, offered=offered: dl.distinct_name(n, fid, rec, offered)))
                            prev = next((k for k, v in rec["files"].items() if v.get("path") == fname and k != fid), None)
                            # an update replaces a file: one it had (this file, or one saved under this name), or
                            # one already on disk by this name; a file new to the product isn't one
                            is_update = old is not None or bool(replaces) or prev is not None or fname in on_disk
                        except dl.NotLoggedIn:
                            raise
                        except Exception as e:
                            report.failed.append(f"Booth: {creator} / {name} / {f['name']} - {e}")
                            continue
                        if prev:
                            rec["files"].pop(prev, None)
                        rec["files"][fid] = {"path": fname, "size": got, "label": f["name"], "downloaded_at": dl.now_iso()}
                        on_disk.add(fname)
                        dl.log(f"    {'updated' if is_update else 'saved'}: {fname}")
                        (report.updated if is_update else report.new_files).append(f"Booth: {creator} / {name} / {fname}")
                        report.saved("booth", name, f["name"] or guess)
                        got_any = True
                        man.checkpoint()
                        dl.pause(delay)

                    if got_any and is_new_asset:
                        report.new_assets.append(f"Booth: {creator} / {name}")
                    if bcfg.get("save_thumbnails", True) and not args.dry_run:
                        dl.save_thumbnail(b["thumbnail"], folder, "https://booth.pm/")
                    man.checkpoint()
            finally:
                sess.cookies.clear()  # the copied sign-in only lives for this sync
                sess.close()
        finally:
            man.save_changes()   # every finished file recorded, however the sync ended
            ctx.close()


wish_BOOTH_WISHES = "https://accounts.booth.pm/wish_lists"


# ----------------------------------------------------------------------------- what's on a page

# Booth's loved items (accounts.booth.pm/wish_lists): a card for each item, 20 to a page; above them, a button for
# each of your lists ("all", "uncategorized" and any you made), the shown one data-state="default".
wish_BOOTH_JS = r"""() => {
  const cards = [];
  for (const w of document.querySelectorAll('.item-card-wrapper')) {
    const links = [...w.querySelectorAll('a[href*="/items/"]')];
    const m = links.length ? links[0].href.match(/\/items\/(\d+)/) : null;
    if (!m) continue;
    const title = w.querySelector('a[href*="/items/"] .break-all') || links.reverse().find(a => a.textContent.trim() && !/^Loading/.test(a.textContent.trim()));
    const shop = [...w.querySelectorAll('a[href]')].find(a => /^https:\/\/[a-z0-9-]+\.booth\.pm\/?$/i.test(a.href));
    const img = [...w.querySelectorAll('img')].find(i => !i.classList.contains('hidden') && /\/i\/\d+\//.test(i.src));
    const leaves = [...w.querySelectorAll('div, span')].filter(e => !e.children.length).map(e => e.textContent.trim());
    cards.push({id: m[1], url: 'https://booth.pm/en/items/' + m[1], name: title ? title.textContent.trim() : '',
                creator: shop ? shop.textContent.trim() : '', creator_url: shop ? shop.href : '', thumbnail: img ? img.src : '',
                price: leaves.find(t => /^[~〜]?\s*(¥\s*\d|\d[\d,]*\s*(JPY|円))/.test(t)) || ''});
  }
  const lists = [...document.querySelectorAll('button.charcoal-tag-item')].map(b => ({name: b.textContent.trim(),
    shown: b.getAttribute('data-state') === 'default'})).filter(l => l.name);
  return {cards, lists};
}"""


# Booth's next page of loved items: its page numbers, under the cards, are drawn by its script, not links (an address
# with ?page=2 shows the first page again), so its arrow to the next page is chosen. False on the last page.
wish_BOOTH_NEXT_JS = r"""() => {
  const arrow = [...document.querySelectorAll('pixiv-icon[name="24/ArrowOpenRight"]')].map(i => i.closest('.cursor-pointer'))
    .find(el => el && el.offsetParent !== null);
  if (!arrow) return false;
  arrow.click();
  return true;
}"""


# ...and the first card shown, to know when the next page has taken its place
wish_BOOTH_FIRST_JS = r"""() => { const a = document.querySelector('.item-card-wrapper a[href*="/items/"]');
  const m = a && a.href.match(/\/items\/(\d+)/); return m ? m[1] : ''; }"""


def wish_booth_products(cards) -> list[dict]:
    """Booth's wishlist cards, as products."""
    return [p for p in (wish.product("booth", c.get("name"), id_=c.get("id"), creator=c.get("creator"), url=c.get("url"),
                                thumbnail=c.get("thumbnail"), price=c.get("price")) for c in cards) if p]


def wish_read_booth(ctx, cfg, progress) -> list[dict]:
    """Your loved items on Booth, all of them as one list, and each list of them you made as one more."""
    page = ctx.new_page()
    delay = float(cfg.get("request_delay", 0.8))
    try:
        def read_all(url: str, label: str) -> tuple[list[dict], bool]:
            """Every product on one of your Booth lists, page by page; and whether a quick refresh stopped short."""
            found: dict[str, dict] = {}
            wish.goto(page, url)
            wish.settle(page, 900)
            wish._signed_in(page, "accounts.booth.pm")
            short = False
            for n in range(1, wish.MAX_PAGES + 1):
                new = 0
                for c in page.evaluate(wish.BOOTH_JS)["cards"]:
                    if c["id"] in found:
                        continue
                    if cfg.get("_quick") and len(found) >= wish.QUICK_ITEMS:   # (one past the limit: the rest left)
                        short = True
                        break
                    found[c["id"]] = c
                    new += 1
                progress(f"{label}, page {n}: {len(found)} items")
                first = page.evaluate(wish.BOOTH_FIRST_JS)
                if not new or not page.evaluate(wish.BOOTH_NEXT_JS):   # the last page
                    break
                if wish.quick_done(cfg, n, len(found)):
                    short = True
                    break
                try:   # the next page's cards in place of these (Booth reads them as you turn the page)
                    page.wait_for_function(f"() => ({wish.BOOTH_FIRST_JS})() !== {first!r}", timeout=20000)
                except Exception:
                    break
                wish.settle(page, 600)
                wish.time.sleep(delay)
            return wish.booth_products(found.values()), short
        everything, short = read_all(wish.BOOTH_WISHES, wish.LIST_NAMES["booth"])
        out = [{"store": "booth", "list": wish.LIST_NAMES["booth"], "url": wish.BOOTH_WISHES, "products": everything,
                **({"partial": True} if short else {})}]
        wish.goto(page, wish.BOOTH_WISHES)
        wish.settle(page, 900)
        names = [x["name"] for x in page.evaluate(wish.BOOTH_JS)["lists"]][2:wish.MAX_LISTS + 2]   # after "all" and "uncategorized"
        for name in names:   # a list you made: its button shows it, and the address it goes to is the list's
            try:
                page.locator("button.charcoal-tag-item", has_text=name).first.click(timeout=10000)
                page.wait_for_url(lambda u: u != wish.BOOTH_WISHES, timeout=10000)
            except Exception:
                continue
            url = page.url
            products, short = read_all(url, name)
            out.append({"store": "booth", "list": wish.clean_text(name, 60), "url": url, "products": products,
                        **({"partial": True} if short else {})})
            wish.goto(page, wish.BOOTH_WISHES)
            wish.settle(page, 600)
        return out
    finally:
        page.close()

LIBRARY_EXPORTS = {
    'BOOTH_JS': lib_BOOTH_JS,
    'booth_item': lib_booth_item,
    'booth_cards': lib_booth_cards,
    'fetch_booth': lib_fetch_booth,
}

DOWNLOADER_EXPORTS = {
    'BOOTH_LIBRARY': dl_BOOTH_LIBRARY,
    'booth_library': dl_booth_library,
    'booth_file_location': dl_booth_file_location,
    'booth_filename': dl_booth_filename,
    'BOOTH_ITEM_FILES_JS': dl_BOOTH_ITEM_FILES_JS,
    'booth_item_files': dl_booth_item_files,
    'BOOTH_CLICK_JS': dl_BOOTH_CLICK_JS,
    'booth_browser_download': dl_booth_browser_download,
    'booth_fetch': dl_booth_fetch,
    'sync_booth': dl_sync_booth,
}

WISHLISTS_EXPORTS = {
    'BOOTH_WISHES': wish_BOOTH_WISHES,
    'BOOTH_JS': wish_BOOTH_JS,
    'BOOTH_NEXT_JS': wish_BOOTH_NEXT_JS,
    'BOOTH_FIRST_JS': wish_BOOTH_FIRST_JS,
    'booth_products': wish_booth_products,
    'read_booth': wish_read_booth,
}


from .base import Adapter

STORE = Adapter('booth', 'Booth', 'https://accounts.booth.pm/library', 'https://booth.pm/', 1)


def read_saved(page, cfg: dict, prep: dict) -> list[dict]:
    """Parse this store's saved library page in the caller's isolated browser."""
    gift = "/gifts" in lib.urlparse(prep["base"]).path
    items = [lib.booth_item(b, gift, prep["base"].split("?")[0]) for b in page.evaluate(lib.BOOTH_JS)]
    return items


def saved_wishlist(page, kind: str, url: str, html: str, name: str) -> list[dict]:
    """Parse this store's saved wishlist with scripts and network already disabled."""
    lists = [{"store": "booth", "list": name, "url": url, "products": wish.booth_products(page.evaluate(wish.BOOTH_JS)["cards"])}]
    return lists


def read_tags(got) -> list:
    """Read the raw creator tags; the shared normalizer bounds and cleans them."""
    import json
    import html as html_text
    if not isinstance(got, dict):
        return []
    raw = [t.get("name") for t in got.get("tags") or [] if isinstance(t, dict)]
    cat = got.get("category") if isinstance(got.get("category"), dict) else {}
    raw += [cat.get("name"), (cat.get("parent") or {}).get("name") if isinstance(cat.get("parent"), dict) else None]
    return raw
