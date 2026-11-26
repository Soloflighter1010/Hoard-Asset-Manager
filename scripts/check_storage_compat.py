"""Exercise a published JSON-only source package against a migrated SQLite fixture.

python scripts/check_storage_compat.py --legacy-root /path/to/release/Hoard
Add --shell-root /path/to/Tauri-release/Hoard to exercise its real sidecar protocol.
This uses temporary data/download folders and never installs an app or opens a window.
The shell check covers source/compiled sidecars, not the native Tauri window or installer execution.
"""
from __future__ import annotations
import argparse
import http.client
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
LEGACY = r'''
import json, os
from pathlib import Path
from hoard import __version__, config, library, paths
assert Path(__import__("hoard").__file__).resolve().is_relative_to(Path.cwd())
cfg = config.load_config()
assert cfg["setup_done"] and cfg["new_days"] == 7
lib = library.Library(paths.LIBRARY_FILE)
assert len(lib.data["items"]) == 2
assert all(p["url"] for p in lib.data["items"])
notes = json.loads((paths.data_dir()/"tags.json").read_text("utf-8"))["notes"]
assert len(notes) == 2 and set(notes.values()) == {"first", "second"}
config.save_config({**cfg, "new_days": 30})
lib.data["items"][0]["name"] = "Hair Pack One"
lib.save()
print(json.dumps({"release": __version__, "settings_and_library": "passed", "legacy_edits": "saved"}))
'''


def worker(phase, home):
    """Seed or verify a disposable fixture in a fresh application process."""
    os.environ.update(HOARD_DATA_DIR=str(home), HOARD_METADATA="sqlite")
    sys.path.insert(0, str(ROOT))
    from hoard import config, library, paths, storage
    from hoard.tags import TagStore, tag_key
    if phase == "seed":
        cfg = config.load_config()
        cfg.update(setup_done=True, new_days=7, check_for_updates=False, auto_sync_hours=0, routine_hours=0,
                   root=str(home / "downloads"))
        config.save_config(cfg)
        lib = library.Library(paths.LIBRARY_FILE)
        lib.data = {"items": [library.item("booth", str(n), name=f"Hair Pack {n}", creator="Example",
                                         url=f"https://booth.pm/en/items/{n}") for n in (1, 2)],
                    "stores": {"booth": {"count": 2}}}
        lib.save()
        keys = [tag_key("booth", p["name"], p["id"]) for p in lib.data["items"]]
        assert keys[0] != keys[1]
        storage.database().write("tags.json", {**TagStore.empty(), "notes": dict(zip(keys, ("first", "second")))})
    else:
        assert config.load_config()["new_days"] == 30
        lib = library.Library(paths.LIBRARY_FILE)
        assert lib.data["items"][0]["name"] == "Hair Pack One"
        assert len(lib.data["items"]) == 2
        notes = TagStore().load()["notes"]
        assert len(notes) == 2 and set(notes.values()) == {"first", "second"}
        keys = [tag_key("booth", p["name"], p["id"]) for p in lib.data["items"]]
        assert notes[keys[0]] == "first" and notes[keys[1]] == "second"
    storage.close_all()


def request(origin, method, path, body=None, key=None):
    """Make one authenticated sidecar API request and require a successful JSON response."""
    url = urlsplit(origin)
    conn = http.client.HTTPConnection(url.hostname, url.port, timeout=10)
    try:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["X-Hoard-Key"] = key
        conn.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = conn.getresponse()
        data = response.read()
        assert response.status == 200, (path, response.status, data[:200])
        return json.loads(data)
    finally:
        conn.close()


def shell_check(root, home, *, sqlite=False, recovered=False, command=None):
    """Exercise startup, authentication and clean shutdown through the real shell protocol."""
    env = {**os.environ, "HOARD_DATA_DIR": str(home), "HOARD_METADATA": "sqlite" if sqlite else "json", "PYTHONPATH": str(root)}
    messages = queue.Queue()
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errors:
        process = subprocess.Popen(command or [sys.executable, "-m", "hoard", "--shell"], cwd=root, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        def read():
            """Forward marked protocol messages from sidecar output to the waiting test."""
            for line in process.stdout:
                if line.startswith("\x1ehoard:"):
                    messages.put(json.loads(line[len("\x1ehoard:"):]))
            messages.put(None)
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + 30
            while True:
                message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
                assert message is not None, "sidecar exited before opening its page"
                if message.get("do") == "open":
                    break
            link = urlsplit(message["url"])
            origin = f"{link.scheme}://{link.netloc}"
            key = request(origin, "POST", "/api/enter", {"token": link.fragment.split("enter=", 1)[1]})["key"]
            # The same authenticated request the native shell's page makes.
            state = request(origin, "GET", "/api/settings", key=key)
            assert state["new_days"] == 30
            setup = request(origin, "GET", "/api/setup", key=key)
            assert setup["done"]
            listing = request(origin, "GET", "/api/library", key=key)
            assert len(listing["items"]) == 2
            assert {p["name"] for p in listing["items"]} == {"Hair Pack One", "Hair Pack 2"}
            if sqlite:
                assert len({p["tag_key"] for p in listing["items"]}) == 2
            if recovered:
                assert all(p["url"] is None for p in listing["items"])
                assert "refresh" in listing["stores"]["booth"]["error"]
            process.stdin.write(json.dumps({"event": "closing", "quitting": True}) + "\n")
            process.stdin.flush()
            assert process.wait(timeout=15) == 0
        except BaseException:
            errors.seek(0)
            print(errors.read()[-3000:], file=sys.stderr)
            raise
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            process.stdin.close()
            reader.join(timeout=3)
            process.stdout.close()


def current_shell_checks(root, home, command=None):
    """Exercise a current sidecar before and after losing or replacing its sealing key."""
    shell_check(root, home, sqlite=True, command=command)
    for missing in (True, False):
        key_path = home / "integrity.key"
        if missing:
            key_path.unlink()
        else:
            key_path.write_text("ab" * 32, encoding="ascii")
        shell_check(root, home, sqlite=True, recovered=True, command=command)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", "verify", "--home", str(home)],
                       cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)


def main():
    """Run requested source and compiled compatibility checks in temporary homes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy-root", type=Path, action="append", default=[])
    parser.add_argument("--shell-root", type=Path)
    parser.add_argument("--sidecar", type=Path, help="extracted compiled hoard-server; runs its --shell protocol")
    parser.add_argument("--current-sidecar", type=Path, help="newly compiled sidecar; also checks SQLite key recovery")
    parser.add_argument("--check-current-shell", action="store_true")
    parser.add_argument("--worker", choices=("seed", "verify"), help=argparse.SUPPRESS)
    parser.add_argument("--home", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.home.resolve())
        return
    if not args.legacy_root:
        parser.error("provide at least one --legacy-root containing hoard/")
    for release in args.legacy_root:
        release = release.resolve()
        assert (release / "hoard" / "__init__.py").is_file(), release
        with tempfile.TemporaryDirectory(prefix="hoard-storage-compat-") as folder:
            home = Path(folder) / "data"
            def current(phase):
                """Run a fixture phase with the current source in a fresh interpreter."""
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "--worker", phase, "--home", str(home)],
                               cwd=ROOT, check=True, capture_output=True, text=True, encoding="utf-8", timeout=60)
            current("seed")
            env = {**os.environ, "HOARD_DATA_DIR": str(home), "HOARD_METADATA": "json", "PYTHONPATH": str(release)}
            result = subprocess.run([sys.executable, "-c", LEGACY], cwd=release, env=env, check=True,
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
            current("verify")
            print(result.stdout.strip())
            if args.shell_root:
                shell_check(args.shell_root.resolve(), home)
                print(json.dumps({"shell": str(args.shell_root), "sidecar_protocol": "passed"}))
                current("verify")
            if args.sidecar:
                executable = args.sidecar.resolve()
                shell_check(executable.parent, home, command=[str(executable), "--shell"])
                print(json.dumps({"compiled_sidecar": executable.name, "sidecar_protocol": "passed"}))
                current("verify")
            if args.current_sidecar:
                executable = args.current_sidecar.resolve()
                command = [str(executable), "--shell"]
                current_shell_checks(executable.parent, home, command)
                print(json.dumps({"compiled_sqlite_sidecar": executable.name,
                                  "lost_and_foreign_key_recovery": "passed"}))
            if args.check_current_shell:
                current_shell_checks(ROOT, home)
                print(json.dumps({"current_sqlite_sidecar": "passed", "lost_and_foreign_key_sidecar_recovery": "passed"}))


if __name__ == "__main__":
    main()
