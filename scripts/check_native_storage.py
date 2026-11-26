"""The installed app keeps its metadata in SQLite (#320, #348): checked on the app as a release hands it out.

    python scripts/check_native_storage.py PACKAGE [--legacy-root DIR ...]

PACKAGE is Windows' installer (Hoard_*-setup.exe: installed silently into a folder of its own, and uninstalled
after), a Mac's disk image (Hoard_*.dmg: its Hoard.app copied out, as you would) or Linux's AppImage (unpacked each
start, as CI has no FUSE; under xvfb-run in CI). It runs with a data folder of its own (HOARD_DATA_DIR) and, as the
app would be for anyone, nothing saying where to keep its metadata. It checks that:

1. a home kept by a Hoard that kept everything in JSON (as beta 12 did) moves into metadata.sqlite3 as the app
   starts: every document, with the originals kept beside it (.pre-sqlite-v1) and JSON copies that Hoard can read;
2. killed outright (the window and Hoard's server with it) part way through that move, in the middle of a write, or
   just as it's ready, nothing is lost: every original is still there, and the next start finishes the move;
3. each --legacy-root's Hoard (its source, kept in JSON with HOARD_METADATA=json) reads that home after it, and saves
   edits (a setting, a product's name, a note), and the app brings them in at its next start, also when it's
   killed in the middle of bringing them in;
4. with its sealing key (integrity.key) lost, or another's in its place, it starts: the database is kept aside as it
   was (metadata.before-recovery-*.sqlite3), what's in it is kept but no longer trusted, and automatic work is off.

--source runs Hoard's own source in place of an installed app (its server, as the window runs it), to try this out
without building one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import sqlite3
import string
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WAIT = 180      # seconds a start may take (unpacking an AppImage, then Hoard's server starting)
PRODUCTS = 4000  # enough for the move to take a moment, so a kill can land in the middle of it
SEEDED = ("config.json", "library.json", "tags.json", "sets.json")
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"


def name_of(n: int) -> str:
    """A product's name: letters, never numbers, so a JSON-only Hoard's tag keys (which leave out version numbers)
    tell every product apart, as they do for most people's."""
    letters = ""
    n += 26 * 26
    while n:
        n, r = divmod(n, 26)
        letters = string.ascii_lowercase[r] + letters
    return f"Hair Pack {letters.capitalize()}"


# ---- the fixture, written and read by this checkout's source in a process of its own

def worker(phase: str, home: Path, expect: dict) -> None:
    """seed: a JSON-only home, as beta 12 kept it. verify: read back through SQLite as Hoard reads it. automatic:
    automatic work turned on (syncs and routine checks every 6 hours), saved through SQLite."""
    os.environ.update(HOARD_DATA_DIR=str(home), HOARD_METADATA="json" if phase == "seed" else "")
    sys.path.insert(0, str(ROOT))
    from hoard import config, library, paths, storage
    from hoard.sets import SetStore
    from hoard.tags import TagStore, tag_key
    if phase == "seed":
        assert not storage.enabled()
        cfg = config.load_config()
        cfg.update(setup_done=True, new_days=7, check_for_updates=False, auto_sync_hours=0, routine_hours=0,
                   notify_found=False, root=str(home.parent / "downloads"))
        config.save_config(cfg)
        lib = library.Library(paths.LIBRARY_FILE)
        lib.data = {"items": [library.item("booth", str(1000 + n), name=name_of(n), creator=f"Maker {n % 40}",
                                           url=f"https://booth.pm/en/items/{1000 + n}") for n in range(PRODUCTS)],
                    "stores": {"booth": {"count": PRODUCTS}}}
        lib.save()
        keys = [tag_key("booth", p["name"], p["id"]) for p in lib.data["items"]]
        assert len(set(keys)) == PRODUCTS
        tags = TagStore()
        tags._save({**TagStore.empty(), "tags": {"hair": {"match": None}},
                    "items": {k: ["hair"] for k in keys}, "notes": {keys[0]: "first", keys[1]: "second"}})
        SetStore()._save({"sets": [{"id": "outfit1", "name": "Outfit", "items": keys[:50]}]})
        return
    assert storage.enabled(), "HOARD_METADATA unset should mean SQLite"
    if phase == "automatic":   # (turned on, so only a recovery can turn it off: recovered())
        config.save_config({**config.load_config(), "auto_sync_hours": 6, "routine_hours": 6})
        storage.close_all()
        return
    cfg = config.load_config()
    assert cfg["new_days"] == expect["new_days"], cfg["new_days"]
    items = library.Library(paths.LIBRARY_FILE).data["items"]
    assert len(items) == PRODUCTS, len(items)
    names = [p["name"] for p in items]
    for index, name in expect["names"].items():
        assert names[int(index)] == name, (index, names[int(index)], name)
    keys = [tag_key("booth", p["name"], p["id"]) for p in items]
    data = TagStore().load()
    for index, note in expect["notes"].items():
        assert data["notes"].get(keys[int(index)]) == note, (index, data["notes"].get(keys[int(index)]), note)
    assert len(data["notes"]) == len(expect["notes"]), data["notes"]
    assert sum(1 for k in keys if data["items"].get(k) == ["hair"]) == PRODUCTS
    outfit = SetStore().load()["sets"][0]
    assert outfit["name"] == "Outfit" and outfit["items"] == keys[:50]
    storage.close_all()


def run_worker(phase: str, home: Path, expect: dict | None = None) -> None:
    """A worker phase, in a fresh interpreter (so nothing it opened stays open here)."""
    result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", phase, "--home", str(home),
                             "--expect", json.dumps(expect or {})], cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", timeout=300, env={k: v for k, v in os.environ.items()
                                                                 if not k.startswith("HOARD_")})
    if result.returncode:
        raise AssertionError(f"{phase} failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")


# A JSON-only Hoard after the move: it reads the home (the JSON copies the app keeps), and saves edits to it.
LEGACY = r'''
import json, sys
from pathlib import Path
from hoard import __version__, config, library, paths, tags
assert Path(tags.__file__).resolve().is_relative_to(Path.cwd()), tags.__file__
expect, edit = json.loads(sys.argv[1]), json.loads(sys.argv[2])
key = getattr(tags, "legacy_tag_key", None) or (lambda store, name: tags.tag_key(store, name))
cfg = config.load_config()
assert cfg["setup_done"] and cfg["new_days"] == expect["new_days"], cfg.get("new_days")
lib = library.Library(paths.LIBRARY_FILE)
items = lib.data["items"]
assert len(items) == expect["count"], len(items)
for index, name in expect["names"].items():
    assert items[int(index)]["name"] == name, (index, items[int(index)]["name"])
store = tags.TagStore()
data = store.load()
for index, note in expect["notes"].items():
    found = data["notes"].get(key("booth", items[int(index)]["name"]))
    assert found == note, (index, found, note)
data["notes"][key("booth", items[edit["note_on"]]["name"])] = edit["note"]
store._save(data)
config.save_config({**cfg, "new_days": edit["new_days"]})
items[edit["rename"]]["name"] = edit["name"]
lib.save()
print(json.dumps({"release": __version__, "read_after_sqlite": "passed", "edits": "saved"}))
'''


def legacy(root: Path, home: Path, expect: dict, edit: dict) -> str:
    """Run a JSON-only Hoard's source on the home: it checks what it reads, then saves the edits."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("HOARD_")}
    env.update(HOARD_DATA_DIR=str(home), HOARD_METADATA="json", PYTHONPATH=str(root))
    result = subprocess.run([sys.executable, "-c", LEGACY, json.dumps(expect), json.dumps(edit)], cwd=root, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=300)
    if result.returncode:
        raise AssertionError(f"the JSON-only Hoard in {root} failed:\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
    return result.stdout.strip()


# ---- what's on disk

def digests(home: Path) -> dict:
    """Each seeded document's bytes, as hashes."""
    return {name: hashlib.sha256((home / name).read_bytes()).hexdigest() for name in SEEDED}


def state(home: Path) -> str:
    """How the database was left: its version (from its header) and whether a write was cut off (its journal)."""
    db = home / "metadata.sqlite3"
    if not db.exists():
        return "no database yet"
    with open(db, "rb") as f:
        head = f.read(100)
    version = int.from_bytes(head[60:64], "big") if len(head) == 100 else 0
    cut = (home / "metadata.sqlite3-journal").exists()
    return f"database version {version}" + (", a write cut off (its journal left behind)" if cut else "")


def originals_kept(home: Path, before: dict) -> None:
    """Every original document is still there, as it was: in its place, or put aside by the move."""
    for name, digest in before.items():
        found = [p for p in (home / name, home / (name + ".pre-sqlite-v1"))
                 if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == digest]
        assert found, f"{name}: the original is gone (neither {name} nor {name}.pre-sqlite-v1 has it)"


def documents(home: Path) -> tuple[int, dict, dict]:
    """What the app's database holds, read as it is (not through Hoard, which would bring in edits itself): its
    version, each document, and whether each is trusted."""
    connection = sqlite3.connect((home / "metadata.sqlite3").as_uri() + "?mode=ro", uri=True)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        rows = connection.execute("SELECT name, body, trust FROM documents").fetchall()
        return version, {name: json.loads(body) for name, body, _ in rows}, {name: trust for name, _, trust in rows}
    finally:
        connection.close()


def moved(home: Path, before: dict, expect: dict, recovering: bool = False) -> None:
    """The app moved the home into SQLite, and holds what's expected, with the originals and JSON copies kept. (A
    recovery keeps the JSON copies sealed with the lost key aside too, as conflict copies.)"""
    version, docs, _ = documents(home)
    assert version == 2, f"the database is at version {version}"
    assert set(SEEDED) <= set(docs), sorted(docs)
    assert docs["config.json"]["new_days"] == expect["new_days"], docs["config.json"]["new_days"]
    items = docs["library.json"]["items"]
    assert len(items) == PRODUCTS, len(items)
    for index, name in expect["names"].items():
        assert items[int(index)]["name"] == name, (index, items[int(index)]["name"], name)
    assert sorted(docs["tags.json"]["notes"].values()) == sorted(expect["notes"].values()), docs["tags.json"]["notes"]
    for name, digest in before.items():
        aside = home / (name + ".pre-sqlite-v1")
        assert aside.is_file() and hashlib.sha256(aside.read_bytes()).hexdigest() == digest, f"{aside.name} isn't the original"
        json.loads((home / name).read_text("utf-8"))   # (its JSON copy, for a JSON-only Hoard)
    conflicts = sorted(p.name for p in home.glob("*.legacy-conflict-*"))
    assert recovering or not conflicts, f"conflict copies were made: {conflicts}"
    for name in conflicts:
        json.loads((home / name).read_text("utf-8"))


def recovered(home: Path, before: dict, expect: dict) -> None:
    """The app started without its sealing key: the database kept aside as it was, what's in it kept, none of it
    trusted (so its links and pictures stay hidden until a refresh), and automatic work off."""
    moved(home, before, expect, recovering=True)
    aside = list(home.glob("metadata.before-recovery-*.sqlite3"))
    assert len(aside) == 1, f"the database wasn't kept aside once: {[p.name for p in aside]}"
    _, docs, trust = documents(home)
    assert {trust[name] for name in SEEDED} == {"changed"}, trust   # (its queue and schedule are new, and empty)
    assert docs["config.json"]["auto_sync_hours"] == 0 and docs["config.json"]["routine_hours"] == 0


# ---- the app

def answers(url: str) -> bool:
    """Does Hoard's server answer at url (any HTTP answer: it's up)? Never through a proxy."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=5):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def alive(pid: int) -> bool:
    """Is this process still running (not ended, nor a zombie waiting to be reaped)?"""
    if WINDOWS:
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
        finally:
            kernel.CloseHandle(handle)
    if MAC:
        stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
        return stat.returncode == 0 and not stat.stdout.strip().startswith("Z")
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except (OSError, IndexError):
        return False


def running(home: Path) -> dict | None:
    """What running.json says (address, pass, the server's pid), or None while there's none."""
    try:
        return json.loads((home / "running.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


class App:
    """The app to start: an installed one (its program), or this checkout's source run as the window runs it."""

    def __init__(self, program: list[str], source: bool = False):
        self.program, self.source, self.log, self.unpacked = program, source, None, None

    def env(self, home: Path, n: int) -> dict:
        """Its environment: its own data folder, nothing saying where to keep metadata; an AppImage unpacked fresh."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("HOARD_")}
        env["HOARD_DATA_DIR"] = str(home)
        if self.program[0].lower().endswith(".appimage"):
            self.unpacked = home.parent / f"unpacked{n}"
            self.unpacked.mkdir(exist_ok=True)
            env.update(APPIMAGE_EXTRACT_AND_RUN="1", TMPDIR=str(self.unpacked))
        if self.source:
            env["PYTHONPATH"] = str(ROOT)
        return env

    def start(self, home: Path, n: int) -> subprocess.Popen:
        """Start it (in a process group of its own, so all of it can be killed at once)."""
        self.log = home.parent / f"start{n}.log"
        extra = {"creationflags": 0x00000200} if WINDOWS else {"start_new_session": True}   # (a new process group)
        return subprocess.Popen(self.program, env=self.env(home, n), cwd=ROOT if self.source else home.parent,
                                stdin=subprocess.PIPE, stdout=open(self.log, "wb"), stderr=subprocess.STDOUT, **extra)

    def kill(self, proc: subprocess.Popen) -> None:
        """Kill all of it outright, as a crash or a power cut would end it: the window and Hoard's server."""
        if WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait(timeout=60)
        deadline = time.monotonic() + 60
        while self.leftover(proc) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not self.leftover(proc), "part of Hoard was still running after it was killed"
        self.tidy()
        self.settle()

    @staticmethod
    def describe(proc: subprocess.Popen, home: Path) -> None:
        """Say what's there when a start never answers: Hoard's programs still running, what's in its data folder,
        and on a Mac where each of them is waiting (sample) and what the system said about it (a privacy prompt for
        a folder would hold it up for good)."""
        def show(title: str, command: list[str], lines: int = 60) -> None:
            """A command's output, its first lines, under a title (nothing, if it can't run)."""
            try:
                said = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=60).stdout
            except (OSError, subprocess.SubprocessError) as e:
                said = f"({type(e).__name__})"
            print(f"--- {title}\n" + "\n".join(said.splitlines()[:lines]), flush=True)
        print("--- its data folder: " + ", ".join(sorted(p.name for p in home.iterdir())) if home.is_dir() else "", flush=True)
        if WINDOWS:
            show("Hoard's programs", ["tasklist", "/V", "/FI", "IMAGENAME eq Hoard.exe"])
            show("Hoard's server", ["tasklist", "/V", "/FI", "IMAGENAME eq hoard-server.exe"])
            return
        listed = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid=,stat=,etime=,command="], capture_output=True,
                                text=True, errors="replace").stdout.splitlines()
        def ours(line: str) -> bool:
            """Is this process the app's (its process group), or a program named as Hoard's are?"""
            fields = line.split(None, 5)
            return len(fields) == 6 and (fields[2] == str(proc.pid) or
                                         Path(fields[5].split()[0]).name.lower() in ("hoard", "hoard-server"))
        mine = [line for line in listed if ours(line)]
        print("--- Hoard's programs (pid, parent, group, state, time, command)\n" +
              "\n".join(line[:300] for line in mine[:40]), flush=True)
        if MAC:
            for line in mine:
                pid = line.split()[0]
                if line.split()[2:3] == [str(proc.pid)]:
                    show(f"where {pid} is waiting", ["sample", pid, "2"], 120)
            show("what the system said about it", ["log", "show", "--last", "5m", "--style", "compact", "--predicate",
                 'subsystem == "com.apple.TCC" OR process == "Hoard" OR process == "hoard-server"'], 80)

    @staticmethod
    def settle() -> None:
        """On Windows, wait a moment for the window's WebView2 to end after it (it ends on its own, and holds the
        window's own data folder until it does, which the next start opens). Elsewhere, nothing to wait for."""
        deadline = time.monotonic() + 20
        while WINDOWS and time.monotonic() < deadline:
            listed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq msedgewebview2.exe", "/NH"],
                                    capture_output=True, text=True).stdout
            if "msedgewebview2.exe" not in listed.lower():
                return
            time.sleep(0.5)

    def tidy(self) -> None:
        """Take away the AppImage's unpacked copy, which a kill leaves behind (a start that ends well takes it away
        itself): each is the size of the app, and there are a dozen starts."""
        if self.unpacked:
            shutil.rmtree(self.unpacked, ignore_errors=True)

    @staticmethod
    def leftover(proc: subprocess.Popen) -> bool:
        """Is any of it still running (its process group, or on Windows Hoard's server)?"""
        if WINDOWS:
            listed = subprocess.run(["tasklist", "/FI", "IMAGENAME eq hoard-server.exe", "/NH"],
                                    capture_output=True, text=True).stdout
            return "hoard-server.exe" in listed.lower()
        if MAC:
            return subprocess.run(["pgrep", "-g", str(proc.pid)], capture_output=True).returncode == 0
        for stat in Path("/proc").glob("[0-9]*/stat"):
            try:
                fields = stat.read_text().split(") ", 1)[1].split()
            except (OSError, IndexError):
                continue
            if int(fields[2]) == proc.pid and fields[0] != "Z":   # (its process group, the same as its pid)
                return True
        return False

    def stop(self, proc: subprocess.Popen, server: int) -> None:
        """Close it as it closes when its window ends: Hoard's server sees the window go, and quits cleanly."""
        if self.source:
            proc.stdin.close()
        elif WINDOWS:
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)   # (the window alone)
        else:
            window = proc.pid
            if not MAC:   # (an AppImage's window is its server's parent, below the AppImage's own programs)
                window = int(Path(f"/proc/{server}/stat").read_text().split(") ", 1)[1].split()[1])
            os.kill(window, signal.SIGTERM)


def fail(why: str, home: Path) -> None:
    """Say what went wrong, with the end of Hoard's logs and what the app printed, and stop."""
    print(f"FAILED: {why}", flush=True)
    for log in sorted((home / "logs").glob("*.log")) + sorted(home.parent.glob("start*.log")):
        print(f"--- {log.name}\n" + log.read_text("utf-8", "replace")[-4000:], flush=True)
    sys.exit(1)


class Starts:
    """Starting and stopping the app, counted (each start has its own log)."""

    def __init__(self, app: App):
        self.app, self.n = app, 0

    def ready(self, home: Path) -> tuple[subprocess.Popen, dict, dict]:
        """Start it and wait until its server answers: the process, running.json, and when each step came (seconds
        from the start: the database seen, and the server ready)."""
        self.n += 1
        began = time.monotonic()
        proc = self.app.start(home, self.n)
        times = {}
        while time.monotonic() - began < WAIT:
            if "db" not in times and (home / "metadata.sqlite3").exists():
                times["db"] = time.monotonic() - began
            info = running(home)
            if info and alive(int(info.get("pid", 0))) and answers(str(info.get("url", ""))):
                times["ready"] = time.monotonic() - began
                times.setdefault("db", times["ready"])
                return proc, info, times
            if proc.poll() is not None:
                fail(f"start {self.n}: it ended (exit code {proc.returncode}) before Hoard's server answered", home)
            time.sleep(0.01)
        self.app.describe(proc, home)
        self.app.kill(proc)
        fail(f"start {self.n}: Hoard's server didn't answer within {WAIT} seconds", home)

    def stop(self, home: Path, proc: subprocess.Popen, info: dict) -> None:
        """Close it cleanly, and wait until all of it has ended (its server gone, running.json taken away)."""
        server = int(info["pid"])
        self.app.stop(proc, server)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if not alive(server) and running(home) is None and proc.poll() is not None:
                self.app.tidy()
                self.app.settle()
                return
            time.sleep(0.1)
        self.app.kill(proc)
        fail(f"start {self.n}: Hoard was left running after its window closed", home)

    def once(self, home: Path) -> dict:
        """Start it, wait until it's ready, and close it: when each step came."""
        proc, info, times = self.ready(home)
        self.stop(home, proc, info)
        return times

    def killed(self, home: Path, when: str, after: float = 0.0) -> str:
        """Start it and kill all of it: when its database is first being written (its journal seen), a moment
        after the database is first seen, or as soon as it's ready. Then how the database was left."""
        self.n += 1
        began = time.monotonic()
        proc = self.app.start(home, self.n)
        seen = None
        while time.monotonic() - began < WAIT and proc.poll() is None:
            now = time.monotonic()
            if when == "journal" and (home / "metadata.sqlite3-journal").exists():
                break
            if when == "after" and seen is None and (home / "metadata.sqlite3").exists():
                seen = now
            if when == "after" and seen is not None and now - seen >= after:
                break
            info = running(home)
            if info and alive(int(info.get("pid", 0))):   # (ready: for "ready", or a moment that never came)
                if when != "ready":
                    when += " (it was ready first)"
                break
            time.sleep(0.002)
        else:
            fail(f"start {self.n}: it ended, or didn't start, before it could be killed", home)
        self.app.kill(proc)
        return state(home)


def install(package: Path, work: Path) -> tuple[App, callable]:
    """Install or unpack the package: the app, and how to take it away again."""
    name = package.name.lower()
    if name.endswith(".exe"):
        target = work / "installed"
        clean = {k: v for k, v in os.environ.items() if not k.startswith("HOARD_")}
        subprocess.run([str(package), "/S", f"/D={target}"], check=True, timeout=600, env=clean)
        program = target / "Hoard.exe"
        if not program.is_file():   # (an installer that keeps to its own folder, for this account alone)
            target = Path(os.environ["LOCALAPPDATA"]) / "Hoard"
            program = target / "Hoard.exe"
        assert program.is_file(), f"the installer put no Hoard.exe in {work / 'installed'} or {target}"
        if "hoard.exe" in subprocess.run(["tasklist", "/FI", "IMAGENAME eq Hoard.exe", "/NH"], capture_output=True,
                                         text=True).stdout.lower():
            subprocess.run(["taskkill", "/F", "/T", "/IM", "Hoard.exe"], capture_output=True)
            raise AssertionError("the silent install started Hoard")
        print(f"Installed silently in {target}", flush=True)

        def remove():
            """Uninstall it, silently."""
            subprocess.run([str(target / "uninstall.exe"), "/S"], timeout=600, check=True)
        return App([str(program)]), remove
    if name.endswith(".dmg"):
        mount = work / "mount"
        mount.mkdir()
        subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", str(mount),
                        str(package)], check=True, timeout=300, capture_output=True)
        try:
            bundle = next(mount.glob("*.app"))
            subprocess.run(["ditto", str(bundle), str(work / bundle.name)], check=True, timeout=300)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-force"], timeout=120, capture_output=True)
        program = work / bundle.name / "Contents" / "MacOS" / "Hoard"
        assert program.is_file(), f"{bundle.name} has no Contents/MacOS/Hoard"
        print(f"Copied {bundle.name} out of the disk image", flush=True)
        return App([str(program)]), lambda: None
    if name.endswith(".appimage"):
        package.chmod(0o755)
        return App([str(package)]), lambda: None
    raise SystemExit(f"not an installer, a disk image or an AppImage: {package.name}")


class Run:
    """One run of the checks: its folder, the app (once it's installed), and how to take it away again."""

    def __init__(self, work: Path):
        self.work, self.app, self.remove = work, None, lambda: None

    def last_home(self) -> Path:
        """The data folder of the app's last start (where a failed check's logs are), else the run's folder."""
        return self.app.log.parent / "data" if self.app and self.app.log else self.work


def main(argv: list[str]) -> int:
    """Seed, move, kill, roll back and come back, as the module says."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", type=Path, nargs="?")
    parser.add_argument("--legacy-root", type=Path, action="append", default=[],
                        help="a Hoard's source (a folder with hoard/ in it), run kept in JSON after the app")
    parser.add_argument("--source", action="store_true", help="run this checkout's source in place of an app")
    parser.add_argument("--worker", choices=("seed", "verify", "automatic"), help=argparse.SUPPRESS)
    parser.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--expect", default="{}", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(errors="replace")   # (a log's words in any language, on a console that has only some)
    if args.worker:
        worker(args.worker, args.home.resolve(), json.loads(args.expect))
        return 0
    if not args.source and not (args.package and args.package.is_file()):
        parser.error("give the installer, disk image or AppImage (or --source)")
    for root in args.legacy_root:
        assert (root / "hoard" / "__init__.py").is_file(), f"{root} has no hoard/"
    run = Run(Path(tempfile.mkdtemp(prefix="hoard-native-storage-")))
    try:
        checks(args, run)
        return 0
    except AssertionError as e:   # (a check that failed: said with what Hoard said, as fail() says it)
        fail(str(e) or "a check failed", run.last_home())
    finally:
        try:
            run.remove()
        finally:
            shutil.rmtree(run.work, ignore_errors=True)


def checks(args, run: Run) -> None:
    """Install the app, then seed, move, kill, roll back and come back, as the module says."""
    work = run.work
    if args.source:
        run.app = App([sys.executable, "-m", "hoard", "--shell"], source=True)
    else:
        run.app, run.remove = install(args.package.resolve(), work)
    starts = Starts(run.app)
    pristine = work / "seed" / "data"
    pristine.mkdir(parents=True)
    run_worker("seed", pristine)
    before = digests(pristine)
    expect = {"new_days": 7, "names": {"0": name_of(0), str(PRODUCTS - 1): name_of(PRODUCTS - 1)},
              "notes": {"0": "first", "1": "second"}, "count": PRODUCTS}

    def fresh(label: str, source: Path) -> Path:
        """A copy of a home, in a folder of its own."""
        home = work / label / "data"
        shutil.copytree(source, home)
        return home

    # 1. The move, as the app starts.
    home = fresh("moved", pristine)
    times = starts.once(home)
    moved(home, before, expect)
    run_worker("verify", home, expect)
    took = max(times["ready"] - times["db"], 0.05)
    print(f"1. It moved {PRODUCTS} products' metadata into SQLite as it started (its database {times['db']:.1f} s "
          f"in, ready {times['ready']:.1f} s in), keeping the originals and JSON copies", flush=True)

    # 2. Killed part way through the move.
    for n, (when, after) in enumerate((("journal", 0), ("after", 0.1 * took), ("after", 0.35 * took),
                                       ("after", 0.7 * took), ("ready", 0))):
        trial = fresh(f"killed{n}", pristine)
        left = starts.killed(trial, when, after)
        originals_kept(trial, before)
        starts.once(trial)
        moved(trial, before, expect)
        run_worker("verify", trial, expect)
        moment = {"journal": "as it first wrote to its database", "ready": "just as it was ready"}.get(
            when.split(" ")[0], f"{after:.2f} s after its database was made")
        print(f"2. Killed {moment}{when[len(when.split(' ')[0]):]} ({left}): every original kept, and the next "
              "start finished the move", flush=True)

    # 3. A JSON-only Hoard after it, then the app again.
    for n, root in enumerate(args.legacy_root, 1):
        edit = {"new_days": expect["new_days"] + 1, "rename": PRODUCTS - 1, "name": f"Hair Pack Renamed {n}",
                "note_on": 2 + n, "note": f"edited by a JSON-only Hoard ({n})"}
        said = legacy(root.resolve(), home, expect, edit)
        expect = {**expect, "new_days": edit["new_days"],
                  "names": {**expect["names"], str(edit["rename"]): edit["name"]},
                  "notes": {**expect["notes"], str(edit["note_on"]): edit["note"]}}
        for when in ("journal", "ready"):
            trial = fresh(f"legacy{n}-{when}", home)
            left = starts.killed(trial, when)
            starts.once(trial)
            moved(trial, before, expect)
            run_worker("verify", trial, expect)
            print(f"3. Killed {'as it brought them in' if when == 'journal' else 'just as it was ready'} "
                  f"({left}): the edits were brought in at the next start", flush=True)
        starts.once(home)
        moved(home, before, expect)
        run_worker("verify", home, expect)
        print(f"3. {said}: the app brought its edits in", flush=True)

    # 4. Its sealing key lost, or another's in its place.
    for how in ("lost", "replaced"):
        trial = fresh(f"key-{how}", home)
        run_worker("automatic", trial)
        key = trial / "integrity.key"
        if how == "lost":
            key.unlink()
        else:
            key.write_text("ab" * 32, encoding="ascii")
        starts.once(trial)
        recovered(trial, before, expect)
        run_worker("verify", trial, expect)
        print(f"4. Its sealing key {how}: it started, with its database kept aside as it was, and what was in it "
              "kept, untrusted until a refresh", flush=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
