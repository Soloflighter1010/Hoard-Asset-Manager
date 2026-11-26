"""Issue #423: the AppImage opened once, then wouldn't open again. This starts an AppImage with a home folder of its
own, on the screen it's given (in CI: xvfb-run), unpacked each time as CI has no FUSE (APPIMAGE_EXTRACT_AND_RUN, so
it runs from a new place each start, as a mounted one does), and checks that:

1. it starts: its server answers at the address it notes in running.json;
2. a second start while it runs hands over to it and ends, starting no other server;
3. its window ending (killed, as a crash would end it) ends its server, leaving nothing behind (running.json goes);
4. it starts again after that, and again after its window is killed outright.

    xvfb-run -a python scripts/check_appimage.py shell/target/release/bundle/appimage/Hoard_*.AppImage
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

WAIT = 180   # seconds a start may take: unpacking the AppImage, then Hoard's server starting


def env_for(home: Path) -> dict:
    """The environment each start gets: its own home (so Hoard's data folder is new), unpacked rather than mounted."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("XDG_DATA", "XDG_CONFIG", "XDG_CACHE", "HOARD_"))}
    env.update(HOME=str(home), APPIMAGE_EXTRACT_AND_RUN="1", XDG_DATA_HOME=str(home / ".local" / "share"),
               XDG_CONFIG_HOME=str(home / ".config"), XDG_CACHE_HOME=str(home / ".cache"))
    return env


def running(data: Path) -> dict | None:
    """What running.json says (address, pass, the server's pid), or None while there's none."""
    try:
        return json.loads((data / "running.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


def answers(url: str) -> bool:
    """Does Hoard's server answer at url (any HTTP answer counts: it's up)?"""
    try:
        with urllib.request.urlopen(url, timeout=5):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def alive(pid: int) -> bool:
    """Is this process still running (and not a zombie waiting to be reaped)?"""
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except (OSError, IndexError):
        return False


def parent(pid: int) -> int:
    """The process that started this one: Hoard's server's is its window (the Tauri shell)."""
    return int(Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1].split()[1])


def start(app: Path, env: dict, data: Path, out: Path, n: int) -> tuple[subprocess.Popen, dict]:
    """Start the AppImage and wait until its server answers: the process, and what running.json says."""
    proc = subprocess.Popen([str(app)], env=env, stdout=open(out / f"start{n}.log", "wb"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        info = running(data)
        if info and alive(int(info.get("pid", 0))) and answers(str(info.get("url", ""))):
            return proc, info
        if proc.poll() is not None:
            fail(f"start {n}: the AppImage ended (exit code {proc.returncode}) before Hoard's server answered", data, out)
        time.sleep(1)
    fail(f"start {n}: Hoard's server didn't answer within {WAIT} seconds", data, out)


def ended(proc: subprocess.Popen, server: int, data: Path, out: Path, what: str) -> None:
    """Wait for Hoard to have stopped after its window ended: its server gone, running.json taken away, the AppImage
    ended (and its unpacked copy tidied)."""
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if not alive(server) and running(data) is None and proc.poll() is not None:
            return
        time.sleep(0.5)
    fail(f"{what}: Hoard was left running (server {'alive' if alive(server) else 'gone'}, running.json "
         f"{'still there' if running(data) else 'gone'}, AppImage {'running' if proc.poll() is None else 'ended'})", data, out)


def fail(why: str, data: Path, out: Path):
    """Say what went wrong, with the end of Hoard's logs and of what the AppImage printed, and stop."""
    print(f"FAILED: {why}", flush=True)
    for log in sorted((data / "logs").glob("*.log")) + sorted(out.glob("start*.log")):
        print(f"--- {log.name}\n" + log.read_text("utf-8", "replace")[-3000:], flush=True)
    sys.exit(1)


def main(argv: list[str]) -> int:
    """Start, hand over, end and start again, as the module says."""
    if len(argv) != 1 or not Path(argv[0]).is_file():
        print(__doc__)
        return 2
    app = Path(argv[0]).resolve()
    app.chmod(0o755)
    home = Path(tempfile.mkdtemp(prefix="hoard-appimage-"))
    out = home / "printed"
    out.mkdir()
    env, data = env_for(home), home / ".local" / "share" / "Hoard"

    proc, info = start(app, env, data, out, 1)
    server = int(info["pid"])
    print(f"1. It started: its server answers at {info['url']}", flush=True)

    second = subprocess.run([str(app)], env=env, stdout=open(out / "start2.log", "wb"), stderr=subprocess.STDOUT,
                            timeout=WAIT)
    if second.returncode != 0:
        fail(f"a second start while it ran ended with exit code {second.returncode}, not handing over", data, out)
    again = running(data)
    if not again or int(again["pid"]) != server or not alive(server):
        fail("a second start while it ran started another server, or stopped the first", data, out)
    print("2. A second start handed over to it, and ended", flush=True)

    os.kill(parent(server), signal.SIGTERM)
    ended(proc, server, data, out, "its window ended")
    print("3. Its window ended, and Hoard stopped with it, leaving nothing behind", flush=True)

    proc, info = start(app, env, data, out, 3)
    server = int(info["pid"])
    os.kill(parent(server), signal.SIGKILL)
    ended(proc, server, data, out, "its window killed")
    proc, info = start(app, env, data, out, 4)
    server = int(info["pid"])
    print("4. It started again, and again after its window was killed outright", flush=True)
    os.kill(parent(server), signal.SIGTERM)
    ended(proc, server, data, out, "the last start's window ended")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
