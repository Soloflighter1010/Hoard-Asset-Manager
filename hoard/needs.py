"""What a download needs (Downloads, What it needs; Hoard for Unity's warning before importing).

Unity names assets by GUID: a material names its shader's GUID, a prefab each component's script's, and an outfit
made for an avatar names that avatar's models and prefabs. So a package's text assets list what it uses, and a GUID it
names that isn't in the package is something it needs from elsewhere. Hoard knows the GUIDs of the tools avatar
assets most often need (known_tools.json, built by scripts/build_known_tools.py from each tool's own repository), and
of every package you've downloaded; what neither covers is only counted.

Every downloaded .unitypackage, and each one in a .zip, is read once in the background (NeedsReader), a file at a
time and never while a job runs, and what it holds and names is kept in package-needs.json (sealed, as Hoard's other
data is): read again only when the file changes.
"""
from __future__ import annotations

import json
import os
import re
import stat
import threading
import time
import zipfile
import zlib
from pathlib import Path

from . import packages
from .paths import data_dir
from .safety import DataFileError, check_seal, read_json_file, remember_sealed, seal, write_file_safely

FORMAT = {"format": "hoard-package-needs", "version": 2}   # 2: what code each package holds (issue #303)
KNOWN_FILE = Path(__file__).resolve().parent / "known_tools.json"
MAX_FILES = 50_000
MAX_LISTED = 5          # other products named as needed, the most needed first
# A weak match isn't named (it's counted with what Hoard doesn't know): files this many other products carry too are a
# creator's shared files, which say nothing about which product it needs; and a few files from another product by the
# same creator are most often their own files used again (a texture a reused material still names), not a need.
SHARED_BY = 3
SAME_CREATOR_MIN = 5
# Naming the other products a product needs is off for now (4.0.3): telling a real need (an outfit's avatar) from
# files creators share and reuse wasn't reliable enough. What's needed from elsewhere is only said to be there.
MATCH_PRODUCTS = False
BUILT_IN = "0000000000000000"   # Unity's own resources (the default material, built-in shaders): never needed


def index_file() -> Path:
    """Where what each package names and has is kept (package-needs.json), so packages are read once."""
    return data_dir() / "package-needs.json"


_KNOWN: dict | None = None


def known() -> dict:
    """{"tools": {key: {"name", "url"}}, "guids": {guid: [key] or [key, version]}}: the tools Hoard knows by GUID."""
    global _KNOWN
    if _KNOWN is None:
        try:
            data = json.loads(KNOWN_FILE.read_text("utf-8"))
            _KNOWN = {"tools": data["tools"], "guids": data["guids"]}
        except (OSError, ValueError, KeyError, TypeError):
            _KNOWN = {"tools": {}, "guids": {}}
    return _KNOWN


# ----------------------------------------------------------------------------- reading one file

def _clean(guids) -> list[str]:
    """GUIDs as kept: well-formed, each once, sorted, Unity's own built-in ones left out."""
    return sorted(g for g in guids if isinstance(g, str) and packages.GUID.fullmatch(g) and not g.startswith(BUILT_IN))


def _one(stream, tools: dict) -> dict:
    """What one .unitypackage has (its assets' GUIDs), names that it doesn't have (what it needs from elsewhere), and
    the code it holds (packages.code_in, without each file's marks: issue #303)."""
    refs: set = set()
    seen: dict = {}
    assets = packages.read_unitypackage(stream, refs=refs, code=seen)
    own = set(assets)
    return {"own": _clean(own), "refs": _clean(refs - own), "code": packages._summary(packages.code_in(assets, seen, tools))}


def read_file(path: Path) -> dict:
    """What one download holds and names: {"size", "mtime_ns", "packages": [{"member" (its path in a .zip, or None),
    "own", "refs", "code"}], "loose" (in a .zip, the scripts and plugins loose in it), "error"}."""
    st = os.stat(path, follow_symlinks=False)
    entry = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "packages": [], "error": None}
    tools = packages.known_code_tools()
    if not stat.S_ISREG(st.st_mode):
        entry["error"] = "not a plain file"
        return entry
    try:
        if path.name.lower().endswith(".zip"):
            with zipfile.ZipFile(path) as zf:
                loose = {"scripts": 0, "plugins": 0, "editor": 0}
                entry["loose"] = loose
                for info in zf.infolist()[:packages.MAX_ZIP_MEMBERS]:
                    name = packages.zip_name(info)
                    kind = None if info.is_dir() else packages.code_kind(name)
                    if kind:
                        loose[kind + "s"] += 1
                        loose["editor"] += packages._in_editor_folder(name)
                    if info.is_dir() or not name.lower().endswith(".unitypackage") or info.flag_bits & 0x1:
                        continue
                    try:
                        with zf.open(info) as member:
                            entry["packages"].append({"member": name, **_one(member, tools)})
                    except (packages.NotAPackage, zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError, zlib.error):
                        continue
                    if len(entry["packages"]) >= packages.MAX_ZIP_PACKAGES:
                        break
        else:
            with open(path, "rb") as fh:
                entry["packages"].append({"member": None, **_one(fh, tools)})
    except (packages.NotAPackage, zipfile.BadZipFile, zipfile.LargeZipFile, OSError, NotImplementedError) as e:
        entry["error"] = str(e)[:200] or e.__class__.__name__
    return entry


# ----------------------------------------------------------------------------- code in a download (issue #303)

def _clean_code(value) -> dict:
    """A package's code as kept (packages.code_in, without its items): counts, tools' names and folders, checked."""
    from .safety import clean_text
    v = value if isinstance(value, dict) else {}

    def count(k):
        """One of its counts, or 0."""
        n = v.get(k)
        return n if isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 10 ** 7 else 0
    tools = v.get("tools") if isinstance(v.get("tools"), dict) else {}
    folders = v.get("folders") if isinstance(v.get("folders"), list) else []
    return {"scripts": count("scripts"), "plugins": count("plugins"), "editor": count("editor"),
            "tools": {clean_text(t, 100): n for t, n in list(tools.items())[:20]
                      if isinstance(t, str) and clean_text(t, 100) and isinstance(n, int) and n > 0},
            "folders": [f for f in (clean_text(x, 300) for x in folders[:8] if isinstance(x, str)) if f]}


def file_code(entry: dict | None) -> dict | None:
    """What code a download holds, all of its packages together (and in a .zip, what's loose in it): {"scripts",
    "plugins", "editor", "tools": {a known tool's name: how many}, "folders" (where the rest goes), "loose": {"scripts",
    "plugins", "editor"}}; None when it holds none, or hasn't been read yet."""
    if not entry:
        return None
    out = {"scripts": 0, "plugins": 0, "editor": 0, "tools": {}, "folders": [], "loose": dict(entry.get("loose") or {})}
    for p in entry.get("packages") or []:
        c = _clean_code(p.get("code"))
        for k in ("scripts", "plugins", "editor"):
            out[k] += c[k]
        for t, n in c["tools"].items():
            out["tools"][t] = out["tools"].get(t, 0) + n
        out["folders"] += [f for f in c["folders"] if f not in out["folders"]][:max(0, 8 - len(out["folders"]))]
    loose = out["loose"]
    if not (out["scripts"] or out["plugins"] or loose.get("scripts") or loose.get("plugins")):
        return None
    return out


# ----------------------------------------------------------------------------- the index

class NeedsIndex:
    """package-needs.json: {absolute path: read_file()} for every package Hoard has read. Safe across threads."""

    def __init__(self, path: Path | None = None):
        self.path = path or index_file()
        self.lock = threading.Lock()
        self.files: dict[str, dict] = {}
        self.changed_at = 0.0   # when what it knows last changed (time.monotonic), for whoever keeps answers from it
        if self.path.is_file():
            try:
                raw = read_json_file(self.path, 256 * 1024 * 1024)
                if (check_seal(raw, self.path) in ("sealed",) and raw.get("version") == FORMAT["version"]
                        and isinstance(raw.get("files"), dict)):   # (an older version's: every file read again, once)
                    self.files = {k: v for k, v in list(raw["files"].items())[:MAX_FILES] if self._valid(k, v)}
            except (DataFileError, OSError, AttributeError):
                pass   # read again from the files themselves

    @staticmethod
    def _valid(path, entry) -> bool:
        """Is a kept entry as Hoard writes it (an absolute path, the file's size and time, and its packages' GUIDs)?"""
        if not isinstance(path, str) or not os.path.isabs(path) or not isinstance(entry, dict):
            return False
        if not isinstance(entry.get("size"), int) or not isinstance(entry.get("mtime_ns"), int):
            return False
        pk = entry.get("packages")
        if not isinstance(pk, list):
            return False
        for p in pk:
            if not isinstance(p, dict) or not isinstance(p.get("own"), list) or not isinstance(p.get("refs"), list):
                return False
            p["own"], p["refs"] = _clean(p["own"]), _clean(p["refs"])
            p["code"] = _clean_code(p.get("code"))
        if "loose" in entry:
            entry["loose"] = {k: v for k, v in _clean_code(entry["loose"]).items() if k in ("scripts", "plugins", "editor")}
        return True

    def fresh(self, path: str) -> bool:
        """Is what's known about this file still true (same size and time)?"""
        with self.lock:
            e = self.files.get(path)
        if e is None:
            return False
        try:
            st = os.stat(path, follow_symlinks=False)
        except OSError:
            return False
        return e["size"] == st.st_size and e["mtime_ns"] == st.st_mtime_ns

    def put(self, path: str, entry: dict) -> None:
        """Keep what a file has and names."""
        with self.lock:
            self.files[path] = entry
            self.changed_at = time.monotonic()

    def keep_only(self, paths: set) -> None:
        """Forget files that are no longer among the downloads."""
        with self.lock:
            gone = [p for p in self.files if p not in paths]
            for p in gone:
                del self.files[p]
            if gone:
                self.changed_at = time.monotonic()

    def get(self, path: str) -> dict | None:
        """What a file has and names, if it's been read."""
        with self.lock:
            return self.files.get(path)

    def save(self) -> None:
        """Write what's kept, sealed."""
        with self.lock:
            data = json.dumps(seal({**FORMAT, "files": self.files}), separators=(",", ":"), ensure_ascii=False)
        write_file_safely(self.path, data)
        remember_sealed(self.path)


def package_files(assets: list[dict]) -> list[tuple[str, dict]]:
    """(absolute path, product) for every .unitypackage and .zip in the downloads index that's on disk."""
    out = []
    for a in assets:
        for f in a.get("files") or []:
            if not f.get("missing") and packages.can_look_inside(f.get("path") or ""):
                out.append((os.path.join(a["abs_folder"], *f["path"].split("/")), a))
    return out


# ----------------------------------------------------------------------------- what each product needs

def work_out(assets: list[dict], index: NeedsIndex) -> dict:
    """{product id (in the downloads index): {"tools": [{"key", "name", "url", "versions", "guids"}], "products":
    [{"id", "name", "creator", "store", "folder", "guids"}], "unknown": how many GUIDs nothing here has, "read":
    whether every package of it has been read}} for every product with a package."""
    tools, by_guid = known()["tools"], known()["guids"]
    own: dict[int, set] = {}
    refs: dict[int, set] = {}
    unread: set = set()
    for path, a in package_files(assets):
        e = index.get(path)
        if e is None or not index.fresh(path):
            unread.add(a["id"])
            continue
        for p in e["packages"]:
            own.setdefault(a["id"], set()).update(p["own"])
            refs.setdefault(a["id"], set()).update(p["refs"])
    providers: dict[str, set] = {}   # guid -> the products whose packages hold it
    for pid, guids in own.items():
        for g in guids:
            providers.setdefault(g, set()).add(pid)
    by_id = {a["id"]: a for a in assets}
    out = {}
    for a in assets:
        pid = a["id"]
        if pid not in refs and pid not in unread:
            continue
        need = refs.get(pid, set()) - own.get(pid, set())
        found_tools: dict[str, dict] = {}
        rest = set()
        for g in need:
            k = by_guid.get(g)
            if k and k[0] in tools:
                t = found_tools.setdefault(k[0], {"key": k[0], "name": tools[k[0]]["name"], "url": tools[k[0]]["url"],
                                                  "common": bool(tools[k[0]].get("common")), "versions": set(), "guids": set()})
                t["guids"].add(g)
                if len(k) > 1 and k[1]:
                    t["versions"].add(k[1])
            else:
                rest.add(g)
        counts: dict[int, set] = {}
        holders: dict[str, set] = {}   # guid -> the products (as who made them and what they're called) that carry it
        for g in rest if MATCH_PRODUCTS else ():   # (off: each is counted with what Hoard doesn't know)
            for other in providers.get(g, ()):
                if other != pid and by_id[other]["tag_key"] != a["tag_key"] and _who(by_id[other]) != _who(a):
                    counts.setdefault(other, set()).add(g)   # (a copy on another store isn't another product)
                    holders.setdefault(g, set()).add(_who(by_id[other]))

        def weak(o: int) -> bool:
            """Is a product's match too weak to count: only GUIDs many products carry, or a few shared with another of
            the same creator's?"""
            shared = all(len(holders[g]) >= SHARED_BY for g in counts[o])
            maker = _who(by_id[o])[0]
            return shared or (bool(maker) and maker == _who(a)[0] and len(counts[o]) < SAME_CREATOR_MIN)
        kept = [o for o in counts if not weak(o)]
        listed = sorted(kept, key=lambda o: (-len(counts[o]), by_id[o]["name"].lower()))[:MAX_LISTED]
        covered = set().union(*(counts[o] for o in kept)) if kept else set()
        out[pid] = {
            "tools": [{**t, "versions": sorted(t["versions"], key=_version_key), "guids": sorted(t["guids"])}
                      for t in sorted(found_tools.values(), key=lambda t: (t["common"], t["name"].lower()))],
            "products": [{"id": o, "name": by_id[o]["name"], "creator": by_id[o]["creator"], "store": by_id[o]["store"],
                          "folder": by_id[o].get("catalog_folder"), "guids": sorted(counts[o])} for o in listed],
            "unknown": len(rest - covered),
            "read": pid not in unread,
        }
    return out


def _who(a: dict) -> tuple[str, str]:
    """A product as who made it and what it's called, written plainly: the same product bought on two stores is one."""
    plain = lambda s: re.sub(r"\W+", "", str(s or "").casefold())
    return plain(a.get("creator")), plain(a.get("name"))


MAX_CATALOG_GUIDS = 50   # GUIDs listed for one need in catalog.json: enough for Hoard for Unity to tell if it's there
VERSION = re.compile(r"\d{1,3}\.\d{1,3}")


def tool_urls() -> set:
    """The websites of the tools Hoard knows (lilToon, Modular Avatar...)."""
    return {t["url"] for t in known()["tools"].values()}


def add_to_catalog(root: Path, catalog: list[dict], index: NeedsIndex | None = None) -> None:
    """Give each catalog.json entry what it needs ("needs", docs/DATA-FORMATS.md), from what's been read so far:
    [{"kind": "tool", "name", "url", "versions", "guids"} or {"kind": "product", "name", "creator", "store", "folder",
    "guids"}]. Hoard for Unity says which of them aren't in the project before importing."""
    from .safety import valid_rel
    from .tags import tag_key
    index = index or NeedsIndex()
    if not index.files:
        return
    assets = []
    for i, e in enumerate(catalog):
        base = Path(e["location"]) if e.get("location") else (Path(e["library"]) if e.get("library") else root) / e["folder"]
        assets.append({"id": i, "abs_folder": str(base), "files": [{"path": f} for f in e["files"]],
                       "tag_key": tag_key(e["store"], e["name"]), "name": e["name"], "creator": e["creator"],
                       "store": e["store"], "catalog_folder": e["folder"]})
    for i, a in enumerate(assets):   # what code its packages hold, for Hoard for Unity's warning (issue #303)
        found = [c for c in (file_code(index.get(p)) for p, _a in package_files([a])) if c]
        if found:
            catalog[i]["code"] = {"scripts": sum(c["scripts"] for c in found), "plugins": sum(c["plugins"] for c in found),
                                  "editor": sum(c["editor"] for c in found),
                                  "tools": sorted({t for c in found for t in c["tools"]})[:20],
                                  "folders": list(dict.fromkeys(f for c in found for f in c["folders"] if valid_rel(f)))[:8]}
            if not (catalog[i]["code"]["scripts"] or catalog[i]["code"]["plugins"]):
                del catalog[i]["code"]   # (only loose in a .zip: not imported from it)
    for i, n in work_out(assets, index).items():
        listed = [{"kind": "tool", "name": t["name"], "url": t["url"], "versions": t["versions"],
                   "guids": t["guids"][:MAX_CATALOG_GUIDS]} for t in n["tools"]]
        listed += [{"kind": "product", "name": o["name"], "creator": o["creator"], "store": o["store"],
                    "folder": o["folder"], "guids": o["guids"][:MAX_CATALOG_GUIDS]} for o in n["products"]]
        if listed:
            catalog[i]["needs"] = listed


def valid_code(value) -> bool:
    """A catalog entry's "code" as Hoard writes it (docs/DATA-FORMATS.md): counts, tools' names and folders."""
    from .safety import clean_text, valid_rel
    if not isinstance(value, dict) or set(value) != {"scripts", "plugins", "editor", "tools", "folders"}:
        return False
    counts = [value[k] for k in ("scripts", "plugins", "editor")]
    if not all(isinstance(n, int) and not isinstance(n, bool) and 0 <= n < 10 ** 7 for n in counts) or not (counts[0] or counts[1]):
        return False
    if value["editor"] > value["scripts"] + value["plugins"]:
        return False
    if not isinstance(value["tools"], list) or len(value["tools"]) > 20 or not all(
            isinstance(t, str) and t and t == clean_text(t, 100) for t in value["tools"]):
        return False
    return isinstance(value["folders"], list) and len(value["folders"]) <= 8 and all(valid_rel(f) for f in value["folders"])


def valid_needs(value, stores) -> bool:
    """A catalog entry's "needs" as Hoard writes it (the promises in docs/DATA-FORMATS.md)."""
    from .safety import clean_text, valid_rel
    if not isinstance(value, list) or not 0 < len(value) <= 30:
        return False
    for n in value:
        if not isinstance(n, dict) or n.get("kind") not in ("tool", "product"):
            return False
        guids = n.get("guids")
        if (not isinstance(guids, list) or not 0 < len(guids) <= MAX_CATALOG_GUIDS
                or not all(isinstance(g, str) and packages.GUID.fullmatch(g) for g in guids)):
            return False
        if not isinstance(n.get("name"), str) or not n["name"] or n["name"] != clean_text(n["name"], 200):
            return False
        if n["kind"] == "tool":
            if n.get("url") not in tool_urls() or not isinstance(n.get("versions"), list) or len(n["versions"]) > 30:
                return False
            if not all(isinstance(v, str) and VERSION.fullmatch(v) for v in n["versions"]):
                return False
        elif (n.get("store") not in stores or not valid_rel(n.get("folder"))
              or not isinstance(n.get("creator"), str) or n["creator"] != clean_text(n["creator"], 200) or not n["creator"]):
            return False
    return True


def _version_key(v: str):
    """A version's numbers, to sort by (1.10 after 1.9)."""
    try:
        return [int(n) for n in v.split(".")]
    except ValueError:
        return [0]


# ----------------------------------------------------------------------------- reading in the background

class NeedsReader:
    """Reads every downloaded package that hasn't been read (or has changed since), one file at a time, while Hoard
    runs: never while a job does (the disk is busy enough), and saying how far it's got."""

    IDLE = 600          # seconds between looks when there's nothing to read
    SAVE_EVERY = 30     # seconds between saves of the index while reading

    def __init__(self, index: NeedsIndex, assets, busy):
        """assets(): the downloads index's products; busy(): is a job running?"""
        self.index, self.assets, self.busy = index, assets, busy
        self.wake = threading.Event()
        self.state = {"reading": False, "done": 0, "total": 0}
        self.on_read = None   # called (without arguments) after something new was read: the catalog can be rebuilt

    def poke(self) -> None:
        """Look again now (after a download, a rescan or a move)."""
        self.wake.set()

    def run_once(self, stop: threading.Event | None = None) -> int:
        """Read what needs reading. Returns how many files were read."""
        items = package_files(self.assets())
        self.index.keep_only({p for p, _ in items})
        todo = [p for p, _ in items if not self.index.fresh(p)]
        self.state.update(total=len(todo), done=0, reading=bool(todo))
        read, saved = 0, time.monotonic()
        try:
            for path in todo:
                while self.busy() and not (stop and stop.is_set()):
                    time.sleep(2)
                if stop and stop.is_set():
                    break
                try:
                    self.index.put(path, read_file(Path(path)))
                    read += 1
                except OSError:
                    pass   # gone since: forgotten next time
                self.state["done"] += 1
                if time.monotonic() - saved > self.SAVE_EVERY:
                    self.index.save()
                    saved = time.monotonic()
        finally:
            self.state["reading"] = False
            if read or not self.index.path.exists():
                self.index.save()
        if read and self.on_read:
            self.on_read()
        return read

    def run_forever(self, stop: threading.Event) -> None:
        """Read new and changed packages in the background, a little at a time, until Hoard stops."""
        time.sleep(20)   # after Hoard has started up
        while not stop.is_set():
            try:
                self.run_once(stop)
            except Exception as e:   # never takes Hoard down: tried again later
                print(f"Reading packages for What it needs stopped: {e}", flush=True)
            self.wake.wait(self.IDLE)
            self.wake.clear()
