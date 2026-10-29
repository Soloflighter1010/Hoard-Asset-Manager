"""Notifications through Apprise (issue #230): the news you choose, sent to the services you give Hoard Apprise
addresses for (Discord, Telegram, ntfy, email and many more: https://github.com/caronc/apprise/wiki).

What can be sent (EVENTS), each only when you tick it in Settings:
- new: the routine check found new products to download
- updates: the routine check found updates to products you've downloaded
- prices: products on your wishlists got cheaper
- tasks: a task finished or failed
- routine: the routine check finished (what it found, or that nothing was new)
- other: other news: a new version of Hoard, or files the check of your downloads found changed or missing

- The addresses have each service's token in them, so they're kept as API keys are (hoard/vault.py), never in
  config.json, and never sent back to the page: it only learns how many there are.
- What's sent says how many, never a product's name (a hidden one stays hidden there too), as the system's own
  notifications do (hoard/notify.py).
- Sending happens in the background, one notification at a time, and never holds up what Hoard is doing. Hoard's
  log notes each one sent (what it was for, and whether each service took it) and why one wasn't, in what the service
  said, with every address and anything from one taken out (issue #238). Apprise's own log goes nowhere else.
- Apprise reaches each service directly, wherever you said it is (your own ntfy on your network, say): these requests
  don't go through egress.py's rules, which are for stores.
"""
from __future__ import annotations

import importlib.util
import logging
import queue
import re
import threading

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


def kept(cfg: dict) -> int:
    """How many addresses are kept, for Settings: read once, then remembered (reading the Keychain or the keyring
    starts a program, and Settings asks every time it opens)."""
    global _kept
    if _kept is None:
        _kept = len(urls(cfg))
    return _kept


def save_urls(cfg: dict, addresses: list[str]) -> None:
    """Keep these addresses (protected, as API keys are); none forgets them."""
    global _kept
    if addresses:
        vault.save_secret(cfg, SECRET, "\n".join(addresses))
    else:
        vault.forget_key(cfg, SECRET)
    _kept = len(addresses)


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


def deliver(addresses: list[str], body: str, title: str = TITLE, event: str = "test") -> str | None:
    """Send now, to each service in turn, noting in Hoard's log what it was for (event) and how each service took it
    (issue #238). None when every service took it, or what went wrong, in what each service said (never an address:
    they hold tokens)."""
    try:
        import apprise
    except ImportError:
        log(f"A notification through Apprise ({event}) wasn't sent: Apprise isn't installed.")
        return "Apprise isn't installed."
    try:   # (a service Apprise can't find, as when its services weren't packed with Hoard's app: issue #237)
        sender = apprise.Apprise()
        added = sum(bool(sender.add(u)) for u in addresses)
        services = list(sender)
    except Exception as e:  # noqa: BLE001 - Apprise's own problem, said in Hoard's words
        log(f"A notification through Apprise ({event}) wasn't sent: Apprise couldn't start ({type(e).__name__}).")
        return f"Apprise couldn't start ({type(e).__name__}). Run Setup again, or reinstall Hoard."
    unknown = len(addresses) - added
    if not services:
        log(f"A notification through Apprise ({event}) wasn't sent: none of the addresses is one Apprise knows.")
        return "None of the addresses is one Apprise knows."
    took, problems = [], []
    for service in services:
        name = str(getattr(service, "service_name", "") or type(service).__name__)
        _heard.here.lines = []
        try:
            ok = bool(service.notify(body=body, title=title))
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


def send(cfg: dict, event: str, body: str, title: str = TITLE) -> bool:
    """Send this news in the background, if it's an event you chose and there may be addresses kept. True when it's
    on its way. Never raises: notifications never get in the way of what Hoard is doing. The addresses are read by
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
        _out.put_nowait((cfg, event, body, title))
    except queue.Full:
        return False
    return True


def _work() -> None:
    """The background worker: send each notification waiting, to the addresses kept (deliver notes each in Hoard's
    log). Nothing stops it: a notification that can't be sent is noted, and the next one is sent."""
    global _kept
    while True:
        cfg, event, body, title = _out.get()
        try:
            addresses = urls(cfg)
            _kept = len(addresses)
            if addresses:
                deliver(addresses, body, title, event)
        except Exception as e:  # noqa: BLE001 - the worker carries on with the next
            log(f"A notification through Apprise ({event}) wasn't sent ({type(e).__name__}).")


# What's sent, in words: counts only, never a product's name.
def plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else many or one + 's'}"


def found_text(counts: dict, event: str) -> str | None:
    """The routine check's news, for "new" or "updates" (None when there's none of that)."""
    n = counts.get("new" if event == "new" else "updates") or 0
    if not n:
        return None
    what = plural(n, "new product") if event == "new" else plural(n, "update")
    return f"The routine check found {what}. Open Hoard to choose what to download."


def task_text(record: dict) -> str:
    """A finished task, as the news says it: its name, how it went, and its counts (from its report)."""
    from .jobs import TASK_NAMES
    name = TASK_NAMES.get(record.get("task"), "A task")
    outcome = record.get("outcome")
    report = record.get("report") if isinstance(record.get("report"), dict) else {}
    counts = []
    for key, one in (("new_assets", "new"), ("updated", "updated"), ("failed", "couldn't be downloaded")):
        if isinstance(report.get(key), int) and report[key]:
            counts.append(f"{report[key]:,} {one}")
    if isinstance(report.get("updates"), int):
        counts.append(plural(report["updates"], "product") + " with updates")
    said = {"failed": "failed", "partial": "partly done", "stopped": "stopped"}.get(outcome, "done")
    return f"{name}: {said}" + (f" ({', '.join(counts)})." if counts else ".")
