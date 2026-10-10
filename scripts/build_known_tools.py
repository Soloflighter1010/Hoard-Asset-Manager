"""Build hoard/known_tools.json: the GUIDs of the shaders and components avatar assets most often need.

A material names its shader by the shader's GUID, and a prefab names each component's script by the script's GUID.
When a package's material or prefab names a GUID that isn't in the package, the package needs something else: this
table says which tool that is (lilToon, Poiyomi, Modular Avatar...). The GUIDs come from each tool's own public
repository, from every release tag, so a material made with an older version is still known (Poiyomi's shaders
change GUID between versions, so its versions are told apart too). The VRChat SDK, which almost every avatar uses,
comes from VRChat's own package listing: the newest release of each of its versions.

    python3 scripts/build_known_tools.py [WORK_DIR]

Needs git and the network; the repositories are cloned without their large files (only .meta files are read) into
WORK_DIR (a temporary folder unless given). Standard library only. Run it again to take in new releases.
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "hoard" / "known_tools.json"

# kinds: "shader" (what materials name) and "component" (the scripts prefabs name; runtime ones, not Editor code)
TOOLS = [
    {"key": "liltoon", "name": "lilToon", "repo": "https://github.com/lilxyzw/lilToon",
     "url": "https://lilxyzw.github.io/lilToon/", "kinds": ("shader",)},
    {"key": "poiyomi", "name": "Poiyomi Toon", "repo": "https://github.com/poiyomi/PoiyomiToonShader",
     "url": "https://www.poiyomi.com/", "kinds": ("shader",), "versions": True},
    {"key": "modular-avatar", "name": "Modular Avatar", "repo": "https://github.com/bdunderscore/modular-avatar",
     "url": "https://modular-avatar.nadena.dev/", "kinds": ("component",)},
    {"key": "vrcfury", "name": "VRCFury", "repo": "https://github.com/VRCFury/VRCFury",
     "url": "https://vrcfury.com/", "kinds": ("component",)},
    {"key": "ndmf", "name": "NDMF", "repo": "https://github.com/bdunderscore/ndmf",
     "url": "https://ndmf.nadena.dev/", "kinds": ("component",)},
    {"key": "avatar-optimizer", "name": "Avatar Optimizer", "repo": "https://github.com/anatawa12/AvatarOptimizer",
     "url": "https://vpm.anatawa12.com/avatar-optimizer/", "kinds": ("component",)},
]

# packages from a VPM listing (the VRChat Creator Companion's), read from their release zips
VPM_TOOLS = [
    {"key": "vrchat-sdk", "name": "VRChat SDK", "listing": "https://packages.vrchat.com/official?download",
     "packages": ("com.vrchat.base", "com.vrchat.avatars"), "url": "https://creators.vrchat.com/sdk/",
     "kinds": ("shader", "component"), "common": True},
]
# who's asking, as VRChat's listing asks every program to say
USER_AGENT = "Hoard-known-tools/1.0 (+https://github.com/Soloflighter1010/Hoard-Asset-Manager)"

GUID = re.compile(r"^guid: ([0-9a-f]{32})\s*$", re.M)
VERSION_FOLDER = re.compile(r"/Shaders/(\d+\.\d+)/")
TAG_VERSION = re.compile(r"(\d+)\.(\d+)")


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def wanted(path: str, kinds: tuple) -> bool:
    if "shader" in kinds and path.endswith((".shader.meta", ".lilcontainer.meta")):
        return True
    if "component" in kinds and path.endswith((".cs.meta", ".dll.meta")):   # (a DLL's components are named by its GUID)
        parts = path.split("/")
        return not any(p == "Editor" or p.endswith("~") or p.lower() in ("tests", "test", "editor tests") for p in parts[:-1])
    return False


def collect(tool: dict, work: Path) -> tuple[dict, str]:
    """{guid: version label or ""} for one tool, from every tag (and the default branch), and the commit read last."""
    clone = work / (tool["key"] + ".git")
    if not clone.exists():
        subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:limit=4k", tool["repo"], str(clone)], check=True)
    head = git("rev-parse", "HEAD", cwd=clone).strip()
    refs = ["HEAD"] + sorted(git("tag", cwd=clone).split(), key=lambda t: [int(n) for n in re.findall(r"\d+", t)] or [0])
    found: dict[str, list] = {}
    blobs: dict[str, list[tuple[str, str]]] = {}   # blob id -> where it is [(path, ref)]: each .meta read once
    for ref in refs:
        for line in git("ls-tree", "-r", ref, cwd=clone).splitlines():
            meta, path = line.split("\t", 1)
            if wanted(path, tool["kinds"]):
                blobs.setdefault(meta.split()[2], []).append((path, ref))
    out = subprocess.run(["git", "cat-file", "--batch"], cwd=clone, input=("\n".join(blobs) + "\n").encode(),
                         capture_output=True, check=True).stdout
    at = 0
    while at < len(out):
        end = out.index(b"\n", at)
        header = out[at:end].decode().split()
        at = end + 1
        if len(header) < 3 or header[1] != "blob":
            continue   # "<id> missing"
        size = int(header[2])
        text, at = out[at:at + size].decode("utf-8", "replace"), at + size + 1
        m = GUID.search(text)
        if not m:
            continue
        places = found.setdefault(m.group(1), [])
        places.extend(blobs[header[0]])
    return {g: version_label(places) if tool.get("versions") else "" for g, places in found.items()}, head


def version_label(places: list[tuple[str, str]]) -> str:
    """Which version of the tool a GUID is: the version folder it's kept in ("Shaders/8.1/..."), or the one version
    (major.minor) of every release it's in; "" for one that's in several versions alike."""
    folders = {m.group(1) for path, _ in places if (m := VERSION_FOLDER.search("/" + path))}
    if len(folders) == 1:
        return folders.pop()
    tags = {f"{m.group(1)}.{m.group(2)}" for _, ref in places if ref != "HEAD" and (m := TAG_VERSION.search(ref))}
    return tags.pop() if len(tags) == 1 and not folders else ""


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def stable_newest(versions) -> list[str]:
    """The newest release (not a beta) of each major.minor version."""
    best: dict[tuple, tuple] = {}
    for v in versions:
        m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", v)
        if m:
            key, n = (int(m.group(1)), int(m.group(2))), int(m.group(3))
            if key not in best or n > best[key][0]:
                best[key] = (n, v)
    return [v for _, v in sorted(best.values(), key=lambda nv: [int(x) for x in nv[1].split(".")])]


def collect_vpm(tool: dict) -> tuple[dict, str]:
    listing = json.loads(fetch(tool["listing"]))["packages"]
    found, read = {}, []
    for name in tool["packages"]:
        versions = listing[name]["versions"]
        for v in stable_newest(versions):
            with zipfile.ZipFile(io.BytesIO(fetch(versions[v]["url"]))) as zf:
                for info in zf.infolist():
                    if wanted(info.filename, tool["kinds"]):
                        m = GUID.search(zf.read(info).decode("utf-8", "replace"))
                        if m:
                            found.setdefault(m.group(1), "")
            read.append(f"{name} {v}")
        print(f"  {name}: {', '.join(stable_newest(versions))}", flush=True)
    return found, f"{tool['listing']} ({len(read)} releases)"


def main() -> int:
    work = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="hoard-tools-"))
    work.mkdir(parents=True, exist_ok=True)
    tools, guids = {}, {}
    for tool in TOOLS:
        found, head = collect(tool, work)
        tools[tool["key"]] = {"name": tool["name"], "url": tool["url"], "from": f"{tool['repo']} @ {head[:12]}"}
        for g, label in sorted(found.items()):
            if g not in guids and not g.startswith("0000000000000000"):
                guids[g] = [tool["key"], label] if label else [tool["key"]]
        print(f"{tool['name']}: {len(found)} GUIDs", flush=True)
    for tool in VPM_TOOLS:
        found, source = collect_vpm(tool)
        tools[tool["key"]] = {"name": tool["name"], "url": tool["url"], "from": source, "common": True}
        for g in sorted(found):
            if g not in guids and not g.startswith("0000000000000000"):
                guids[g] = [tool["key"]]
        print(f"{tool['name']}: {len(found)} GUIDs", flush=True)
    doc = {"format": "hoard-known-tools", "version": 1, "made": date.today().isoformat(), "tools": tools,
           "guids": dict(sorted(guids.items()))}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=False) + "\n", "utf-8")
    print(f"{OUT.relative_to(REPO)}: {len(guids)} GUIDs, {OUT.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
