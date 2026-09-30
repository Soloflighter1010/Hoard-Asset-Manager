"""Local, privacy-first diagnostics and support-report export.

Support reports are built entirely on the user's computer. The raw diagnostic data never leaves Hoard;
only the sanitized files written into a report ZIP are intended to be shared.
"""
from __future__ import annotations

import json
import os
import platform
import re
import secrets
import shutil
import sys
import tempfile
import threading
import time
import traceback as traceback_module
import zipfile
from pathlib import Path
from typing import Iterable

from . import __version__
from . import paths
from .paths import data_dir, documents_dir, log_files
from .safety import scrub, write_file_safely


_HOOKS_INSTALLED = False
_HOOK_LOCK = threading.Lock()
_INCIDENT_LOCK = threading.Lock()


MAX_LOG_BYTES = 350 * 1024
MAX_OLD_LOG_BYTES = 175 * 1024
MAX_INCIDENTS = 40
MAX_EXPORTED_INCIDENTS = 10
MAX_PREVIEW_CHARS = 20_000
MAX_ANON_TERMS = 6_000


def install_exception_hooks() -> None:
    """Record uncaught main-thread and worker-thread exceptions locally before Python handles them normally."""
    global _HOOKS_INSTALLED
    with _HOOK_LOCK:
        if _HOOKS_INSTALLED:
            return
        previous_main = sys.excepthook
        previous_thread = getattr(threading, "excepthook", None)

        def main_hook(exc_type, exc_value, exc_tb):
            if isinstance(exc_value, BaseException):
                record_exception(exc_value, area="uncaught", task="application", include_traceback=True)
            previous_main(exc_type, exc_value, exc_tb)

        sys.excepthook = main_hook
        if previous_thread is not None:
            def thread_hook(args):
                exc = args.exc_value
                if isinstance(exc, BaseException):
                    record_exception(exc, area="uncaught-thread", task=args.thread.name, include_traceback=True)
                previous_thread(args)
            threading.excepthook = thread_hook
        _HOOKS_INSTALLED = True


def support_report_dir() -> Path:
    """A user-visible local folder for reports. Reports are exported outside Hoard's private app-data.

    This is still entirely local: Hoard never uploads the file. Keeping the export in the user's
    Documents/Hoard folder makes the result easy to find and attach to a bug report.
    """
    return documents_dir() / "Hoard" / "Support Reports"


def incidents_file() -> Path:
    """The local incident history. It never leaves Hoard except through this module's sanitizer."""
    return data_dir() / "diagnostics" / "incidents.jsonl"


def _clip(text: object, limit: int = 6000) -> str:
    value = str(text or "")
    return value if len(value) <= limit else value[:limit] + "\n[truncated]"


def _path_text(path: Path | None) -> tuple[str, str]:
    try:
        resolved = str(path.resolve()) if path is not None else ""
        return resolved, str(path) if path is not None else ""
    except (OSError, RuntimeError, ValueError):
        return str(path or ""), str(path or "")


def _replace_paths(text: str, cfg: dict | None = None) -> str:
    """Replace known local paths and generic user-path prefixes with stable placeholders."""
    replacements: list[tuple[str, str]] = []
    for path, label in ((data_dir(), "<HOARD_DATA>"), (support_report_dir(), "<SUPPORT_REPORTS>"),
                        (Path.home(), "<HOME>")):
        resolved, literal = _path_text(path)
        for value in {resolved, literal}:
            if value:
                replacements.append((value, label))
    if cfg is not None:
        try:
            from .config import root_dir
            resolved, literal = _path_text(root_dir(cfg))
            for value in {resolved, literal}:
                if value:
                    replacements.append((value, "<DOWNLOADS>"))
        except Exception:
            pass

    # Longest first so a parent such as <HOME> doesn't win before a more specific Hoard path.
    for old, new in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        text = text.replace(old, new).replace(old.replace("\\", "/"), new)
        if "\\" in old:
            # any run of separators: a path in an error message is often written with doubled backslashes
            # (C:\\Users\\name, as Python shows a path inside quotes), and in 2.8.4 those got through
            text = re.sub(re.escape(old).replace(r"\\", r"[\\\\/]+"), new, text, flags=re.I)
    # Catch conventional absolute user-profile paths that weren't discoverable above, doubled backslashes included.
    text = re.sub(r"(?i)(?:[A-Z]:[\\/]+Users[\\/]+)[^\\/'\"\r\n]+", r"<WINDOWS_USER>", text)
    text = re.sub(r"(?i)(?:/home/|/Users/)[^/'\"\r\n]+", r"<USER>", text)
    return text


def _redact_credentials(text: str) -> str:
    """Remove credential-shaped values from logs and exception text."""
    patterns = (
        (re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s,]+"), r"\1[credential]"),
        (re.compile(r"(?i)(cookie\s*[:=]\s*)[^\r\n]+"), r"\1[credential]"),
        (re.compile(r"(?i)(x-api-key\s*[:=]\s*)[^\s,]+"), r"\1[credential]"),
        (re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|refresh[_ -]?token|token|secret|password|passwd|credential)\b\s*[:=]\s*[^\s,;&]+"),
         r"\1=[credential]"),
        # "token abc123..." without a colon: only a value that looks like one (long, no spaces), so a name such as
        # "Secret Fox Avatar" keeps its words
        (re.compile(r"(?i)\b(token|secret)\b\s+[A-Za-z0-9._~+/=-]{16,}"), r"\1 [credential]"),
    )
    for pattern, replacement in patterns:
        text = pattern.sub(replacement, text)
    return text


_STORE_TAGS = ("[Booth]", "[Gumroad]", "[Jinxxy]", "[Payhip]", "[itch.io]")
_STORE_LABELS = ("Booth", "Gumroad", "Jinxxy", "Payhip", "itch.io")
_ASSET_PREFIXES = ("would update", "would download", "updated:", "saved:", "downloaded:", "downloading:", "failed:")


def _store_line(line: str) -> tuple[str, str, str] | None:
    """A "[Store] creator / asset" log line split into (lead, creator, asset), or None when it isn't one.
    Read with string operations, not a pattern: a pattern for this can take very long on a line with a long run of
    spaces, and support reports read whatever the logs hold."""
    rest = line.lstrip()
    tag = next((t for t in _STORE_TAGS if rest.startswith(t)), None)
    if tag is None:
        return None
    after = rest[len(tag):]
    body = after.lstrip()
    if body == after or not body:   # the tag needs space after it, then something
        return None
    lead = line[:len(line) - len(body)]
    slash = body.find("/", 1)   # the creator is at least one character
    while slash >= 0:
        asset = _after_slash(body[slash + 1:])
        if asset:
            return lead, body[:slash].rstrip(), asset
        slash = body.find("/", slash + 1)
    gap = len(after) - len(body)
    if body.startswith("/") and gap >= 2 and _after_slash(body[1:]):   # no creator: "[Booth]  / asset"
        return lead[:-1], lead[-1], _after_slash(body[1:])
    return None


def _summary_line(line: str) -> tuple[str, str] | None:
    """A line of the summary a sync ends with ("  - Booth: creator / product / file - why") split into (lead, the
    rest after the store's name), or None. These name products and creators too, in their own format."""
    rest = line.lstrip()
    if not rest.startswith("- "):
        return None
    body = rest[2:]
    label = next((x for x in _STORE_LABELS if body.startswith(x + ": ")), None)
    if label is None:
        return None
    item = body[len(label) + 2:]
    return line[:len(line) - len(item)], item


def _anon_summary(item: str, anon) -> str:
    """Hide the names in a summary line's item: "creator / product / file - why" (and the shorter "product /
    file - why" and "creator / product - why"). The reason after " - " stays, for what went wrong. An item without
    " / " is left to the library's own names (see _ReportSanitizer.text)."""
    parts = item.split(" / ")
    if len(parts) < 2:
        return item
    last, reason = (parts[-1].split(" - ", 1) + [None])[:2]
    first = parts[0]
    names = [anon(first, "CREATOR" if len(parts) >= 3 else None)] + [anon(p, "ASSET") for p in parts[1:-1]]
    names.append(anon(last, "ASSET"))
    return " / ".join(names) + (f" - {reason}" if reason is not None else "")


def _after_slash(text: str) -> str:
    """The asset part after a store line's slash: trimmed, or its last space if it's only spaces; "" if empty."""
    return text.strip() or text[-1:]


def _asset_line(line: str) -> tuple[str, str] | None:
    """A "saved: asset" (downloaded:, failed:, would update ...) log line split into (lead, asset), or None."""
    rest = line.lstrip()
    low = rest.lower()
    prefix = next((p for p in _ASSET_PREFIXES if low.startswith(p)), None)
    if prefix is None:
        return None
    after = rest[len(prefix):]
    body = after.strip()
    if not after or not after[0].isspace():
        return None
    if not body:   # only spaces after it: nothing to hide
        return line, ""
    lead = line[:len(line) - len(after.lstrip())]
    return lead, body


def _progress_line(line: str) -> tuple[str, str] | None:
    """A download progress bar ("name.unitypackage:  82%|####  | 1.00M/1.22M ...") split into (name, the rest), or
    None. Found with string operations (see _store_line): the file name is whatever comes before ": " and a
    percentage followed by "|"."""
    at = line.find("%|")
    if at < 0:
        return None
    colon = line.rfind(": ", 0, at)
    if colon < 0 or not line[colon + 2:at].strip().isdigit():
        return None
    return line[:colon], line[colon:]


def _anon_assets(text: str, creators: dict[str, str] | None = None, assets: dict[str, str] | None = None) -> str:
    """Hide likely purchased asset names in common Hoard log lines while keeping repeated references stable."""
    creators = creators if creators is not None else {}
    assets = assets if assets is not None else {}

    def anon(mapping: dict[str, str], value: str, label: str) -> str:
        clean = value.strip()
        if not clean or len(clean) > 240:
            return value
        key = clean.casefold()
        if key not in mapping:
            mapping[key] = f"<{label}_{len(mapping) + 1:03d}>"
        return mapping[key]

    def anon_either(value: str, label: str | None) -> str:
        """A name the summary doesn't label: a creator if it's already known as one, else a product."""
        if label is None:
            label = "CREATOR" if value.strip().casefold() in creators else "ASSET"
        return anon(creators if label == "CREATOR" else assets, value, label)

    lines: list[str] = []
    for line in text.splitlines():
        summary = _summary_line(line)
        if summary:
            lines.append(summary[0] + _anon_summary(summary[1], anon_either))
            continue
        bar = _progress_line(line)
        if bar:   # a download's progress bar starts with the file's name
            lines.append(f"{anon(assets, bar[0], 'ASSET') if bar[0].strip() else bar[0]}{bar[1]}")
            continue
        store = _store_line(line)
        if store:
            lead, creator, asset = store
            line = f"{lead}{anon(creators, creator, 'CREATOR')} / {anon(assets, asset, 'ASSET')}"
        else:
            saved = _asset_line(line)
            if saved and not saved[1].startswith("["):
                line = saved[0] + anon(assets, saved[1], "ASSET")
        lines.append(line)
    return "\n".join(lines)


class _ReportSanitizer:
    """Sanitizer used for one report, keeping the same anonymization mapping across all exported files."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.creators: dict[str, str] = {}
        self.assets: dict[str, str] = {}
        self._known: dict[str, str] = {}
        self._patterns: list[tuple[re.Pattern, dict[str, str]]] = []
        self._dirty = False

    def _add(self, value: object, label: str) -> None:
        clean = str(value or "").strip()
        if len(clean) < 3 or len(clean) > 240:
            return
        if clean.casefold() in {"unknown creator", "unknown", "asset", "product"}:
            return
        key = clean.casefold()
        mapping = self.creators if label == "CREATOR" else self.assets
        if key not in mapping:
            placeholder = f"<{label}_{len(mapping) + 1:03d}>"
            mapping[key] = placeholder
            self._known[key] = placeholder
            self._dirty = True

    def seed_library(self, lib) -> None:
        try:
            items, _stores = lib.snapshot()
        except Exception:
            return
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            self._add(item.get("creator"), "CREATOR")
            self._add(item.get("name"), "ASSET")

    def _rebuild_patterns(self) -> None:
        if not self._dirty:
            return
        self._patterns = []
        for label, mapping_source in (("CREATOR", self.creators), ("ASSET", self.assets)):
            terms = sorted(mapping_source.items(), key=lambda pair: len(pair[0]), reverse=True)
            if not terms:
                continue
            # One compiled expression per kind is much faster for large libraries than hundreds of small ones.
            pattern = re.compile("|".join(re.escape(key) for key, _placeholder in terms), re.I)
            self._patterns.append((pattern, dict(terms)))
        self._dirty = False

    def _replace_known(self, text: str) -> str:
        self._rebuild_patterns()
        for pattern, mapping in self._patterns:
            text = pattern.sub(lambda m: mapping[m.group(0).casefold()], text)
        return text

    def text(self, value: object, *, asset_names: bool = False, limit: int | None = None,
             replace_known: bool = True) -> str:
        clean = sanitize_text(value, self.cfg, asset_names=False, limit=limit)
        if not asset_names:
            return clean
        # Parse Hoard's structured log lines first; known library names already use the same mappings, and this
        # avoids running a very large library regex over every log line.
        before = len(self._known)
        clean = _anon_assets(clean, self.creators, self.assets)
        for mapping in (self.creators, self.assets):
            for key, placeholder in mapping.items():
                self._known.setdefault(key, placeholder)
        if len(self._known) != before:
            self._dirty = True
        if replace_known:
            clean = self._replace_known(clean)
        else:   # a log: the library's names are looked for only in the sync summaries, which is quick
            clean = "\n".join(self._replace_known(line) if _summary_line(line) else line for line in clean.split("\n"))
        return _sanitize_urls(clean, asset_names=True)


def _sanitize_urls(text: str, *, asset_names: bool = False) -> str:
    """Keep public store hosts useful for debugging while hiding URL paths that commonly identify purchases."""
    if not asset_names:
        return text
    known_hosts = {"booth.pm", "gumroad.com", "jinxxy.com", "payhip.com", "itch.io"}
    seen_hosts: dict[str, str] = {}

    def replace(match):
        scheme = match.group(1)
        host = match.group(2).lower()
        # Never preserve an arbitrary hostname from a user's log. A stable placeholder still lets repeated
        # references be recognized without disclosing a private/custom storefront domain.
        if host in known_hosts or any(host.endswith("." + suffix) for suffix in known_hosts):
            return f"{scheme}{host}/<path>"
        if host not in seen_hosts:
            seen_hosts[host] = f"<URL_HOST_{len(seen_hosts) + 1:03d}>"
        return f"{scheme}{seen_hosts[host]}/<path>"

    return re.sub(r"(?i)\b(https?://)([a-z0-9.-]+)(?::\d+)?(?:/[^\s<>'\"]*)?", replace, text)


def sanitize_text(text: object, cfg: dict | None = None, *, asset_names: bool = False, limit: int | None = None) -> str:
    """Sanitize text for export. Raw content is never written to the support-report ZIP."""
    value = _clip(text, limit or 100_000)
    value = _replace_paths(value, cfg)
    value = _redact_credentials(value)
    value = scrub(value)
    value = _sanitize_urls(value, asset_names=asset_names)
    if asset_names:
        value = _anon_assets(value)
    return value


def sanitize_json(obj, cfg: dict | None = None) -> object:
    """Recursively sanitize a JSON-compatible value without changing its shape."""
    if isinstance(obj, dict):
        return {str(k): sanitize_json(v, cfg) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v, cfg) for v in obj]
    if isinstance(obj, str):
        return sanitize_text(obj, cfg, asset_names=False, limit=10_000)
    return obj


def _read_tail(path: Path, max_bytes: int) -> str:
    try:
        with path.open("rb") as fh:
            size = path.stat().st_size
            if size > max_bytes:
                fh.seek(-max_bytes, os.SEEK_END)
            data = fh.read(max_bytes)
        text = data.decode("utf-8", "replace")
        if size > max_bytes:
            text = "[earlier log lines omitted]\n" + text
        return text
    except (OSError, ValueError):
        return "[log unavailable]"


def _recent_incidents() -> list[dict]:
    path = incidents_file()
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()[-MAX_INCIDENTS:]
    except OSError:
        return []
    incidents = []
    for line in lines:
        try:
            value = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict):
            incidents.append(value)
    return incidents


def _write_incidents(incidents: Iterable[dict]) -> None:
    path = incidents_file()
    payload = "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in list(incidents)[-MAX_INCIDENTS:])
    write_file_safely(path, payload)


def record_exception(exc: BaseException, *, area: str = "unknown", task: str | None = None,
                     store: str | None = None, include_traceback: bool = True) -> dict:
    """Record one local incident and return its diagnostic fields for the current job state."""
    incident = {
        "id": "H-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3).upper(),
        "time": time.time(),
        "area": str(area or "unknown")[:120],
        "task": str(task or "")[:80],
        "store": str(store or "")[:80],
        "type": type(exc).__name__[:120],
        "message": _clip(str(exc), 4000),
    }
    if include_traceback:
        frames = traceback_module.extract_tb(exc.__traceback__)
        lines = ["Traceback (most recent call last):"]
        for frame in frames:
            lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}')
        lines.append(f"{type(exc).__name__}: {str(exc)}")
        incident["traceback"] = _clip("\n".join(lines), 24_000)
    try:
        history = _recent_incidents()
        history.append(incident)
        _write_incidents(history)
    except Exception:
        pass
    return incident


def record_note(*, area: str, message: str, task: str | None = None, store: str | None = None) -> dict:
    """Record a non-exception problem locally, for failures that are intentionally handled by Hoard."""
    return record_exception(RuntimeError(message), area=area, task=task, store=store, include_traceback=False)


def _environment(cfg: dict, sanitizer: _ReportSanitizer) -> dict:
    import importlib.metadata as metadata
    try:
        playwright_version = metadata.version("playwright")
    except Exception:
        playwright_version = None
    try:
        import webview
        # pywebview has no __version__: its package details give it, and where a packaged app left those out,
        # "installed" still tells it apart from a WebView that's missing (in 2.8.4 both said "not installed")
        try:
            webview_version = metadata.version("pywebview")
        except Exception:
            webview_version = getattr(webview, "__version__", None) or "installed"
    except Exception:
        webview_version = None
    frozen = bool(getattr(__import__("sys"), "frozen", False))
    try:
        from .browser import signin_protection
        signins_note = signin_protection(cfg)
    except Exception:
        signins_note = None
    return {
        "hoard_version": __version__,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "playwright": playwright_version,
        "webview": webview_version,
        "desktop_app": frozen,
        "store_signin_protection": sanitizer.text(signins_note or "unknown"),
        "downloads_folder_exists": _downloads_exists(cfg),
    }


def _downloads_exists(cfg: dict) -> bool:
    try:
        from .config import root_dir
        return root_dir(cfg).is_dir()
    except Exception:
        return False


def _stores_summary(cfg: dict, lib, sanitizer: _ReportSanitizer) -> dict:
    try:
        _items, stores = lib.snapshot()
    except Exception:
        stores = {}
    summary = {}
    for store in ("booth", "gumroad", "jinxxy", "payhip", "itch"):
        info = stores.get(store, {}) if isinstance(stores.get(store, {}), dict) else {}
        option = cfg.get(store, {}) if isinstance(cfg.get(store), dict) else {}
        summary[store] = {
            "enabled": bool(option.get("enabled", True)),
            "library_count": info.get("count") if isinstance(info.get("count"), int) else 0,
            "source": info.get("source") if info.get("source") in ("import", "refresh") else None,
            "has_error": bool(info.get("error")),
            "error": sanitizer.text(info.get("error"), asset_names=True) if info.get("error") else None,
            **({"payhip_shop_count": len(info.get("found_shops", []))} if store == "payhip" and isinstance(info.get("found_shops"), list) else {}),
        }
    return summary


def _export_incident(incident: dict, sanitizer: _ReportSanitizer) -> dict:
    """Export incident history without carrying raw tracebacks or unsanitized exception data in JSON."""
    if not isinstance(incident, dict):
        return {}
    return {
        "id": sanitizer.text(incident.get("id")),
        "time": incident.get("time"),
        "area": sanitizer.text(incident.get("area")),
        "task": sanitizer.text(incident.get("task")),
        "store": sanitizer.text(incident.get("store")),
        "type": sanitizer.text(incident.get("type")),
        "message": sanitizer.text(incident.get("message"), asset_names=True),
        "has_traceback": bool(incident.get("traceback")),
    }


def _job_summary(job: dict, sanitizer: _ReportSanitizer) -> dict:
    if not isinstance(job, dict):
        return {}
    keep = {"running", "task", "store", "message", "error", "sync", "scheduled"}
    out = {k: job.get(k) for k in keep if k in job}
    diagnostic = job.get("diagnostic") if isinstance(job.get("diagnostic"), dict) else {}
    if diagnostic:
        out["task"] = out.get("task") or diagnostic.get("task")
        out["store"] = out.get("store") or diagnostic.get("store")
        out["error"] = out.get("error") or diagnostic.get("message")
        out["incident_id"] = diagnostic.get("id")
    if isinstance(job.get("report"), dict):
        report = job["report"]
        out["report"] = {k: report.get(k) for k in ("new_assets", "new_files", "updated", "skipped", "failed") if k in report}
        if isinstance(report.get("problems"), list):
            out["report"]["problem_count"] = len(report["problems"])
    out["message"] = sanitizer.text(out.get("message"), asset_names=True)
    out["error"] = sanitizer.text(out.get("error"), asset_names=True)
    if out.get("store"):
        out["store"] = str(out["store"])[:80]
    return sanitize_json(out, sanitizer.cfg)


def _browser_in_use(cfg: dict) -> str | None:
    """The browser Hoard really starts for sign-ins on this computer (msedge, chrome or chromium)."""
    try:
        from .browser import use_channel
        return use_channel(cfg)
    except Exception:
        return None


def _settings_summary(cfg: dict) -> dict:
    display = cfg.get("display") if isinstance(cfg.get("display"), dict) else {}
    return {
        "enabled_stores": [s for s in ("booth", "gumroad", "jinxxy", "payhip", "itch")
                           if bool((cfg.get(s) or {}).get("enabled", True))],
        "browser_channel": cfg.get("browser_channel") or "automatic",
        "browser_in_use": _browser_in_use(cfg),
        "offline_images": bool(cfg.get("offline_images", True)),
        "check_for_updates": bool(cfg.get("check_for_updates", False)),
        "auto_sync_hours": cfg.get("auto_sync_hours") if cfg.get("auto_sync_hours") in (0, 6, 12, 24, 168) else 0,
        "request_delay": cfg.get("request_delay", 1.0),
        "display_text_size": display.get("text_size", 100),
        "reduce_motion": bool(display.get("reduce_motion")),
        "pause_animations": bool(display.get("pause_animations")),
        "payhip_shop_count": len((cfg.get("payhip") or {}).get("shops") or []) if isinstance(cfg.get("payhip"), dict) else 0,
        "jinxxy_pattern_customized": ((cfg.get("jinxxy") or {}).get("item_link_pattern") !=
                                      "^/my/(inventory|purchases|library)/[^/]+/?$"),
    }


def _checks(cfg: dict) -> dict:
    try:
        __import__("webview")
        window = True
    except Exception:
        window = False
    try:
        from playwright._impl._driver import compute_driver_executable
        node, cli = compute_driver_executable()
        playwright_driver = Path(node).is_file() and Path(cli).is_file()
    except Exception:
        playwright_driver = False
    try:
        root = data_dir()
        checks = {
            "app_data_exists": root.is_dir(),
            "logs_directory_exists": (root / "logs").is_dir(),
            "playwright_driver_available": playwright_driver,
            "webview_available": window,
        }
        from .config import root_dir
        checks["downloads_directory_exists"] = root_dir(cfg).is_dir()
        return checks
    except Exception:
        return {"app_data_exists": False, "logs_directory_exists": False, "playwright_driver_available": playwright_driver}


def create_support_report(cfg: dict, lib, job: dict | None = None, notes: str = "", context: dict | None = None) -> dict:
    """Create a sanitized ZIP in the user's Support Reports folder and return its local metadata."""
    report_id = "H-" + time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3).upper()
    target_dir = support_report_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = f"Hoard-Support-Report-{time.strftime('%Y-%m-%d-%H%M%S')}-{secrets.token_hex(2)}.zip"
    final_path = target_dir / filename
    tmp_dir = Path(tempfile.mkdtemp(prefix=".hoard-report-", dir=str(target_dir)))
    try:
        effective_job = dict(job or {}) if isinstance(job, dict) else {}
        given_context = context if isinstance(context, dict) else {}
        if given_context.get("store") and not effective_job.get("store"):
            effective_job["store"] = str(given_context.get("store"))[:80]
        if given_context.get("error") and not effective_job.get("error"):
            effective_job["error"] = str(given_context.get("error"))[:4000]
        sanitizer = _ReportSanitizer(cfg)
        sanitizer.seed_library(lib)
        # this launch's log (or the newest, when Hoard has a console), and the one before it
        logs = log_files()
        current = paths.current_log if paths.current_log and paths.current_log.exists() else (logs[0] if logs else None)
        previous = next((p for p in logs if p != current), None)
        application_log = (sanitizer.text(_read_tail(current, MAX_LOG_BYTES), asset_names=True, replace_known=False)
                           if current else "[no log yet]")
        old_log_text = (sanitizer.text(_read_tail(previous, MAX_OLD_LOG_BYTES), asset_names=True, replace_known=False)
                        if previous else None)

        report = {
            "report_id": report_id,
            "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "trigger": sanitizer.text(str(given_context.get("source") or "manual"))[:40],
            "notes": sanitizer.text(notes, asset_names=True, limit=5000),
            "environment": _environment(cfg, sanitizer),
            "settings": _settings_summary(cfg),
            "checks": _checks(cfg),
            "stores": _stores_summary(cfg, lib, sanitizer),
            "job": _job_summary(effective_job, sanitizer),
        }
        report["recent_incidents"] = [_export_incident(x, sanitizer) for x in _recent_incidents()[-MAX_EXPORTED_INCIDENTS:]]

        files: dict[str, str] = {
            "README.txt": (
                "Hoard support report\n\n"
                "This ZIP was created locally by Hoard. It contains sanitized diagnostic information only.\n"
                "Hoard did not upload or transmit this report. Review the files before attaching them to a public issue.\n"
                "Passwords, cookies, API keys, account emails, local user paths and downloaded asset names are redacted.\n"
            ),
            "report.json": json.dumps(report, ensure_ascii=False, indent=2),
            "report.txt": _human_report(report),
            "application-log.txt": application_log,   # the report's own names (<CREATOR_001>...), as everywhere in it
        }
        if previous:   # the launch before
            files["application-old-log.txt"] = old_log_text or "[log unavailable]"
        diagnostic = job.get("diagnostic") if isinstance(job, dict) else None
        if isinstance(diagnostic, dict):
            files["incident.txt"] = _incident_text(diagnostic, sanitizer)
            if diagnostic.get("traceback"):
                files["traceback.txt"] = sanitizer.text(diagnostic.get("traceback"), asset_names=True, limit=24_000)

        with zipfile.ZipFile(tmp_dir / "report.zip", "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        os.replace(tmp_dir / "report.zip", final_path)

        preview = files["report.txt"][:MAX_PREVIEW_CHARS]
        return {"ok": True, "id": report_id, "filename": filename, "path": str(final_path),
                "preview": preview, "folder": str(target_dir), "file_count": len(files)}
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _incident_text(incident: dict, sanitizer: _ReportSanitizer) -> str:
    lines = [
        f"Incident: {sanitizer.text(incident.get('id'))}",
        f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(float(incident.get('time', time.time()))))}",
        f"Area: {sanitizer.text(incident.get('area'))}",
        f"Task: {sanitizer.text(incident.get('task'))}",
        f"Store: {sanitizer.text(incident.get('store'))}",
        f"Type: {sanitizer.text(incident.get('type'))}",
        f"Message: {sanitizer.text(incident.get('message'), asset_names=True)}",
    ]
    return "\n".join(lines) + "\n"


def _human_report(report: dict) -> str:
    env = report["environment"]
    lines = [
        "Hoard Support Report",
        "====================",
        f"Report ID: {report['report_id']}",
        f"Generated: {report['generated_utc']}",
        "",
        "Environment",
        "-----------",
        f"Hoard: {env.get('hoard_version')}",
        f"Platform: {env.get('platform')} {env.get('platform_release')}",
        f"Architecture: {env.get('architecture')}",
        f"Python: {env.get('python')}",
        f"Playwright: {env.get('playwright') or 'unknown'}",
        f"WebView: {env.get('webview') or 'not installed/available'}",
        f"Desktop app: {'yes' if env.get('desktop_app') else 'no'}",
        "",
        "Problem",
        "-------",
        _human_job(report.get("job") or {}),
        "",
        "Store status",
        "------------",
    ]
    for store, info in report["stores"].items():
        status = "enabled" if info["enabled"] else "disabled"
        count = info["library_count"]
        error = "; error recorded" if info["has_error"] else ""
        lines.append(f"{store}: {status}, {count} items in library{error}")
        if info.get("error"):
            lines.append(f"  error: {info['error']}")
    if report.get("notes"):
        lines += ["", "User notes", "----------", report["notes"]]
    lines += ["", "Privacy", "-------", "This report was sanitized locally. No report data was uploaded by Hoard."]
    return "\n".join(lines) + "\n"


def _human_job(job: dict) -> str:
    if not job:
        return "No active or recently completed job was available."
    parts = [f"Task: {job.get('task') or 'none'}"]
    if job.get("store"):
        parts.append(f"Store: {job['store']}")
    if job.get("error"):
        parts.append(f"Error: {job['error']}")
    elif job.get("message"):
        parts.append(f"Message: {job['message']}")
    report = job.get("report") or {}
    if report:
        parts.append("Summary: " + ", ".join(f"{k}={report.get(k)}" for k in ("new_assets", "new_files", "updated", "skipped", "failed") if k in report))
    return "\n".join(parts)
