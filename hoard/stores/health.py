"""Store health with fixed failure codes; account details never enter reports."""
from __future__ import annotations

import json
from urllib.parse import urlencode

from .. import storage
from ..common import now_iso
from ..paths import data_dir

PROBLEMS = {
    "signin": "Sign in again, then retry.",
    "blocked": "The store blocked its automated browser.",
    "network": "The store could not be reached.",
    "layout": "The store page could not be read.",
    "empty": "The store returned no items; the previous library was kept.",
    "partial": "Some items could not be read or downloaded.",
}
OPERATIONS = ("library", "wishlists", "list_files", "download_file", "check_updates")


def classify(error: Exception) -> str:
    """Use exception types, never their possibly private message or URL, for a report."""
    from ..common import NotLoggedIn
    from ..browser import Blocked
    from ..net import is_network_error
    if isinstance(error, NotLoggedIn):
        return "signin"
    if isinstance(error, Blocked):
        return "blocked"
    return "network" if is_network_error(error) else "layout"


def record(store: str, operation: str, problem: str = "") -> None:
    """Save only a known store, operation, timestamp and fixed failure category."""
    from . import adapters
    if store not in adapters() or operation not in OPERATIONS or problem and problem not in PROBLEMS:
        raise ValueError("unknown store health category")
    path = data_dir() / "store-health.json"
    with storage.metadata_lock:
        data = storage.read_document(path) if storage.exists(path) else {}
        item = data.setdefault(store, {})
        previous = item.get(operation, {})
        item[operation] = {"last_attempt": now_iso(), "last_success": previous.get("last_success", ""), "problem": problem}
        if not problem:
            item[operation]["last_success"] = item[operation]["last_attempt"]
        storage.write_document(path, json.dumps(data))


def snapshot() -> dict:
    """Health shown in Stores, including an account-free, prefilled issue link on failure."""
    from . import adapters
    from .. import __version__
    path = data_dir() / "store-health.json"
    data = storage.read_document(path) if storage.exists(path) else {}
    result = {}
    for store, adapter in adapters().items():
        operations = {}
        for operation in OPERATIONS:
            info = data.get(store, {}).get(operation)
            if not isinstance(info, dict):
                continue
            problem = info.get("problem") if info.get("problem") in PROBLEMS else ""
            clean = {k: info.get(k, "") for k in ("last_attempt", "last_success")}
            clean.update(problem=problem, message=PROBLEMS.get(problem, ""))
            if problem:
                body = f"Hoard: {__version__}\nStore: {adapter.label}\nOperation: {operation}\nFailure: {problem}\n\nWhat happened:\n"
                clean["report_url"] = "https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?" + urlencode({
                    "title": f"[Store]: {adapter.label} {operation}", "body": body})
            operations[operation] = clean
        result[store] = {"operations": operations, "capabilities": adapter.capabilities}
    return result
