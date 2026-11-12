"""Notifications through Apprise (issue #230): the news you choose, sent to the services you give Hoard Apprise
addresses for (Discord, Telegram, ntfy, email and many more: https://appriseit.com/services/).

What can be sent (EVENTS), each only when you tick it in Settings:
- new: the routine check found new products to download
- updates: the routine check found updates to products you've downloaded
- prices: products on your wishlists got cheaper
- tasks: a task finished or failed
- routine: the routine check finished (what it found, or that nothing was new)
- other: other news: a new version of Hoard, or files the check of your downloads found changed or missing

- The addresses have each service's token in them, so they're kept as API keys are (hoard/vault.py), never in
  config.json, and never sent back to the page: it only learns each one's service and what tells it apart, never a
  token, password or webhook key (describe, issue #287), and names one by an id made from it.
- What's sent says how many, never the name of a product in your library (a hidden one stays hidden there too), as
  the system's own notifications do (hoard/notify.py). A wishlist's products that got cheaper (on a store, not in
  your library) are named, with their picture and a link (issue #285).
- It's sent as a rich message where a service can show one (issue #285): a Discord embed in Hoard's colour, with its
  title, what happened in a few lines and a link; Markdown or HTML where a service takes it; plain text elsewhere.
- Sending happens in the background, one notification at a time, and never holds up what Hoard is doing. Hoard's
  log notes each one sent (what it was for, and whether each service took it) and why one wasn't, in what the service
  said, with every address and anything from one taken out (issue #238). Apprise's own log goes nowhere else.
- Apprise reaches each service directly, wherever you said it is (your own ntfy on your network, say): these requests
  don't go through egress.py's rules, which are for stores.
"""
from __future__ import annotations

import hashlib
import importlib.util
import logging
import queue
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import vault
from .common import log

EVENTS = ("new", "updates", "prices", "tasks", "routine", "other")
SECRET = "apprise"   # (the name the addresses are kept under)
MAX_URLS, MAX_URL = 20, 1000
URL = re.compile(r"[a-z][a-z0-9+.-]{0,30}://[^\s]+", re.I)
TITLE = "Hoard"


def available() -> bool:
    """Is Apprise installed? (Hoard's apps include it; a source install has it once Setup has run again.)"""
    return importlib.util.find_spec("apprise") is not None


def clean_urls(raw) -> list[str]:
    """Apprise addresses as typed or pasted (one a line, or a list), each like discord://... or ntfys://...: anything
    else is dropped. Raises ValueError for more than MAX_URLS, or one longer than MAX_URL characters."""
    lines = raw.splitlines() if isinstance(raw, str) else [x for x in raw if isinstance(x, str)] if isinstance(raw, list) else []
    out = []
    for line in (x.strip() for x in lines):
        if not line:
            continue
        if len(line) > MAX_URL:
            raise ValueError(f"An address is longer than {MAX_URL:,} characters.")
        if not URL.fullmatch(line):
            raise ValueError("Each line needs to be an Apprise address, such as discord://... or ntfys://...")
        if line not in out:
            out.append(line)
    if len(out) > MAX_URLS:
        raise ValueError(f"Hoard keeps up to {MAX_URLS} addresses.")
    return out


def urls(cfg: dict) -> list[str]:
    """The addresses kept, or [] (none, or the protected storage can't be read)."""
    kept = vault.load_secret(cfg, SECRET)
    try:
        return clean_urls(kept or "")
    except ValueError:
        return []


_kept: int | None = None
_described: list[dict] | None = None


def kept(cfg: dict) -> int:
    """How many addresses are kept, for Settings: read once, then remembered (reading the Keychain or the keyring
    starts a program, and Settings asks every time it opens)."""
    return len(described(cfg))


# Each service's name, by the start of its address (Apprise's own: https://appriseit.com/services/)
SERVICES = {"discord": "Discord", "tgram": "Telegram", "ntfy": "ntfy", "ntfys": "ntfy", "mailto": "Email", "mailtos": "Email",
            "pover": "Pushover", "slack": "Slack", "matrix": "Matrix", "matrixs": "Matrix", "gotify": "Gotify",
            "gotifys": "Gotify", "json": "Webhook", "jsons": "Webhook", "xml": "Webhook", "xmls": "Webhook",
            "form": "Webhook", "forms": "Webhook", "msteams": "Microsoft Teams", "pbul": "Pushbullet", "signal": "Signal",
            "signals": "Signal", "line": "LINE", "mastodon": "Mastodon", "toot": "Mastodon", "bark": "Bark", "barks": "Bark"}


def address_id(url: str) -> str:
    """The name the page knows an address by: made from it, but never giving it away."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _tail(text: str, n: int = 4) -> str:
    """The last few letters of something that tells two apart, never all of it."""
    text = str(text or "")
    return "…" + text[-n:] if len(text) > n * 2 else "…"


def _host(part: str) -> str:
    """A server's name from an address's first part (anything before an @ left out: it can be a name and password)."""
    host = part.rsplit("@", 1)[-1]
    name, colon, port = host.partition(":")
    if colon and not re.fullmatch(r"\d{1,5}", port):
        return ""
    head, dot, last = name.rpartition(".")   # (a name: its last part letters only, as example.com)
    named = dot and head and re.fullmatch(r"[A-Za-z0-9.-]+", head) and re.fullmatch(r"[A-Za-z]{2,}", last)
    return host if name == "localhost" or re.fullmatch(r"[\d.]+", name) or named else ""


def describe(url: str) -> dict:
    """An address as Settings shows it (issue #287): {"id", "service", "label"}, the label only what tells two of a
    service apart (a server's name, the end of a chat's or a webhook's number), never a token, password or key."""
    native = re.match(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/(\d+)/", url, re.I)
    if native:   # (a Discord webhook's own address, pasted as it is: Apprise takes it)
        return {"id": address_id(url), "service": "Discord", "label": f"webhook {_tail(native.group(1))}"}
    scheme, _, rest = url.partition("://")
    s = scheme.lower()
    path, _, query = rest.partition("?")
    parts = [x for x in path.split("/") if x]
    label = ""
    if s == "discord":
        label = f"webhook {_tail(parts[0])}" if parts else ""
    elif s == "tgram":
        label = f"chat {_tail(parts[1])}" if len(parts) > 1 else ""
    elif s in ("ntfy", "ntfys"):
        host = _host(parts[0]) if len(parts) > 1 else "ntfy.sh"
        label = ", ".join(x for x in (host, f"topic {_tail(parts[-1], 3)}" if parts else "") if x)
    elif s in ("mailto", "mailtos"):
        to = (parse_qs(query).get("to") or [""])[0]
        if "@" in to:
            name, _, domain = to.partition("@")
            label = f"to {name[:1]}•••@{domain}"
        else:
            label = _host(parts[0]) if parts else ""
    elif s == "pover":
        label = f"user {_tail(parts[0].split('@')[0])}" if parts else ""
    elif s == "slack":
        label = f"workspace {_tail(parts[0])}" if parts else ""
    elif s in ("matrix", "matrixs"):
        label = ", ".join(x for x in (_host(parts[0]) if parts else "", f"room {_tail(parts[-1], 3)}" if len(parts) > 1 else "") if x)
    elif parts:
        label = _host(parts[0])
    return {"id": address_id(url), "service": SERVICES.get(s, scheme), "label": label}


def described(cfg: dict) -> list[dict]:
    """Each address kept, as Settings shows it (describe): read once, then remembered (see kept)."""
    global _described, _kept
    if _described is None:
        _described = [describe(u) for u in urls(cfg)]
        _kept = len(_described)
    return _described


def save_urls(cfg: dict, addresses: list[str]) -> None:
    """Keep these addresses (protected, as API keys are); none forgets them."""
    global _kept, _described
    if addresses:
        vault.save_secret(cfg, SECRET, "\n".join(addresses))
    else:
        vault.forget_key(cfg, SECRET)
    _kept, _described = len(addresses), [describe(u) for u in addresses]


def change(cfg: dict, action: str, address_id_: str = "", raw=None) -> list[dict]:
    """Change the addresses one at a time (issue #287): "add" these (one a line), "replace" the one with this id by
    another, or "remove" it. Returns them as Settings shows them. ValueError says what's wrong."""
    have = urls(cfg)
    ids = [address_id(u) for u in have]
    if action == "add":
        new = clean_urls(raw)
        if not new:
            raise ValueError("Type an address first, or build one.")
        merged = have + [u for u in new if u not in have]
        if len(merged) > MAX_URLS:
            raise ValueError(f"Hoard keeps up to {MAX_URLS} addresses.")
        save_urls(cfg, merged)
    elif action in ("replace", "remove"):
        if address_id_ not in ids:
            raise ValueError("That address isn't kept any more. Look again.")
        at = ids.index(address_id_)
        if action == "remove":
            save_urls(cfg, have[:at] + have[at + 1:])
        else:
            new = clean_urls(raw)
            if len(new) != 1:
                raise ValueError("Type or build the one address to put in its place.")
            save_urls(cfg, [u for u in have[:at] if u != new[0]] + new + [u for u in have[at + 1:] if u != new[0]])
    else:
        raise ValueError("Hoard doesn't know that.")
    return described(cfg)


def by_id(cfg: dict, address_id_: str) -> list[str]:
    """The address kept with this id, as a list of one (none when there's no such address)."""
    return [u for u in urls(cfg) if address_id(u) == address_id_]


def chosen(cfg: dict) -> set[str]:
    """What you chose to be sent (config.json's "apprise_events": names only, nothing secret)."""
    raw = cfg.get("apprise_events")
    return {e for e in raw if e in EVENTS} if isinstance(raw, list) else set()


class _Heard(logging.Handler):
    """What Apprise's services say went wrong (its warnings and errors), kept for the thread sending, so a failure
    can say why. Apprise's log goes only here: it can hold an address."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.here = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        """Keep what's said while this thread is sending (and nothing at other times)."""
        lines = getattr(self.here, "lines", None)
        if lines is not None and len(lines) < 10:
            try:
                lines.append(record.getMessage())
            except Exception:  # noqa: BLE001 - a message that can't be put together is one less reason, nothing more
                pass


_heard = _Heard()
_apprise_log = logging.getLogger("apprise")
_apprise_log.addHandler(_heard)
_apprise_log.propagate = False   # (not on to the launch log as it is: what it says can hold an address)


def scrub(text: str, addresses: list[str]) -> str:
    """What a service said, with every address and anything from one (a token, a host, a name) taken out."""
    text = URL.sub("…", str(text))
    for address in addresses:
        for part in re.split(r"[/:@?&=#,;+]+", address.split("://", 1)[-1]):
            if len(part) >= 4:
                text = text.replace(part, "…")
    return re.sub(r"\s+", " ", text).strip()[:300]


GOLD = "#F0B429"   # Hoard's colour, on a Discord embed's edge
HOARD_URL = "https://github.com/Soloflighter1010/Hoard-Asset-Manager"
HOARD_ICON = "https://raw.githubusercontent.com/Soloflighter1010/Hoard-Asset-Manager/main/packaging/icons/hoard-256.png"


def _asset(apprise, picture_url: str | None = None):
    """Hoard as Apprise names it on a rich message: its name, a line about it, its address, its icon and its colour.
    With picture_url, the picture a rich message shows is that one (a product's, on its store's image host) and not
    Hoard's icon, which stays in the footer."""
    asset = apprise.AppriseAsset(app_id="Hoard", app_desc="Hoard Asset Manager", app_url=HOARD_URL)
    try:
        asset.image_url_mask = picture_url or HOARD_ICON
        asset.image_url_logo = HOARD_ICON
        asset.html_notify_map = {k: GOLD for k in list(asset.html_notify_map)}
        asset.default_html_color = GOLD
    except Exception:  # noqa: BLE001 - an Apprise without these: its own look, the message all the same
        pass
    return asset


def embeds(url: str) -> bool:
    """Whether an address is a Discord webhook's, which shows a message as an embed."""
    return url.split("://", 1)[0].lower() == "discord" or \
        bool(re.match(r"https://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/", url, re.I))


def rich(url: str, link: str | None = None) -> str:
    """An address as it's sent to (issue #285): a Discord webhook's asks for an embed (Markdown, Hoard's footer and icon,
    and the link, when there is one); others are as you gave them. Nothing you set on an address is changed."""
    if not embeds(url):
        return url
    have = {k.lower() for k in parse_qs(urlsplit(url).query, keep_blank_values=True)}
    add = [f"{k}={v}" for k, v in (("format", "markdown"), ("footer", "yes"), ("image", "yes")) if k not in have]
    if link and "href" not in have and re.fullmatch(r"https://[^\s?#]+(?:\?[^\s#]*)?", link):
        from urllib.parse import quote
        add.append("href=" + quote(link, safe=""))
    return url + ("&" if "?" in url else "?") + "&".join(add) if add else url


def deliver(addresses: list[str], body: str, title: str = TITLE, event: str = "test", link: str | None = None,
            picture=None, picture_url: str | None = None) -> str | None:
    """Send now, to each service in turn, noting in Hoard's log what it was for (event) and how each service took it
    (issue #238). body is Markdown: each service gets it as it shows best (issue #285); link is what a Discord embed
    links to. picture (its bytes and type, or what fetches them) goes with it where a service takes pictures, as a
    file; a Discord embed shows the picture at picture_url itself (its https address on a store's image host), in
    the embed with everything else, and is sent no file: Discord posts a file as a message of its own, under the
    embed (issue #330). None when every service took it, or what went wrong, in what each service said (never an
    address: they hold tokens)."""
    try:
        import apprise
    except ImportError:
        log(f"A notification through Apprise ({event}) wasn't sent: Apprise isn't installed.")
        return "Apprise isn't installed."
    try:   # (a service Apprise can't find, as when its services weren't packed with Hoard's app: issue #237)
        sender = apprise.Apprise(asset=_asset(apprise))
        shown = picture_url if isinstance(picture_url, str) and re.fullmatch(r"https://[^\s{}]+", picture_url) else None
        pictured = _asset(apprise, shown) if shown and any(embeds(u) for u in addresses) else None
        added = sum(bool(sender.add(rich(u, link), asset=pictured) if pictured is not None and embeds(u)
                         else sender.add(rich(u, link))) for u in addresses)
        services = list(sender)
    except Exception as e:  # noqa: BLE001 - Apprise's own problem, said in Hoard's words
        log(f"A notification through Apprise ({event}) wasn't sent: Apprise couldn't start ({type(e).__name__}).")
        return f"Apprise couldn't start ({type(e).__name__}). Run Setup again, or reinstall Hoard."
    unknown = len(addresses) - added
    if not services:
        log(f"A notification through Apprise ({event}) wasn't sent: none of the addresses is one Apprise knows.")
        return "None of the addresses is one Apprise knows."
    took, problems = [], []
    attach, pic_file = None, None

    def in_embed(service) -> bool:
        """Whether this service's message shows the picture itself."""
        return pictured is not None and getattr(service, "asset", None) is pictured
    if picture and any(getattr(s, "attachment_support", False) and not in_embed(s) for s in services):
        try:   # (fetched only now there's a service to send it to as a file)
            picture = picture() if callable(picture) else picture
        except Exception:  # noqa: BLE001 - no picture, the message all the same
            picture = None
    else:
        picture = None
    if picture:   # (the product's picture, as a file Apprise can send)
        ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(picture[1], ".jpg")
        with tempfile.NamedTemporaryFile(prefix="hoard-picture-", suffix=ext, delete=False) as fh:
            fh.write(picture[0])
            pic_file = Path(fh.name)
        try:
            attach = apprise.AppriseAttachment(str(pic_file))
        except Exception:  # noqa: BLE001 - no picture, the message all the same
            attach = None
    for service in services:
        name = str(getattr(service, "service_name", "") or type(service).__name__)
        _heard.here.lines = []
        try:
            kwargs = {"attach": attach} if attach is not None and getattr(service, "attachment_support", False) \
                and not in_embed(service) else {}
            # (a service that shows only plain text gets it as text, as Apprise would render it for that service)
            resolve = getattr(service, "resolve_format", None)
            text_only = callable(resolve) and str(getattr(resolve(apprise.NotifyFormat.MARKDOWN), "value", "")) == "text"
            ok = bool(service.notify(body=plain(body) if text_only else body, title=title,
                                     body_format=apprise.NotifyFormat.TEXT if text_only else apprise.NotifyFormat.MARKDOWN, **kwargs))
        except Exception as e:  # noqa: BLE001 - a service's own error: its kind, never its words (they may hold an address)
            ok = False
            _heard.here.lines.append(type(e).__name__)
        finally:
            said, _heard.here.lines = _heard.here.lines, None
        if ok:
            took.append(name)
        else:
            why = scrub(said[-1], addresses) if said else "it didn't answer as it should"
            problems.append(f"{name} didn't take it: {why}")
    if pic_file is not None:
        try:
            pic_file.unlink()
        except OSError:
            pass
    if took:
        log(f"A notification through Apprise ({event}) was sent: {', '.join(took)} took it.")
    for p in problems:
        log(f"A notification through Apprise ({event}) wasn't sent: {p}")
    if unknown:
        log(f"A notification through Apprise ({event}): {unknown} of the addresses isn't one Apprise knows.")
    if problems:
        return " ".join(p if p.endswith(".") else p + "." for p in problems) + \
            " Check its address, and that it can be reached from this computer."
    if unknown:
        return f"{unknown} of the addresses isn't one Apprise knows; the rest were sent it."
    return None


_out: queue.Queue = queue.Queue(maxsize=50)
_worker: threading.Thread | None = None
_lock = threading.Lock()


def send(cfg: dict, event: str, body: str, title: str = TITLE, link: str | None = None, picture=None,
         picture_url: str | None = None) -> bool:
    """Send this news in the background, if it's an event you chose and there may be addresses kept. True when it's
    on its way. picture and picture_url are deliver's. Never raises: notifications never get in the way of what Hoard is doing. The addresses are read by
    the worker, not here: reading the Keychain or the keyring starts a program, and a task that sends news (as it
    finishes) would wait for it."""
    global _worker
    if event not in chosen(cfg) or not available() or _kept == 0:   # (none kept, as far as Hoard knows)
        return False
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="apprise", daemon=True)
            _worker.start()
    try:
        _out.put_nowait((cfg, event, body, title, link, picture, picture_url))
    except queue.Full:
        return False
    return True


def _work() -> None:
    """The background worker: send each notification waiting, to the addresses kept (deliver notes each in Hoard's
    log). Nothing stops it: a notification that can't be sent is noted, and the next one is sent."""
    global _kept
    while True:
        cfg, event, body, title, link, picture, picture_url = _out.get()
        try:
            addresses = urls(cfg)
            _kept = len(addresses)
            if addresses:
                deliver(addresses, body, title, event, link, picture, picture_url)
        except Exception as e:  # noqa: BLE001 - the worker carries on with the next
            log(f"A notification through Apprise ({event}) wasn't sent ({type(e).__name__}).")


# What's sent, in words: counts only, never a product's name.
def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def found_text(counts: dict, event: str) -> str | None:
    """The routine check's news, for "new" or "updates" (None when there's none of that), in Markdown."""
    n = counts.get("new" if event == "new" else "updates") or 0
    if not n:
        return None
    what = plural(n, "new product") if event == "new" else plural(n, "update")
    return f"The routine check found **{what}**. Open Hoard to choose what to download."


def md(text) -> str:
    """Text as Markdown shows it as it is (a product's name with * or [ in it, say)."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|~>])", r"\\\1", str(text or ""))


def plain(text: str) -> str:
    """Markdown as plain text, for a service that shows only that: no ** or ~~, a link's words then its address."""
    text = re.sub(r"\[((?:\\.|[^\]\\])*)\]\((https?://[^)\s]+)\)", r"\1 (\2)", str(text or ""))
    text = re.sub(r"~~(.+?)~~ \*\*(.+?)\*\*", r"\1 → \2", text)   # (a price that went down: was, then now)
    text = re.sub(r"(\*\*|~~)(.+?)\1", r"\2", text)
    return re.sub(r"\\([\\`*_{}\[\]()#+\-.!|~>])", r"\1", text)


def cheaper_text(count: int, items: list[dict]) -> tuple[str, str | None]:
    """Wishlist products that got cheaper (issue #285), in Markdown: how many, then each of the first few by its name
    (linked to its store page), its old price struck out and its new one; and the first one's page, to link."""
    from .safety import store_link
    lines = [f"**{plural(count, 'product')}** on your wishlists {'is' if count == 1 else 'are'} cheaper than before."]
    first = None
    for i in items[:5]:
        url = store_link(i.get("store"), i.get("url")) if i.get("store") else None
        name = md(i.get("name"))
        lines.append(f"- {f'[{name}]({url})' if url else name}: ~~{md(i.get('was'))}~~ **{md(i.get('now'))}**")
        first = first or url
    if items and count > len(items[:5]):
        lines.append(f"- and {count - len(items[:5]):,} more")
    return "\n".join(lines), first


# What a task counted (jobs.Jobs._counted), as its news says each, in this order (issue #342). Those in SAID_AT_NONE
# are said at 0 too: "0 new" is news, "0 left out" isn't.
COUNTED = (("read", lambda n: plural(n, "product") + " read"), ("new", lambda n: f"{n:,} new"),
           ("added", lambda n: f"{n:,} added"), ("already", lambda n: f"{n:,} already there"),
           ("taken_out", lambda n: f"{n:,} taken out"), ("moved", lambda n: f"{n:,} moved"),
           ("deleted", lambda n: plural(n, "file") + " deleted"),
           ("matched", lambda n: f"{n:,} matched to your library"), ("local", lambda n: plural(n, "Local product")),
           ("notes", lambda n: plural(n, "note")), ("files", lambda n: plural(n, "file")),
           ("lists", lambda n: plural(n, "wishlist") + " read"), ("cheaper", lambda n: f"{n:,} cheaper than before"),
           ("left_out", lambda n: f"{n:,} left out"))
SAID_AT_NONE = ("new", "added", "taken_out", "deleted")


def task_text(record: dict) -> str:
    """A finished task, as the news says it: its name, how it went, and its counts (from its report): how many, never
    which. A download that found nothing says so."""
    from .jobs import TASK_NAMES
    name = TASK_NAMES.get(record.get("task"), "A task")
    outcome = record.get("outcome")
    report = record.get("report") if isinstance(record.get("report"), dict) else {}
    counts = []
    counted = report.get("counts") if isinstance(report.get("counts"), dict) else {}
    downloaded = [report.get(k) for k in ("new_assets", "updated", "failed")]
    for key, say in COUNTED:
        n = counted.get(key)
        if isinstance(n, int) and not isinstance(n, bool) and (n > 0 or (n == 0 and key in SAID_AT_NONE)) \
                and not (key == "new" and isinstance(downloaded[0], int)):   # (a sync says what it downloaded, below)
            counts.append(say(n))
    for key, one in (("new_assets", "new"), ("updated", "updated"), ("failed", "couldn't be downloaded")):
        if isinstance(report.get(key), int) and report[key]:
            counts.append(f"{report[key]:,} {one}")
    if all(isinstance(n, int) for n in downloaded) and not any(downloaded):
        counts.append("nothing new")
    if isinstance(report.get("updates"), int):
        counts.append(plural(report["updates"], "product") + " with updates")
    said = {"failed": "failed", "partial": "partly done", "stopped": "stopped"}.get(outcome, "done")
    return f"**{name}**: {said}" + (f" ({', '.join(counts)})." if counts else ".")
