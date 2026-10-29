"""Project templates, and making a new project from one, as ALCOM does.

- Built in: VRChat Avatars and VRChat Worlds for Unity 2019.4.31f1, 2022.3.6f1 and 2022.3.22f1 (ALCOM's own
  templates, MIT, kept in templates/ as one .tar.gz each), and Blank, for any Unity installed.
- ALCOM's custom templates: .alcomtemplate files in vrc-get/templates (a base template, packages to add, and
  .unitypackage files to import), so a template made in ALCOM can be used here.
- The Creator Companion's own template folders (Templates/<name>).

A new project is made as ALCOM makes one: the base unpacked into an empty folder, the template's .unitypackage
files placed, the product name and a new product GUID set in ProjectSettings.asset, and the packages it asks for
written into vpm-manifest.json. Installing those packages is the caller's next step (resolve.repair).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tarfile
import uuid
from pathlib import Path

from ..paths import PACKAGE
from ..safety import clean_text
from . import unitypackage
from .project import UnityProject
from .version import DependencyRange, UnityVersion, VersionError, VersionRange

BUILTIN = PACKAGE / "vpm" / "templates"
AVATARS, WORLDS, BLANK = "com.anatawa12.vrc-get.vrchat.avatars", "com.anatawa12.vrc-get.vrchat.worlds", "com.anatawa12.vrc-get.blank"
RESERVED_PREFIX = "com.anatawa12.vrc-get"
VCC_PREFIX = "com.anatawa12.vrc-get.vcc."
USER_PREFIX = "com.anatawa12.vrc-get.user."
MAGIC = "com.anatawa12.vrc-get.custom-template"
VRCHAT_UNITY = ("2022.3.22f1", "2022.3.6f1", "2019.4.31f1")
TEMPLATE_ID = re.compile(r"[0-9A-Za-z._-]+")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
RESERVED_CHARS = set('<>:"/\\|?*')
MAX_TEMPLATE = 1 << 20


class TemplateError(Exception):
    """A template that can't be used, or a project that can't be made, in words to show."""


def _builtin_archive(template_id: str, unity: UnityVersion) -> Path | None:
    """The VRChat template Hoard ships for an avatars or worlds project in that Unity version, or None."""
    kind = {AVATARS: "avatars", WORLDS: "worlds"}.get(template_id)
    return BUILTIN / f"{kind}-{unity}.tar.gz" if kind and str(unity) in VRCHAT_UNITY else None


def parse_alcomtemplate(data: bytes) -> dict:
    """An .alcomtemplate file (JSON, up to the first NUL byte), checked as ALCOM checks it."""
    raw = data.split(b"\x00", 1)[0]
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise TemplateError("That isn't an ALCOM template.") from None
    if not isinstance(doc, dict) or doc.get("$type") != MAGIC:
        raise TemplateError("That isn't an ALCOM template.")
    major = str(doc.get("formatVersion", "")).split(".")[0]
    if major != "1":
        raise TemplateError(f"That template is in a newer format ({doc.get('formatVersion')}) than Hoard reads.")
    base = doc.get("base")
    if not isinstance(base, str) or not TEMPLATE_ID.fullmatch(base) or base.startswith((USER_PREFIX, VCC_PREFIX)):
        raise TemplateError("That template's base template can't be used.")
    tid = doc.get("id")
    if tid is not None and (not isinstance(tid, str) or not TEMPLATE_ID.fullmatch(tid)
                            or (tid.startswith(RESERVED_PREFIX) and not re.fullmatch(re.escape(USER_PREFIX) + "[0-9a-f]{32}", tid))):
        raise TemplateError("That template's id can't be used.")
    deps = {}
    for name, text in (doc.get("vpmDependencies") or {}).items() if isinstance(doc.get("vpmDependencies"), dict) else ():
        try:
            deps[name] = VersionRange.parse(text)
        except VersionError:
            raise TemplateError(f"That template asks for {name} in a way Hoard can't read.") from None
    unity = None
    if doc.get("unityVersion") is not None:
        try:
            unity = VersionRange.parse(doc["unityVersion"])
        except VersionError:
            raise TemplateError("That template's Unity version can't be read.") from None
    packages = [p for p in doc.get("unityPackages") or [] if isinstance(p, str)] if isinstance(doc.get("unityPackages"), list) else []
    return {"name": clean_text(doc.get("displayName"), 200) or "Template", "id": tid, "base": base, "unity": unity,
            "dependencies": deps, "unitypackages": packages, "updated": doc.get("updateDate") if isinstance(doc.get("updateDate"), str) else None}


def write_alcomtemplate(name: str, base: str, dependencies: dict, unitypackages: list[str], unity: str | None = None,
                        template_id: str | None = None) -> bytes:
    """An .alcomtemplate ALCOM can read: for a preset's packages and plain .unitypackage files."""
    doc = {"$type": MAGIC, "formatVersion": "1.0", "displayName": name, "id": template_id or USER_PREFIX + uuid.uuid4().hex,
           "base": base, "vpmDependencies": {k: str(v) for k, v in dependencies.items()}, "unityPackages": list(unitypackages)}
    if unity:
        doc["unityVersion"] = unity
    return json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8")


def templates(vcc_folder: Path, installed_unity: list[str]) -> list[dict]:
    """Every template: [{"id", "name", "kind", "unity" (versions it can be made for), "available", "path"}]."""
    out = {
        AVATARS: {"id": AVATARS, "name": "VRChat Avatars", "kind": "builtin", "unity": list(VRCHAT_UNITY), "available": True},
        WORLDS: {"id": WORLDS, "name": "VRChat Worlds", "kind": "builtin", "unity": list(VRCHAT_UNITY), "available": True},
        BLANK: {"id": BLANK, "name": "Blank", "kind": "builtin", "unity": list(installed_unity), "available": True},
    }
    custom = vcc_folder / "vrc-get" / "templates"
    for path in sorted(custom.glob("*.alcomtemplate")) if custom.is_dir() else []:
        try:
            if path.stat().st_size > MAX_TEMPLATE:
                continue
            t = parse_alcomtemplate(path.read_bytes())
        except (OSError, TemplateError):
            continue
        tid = t["id"] or USER_PREFIX + uuid.uuid5(uuid.NAMESPACE_URL, str(path)).hex
        out[tid] = {"id": tid, "name": t["name"], "kind": "alcom", "unity": [], "available": False, "path": str(path),
                    "template": t}
    vcc_templates = vcc_folder / "Templates"
    for folder in sorted(vcc_templates.iterdir()) if vcc_templates.is_dir() else []:
        if folder.is_dir() and (folder / "package.json").is_file():
            try:
                unity = UnityProject.load(folder).unity
            except Exception:
                continue
            out[VCC_PREFIX + folder.name] = {"id": VCC_PREFIX + folder.name, "name": folder.name, "kind": "vcc",
                                             "unity": [str(unity)] if unity else [], "available": unity is not None,
                                             "path": str(folder)}
    changed = True
    while changed:   # a custom template is available once its base is, for the Unity versions both allow
        changed = False
        for t in out.values():
            if t["available"] or t["kind"] != "alcom":
                continue
            base = out.get(t["template"]["base"])
            if base and base["available"]:
                rng = t["template"]["unity"]
                t["unity"] = [u for u in base["unity"] if rng is None or rng.matches(UnityVersion.parse(u).as_semver())]
                t["available"] = changed = True
    return [{k: v for k, v in t.items() if k != "template"} for t in out.values()]


def _resolve(all_templates: dict, template_id: str, unity: UnityVersion, depth: int = 0) -> dict:
    """What a template makes: its base (an archive, a folder or nothing) and the packages it and its bases ask for.
    Raises TemplateError for a template that can't be used."""
    if depth > 20:
        raise TemplateError("That template's bases go round in a loop.")
    if template_id in (AVATARS, WORLDS):
        archive = _builtin_archive(template_id, unity)
        if archive is None or not archive.is_file():
            raise TemplateError(f"The VRChat templates are for Unity {', '.join(VRCHAT_UNITY)}.")
        return {"base": ("archive", archive), "dependencies": {}, "unitypackages": []}
    if template_id == BLANK:
        return {"base": ("blank", unity), "dependencies": {}, "unitypackages": []}
    t = all_templates.get(template_id)
    if t is None:
        raise TemplateError("That template isn't there any more.")
    if t["kind"] == "vcc":
        return {"base": ("folder", Path(t["path"])), "dependencies": {}, "unitypackages": []}
    parsed = parse_alcomtemplate(Path(t["path"]).read_bytes())
    resolved = _resolve(all_templates, parsed["base"], unity, depth + 1)
    for name, r in parsed["dependencies"].items():
        resolved["dependencies"][name] = r.intersect(resolved["dependencies"][name]) if name in resolved["dependencies"] else r
    resolved["unitypackages"] += parsed["unitypackages"]
    return resolved


def check_name(base: Path, name: str) -> tuple[str | None, str | None]:
    """(why the name can't be used, or None; a warning about it, or None), as ALCOM checks a new project's name."""
    name = (name or "").strip()
    if not name or len(name) > 255 or name.upper() in WINDOWS_RESERVED or any(c in RESERVED_CHARS or ord(c) < 32 for c in name) \
            or name.endswith(".") or name in (".", ".."):
        return "That name can't be used as a folder name.", None
    if (Path(base) / name).exists():
        return "A folder with that name is already there.", None
    if sys.platform == "win32" and "%" in name:
        return None, "A % in a project's name can cause problems in Unity."
    if sys.platform == "win32" and any(ord(c) > 0x7F for c in name):
        return None, "Unity can have trouble with letters outside English ones in a project's folder name on Windows."
    return None, None


def _unpack(archive: Path, dest: Path) -> None:
    """Unpack a template archive into the new project, skipping anything that would land outside it, and links."""
    with tarfile.open(archive, "r:gz") as tar:
        for m in tar.getmembers():
            parts = [p for p in m.name.replace("\\", "/").split("/") if p not in ("", ".")]
            if not parts or ".." in parts or m.name.startswith("/"):
                continue
            target = dest.joinpath(*parts)
            if m.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(m) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)


def _yaml_quote(value: str) -> str:
    """A string as a double-quoted YAML scalar."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r") + '"'


def set_product(project: Path, name: str) -> None:
    """A new project's name and product GUID in ProjectSettings.asset (ALCOM's update_project_name_and_guid)."""
    path = project / "ProjectSettings" / "ProjectSettings.asset"
    try:
        text = path.read_text("utf-8")
    except OSError:
        return
    def put(text, key, value):
        """Replace the first value of key in the settings text."""
        return re.sub(rf"(?m)^(\s*{key}: ).*$", lambda m: m.group(1) + value, text, count=1)
    text = put(text, "productGUID", uuid.uuid4().hex)
    text = put(text, "productName", _yaml_quote(name))
    path.write_text(text, "utf-8")


def create(vcc_folder: Path, installed_unity: list[str], template_id: str, location: Path, name: str,
           unity: UnityVersion, extra: dict | None = None) -> UnityProject:
    """Make the project folder and fill it from the template. The folder must not be there yet. extra: more
    packages to ask for ({name: VersionRange})."""
    problem, _warning = check_name(location, name)
    if problem:
        raise TemplateError(problem)
    all_templates = {t["id"]: t for t in templates(vcc_folder, installed_unity)}
    plan = _resolve(all_templates, template_id, unity)
    location.mkdir(parents=True, exist_ok=True)
    project = location / name.strip()
    project.mkdir()   # (fails if it's there: never made into an existing folder)
    try:
        kind, source = plan["base"]
        if kind == "archive":
            _unpack(source, project)
        elif kind == "folder":
            def ignore(folder, names):
                """What not to copy from a template folder: links, and its own package.json."""
                return [n for n in names if (Path(folder) / n).is_symlink()] + (["package.json"] if Path(folder) == source else [])
            shutil.copytree(source, project, ignore=ignore, dirs_exist_ok=True)
        else:
            for sub in ("Assets", "ProjectSettings", "Packages"):
                (project / sub).mkdir()
            (project / "ProjectSettings" / "ProjectVersion.txt").write_text(f"m_EditorVersion: {unity}\n", "utf-8")
        for package in plan["unitypackages"]:
            try:
                unitypackage.place_file(project, Path(package))
            except (OSError, unitypackage.NotAPackage) as e:
                raise TemplateError(f"The template's package {Path(package).name} couldn't be imported: {e}") from None
        set_product(project, name.strip())
        p = UnityProject.load(project)
        for dep, r in {**plan["dependencies"], **(extra or {})}.items():
            p.add_dependency(dep, DependencyRange.from_version_range(r))
        p.save()
        return p
    except BaseException:
        shutil.rmtree(project, ignore_errors=True)
        raise

