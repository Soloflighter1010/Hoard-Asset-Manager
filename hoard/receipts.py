"""Gumroad purchases by their receipts.

A product bought on Gumroad without an account, or with an email that isn't your account's, isn't in your Gumroad
library, so a refresh can't find it. Its receipt can: the receipt's View content button opens the purchase's
download page (gumroad.com/d/<token>), which shows what was bought and its files to whoever has the link. Add the
receipt to Hoard (the email saved as a file, the receipt's page, the download page saved from your browser, or just
the View content link) and Gumroad's refresh reads it with the rest, and Download gets its files.

- The link is all it takes to open the purchase, so it's kept on this computer only, in gumroad-receipts.json beside
  your library list (which keeps your library's own download links), sealed like it: never in a backup, a support
  report or a log.
- Gumroad asks for the email a purchase was made with before showing it on a computer or network it hasn't seen it
  on. Hoard answers with the email on the receipt, kept protected by your operating system (vault.py), never in a
  file, and only ever sent to gumroad.com, for that purchase. Gumroad then gives that purchase's own cookie, which is
  kept with it, so the email isn't sent again. A receipt added by its link alone has no email: if Gumroad asks,
  Hoard says to add the receipt email itself instead.
- A receipt is read without your Gumroad sign-in, each in a session of its own, so it works signed out, and one
  account's sign-in never mixes with a purchase made by another email.
"""
from __future__ import annotations

import email
import hashlib
import html
import json
import re
import threading
from email import policy
from pathlib import Path
from urllib.parse import unquote, unquote_plus, urlparse

from .common import NotLoggedIn, now_iso
from .paths import data_dir

FILE_NAME = "gumroad-receipts.json"
EMAILS = "gumroad-receipt-emails"   # the vault's name for the receipts' emails (one a line)
MOST = 2000                          # receipts kept, at most
MOST_EMAILS = 40
MAX_FILE = 30 * 1024 * 1024          # a receipt file, at most (a saved download page with its pictures)
SITE = "https://gumroad.com"
SITES = ["gumroad.com"]
# A purchase's download link: gumroad.com/d/<token> (the receipt's View content button), or the older /r/<token>.
# Gumroad's tokens are 32 hex digits; anything of letters and digits within these lengths is taken, nothing else.
_TOKEN = r"[A-Za-z0-9]{16,64}"
LINK = re.compile(r"(?:https?://)?(?<![A-Za-z0-9.-])(?:app\.|www\.)?gumroad\.com/(?:d|r)/(" + _TOKEN + r")(?![A-Za-z0-9])", re.I)
# The email a purchase was made with, as the receipt's Generate invoice link carries it
_INVOICE = re.compile(r"gumroad\.com/purchases/[^\s\"'<>/]{1,80}/invoice/new\?(?:[^\s\"'<>]*?&(?:amp;)?)?email=([^&\s\"'<>#]{3,300})", re.I)
_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
_COOKIE = re.compile(r"[A-Za-z0-9%+/=_.-]{1,2000}")
COOKIE_NAME = "confirmed_redirect"   # Gumroad's cookie saying a purchase's email was confirmed in this session
_lock = threading.RLock()


class ReceiptError(Exception):
    """A receipt Gumroad didn't show: why, in words to show."""


def path() -> Path:
    """Where the receipts are kept."""
    return data_dir() / FILE_NAME


def email_id(address: str) -> str:
    """A short name for an email, kept with each receipt instead of the email itself (which is in the vault)."""
    return hashlib.sha256(address.strip().lower().encode("utf-8")).hexdigest()[:16]


def ref(token: str) -> str:
    """A receipt's name for the page (to remove it, say): never its link."""
    return hashlib.sha256(("receipt:" + token).encode("ascii")).hexdigest()[:12]


def clean_email(value) -> str | None:
    """An email address, or None."""
    text = str(value or "").strip()
    return text if len(text) <= 254 and _EMAIL.fullmatch(text) else None


def download_link(token: str) -> str:
    """A purchase's download page, made here from its token alone (whatever address it came in)."""
    return f"{SITE}/d/{token}"


def token_of(url) -> str | None:
    """The token in a Gumroad download link (gumroad.com/d/<token>, or one download_link made), or None."""
    if not isinstance(url, str):
        return None
    m = LINK.search(url)
    if m:
        return m.group(1)
    rest = url[len(SITE) + 3:] if url.startswith(SITE + "/d/") else ""   # (SITE: a stand-in Gumroad, in tests)
    return rest if re.fullmatch(_TOKEN, rest) else None


# ----------------------------------------------------------------------------- finding receipts in what you add

def _texts(filename: str, text: str) -> tuple[list[str], bool]:
    """Every part of a file worth looking through (an email's own text and HTML, decoded; a saved page's HTML), and
    whether it's an email."""
    head = text[:8000]
    if filename.lower().endswith((".mhtml", ".mht")) or re.search(r"^Content-Type:\s*multipart/related", head, re.I | re.M):
        from .library import read_saved_page
        try:
            return [read_saved_page(filename, text)[0]], False
        except (ValueError, LookupError):
            return [text], False
    if filename.lower().endswith(".eml") or re.match(r"(?:[A-Za-z-]{1,40}:[^\n]*\n(?:[ \t][^\n]*\n)*){2,}", head) \
            and re.search(r"^(?:Received|Return-Path|Delivered-To|Message-ID|MIME-Version):", head, re.I | re.M):
        msg = email.message_from_string(text, policy=policy.default)
        parts = []
        for part in msg.walk():
            if part.get_content_type() in ("text/html", "text/plain"):
                try:
                    parts.append(part.get_content())
                except (LookupError, ValueError):
                    raw = part.get_payload(decode=True) or b""
                    parts.append(raw.decode("utf-8", "replace"))
        return parts or [text], True
    return [text], False


def _to_header(text: str) -> str | None:
    """An email's To address, when the email is Gumroad's (its receipt was sent to the email it was bought with)."""
    try:
        msg = email.message_from_string(text[:200000], policy=policy.default)
        sender = str(msg.get("From") or "")
        if "gumroad.com" not in sender.lower():
            return None
        to = msg.get("To")
        addresses = getattr(to, "addresses", ()) if to is not None else ()
        return clean_email(addresses[0].addr_spec) if len(addresses) == 1 else None
    except (ValueError, IndexError, TypeError, AttributeError, LookupError):
        return None


def _page_data(page: str) -> dict | None:
    """A Gumroad page's own data (component and props), or None."""
    from .library import extract_page_json
    try:
        data = extract_page_json(page)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def find(filename: str, text: str) -> list[dict]:
    """The receipts in something you added: {"token", "email" (or None), "name" (or None)} each, in order, without
    repeats. A receipt (its email, or its page) gives its View content links and the email it was sent to; a saved
    download page gives its own purchase; pasted text gives the links in it."""
    text = text if isinstance(text, str) else ""
    texts, is_email = _texts(filename or "", text)
    found: dict[str, dict] = {}
    for part in texts:
        data = _page_data(part) if "data-page" in part else None
        props = (data or {}).get("props") if isinstance((data or {}).get("props"), dict) else {}
        if (data or {}).get("component") == "UrlRedirects/DownloadPage" and isinstance(props.get("token"), str) \
                and re.fullmatch(_TOKEN, props["token"]):   # a saved download page: its own purchase, all said
            purchase = props.get("purchase") if isinstance(props.get("purchase"), dict) else {}
            found.setdefault(props["token"], {"token": props["token"], "email": clean_email(purchase.get("email")),
                                              "name": purchase.get("product_name") if isinstance(purchase.get("product_name"), str) else None})
            continue
        sent_to = None
        for look in (part, html.unescape(part)):
            m = _INVOICE.search(look)
            if m:
                sent_to = clean_email(unquote_plus(m.group(1)))
                break
        for look in (part, unquote(html.unescape(part))):   # (a link an email program wrapped: its address encoded)
            for m in LINK.finditer(look):
                found.setdefault(m.group(1), {"token": m.group(1), "email": sent_to, "name": None})
    to = _to_header(text) if is_email else None
    for r in found.values():
        r["email"] = r["email"] or to
        if isinstance(r["name"], str):
            from .safety import clean_text
            r["name"] = clean_text(r["name"], 300) or None
    return list(found.values())


# ----------------------------------------------------------------------------- keeping them

def _clean(raw) -> dict | None:
    """One kept receipt, checked, or None."""
    if not isinstance(raw, dict) or not isinstance(raw.get("token"), str) or not re.fullmatch(_TOKEN, raw["token"]):
        return None
    from .safety import clean_text
    out = {"token": raw["token"], "added": raw["added"] if isinstance(raw.get("added"), str) else now_iso()}
    for k, size in (("name", 300), ("creator", 200), ("error", 400)):
        if isinstance(raw.get(k), str) and raw[k].strip():
            out[k] = clean_text(raw[k], size)
    if isinstance(raw.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_=+/-]{1,80}", raw["id"]):
        out["id"] = raw["id"]
    if isinstance(raw.get("email"), str) and re.fullmatch(r"[0-9a-f]{16}", raw["email"]):
        out["email"] = raw["email"]
    if isinstance(raw.get("cookie"), str) and _COOKIE.fullmatch(raw["cookie"]):
        out["cookie"] = raw["cookie"]
    if isinstance(raw.get("read"), str):
        out["read"] = raw["read"][:40]
    if raw.get("in_library") is True:   # (your Gumroad library has it too: read from there)
        out["in_library"] = True
    return out


def load() -> list[dict]:
    """The receipts kept. A file that something other than Hoard changed, or that Hoard on another computer wrote,
    isn't used (its links could open anyone's purchases): add the receipts again."""
    from . import storage
    from .safety import DataFileError
    p = path()
    with _lock:
        if not storage.exists(p):
            return []
        try:
            raw = storage.read_document(p, 16 * 1024 * 1024)
        except DataFileError as e:
            aside = storage.archive_document(p)
            print(f"{e}, so it was kept as {aside.name}. Add your Gumroad receipts again.", flush=True)
            return []
        status = storage.seal_status(raw, p)
        if status in ("changed", "foreign"):
            print("Hoard's list of Gumroad receipts " + ("was changed by something other than Hoard" if status == "changed"
                  else "was saved by Hoard on another computer") + ", so it isn't used. Add your receipts again.", flush=True)
            return []
        rows = raw.get("receipts") if isinstance(raw, dict) and isinstance(raw.get("receipts"), list) else []
        out, seen = [], set()
        for r in rows[:MOST]:
            c = _clean(r)
            if c and c["token"] not in seen:
                seen.add(c["token"])
                out.append(c)
        return out


def save(rows: list[dict]) -> None:
    """Keep the receipts (sealed), or delete the file when there are none."""
    from . import storage
    from .safety import remember_sealed, seal
    p = path()
    with _lock:
        if not rows:
            if storage.exists(p):
                if storage.managed(p):
                    storage.write_document(p, json.dumps(seal({"receipts": []})))
                else:
                    p.unlink(missing_ok=True)
            return
        storage.write_document(p, json.dumps(seal({"receipts": rows[:MOST]}), indent=1, ensure_ascii=False))
        remember_sealed(p)


def emails(cfg: dict) -> dict[str, str]:
    """The receipts' emails, kept protected by the operating system: {email_id: email}."""
    from . import vault
    kept = vault.load_secret(cfg, EMAILS) or ""
    return {email_id(e): e for e in (clean_email(x) for x in kept.splitlines()) if e}


def _keep_emails(cfg: dict, new: list[str]) -> bool:
    """Add emails to the vault's list. False when this computer has nowhere safe to keep them."""
    from . import vault
    from .browser import SigninsUnprotected
    have = emails(cfg)
    wanted = list(have.values()) + [e for e in dict.fromkeys(new) if email_id(e) not in have]
    if len(wanted) == len(have):
        return True
    try:
        vault.save_secret(cfg, EMAILS, "\n".join(wanted[-MOST_EMAILS:]))
    except (SigninsUnprotected, OSError, ValueError) as e:
        print(f"Couldn't keep a Gumroad receipt's email: {str(e)[:200]}", flush=True)
        return False
    return True


def add(cfg: dict, found: list[dict]) -> dict:
    """Keep these receipts (as find() gives them). {"added": new ones, "already": ones kept before, "emails_kept":
    False when an email couldn't be kept on this computer}. A receipt kept before is given its email, if it had
    none."""
    with _lock:
        rows = load()
        by_token = {r["token"]: r for r in rows}
        added = already = 0
        new_emails = [f["email"] for f in found if clean_email(f.get("email"))]
        kept_ok = _keep_emails(cfg, new_emails) if new_emails else True
        for f in found:
            token = f.get("token")
            if not isinstance(token, str) or not re.fullmatch(_TOKEN, token):
                continue
            mail = clean_email(f.get("email")) if kept_ok else None
            if token in by_token:
                already += 1
                if mail and not by_token[token].get("email"):
                    by_token[token]["email"] = email_id(mail)
                    by_token[token].pop("error", None)
                continue
            if len(rows) >= MOST:
                break
            row = _clean({"token": token, "added": now_iso(), "name": f.get("name"),
                          **({"email": email_id(mail)} if mail else {})})
            rows.append(row)
            by_token[token] = row
            added += 1
        save(rows)
    return {"added": added, "already": already, "emails_kept": kept_ok}


def remove(cfg: dict, which: str) -> dict | None:
    """Forget the receipt with this ref (or "all": every one). Returns what it was ({"id", "name"} of the last), or
    None when there's no such receipt. Its email stays kept for the others (cleared with the last)."""
    with _lock:
        rows = load()
        gone = rows if which == "all" else [r for r in rows if ref(r["token"]) == which]
        if not gone:
            return None
        rest = [r for r in rows if r not in gone]
        save(rest)
        if not rest:
            from . import vault
            vault.forget_key(cfg, EMAILS)
    return {"ids": [r["id"] for r in gone if r.get("id")], "tokens": [r["token"] for r in gone],
            "name": gone[-1].get("name")}


def listing() -> list[dict]:
    """The receipts as the page shows them: never their links, emails or cookies."""
    return [{"ref": ref(r["token"]), "name": r.get("name") or "", "creator": r.get("creator") or "",
             "read": r.get("read") or "", "error": r.get("error") or "", "added": r["added"],
             "has_email": bool(r.get("email")), "in_library": bool(r.get("in_library"))} for r in load()]


def tokens() -> set[str]:
    """The download tokens of the receipts kept."""
    return {r["token"] for r in load()}


def _update(token: str, **change) -> None:
    """Note what reading a receipt found (its name, purchase, cookie or problem), if it's still kept."""
    with _lock:
        rows = load()
        for r in rows:
            if r["token"] == token:
                for k, v in change.items():
                    if v is None:
                        r.pop(k, None)
                    else:
                        r[k] = v
                save([_clean(x) or x for x in rows])
                return


# ----------------------------------------------------------------------------- reading them

_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
_GONE = {"expired": "Gumroad says this purchase's access has ended",
         "rental_expired": "Gumroad says this rental has ended",
         "membership_inactive": "Gumroad says this membership isn't active, so its content isn't shown",
         "check_purchaser": "Gumroad wants the account this was bought with"}
SIGNED_OUT = ("Not signed in to Gumroad, so only the purchases you added by their receipts were read, and the rest of "
              "your Gumroad library was kept as it was. Choose Sign in to read it too.")
NEEDS_EMAIL = ("Gumroad asks for the email this was bought with. Add the receipt email itself (saved from your email "
               "as a file), not just its link, so Hoard has the email to answer with.")


class Reader:
    """One receipt's purchase on Gumroad, in a session of its own (no Gumroad sign-in), as downloader.Gumroad reads a
    library's: page() gives its download page's data, answering Gumroad's email check when it asks; file_url() is
    downloader.Gumroad's."""

    def __init__(self, cfg: dict, receipt: dict, address: str | None):
        """A session carrying only this purchase's own cookie, if Gumroad gave one before."""
        from . import egress
        self.cfg, self.receipt, self.address = cfg, receipt, address
        self.token = receipt["token"]
        self.delay = float(cfg.get("request_delay", 1.0))
        self.sess = egress.session(_AGENT)
        if receipt.get("cookie"):
            self.sess.cookies.set(COOKIE_NAME, receipt["cookie"], domain=urlparse(SITE).hostname, path="/")

    def close(self) -> None:
        """Note this purchase's cookie if Gumroad gave a new one, then close the session."""
        host = urlparse(SITE).hostname or ""
        got = next((c.value for c in self.sess.cookies if c.name == COOKIE_NAME and (c.domain or "").lstrip(".").endswith(host)), None)
        if got and _COOKIE.fullmatch(got) and got != self.receipt.get("cookie"):
            self.receipt["cookie"] = got
            _update(self.token, cookie=got)
        self.sess.cookies.clear()
        self.sess.close()

    def _get(self, url: str):
        """GET a page of Gumroad's, following its redirects on gumroad.com only."""
        from . import egress
        return egress.get(self.sess, url, SITES, timeout=60, headers={"Accept": "text/html"})

    def page(self, url: str | None = None, params: dict | None = None) -> dict:
        """This purchase's download page, as its data (component and props). Raises ReceiptError when Gumroad
        doesn't show it, saying why."""
        from . import egress
        from .common import pause
        pause(self.delay)
        r = self._get(download_link(self.token))
        data, where = self._read(r)
        if where == "confirm":
            if not self.address:
                raise ReceiptError(NEEDS_EMAIL)
            props = (data or {}).get("props") or {}
            info = props.get("confirmation_info") if isinstance(props.get("confirmation_info"), dict) else {}
            form = {"id": self.token, "destination": "download_page", "display": info.get("display") or "",
                    "email": self.address, "authenticity_token": props.get("authenticity_token") or ""}
            if not form["authenticity_token"]:
                m = re.search(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"', r.text or "")
                form["authenticity_token"] = html.unescape(m.group(1)) if m else ""
            pause(self.delay)
            sent = egress.post(self.sess, f"{SITE}/confirm-redirect", SITES, data=form,
                               headers={"Accept": "text/html", "Referer": r.url})
            sent.close()
            if not sent.is_redirect or "/confirm" in urlparse(sent.headers.get("Location", "")).path:
                raise ReceiptError("Gumroad didn't take the email on the receipt for this purchase. Add the receipt "
                                   "email it was sent to, or open its View content link once in your usual browser.")
            pause(self.delay)
            data, where = self._read(self._get(download_link(self.token)))
            if where == "confirm":
                raise ReceiptError("Gumroad asked for the email again. Try again later.")
        if where != "page":
            raise ReceiptError(where)
        return data

    def _read(self, r) -> tuple[dict | None, str]:
        """(The page's data, "page" | "confirm" | why it isn't shown), from Gumroad's answer."""
        final = urlparse(r.url).path.rstrip("/")
        if final.endswith("/confirm"):
            return _page_data(r.text), "confirm"
        last = final.rsplit("/", 1)[-1]
        if last in _GONE:
            return None, _GONE[last] + "."
        if "/login" in final or "/library" in final:
            return None, ("Gumroad shows this purchase only in the library of the account it was bought with (a bundle "
                          "does that). Sign in to Gumroad in Hoard with that account to read it.")
        if r.status_code == 404:
            return None, "Gumroad doesn't know this link any more (the purchase was refunded, or its product removed)."
        if not r.ok:
            raise RuntimeError(f"Gumroad answered HTTP {r.status_code}")
        data = _page_data(r.text)
        component = (data or {}).get("component")
        if component == "UrlRedirects/ConfirmPage":
            return data, "confirm"
        if component != "UrlRedirects/DownloadPage":
            return None, "Gumroad didn't show this purchase's download page (it may have been refunded, or Gumroad changed its site)."
        return data, "page"

    def file_url(self, page_url: str, token: str, file_id: str, fallback: str | None) -> str | None:
        """A file's signed download address, as downloader.Gumroad gets it."""
        from .downloader import Gumroad
        return Gumroad.file_url(self, page_url, token, file_id, fallback)


def reader_for(cfg: dict, token: str, addresses: dict | None = None) -> Reader | None:
    """A Reader for the receipt with this token, or None when it isn't one kept."""
    receipt = next((r for r in load() if r["token"] == token), None)
    if receipt is None:
        return None
    addresses = emails(cfg) if addresses is None and receipt.get("email") else (addresses or {})
    return Reader(cfg, receipt, addresses.get(receipt.get("email") or ""))


def item_from(props: dict, token: str) -> dict:
    """A purchase's download page data, as a library item."""
    from .library import gumroad_page, item
    from .safety import store_link
    purchase = props.get("purchase") if isinstance(props.get("purchase"), dict) else {}
    long_url = store_link("gumroad", purchase.get("product_long_url"))
    host = urlparse(long_url or "").hostname or ""
    creator_url = f"https://{host}" if re.fullmatch(r"[a-z0-9-]{1,63}\.gumroad\.com", host) and not host.startswith(("app.", "www.")) else None
    permalink = purchase.get("product_permalink")
    pid = purchase.get("id") if isinstance(purchase.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_=+/-]{1,80}", purchase.get("id")) \
        else "receipt-" + ref(token)
    link = download_link(token)
    return item("gumroad", pid, name=purchase.get("product_name") or props.get("title"),
                creator=purchase.get("seller_name"), creator_url=creator_url, url=link, download_url=link,
                page=long_url or gumroad_page(creator_url, permalink), archived=purchase.get("is_archived") is True)


def read(cfg: dict, progress=lambda m: None, only_new: bool = False, skip: set | None = None) -> tuple[list[dict], list[str]]:
    """Read each receipt's purchase from Gumroad: (the library items, the keys of purchases read before that couldn't
    be read now, to be kept as they were). only_new: only receipts never read yet (a quick refresh). skip: tokens
    already in your library (signed in), not read again. Each receipt's name, purchase and problem are noted with
    it, for the Receipts list."""
    from .common import Cancelled
    every = load()
    for r in every:   # (in your library as well: read from there, so not again here)
        if skip and r["token"] in skip and not r.get("in_library"):
            _update(r["token"], in_library=True, error=None, read=now_iso())
        elif r.get("in_library") and skip is not None and r["token"] not in skip and not only_new:
            _update(r["token"], in_library=None)
    rows = [r for r in every if not (skip and r["token"] in skip) and not (only_new and r.get("read"))]
    if not rows:
        return [], []
    addresses = emails(cfg) if any(r.get("email") for r in rows) else {}
    items, kept = [], []
    for n, r in enumerate(rows, 1):
        progress(f"Receipts, {n} of {len(rows)}")
        reader = Reader(cfg, r, addresses.get(r.get("email") or ""))
        try:
            got = item_from(reader.page().get("props") or {}, r["token"])
        except ReceiptError as e:
            _update(r["token"], error=str(e), read=now_iso())
            continue
        except (Cancelled, NotLoggedIn):
            raise
        except Exception as e:   # (the network, mostly: a purchase read before stays as it was)
            from .net import is_network_error, plain_error
            why = "Gumroad couldn't be reached" if is_network_error(e) else f"Couldn't read it: {plain_error(e)}"
            _update(r["token"], error=why[:400])
            if r.get("id"):
                kept.append(f"gumroad:{r['id']}")
            continue
        finally:
            reader.close()
        _update(r["token"], id=got["id"], name=got["name"], creator=got["creator"], read=now_iso(), error=None)
        items.append(got)
    return items, kept
