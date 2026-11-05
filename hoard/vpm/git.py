"""Source control with Git for a project (issues #296 to #299).

Hoard manages the project; Git keeps its history. Hoard runs the Git you have installed, never one of its own, and
only for a project on Projects' list (the server checks that before every call here). Each thing it does is a named
action of its own, never a command from the page; Git is never run through a shell, always with a time limit and a
cap on what it prints, and what it prints is cleaned of anything that holds a password or token before it's shown or
logged. Signing in to a remote is Git's own (Git Credential Manager, an SSH agent, a credential helper): Hoard keeps
no Git passwords, and refuses a remote's address with one in it.

A project starts with GitHub's Unity ignore template (CC0) and VRChat's guidance for the VPM
(https://vcc.docs.vrchat.com/vpm/source-control/): Assets, ProjectSettings, the package manifests and the VPM resolver
are kept; Unity's cache and the installed VPM packages, which the resolver restores when the project is opened in
Unity, are left out. An ignore file that's there already is never replaced: only the lines it lacks are added, and
they're shown before anything is written.

Writes to one repository never overlap (repo_lock). What changes your files while Unity has the project open
(switching branches, pulling, aborting a merge) waits until Unity is closed; reading never does.

A repository's own settings can have Git run a program of theirs (a filter as files are read, a hook as you commit,
a remote's helper): a project made by someone else could carry them, and Git would run them as soon as it looks at
the project. So before Git runs in a repository Hoard didn't make, its own settings and hooks are read (reading them
runs nothing), and any that run a program are shown; Git isn't used there until you trust them (concerns, trust).
Git LFS's own filter and hooks don't count. What Hoard runs by itself (a project's details) never runs a repository's
hooks or filters at all.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

READ_TIMEOUT = 30          # seconds Git has for reading a repository
WRITE_TIMEOUT = 300        # ... for staging and committing (a big project's first commit takes a while)
NETWORK_TIMEOUT = 3600     # ... for fetching, pulling, pushing and cloning (Stop stops it sooner)
MAX_OUTPUT = 16 << 20      # bytes of what Git prints that are read, at most
MAX_DIFF = 512 << 10       # bytes of one file's changes shown, at most
MAX_FILES = 5000           # changed files listed, at most
HISTORY = 50               # commits shown at a time
MIN_VERSION = (2, 28)      # (git restore and switch, init.defaultBranch: Git 2.28, July 2020)
GIT_HOME = "https://git-scm.com/downloads"
LFS_HOME = "https://git-lfs.com"

# What every Git Hoard runs is told, whatever a repository's own settings say: no file system monitor (a project's
# .git/config could name a program for it), paths printed as they are, no colours, no pager.
BASE = ["-c", "core.fsmonitor=false", "-c", "core.quotepath=off", "-c", "color.ui=false", "-c", "core.pager=cat"]
# The environment Git is run with: never one that points it at another repository or adds settings, never a prompt
# in a terminal Hoard doesn't have, and its messages in English, as they're read.
_DROPPED_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_NAMESPACE", "GIT_COMMON_DIR", "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
                "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_EXTERNAL_DIFF", "GIT_DIFF_OPTS", "GIT_PAGER")

REMOTE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
HASH = re.compile(r"[0-9a-f]{7,64}")
TOKENS = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{16,}|"
                    r"xox[abpr]-[A-Za-z0-9-]{10,}|[A-Za-z0-9_-]{40,})\b")


class GitError(Exception):
    """Something Git couldn't do, in words to show. code names the kind, for the page: "missing" (no Git), "old",
    "identity" (no name and email for commits), "unity" (Unity has the project open), "changes", "conflicts",
    "diverged", "nested", "owner" (the folder belongs to another user), or ""."""

    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


def redact(text) -> str:
    """Text Git printed, with any password or token in it taken out: an address's password (user:***@; a user's name
    alone, as in ssh://git@..., is kept, so an address shown can be used as it is), and anything shaped like an access
    token."""
    text = str(text or "")
    text = re.sub(r"([A-Za-z][A-Za-z0-9+.-]*://[^/@\s:]*):[^/@\s]+@", r"\1:***@", text)
    return TOKENS.sub("[token]", text)


# ---- finding Git

_found: dict = {"exe": None, "version": None, "looked": False}
_found_lock = threading.Lock()


def _candidates() -> list[str]:
    """Where Git could be: on the PATH, then where Git for Windows (or a Mac's Homebrew) puts it."""
    out = [shutil.which("git")]
    if sys.platform == "win32":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramW6432"),
                     os.path.join(os.environ.get("LOCALAPPDATA") or "", "Programs")):
            if base:
                out.append(os.path.join(base, "Git", "cmd", "git.exe"))
    elif sys.platform == "darwin":
        out += ["/opt/homebrew/bin/git", "/usr/local/bin/git"]
    return [c for c in dict.fromkeys(out) if c]


def _version(exe: str) -> tuple[int, ...] | None:
    """A Git's version, as numbers, or None when it isn't one that runs."""
    try:
        p = subprocess.run([exe, "--version"], capture_output=True, timeout=15, stdin=subprocess.DEVNULL, **_quiet())
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(rb"git version (\d+)\.(\d+)(?:\.(\d+))?", p.stdout or b"")
    return tuple(int(x) for x in m.groups() if x is not None) if p.returncode == 0 and m else None


def find(again: bool = False) -> dict:
    """The Git you have: {"found", "path", "version" ("2.43.0"), "ok" (new enough)}, looked for once (again looks
    again: Check again, after installing it)."""
    with _found_lock:
        if again or not _found["looked"]:
            _found.update(exe=None, version=None, looked=True)
            for c in _candidates():
                if os.path.isfile(c):
                    v = _version(c)
                    if v:
                        _found.update(exe=c, version=v)
                        break
        v = _found["version"]
        return {"found": bool(_found["exe"]), "path": _found["exe"], "version": ".".join(map(str, v)) if v else None,
                "ok": bool(v and v[:2] >= MIN_VERSION), "get": GIT_HOME}


def _exe() -> str:
    """The Git to run, or GitError saying how to get one."""
    g = find()
    if not g["found"]:
        raise GitError(f"Git isn't installed on this computer. Hoard uses the Git you have: get it from {GIT_HOME}, "
                       "then choose Check again.", "missing")
    if not g["ok"]:
        raise GitError(f"This Git is version {g['version']}: Hoard needs Git {'.'.join(map(str, MIN_VERSION))} or newer. "
                       f"Get a newer one from {GIT_HOME}.", "old")
    return g["path"]


# ---- running it

def _quiet() -> dict:
    """How a program is started here: without a window of its own on Windows, in a group of its own elsewhere (so
    Stop ends it and whatever it started)."""
    if sys.platform == "win32":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _env() -> dict:
    """The environment Git runs in (see _DROPPED_ENV)."""
    env = {k: v for k, v in os.environ.items() if k not in _DROPPED_ENV and not k.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0", LC_ALL="C", LANGUAGE="C", GIT_PAGER="cat")
    return env


def _kill(p: subprocess.Popen) -> None:
    """End Git and anything it started (a remote's helper, ssh)."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=15, **_quiet())
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        p.kill()
    except OSError:
        pass


def _pump(stream, buf: bytearray, lines: "queue.Queue | None" = None) -> None:
    """Read what Git prints into buf, MAX_OUTPUT of it at most (the rest is read and dropped, so Git never waits on
    a full pipe); lines, when given, gets each line (or progress update, which ends with a carriage return)."""
    part = b""
    while True:
        chunk = stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536)
        if not chunk:
            break
        if len(buf) < MAX_OUTPUT:
            buf.extend(chunk[:MAX_OUTPUT - len(buf)])
        if lines is not None:
            part += chunk
            *done, part = re.split(rb"[\r\n]", part)
            for line in done:
                if line.strip():
                    lines.put(line.decode("utf-8", "replace"))
    if lines is not None and part.strip():
        lines.put(part.decode("utf-8", "replace"))


class Result:
    """What one run of Git did: its exit code, and what it printed (as text)."""

    def __init__(self, code: int, out: bytes, err: bytes):
        self.code, self.raw = code, out
        self.out = out.decode("utf-8", "replace")
        self.err = redact(err.decode("utf-8", "replace")).strip()


def run(folder, args: list[str], timeout: float = READ_TIMEOUT, data: bytes | None = None, check: bool = True,
        progress=None) -> Result:
    """Run Git in folder with these arguments (a list: never a shell), and its result. check raises GitError when
    Git says it failed. progress, when given, is called with each line Git prints to say how it's going (fetching,
    cloning); if it raises (Stop), Git is ended and the error goes on."""
    cmd = [_exe(), *BASE, *args]
    try:
        p = subprocess.Popen(cmd, cwd=str(folder), stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_env(), **_quiet())
    except OSError as e:
        raise GitError(f"Git couldn't be started ({e.strerror or e}).") from None
    out, err, lines = bytearray(), bytearray(), queue.Queue() if progress else None
    pumps = [threading.Thread(target=_pump, args=(p.stdout, out), daemon=True),
             threading.Thread(target=_pump, args=(p.stderr, err, lines), daemon=True)]
    for t in pumps:
        t.start()
    if data is not None:
        try:
            p.stdin.write(data)
            p.stdin.close()
        except OSError:
            pass
    ends = time.monotonic() + timeout
    try:
        while True:
            try:
                code = p.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                pass
            while lines is not None and not lines.empty():
                progress(redact(lines.get_nowait()))
            if time.monotonic() > ends:
                _kill(p)
                raise GitError("Git took too long, so it was stopped.")
    except BaseException:
        if p.poll() is None:
            _kill(p)
        raise
    for t in pumps:
        t.join(5)
    for stream in (p.stdout, p.stderr):
        stream.close()
    r = Result(code, bytes(out), bytes(err))
    if check and code != 0:
        raise _error(r)
    return r


def _error(r: Result) -> GitError:
    """A failed run's GitError, in plain words where Hoard knows what it means."""
    e = r.err or "Git couldn't do that."
    low = e.lower()
    if "dubious ownership" in low:
        return GitError("Git won't work in this folder: it belongs to another user on this computer. Open it as the user "
                        "who owns it, or tell Git it's safe (git config --global --add safe.directory, with its path).", "owner")
    if "please tell me who you are" in low or "author identity unknown" in low:
        return GitError("Git needs your name and email for commits first.", "identity")
    if "not possible to fast-forward" in low or "diverging branches" in low:
        return GitError("Your branch and the remote's have both moved on since they last met.", "diverged")
    if "conflict" in low and "merge" in low:
        return GitError("Some files changed both here and on the remote: they're in conflict.", "conflicts")
    lines = [l.strip() for l in e.splitlines() if l.strip() and not l.lower().startswith("hint:")]
    return GitError(" ".join(lines[:4])[:800] or "Git couldn't do that.")


# ---- one repository at a time

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def repo_lock(folder) -> threading.Lock:
    """The lock a repository's writes take, so two never overlap."""
    key = os.path.normcase(os.path.normpath(str(folder)))
    with _locks_lock:
        return _locks.setdefault(key, threading.Lock())


def _same(a, b) -> bool:
    """Whether two paths are the same folder."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _unity_open(folder) -> bool:
    """Whether Unity has the project open."""
    from .unity import project_open_in_unity
    return project_open_in_unity(Path(folder))


def where(folder) -> dict:
    """Is the project a repository? {"repo" (its own, at the project's folder), "root" (the repository's folder),
    "parent" (a repository the project is inside of), "worktree" (a linked worktree: its .git is a file)}."""
    folder = Path(folder)
    r = run(folder, ["rev-parse", "--show-toplevel", "--git-dir", "--git-common-dir"], check=False)
    if r.code != 0:
        if "dubious ownership" in r.err.lower():
            raise _error(r)
        return {"repo": False, "root": None, "parent": None, "worktree": False}
    top, git_dir, common = (r.out.splitlines() + ["", "", ""])[:3]
    git_dir, common = (Path(folder, x) if x and not os.path.isabs(x) else Path(x) for x in (git_dir, common))
    if top and _same(top, folder):
        return {"repo": True, "root": str(folder), "parent": None, "worktree": not _same(git_dir, common)}
    return {"repo": False, "root": None, "parent": os.path.normpath(top) if top else None, "worktree": False}   # (C:\\...)


# ---- the ignore rules a project starts with

# GitHub's Unity template (https://github.com/github/gitignore/blob/main/Unity.gitignore, CC0 1.0), as of November 2026
UNITY_GITIGNORE = """\
# This .gitignore file should be placed at the root of your Unity project directory
#
# Get latest from https://github.com/github/gitignore/blob/main/Unity.gitignore
#
.utmp/
/[Ll]ibrary/
/[Tt]emp/
/[Oo]bj/
/[Bb]uild/
/[Bb]uilds/
/[Ll]ogs/
/[Uu]ser[Ss]ettings/
*.log

# Memory Profiler generated files
/[Mm]emory[Cc]aptures/

# Recordings can get excessive in size
/[Rr]ecordings/

# Autogenerated Jetbrains Rider plugin
/[Aa]ssets/Plugins/Editor/JetBrains*
# Jetbrains Rider personal-layer settings
*.DotSettings.user

# Visual Studio cache directory
.vs/

# Gradle cache directory
.gradle/

# Autogenerated VS/MD/Consulo solution and project files
ExportedObj/
.consulo/
*.csproj
*.unityproj
*.sln
*.slnx
*.suo
*.tmp
*.user
*.userprefs
*.pidb
*.booproj
*.svd
*.pdb
*.mdb
*.opendb
*.VC.db

# Unity3D generated meta files
*.pidb.meta
*.pdb.meta
*.mdb.meta

# Unity3D generated file on crash reports
sysinfo.txt

# Mono auto generated files
.dirstamp
mono_crash.*
tmpinst-dir.stamp

# Builds
/*_BackUpThisFolder_ButDontShipItWithYourGame/
/*_BurstDebugInformation_DoNotShip/
*.apk
*.aab
*.obb
*.unitypackage
*.unitypackage.meta
*.app

# Crashlytics generated file
crashlytics-build.properties

# Blender generated backup files
/[Aa]ssets/**/*.blend1
/[Aa]ssets/**/*.blend1.meta

# Unity Crash Recovery generated files
/[Aa]ssets/_Recovery/
/[Aa]ssets/_Recovery.meta

# Auto-generated cache in Assets folder
/[Aa]ssets/[Ss]ceneDependencyCache*
"""
# VRChat's VPM (https://vcc.docs.vrchat.com/vpm/source-control/): its packages are restored by the resolver when the
# project is opened in Unity, so they're left out; the resolver itself is kept
VPM_HEADER = ("# VRChat's packages (VPM): left out, as the resolver restores them when the project is opened in Unity;\n"
              "# the resolver itself is kept. https://vcc.docs.vrchat.com/vpm/source-control/\n")
VPM_RULES = ["/com.vrchat.*", "!/com.vrchat.core.*"]
ADDED_BY_HOARD = "# Added by Hoard (source control)"


def _rules(text: str) -> set[str]:
    """An ignore file's rules, as compared (no comments, no blank lines, no spaces at either end)."""
    return {l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")}


def _locked_packages(folder: Path) -> list[str]:
    """The VPM packages the project's vpm-manifest.json has installed, other than VRChat's (whose rule covers them)
    and the resolver: each is left out, as VRChat's guidance has it."""
    try:
        raw = json.loads((folder / "Packages" / "vpm-manifest.json").read_text("utf-8-sig"))
    except (OSError, ValueError):
        return []
    locked = raw.get("locked") if isinstance(raw, dict) and isinstance(raw.get("locked"), dict) else {}
    return sorted(n for n in locked if isinstance(n, str) and REMOTE_NAME.fullmatch(n.replace(".", "x"))
                  and not n.lower().startswith("com.vrchat.") and (folder / "Packages" / n).is_dir())


def ignore_plan(folder) -> list[dict]:
    """What setting up writes, file by file: {"path" (in the project), "exists", "add" (the rules it lacks), "text"
    (what's written: the whole file when it isn't there, else the lines added at its end)}. A file with every rule
    already isn't listed."""
    folder = Path(folder)
    out = []
    wanted = [(".gitignore", UNITY_GITIGNORE, None),
              ("Packages/.gitignore", VPM_HEADER + "\n".join(VPM_RULES + [f"/{n}/" for n in _locked_packages(folder)]) + "\n", "Packages")]
    for rel, template, inside in wanted:
        if inside and not (folder / inside).is_dir():
            continue
        target = folder / rel
        try:
            have = target.read_text("utf-8-sig") if target.is_file() else None
        except OSError:
            have = None
        lines = [l.strip() for l in template.splitlines() if l.strip() and not l.lstrip().startswith("#")]
        if have is None:
            out.append({"path": rel, "exists": False, "add": lines, "text": template})
            continue
        missing = [l for l in lines if l not in _rules(have)]
        if missing:
            out.append({"path": rel, "exists": True, "add": missing, "text": f"\n{ADDED_BY_HOARD}\n" + "\n".join(missing) + "\n"})
    return out


def write_ignore(folder, plan: list[dict]) -> list[str]:
    """Write a plan from ignore_plan: a new file whole, an existing one only added to at its end (never replaced).
    Returns the files written."""
    folder = Path(folder)
    done = []
    for f in plan:
        target = folder / f["path"]
        if f["exists"]:
            with open(target, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f["text"])
        else:
            part = target.with_name(target.name + ".hoard-part")
            part.write_text(f["text"], "utf-8", newline="\n")
            if target.exists():   # (made since it was read: never replaced)
                part.unlink()
                continue
            os.replace(part, target)
        done.append(f["path"])
    return done


def examples(folder) -> dict:
    """What would be kept and what left out, by a few of the project's own folders and files, before Git is set up."""
    folder = Path(folder)
    keep = [x for x in ("Assets", "ProjectSettings", "Packages/manifest.json", "Packages/vpm-manifest.json") if (folder / x).exists()]
    try:
        keep += [f"Packages/{d.name}" for d in (folder / "Packages").iterdir() if d.is_dir() and d.name.lower().startswith("com.vrchat.core.")]
        vpm = [f"Packages/{d.name}" for d in (folder / "Packages").iterdir() if d.is_dir() and d.name.lower().startswith("com.vrchat.")
               and not d.name.lower().startswith("com.vrchat.core.")]
    except OSError:
        vpm = []
    leave = [x for x in ("Library", "Temp", "Logs", "obj", "UserSettings") if (folder / x).is_dir()]
    leave += vpm + [f"Packages/{n}" for n in _locked_packages(folder)]
    return {"kept": keep[:12], "left_out": leave[:12]}


# ---- a repository's settings that run a program (see the module's note)

# its own settings (local or worktree: the repository's, not yours) that have Git run a program, or fetch with one
RUNS_PROGRAM = re.compile(
    r"filter\..+\.(clean|smudge|process)|diff\..+\.(command|textconv)|merge\..+\.driver|(diff|merge)tool\..+\.cmd|"
    r"core\.(hookspath|fsmonitor|sshcommand|gitproxy|askpass|editor|pager|alternaterefscommand)|sequence\.editor|"
    r"pager\..+|credential\.(.+\.)?helper|gpg\.(.+\.)?(program|defaultkeycommand)|remote\..+\.(uploadpack|receivepack|proxy)|"
    r"protocol\..+|include\.path|includeif\..+\.path|submodule\..+\.update|url\..*::.*\.(insteadof|pushinsteadof)", re.I)
# Git LFS's own filter, as git lfs install writes it (into a repository's settings too, with --local)
LFS_FILTER = re.compile(r"git-lfs (clean|smudge)( --skip)? -- %f|git-lfs filter-process( --skip)?")
# Git LFS's own hooks: a shebang, its "git-lfs isn't installed" line, and git lfs <hook> "$@"
LFS_HOOK_LINE = re.compile(r'#!/bin/sh|command -v git-lfs >/dev/null 2>&1 \|\| \{ .*; exit 2; \}|git lfs [a-z-]+ "\$@"')


def _settings(folder) -> list[tuple[str, str, str]]:
    """Every setting Git reads for this repository: (scope, key, value). Reading them runs nothing."""
    r = run(folder, ["config", "--list", "--show-scope", "-z"], check=False)
    fields, out = r.out.split("\0"), []
    for scope, entry in zip(fields[0::2], fields[1::2]):
        key, _, value = entry.partition("\n")
        out.append((scope, key, value))
    return out


def _hooks(folder) -> Path | None:
    """The repository's hooks folder (its own, or where core.hooksPath points)."""
    r = run(folder, ["rev-parse", "--git-path", "hooks"], check=False)
    where = r.out.strip()
    return (Path(where) if os.path.isabs(where) else Path(folder) / where) if r.code == 0 and where else None


def concerns(folder) -> list[dict]:
    """What in the repository's own settings and hooks runs a program: [{"kind" ("setting" or "hook"), "name",
    "value" (what it runs, a few lines at most)}]; none for a repository with none (Git LFS's own aren't counted)."""
    found = []
    for scope, key, value in _settings(folder):
        if scope not in ("local", "worktree"):   # (yours, or the computer's: not the repository's)
            continue
        low = key.lower()
        risky = bool(RUNS_PROGRAM.fullmatch(key))
        if re.fullmatch(r"remote\..+\.(url|pushurl)", low) and "::" in value.split("/", 1)[0]:
            risky = True   # (a remote reached through a transport that runs a program, ext:: say)
        if re.fullmatch(r"filter\.lfs\.(clean|smudge|process)", low) and LFS_FILTER.fullmatch(value.strip()):
            risky = False
        if risky:
            found.append({"kind": "setting", "name": key, "value": redact(value)[:300]})
    hooks = _hooks(folder)
    try:
        listed = sorted(hooks.iterdir()) if hooks and hooks.is_dir() else []
    except OSError:
        listed = []
    for f in listed[:100]:
        if f.name.endswith(".sample") or not f.is_file():
            continue
        try:
            text = f.read_text("utf-8", "replace")[:20000]
        except OSError:
            text = ""
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("# ")]
        if lines and all(LFS_HOOK_LINE.fullmatch(l) for l in lines) and any(l.startswith("git lfs ") for l in lines):
            continue   # (Git LFS's own)
        found.append({"kind": "hook", "name": f.name, "value": redact("\n".join(lines[:6]))[:300],
                      "hash": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()})
    return found


def _fingerprint(found: list[dict]) -> str:
    """What the concerns were when they were trusted: any change to them asks again."""
    return hashlib.sha256(json.dumps(found, sort_keys=True).encode("utf-8")).hexdigest()


def is_trusted(folder, found: list[dict] | None = None) -> bool:
    """Whether Git may run in this repository: it has nothing that runs a program, or you trusted what it has."""
    found = concerns(folder) if found is None else found
    if not found:
        return True
    from . import listing
    return listing.git_trusted(str(folder)) == _fingerprint(found)


def trust(folder) -> None:
    """Trust what the repository's settings and hooks run, as they are now (Trust it, or a repository Hoard made)."""
    from . import listing
    found = concerns(folder)
    listing.trust_git(str(folder), _fingerprint(found) if found else None)


def _gate(folder) -> None:
    """Refuse to run Git in a repository whose own settings run a program you haven't trusted."""
    if not is_trusted(folder):
        raise GitError("This project's Git settings run programs. Look at them in its Source control tab, and trust "
                       "them there first.", "untrusted")


# ---- what's there

def _status(folder, guard: bool = False) -> dict:
    """The repository's state, from git status (porcelain v2, NUL-separated): its branch, upstream and how far ahead
    and behind, and each changed file. Only in a trusted repository (_gate); guard: run no hook or filter of the
    repository's at all (what Hoard looks at by itself, as for a project's details)."""
    _gate(folder)
    off = []
    if guard:   # (no hooks; each filter the repository's own settings name, with nothing to run)
        off = ["-c", f"core.hooksPath={os.devnull}"]
        for scope, key, _ in _settings(folder):
            m = re.fullmatch(r"filter\.(.+)\.(clean|smudge|process)", key, re.I)
            if m and scope in ("local", "worktree") and m.group(1).lower() != "lfs":
                off += ["-c", f"filter.{m.group(1)}.{m.group(2)}=", "-c", f"filter.{m.group(1)}.required=false"]
    r = run(folder, [*off, "status", "--porcelain=v2", "--branch", "-z", "--untracked-files=normal", "--ignore-submodules=dirty"])
    out = {"branch": None, "detached": False, "initial": False, "upstream": None, "ahead": 0, "behind": 0, "files": [], "more": 0}
    fields = r.out.split("\0")
    i = 0
    while i < len(fields):
        f = fields[i]
        i += 1
        if not f:
            continue
        if f.startswith("# "):
            key, _, value = f[2:].partition(" ")
            if key == "branch.oid":
                out["initial"] = value == "(initial)"
            elif key == "branch.head":
                out["detached"] = value == "(detached)"
                out["branch"] = None if out["detached"] else value
            elif key == "branch.upstream":
                out["upstream"] = value
            elif key == "branch.ab":
                m = re.match(r"\+(\d+) -(\d+)", value)
                if m:
                    out["ahead"], out["behind"] = int(m.group(1)), int(m.group(2))
            continue
        kind = f[0]
        entry = None
        if kind == "1":
            parts = f.split(" ", 8)
            if len(parts) == 9:
                entry = {"path": parts[8], "x": parts[1][0], "y": parts[1][1]}
        elif kind == "2":
            parts = f.split(" ", 9)
            if len(parts) == 10:
                entry = {"path": parts[9], "x": parts[1][0], "y": parts[1][1], "from": fields[i] if i < len(fields) else None}
                i += 1
        elif kind == "u":
            parts = f.split(" ", 10)
            if len(parts) == 11:
                entry = {"path": parts[10], "x": parts[1][0], "y": parts[1][1], "conflict": True}
        elif kind == "?":
            entry = {"path": f[2:], "x": "?", "y": "?", "untracked": True}
        if entry is None:
            continue
        if len(out["files"]) >= MAX_FILES:
            out["more"] += 1
            continue
        entry.setdefault("from", None)
        entry["conflict"] = bool(entry.get("conflict"))
        entry["untracked"] = bool(entry.get("untracked"))
        entry["staged"] = not entry["untracked"] and not entry["conflict"] and entry["x"] != "."
        entry["unstaged"] = entry["untracked"] or entry["conflict"] or entry["y"] != "."
        out["files"].append(entry)
    return out


def _last(folder) -> dict | None:
    """The newest commit on the branch: {"hash", "short", "subject", "author", "when"}, or None before the first."""
    r = run(folder, ["log", "-1", "--format=%H%x1f%h%x1f%s%x1f%an%x1f%aI"], check=False)
    parts = r.out.strip().split("\x1f")
    if r.code != 0 or len(parts) != 5:
        return None
    return dict(zip(("hash", "short", "subject", "author", "when"), parts))


def remotes(folder) -> list[dict]:
    """The repository's remotes, each {"name", "url"} (its fetch address, with any password or token taken out)."""
    r = run(folder, ["remote", "-v"], check=False)
    seen: dict[str, str] = {}
    for line in r.out.splitlines():
        m = re.match(r"(\S+)\s+(\S+)\s+\(fetch\)", line)
        if m:
            seen.setdefault(m.group(1), redact(m.group(2)))
    return [{"name": n, "url": u} for n, u in seen.items()]


def branches(folder) -> list[dict]:
    """The repository's branches here: {"name", "current", "upstream", "track" (as Git says: "ahead 2", "gone")}."""
    r = run(folder, ["for-each-ref", "--format=%(refname:short)%1f%(HEAD)%1f%(upstream:short)%1f%(upstream:track,nobracket)",
                     "refs/heads"], check=False)
    out = []
    for line in r.out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            out.append({"name": parts[0], "current": parts[1] == "*", "upstream": parts[2] or None, "track": parts[3] or None})
    return out


def lfs(folder) -> dict:
    """Whether the project uses Git LFS (its .gitattributes says filter=lfs), and whether Git LFS is installed."""
    try:
        used = "filter=lfs" in (Path(folder) / ".gitattributes").read_text("utf-8", "replace")
    except OSError:
        used = False
    installed = used and run(folder, ["lfs", "version"], check=False).code == 0
    return {"used": used, "installed": installed, "get": LFS_HOME}


def identity(folder) -> dict:
    """The name and email this repository's commits are made with (its own settings, else yours)."""
    get = lambda k: run(folder, ["config", "--get", k], check=False).out.strip()  # noqa: E731
    return {"name": get("user.name"), "email": get("user.email")}


def merging(folder) -> bool:
    """Whether a merge is under way (a pull that stopped on conflicts)."""
    r = run(folder, ["rev-parse", "-q", "--verify", "MERGE_HEAD"], check=False)
    return r.code == 0


def state(folder, again: bool = False) -> dict:
    """Everything the Source control tab shows: whether Git is there, whether the project is a repository (or inside
    another), and for one: its branch and upstream, how far ahead and behind, its changes, the newest commit, its
    remotes and branches, Git LFS, who commits are made by, the ignore rules it lacks, and whether Unity has it open."""
    folder = Path(folder)
    g = find(again)
    out = {"git": g, "open_in_unity": _unity_open(folder)}
    if not g["found"] or not g["ok"]:
        return {**out, "state": "missing" if not g["found"] else "old"}
    try:
        w = where(folder)
    except GitError as e:
        return {**out, "state": "error", "error": str(e), "code": e.code}
    if not w["repo"]:
        return {**out, "state": "none", "parent": w["parent"]}
    found = concerns(folder)
    if not is_trusted(folder, found):   # (its own settings run programs: shown, and Git not run further)
        return {**out, "state": "untrusted", "concerns": found}
    st = _status(folder)
    files = st["files"]
    counts = {"staged": sum(f["staged"] for f in files), "changed": sum(f["unstaged"] and not f["untracked"] and not f["conflict"] for f in files),
              "untracked": sum(f["untracked"] for f in files), "conflicts": sum(f["conflict"] for f in files)}
    kind = "conflicts" if counts["conflicts"] else "changes" if files else "clean"
    return {**out, "state": kind, **st, "counts": counts, "worktree": w["worktree"], "merging": merging(folder),
            "last": _last(folder), "remotes": remotes(folder), "branches": branches(folder), "lfs": lfs(folder),
            "identity": identity(folder), "ignore_missing": [f["path"] for f in ignore_plan(folder)]}


def summary(folder) -> dict:
    """A few words' worth, for a project's details: {"state" (as state() has it), "branch", "changes", "ahead",
    "behind"}, from as few Git runs as it can (none when it isn't a repository of its own)."""
    if not (Path(folder) / ".git").exists():
        return {"state": "none"}
    g = find()
    if not g["found"] or not g["ok"]:
        return {"state": "missing" if not g["found"] else "old"}
    try:
        if not is_trusted(folder):
            return {"state": "untrusted"}
        st = _status(folder, guard=True)
    except GitError:
        return {"state": "error"}
    conflicts = any(f["conflict"] for f in st["files"])
    return {"state": "conflicts" if conflicts else "changes" if st["files"] else "clean", "branch": st["branch"],
            "changes": len(st["files"]) + st["more"], "ahead": st["ahead"], "behind": st["behind"]}


# ---- setting it up

def set_up(folder, nested: bool = False) -> dict:
    """Make the project a repository: its ignore rules written first (ignore_plan, as shown), then git init. Never
    inside another repository unless nested (you were told, and said yes). Returns what was kept and left out."""
    folder = Path(folder)
    with repo_lock(folder):
        w = where(folder)
        if w["repo"]:
            raise GitError("This project has Git already.")
        if w["parent"] and not nested:
            raise GitError(f"This project is inside another Git repository ({w['parent']}). Set it up anyway only if you "
                           "mean it to have a repository of its own inside that one.", "nested")
        written = write_ignore(folder, ignore_plan(folder))
        run(folder, ["init"], timeout=WRITE_TIMEOUT)
        trust(folder)   # (made here, from your own Git's templates)
        return {"written": written, **looked_over(folder)}


def update_ignore(folder) -> list[str]:
    """Add the ignore rules the project lacks (packages installed since it was set up, say), as ignore_plan shows."""
    with repo_lock(folder):
        return write_ignore(folder, ignore_plan(folder))


def looked_over(folder) -> dict:
    """A repository's files as Git sees them now: a few it would keep (not committed yet) and a few it leaves out."""
    keep = run(folder, ["ls-files", "-z", "--others", "--exclude-standard", "--directory"], check=False).out.split("\0")
    left = run(folder, ["ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"], check=False).out.split("\0")
    return {"kept": [x for x in keep if x][:12], "left_out": [x for x in left if x][:12]}


# ---- changes and commits

def _paths(folder, paths, allowed: set[str]) -> list[str]:
    """The paths asked for, each one of the repository's changes as Git listed them (never anything else)."""
    if not isinstance(paths, list) or not paths:
        raise GitError("Choose some files first.")
    chosen = [p for p in paths[:MAX_FILES] if isinstance(p, str) and p in allowed]
    if len(chosen) != len([p for p in paths[:MAX_FILES]]):
        raise GitError("Some of those files aren't among the changes any more. Look again.")
    return chosen


def stage(folder, paths) -> int:
    """Stage the files chosen (only files among the changes), and nothing else."""
    with repo_lock(folder):
        st = _status(folder)
        chosen = _paths(folder, paths, {f["path"] for f in st["files"]})
        left = {f["path"] for f in st["files"] if f["unstaged"]}
        todo = [p for p in chosen if p in left]   # (one staged already, with nothing more to stage: as it is)
        if todo:
            run(folder, ["add", "--all", "--", *todo], timeout=WRITE_TIMEOUT)
        return len(chosen)


def unstage(folder, paths) -> int:
    """Take the files chosen out of what's staged (their changes are kept, not staged)."""
    with repo_lock(folder):
        st = _status(folder)
        staged = [f for f in st["files"] if f["staged"]]
        chosen = _paths(folder, paths, {f["path"] for f in staged} | {f["from"] for f in staged if f["from"]})
        if st["initial"]:   # (no commit yet: nothing to put back from)
            run(folder, ["rm", "--cached", "-r", "-q", "--", *chosen], timeout=WRITE_TIMEOUT)
        else:
            run(folder, ["restore", "--staged", "--", *chosen], timeout=WRITE_TIMEOUT)
        return len(chosen)


def set_identity(folder, name: str, email: str) -> dict:
    """The name and email this repository's commits are made with (its own settings, not your others)."""
    name, email = str(name or "").strip(), str(email or "").strip()
    if not name or len(name) > 100 or any(c in name for c in "<>\n\r\0"):
        raise GitError("Type the name to sign your commits with.")
    if not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+", email) or len(email) > 200:
        raise GitError("Type the email to sign your commits with (it can be one that isn't real, such as you@example.com).")
    with repo_lock(folder):
        run(folder, ["config", "user.name", name])
        run(folder, ["config", "user.email", email])
    return identity(folder)


def commit(folder, message: str) -> dict:
    """Commit what's staged, with this message (one is needed): the new commit."""
    message = str(message or "").replace("\r\n", "\n").strip()
    if not message:
        raise GitError("Write a message for the commit first: what changed, in a few words.")
    if len(message) > 10000:
        raise GitError("That message is too long for a commit.")
    with repo_lock(folder):
        if not any(f["staged"] for f in _status(folder)["files"]):
            raise GitError("Nothing is staged: choose the files to commit, and Stage them, first.")
        who = identity(folder)
        if not who["name"] or not who["email"]:
            raise GitError("Git needs your name and email for commits first.", "identity")
        run(folder, ["commit", "--quiet", "-F", "-"], timeout=WRITE_TIMEOUT, data=message.encode("utf-8"))
        return _last(folder)


def history(folder, skip: int = 0, limit: int = HISTORY) -> list[dict]:
    """The newest commits, skip of them passed by: {"hash", "short", "author", "email", "when", "refs", "subject"}."""
    _gate(folder)   # (a repository's own settings can have git log run a program: log.showSignature, gpg.program)
    skip, limit = max(0, int(skip)), max(1, min(int(limit), 200))
    r = run(folder, ["log", f"--max-count={limit}", f"--skip={skip}", "--format=%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%D%x1f%s%x1e"],
            check=False)
    out = []
    for rec in r.out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) == 7:
            out.append(dict(zip(("hash", "short", "author", "email", "when", "refs", "subject"), parts)))
    return out


def commit_files(folder, ref: str) -> list[dict]:
    """The files one commit changed: {"path", "status" (A, M, D, R...), "from"}."""
    if not isinstance(ref, str) or not HASH.fullmatch(ref):
        raise GitError("That isn't a commit.")
    _gate(folder)
    r = run(folder, ["show", "--format=", "--name-status", "-z", "-M", "--no-ext-diff", ref])
    fields, out, i = r.out.split("\0"), [], 0
    while i < len(fields) and len(out) < MAX_FILES:
        code = fields[i].strip()
        i += 1
        if not code:
            continue
        if code[0] in "RC" and i + 1 < len(fields):
            out.append({"status": code[0], "from": fields[i], "path": fields[i + 1]})
            i += 2
        elif i < len(fields):
            out.append({"status": code[0], "from": None, "path": fields[i]})
            i += 1
    return out


def _looks_binary(data: bytes) -> bool:
    """Whether some bytes are a binary file's (a NUL in its first 8 KB, as Git decides)."""
    return b"\0" in data[:8192]


def diff(folder, path: str, staged: bool = False, ref: str | None = None) -> dict:
    """One file's changes: {"path", "binary", "text" (a unified diff, MAX_DIFF of it at most), "truncated", "added",
    "removed", "size" (a binary file's, in bytes)}: in what's staged, in what isn't, or in a commit (ref). Only a
    file among the changes (or the commit's files) is read."""
    folder = Path(folder)
    _gate(folder)
    if ref is not None:
        changed = commit_files(folder, ref)
        if path not in {f["path"] for f in changed} | {f["from"] for f in changed if f["from"]}:
            raise GitError("That file isn't in that commit.")
        base = ["show", "--format=", "-M", "--no-ext-diff", "--no-textconv", ref]
    else:
        files = {f["path"]: f for f in _status(folder)["files"]}
        f = files.get(path)
        if not f:
            raise GitError("That file isn't among the changes any more.")
        if f["untracked"]:
            return _new_file(folder, path)
        base = ["diff", "-M", "--no-ext-diff", "--no-textconv"] + (["--cached"] if staged else [])
    numstat = run(folder, base[:1] + ["--numstat"] + base[1:] + ["--", path]).out.strip().splitlines()
    added = removed = 0
    binary = False
    for line in numstat:
        a, _, rest = line.partition("\t")
        d, _, _ = rest.partition("\t")
        if a == "-" or d == "-":
            binary = True
        else:
            added, removed = added + int(a or 0), removed + int(d or 0)
    if binary:
        size = (folder / path).stat().st_size if (folder / path).is_file() else None
        return {"path": path, "binary": True, "text": "", "truncated": False, "added": 0, "removed": 0, "size": size}
    r = run(folder, base + ["--", path])
    raw = r.raw[:MAX_DIFF]
    return {"path": path, "binary": False, "text": raw.decode("utf-8", "replace"), "truncated": len(r.raw) > MAX_DIFF,
            "added": added, "removed": removed, "size": None}


def _new_file(folder: Path, path: str) -> dict:
    """A file Git doesn't track yet, as its changes: every line added (a folder: what's in it, by name)."""
    target = folder / path
    if target.is_symlink():
        return {"path": path, "binary": True, "text": "", "truncated": False, "added": 0, "removed": 0, "size": None}
    if target.is_dir():
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in list(target.iterdir())[:200])
        return {"path": path, "binary": False, "folder": names, "text": "", "truncated": False, "added": 0, "removed": 0, "size": None}
    try:
        with open(target, "rb") as fh:
            data = fh.read(MAX_DIFF + 1)
        size = target.stat().st_size
    except OSError as e:
        raise GitError(f"That file can't be read ({e.strerror or e}).") from None
    if _looks_binary(data):
        return {"path": path, "binary": True, "text": "", "truncated": False, "added": 0, "removed": 0, "size": size}
    text = data[:MAX_DIFF].decode("utf-8", "replace")
    lines = text.splitlines()
    return {"path": path, "binary": False, "text": f"--- /dev/null\n+++ b/{path}\n" + "".join(f"+{l}\n" for l in lines),
            "truncated": len(data) > MAX_DIFF, "added": len(lines), "removed": 0, "size": None}


# ---- remotes, syncing and branches

def check_url(url) -> str:
    """A remote's address, checked: https, ssh, git or file addresses, user@host:path, or a folder; never one with a
    password or token in it (signing in is Git's own), nor one of Git's transports that run a program (ext::)."""
    u = str(url or "").strip()
    if not u or len(u) > 2000 or any(c.isspace() or ord(c) < 32 for c in u) or u.startswith("-"):
        raise GitError("Type the remote's address.")
    if "::" in u.split("/", 1)[0]:
        raise GitError("That kind of address isn't one Hoard uses.")
    scheme, sep, _ = u.partition("://")
    if sep and re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]*", scheme):
        scheme = scheme.lower()
        if scheme not in ("https", "http", "ssh", "git", "file"):
            raise GitError("That kind of address isn't one Hoard uses.")
        parts = urlsplit(u)
        if parts.password is not None or (parts.username and (TOKENS.search(parts.username) or ":" in parts.username)):
            raise GitError("That address has a password or token in it. Use the address without it: Git asks you to "
                           "sign in itself (Git Credential Manager, or your SSH key), and Hoard keeps no Git passwords.")
        if scheme != "file" and not parts.hostname:
            raise GitError("That address has no server in it.")
        return u
    user, at, rest = u.partition("@")
    host, colon, where_ = rest.partition(":")
    if at and colon and where_ and re.fullmatch(r"[A-Za-z0-9._-]+", user) and re.fullmatch(r"[A-Za-z0-9.-]+", host):
        return u   # (ssh, as git@github.com:you/project.git; no spaces, as checked above)
    if os.path.isabs(u):   # (a repository in a folder: on this computer, or a shared drive)
        return u
    raise GitError("That isn't an address Hoard can use: an https:// or ssh:// address, user@host:path, or a folder.")


def set_remote(folder, action: str, name: str, url: str | None = None) -> list[dict]:
    """Add, change or remove a remote; returns the remotes as they are now."""
    name = str(name or "").strip()
    if not REMOTE_NAME.fullmatch(name):
        raise GitError("Name the remote with letters, numbers, dots, dashes or underscores (origin, say).")
    with repo_lock(folder):
        have = {r["name"] for r in remotes(folder)}
        if action == "add":
            if name in have:
                raise GitError(f"There's a remote named {name} already.")
            run(folder, ["remote", "add", "--", name, check_url(url)])
        elif action == "set":
            if name not in have:
                raise GitError(f"There's no remote named {name}.")
            run(folder, ["remote", "set-url", "--", name, check_url(url)])
        elif action == "remove":
            if name not in have:
                raise GitError(f"There's no remote named {name}.")
            run(folder, ["remote", "remove", "--", name])
        else:
            raise GitError("Hoard doesn't know that.")
    return remotes(folder)


def _remote(folder, name: str | None) -> str:
    """The remote to sync with: the one named, else the branch's upstream's, else the only one (or origin)."""
    have = [r["name"] for r in remotes(folder)]
    if not have:
        raise GitError("Add a remote first: the address of the repository online to sync with.")
    if name:
        if name not in have:
            raise GitError(f"There's no remote named {name}.")
        return name
    up = _status(folder)["upstream"]
    if up and up.split("/", 1)[0] in have:
        return up.split("/", 1)[0]
    return "origin" if "origin" in have else have[0]


def fetch(folder, remote: str | None = None, progress=None) -> str:
    """Fetch from a remote: only looks, and changes nothing in your files or your branches."""
    _gate(folder)
    with repo_lock(folder):
        name = _remote(folder, remote)
        run(folder, ["fetch", "--prune", "--progress", "--", name], timeout=NETWORK_TIMEOUT, progress=progress)
    st = _status(folder)
    return f"Fetched {name}." + (f" {st['behind']} new on {st['upstream']} to pull." if st["behind"] else "")


def _must_be_closed(folder, what: str) -> None:
    """Refuse something that changes your files while Unity has the project open."""
    if _unity_open(folder):
        raise GitError(f"Unity has this project open. Close it before you {what}, so nothing it has open is changed under it.", "unity")


def pull(folder, merge: bool = False, progress=None) -> str:
    """Bring the upstream's commits into your branch and files: only when they follow on from yours, unless merge
    (you said to merge the two). Waits until Unity is closed."""
    _must_be_closed(folder, "pull")
    with repo_lock(folder):
        st = _status(folder)
        if not st["upstream"]:
            raise GitError("This branch isn't linked to one on a remote yet: Push it first, or fetch the remote's.")
        args = ["pull", "--progress", "--no-edit"] + (["--no-rebase"] if merge else ["--ff-only"])
        run(folder, args, timeout=NETWORK_TIMEOUT, progress=progress)
    return f"Pulled {st['upstream']}."


def push(folder, remote: str | None = None, progress=None) -> str:
    """Send your branch's commits to its remote (linking it to one there of the same name, the first time)."""
    with repo_lock(folder):
        st = _status(folder)
        if st["detached"] or not st["branch"]:
            raise GitError("Switch to a branch first: there's none checked out.")
        if st["initial"]:
            raise GitError("Commit something first: there's nothing to push yet.")
        if st["upstream"] and not remote:
            run(folder, ["push", "--progress"], timeout=NETWORK_TIMEOUT, progress=progress)
            return f"Pushed to {st['upstream']}."
        name = _remote(folder, remote)
        run(folder, ["push", "--progress", "--set-upstream", "--", name, f"HEAD:refs/heads/{st['branch']}"],
            timeout=NETWORK_TIMEOUT, progress=progress)
        return f"Pushed to {name}/{st['branch']}."


def _branch_name(folder, name) -> str:
    """A branch name Git takes (git check-ref-format --branch), or GitError."""
    name = str(name or "").strip()
    if not name or len(name) > 100 or name.startswith("-") or run(folder, ["check-ref-format", "--branch", name], check=False).code != 0:
        raise GitError("That can't be a branch's name: letters, numbers, dashes, slashes and dots, with no spaces.")
    return name


def set_branch(folder, action: str, name: str) -> list[dict]:
    """Make a branch (and switch to it), switch to one, or delete one that's merged; returns the branches now.
    Switching waits until Unity is closed, and until there are no changes it would carry or lose."""
    _gate(folder)
    with repo_lock(folder):
        have = {b["name"]: b for b in branches(folder)}
        if action == "new":
            name = _branch_name(folder, name)
            if name in have:
                raise GitError(f"There's a branch named {name} already.")
            run(folder, ["switch", "--create", name], timeout=WRITE_TIMEOUT)
        elif action == "switch":
            if name not in have:
                raise GitError(f"There's no branch named {name}.")
            _must_be_closed(folder, "switch branches")
            if any(not f["untracked"] for f in _status(folder)["files"]):
                raise GitError("Commit your changes first (or stage none and put them away in your Git app): switching "
                               "would carry them to the other branch, or lose them.", "changes")
            run(folder, ["switch", "--", name], timeout=WRITE_TIMEOUT)
        elif action == "delete":
            if name not in have:
                raise GitError(f"There's no branch named {name}.")
            if have[name]["current"]:
                raise GitError("Switch to another branch before deleting this one.")
            r = run(folder, ["branch", "--delete", "--", name], check=False)
            if r.code != 0:
                raise GitError(f"{name} has commits that aren't on another branch, so Hoard won't delete it.")
        else:
            raise GitError("Hoard doesn't know that.")
    return branches(folder)


def abort_merge(folder) -> None:
    """Give up a merge that stopped on conflicts: your files go back to how they were before the pull."""
    _gate(folder)
    _must_be_closed(folder, "abort the merge")
    with repo_lock(folder):
        if not merging(folder):
            raise GitError("There's no merge to abort.")
        run(folder, ["merge", "--abort"], timeout=WRITE_TIMEOUT)


def bundle(folder, out: Path) -> bool:
    """The project's history in one file (git bundle: every branch and tag), for a backup; False when there's nothing
    to put in one (no commits). Git LFS files aren't in it."""
    if not where(folder)["repo"] or _status(folder)["initial"]:
        return False
    run(folder, ["bundle", "create", str(out), "--all"], timeout=NETWORK_TIMEOUT)
    return True


def clone_name(url: str) -> str:
    """The folder name a clone of this address gets by default: the last part of its path, without .git."""
    tail = re.split(r"[/:\\]", str(url).rstrip("/\\"))[-1]
    return re.sub(r"\.git$", "", tail) or "Project"


def clone(url: str, dest: Path, progress=None) -> None:
    """Copy a repository into dest (a new folder): its files and history. dest's parent must be there already."""
    url = check_url(url)
    dest = Path(dest)
    if dest.exists():
        raise GitError("A folder with that name is already there.")
    run(dest.parent, ["clone", "--progress", "--", url, str(dest)], timeout=NETWORK_TIMEOUT, progress=progress)
    trust(dest)   # (its settings are Git's own, written as it was copied)


def open_app(folder, app: str) -> None:
    """Open the repository in the Git app you chose (its program, given the project's folder), without a shell."""
    app = str(app or "")
    if sys.platform == "darwin" and app.endswith(".app") and os.path.isdir(app):
        args = ["open", "-a", app, str(folder)]
    elif os.path.isfile(app):
        args = [app, str(folder)]
    else:
        raise GitError("Choose your Git app in the Source control tab first (its program).")
    try:
        subprocess.Popen(args, cwd=str(folder), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         close_fds=True, **_quiet())
    except OSError as e:
        raise GitError(f"That app couldn't be started ({e.strerror or e}).") from None
