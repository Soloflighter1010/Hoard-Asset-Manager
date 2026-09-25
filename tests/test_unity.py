"""The Unity package's plain-C# core, checked against material made by Hoard's own Python code: catalogs sealed by
the real seal(), canonical JSON from Python's json.dumps, and a .unitypackage built the way Unity builds them.

Needs a C# compiler and runtime (Mono's mcs and mono); skipped without them. GitHub Actions installs them.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import safety  # noqa: E402

PACKAGE = REPO / "Packages" / "soloflighter.hoard"
CORE = PACKAGE / "Editor" / "Core"
HAVE_CSHARP = bool(shutil.which("mcs") and shutil.which("mono"))


def asset(name, folder, url, files, **extra):
    return {"store": "Booth", "name": name, "creator": "Kitsu Studio", "folder": folder, "url": url, "variants": None,
            "added": "2026-09-25T00:00:00+00:00", "files": files, "tags": ["rusk"], "suggested_tags": [], **extra}


def build_material(d: Path) -> None:
    """Everything CoreTests.cs checks against, made by Hoard's own code."""
    key = safety.integrity_key()
    (d / "integrity.key").write_text(key.hex(), "ascii")
    (d / "key_id.txt").write_text(safety._key_id(key))

    cases = [
        {"b": 1, "a": [True, False, None], "c": {"z": "last", "y": "first"}},
        {"日本": "ラスク", "emoji \U0001F98A": "fox", "\uffff": "bmp end", "\U00010000": "past bmp", "é": "e"},
        {"escapes": "quote \" backslash \\ slash / nl \n cr \r tab \t bs \b ff \f nul \u0000 esc \u001b del \u007f"},
        {"nested": {"deep": [{"k": [1, 2, {"x": -3}]}]}, "big": 12345678901234, "neg": -7},
        json.loads('{"dup": 1, "dup": 2, "other": "x"}'),
        {"line sep": "\u2028 and \u2029", "rtl": "a\u202eb", "zero width": "a\u200bb"},
    ]
    (d / "canonical_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=1), "utf-8")
    (d / "canonical_sha256.txt").write_text("\n".join(hashlib.sha256(safety._canonical(c)).hexdigest() for c in cases))

    doc = {"format": "hoard-catalog", "version": 3, "assets": [{"name": "Kitsu ラスク \U0001F98A", "n": 3}]}
    (d / "seal_sealed.json").write_text(json.dumps(safety.seal(doc), ensure_ascii=False, indent=1), "utf-8")
    edited = safety.seal(doc)
    edited["assets"][0]["n"] = 4
    (d / "seal_edited.json").write_text(json.dumps(edited, ensure_ascii=False, indent=1), "utf-8")
    (d / "seal_unsealed.json").write_text(json.dumps(doc, ensure_ascii=False), "utf-8")

    # a downloads folder: good entries, entries breaking each promise, and a planted link
    root = d / "root"
    rusk = root / "Booth" / "Kitsu Studio" / "Rusk Avatar Base"
    rusk.mkdir(parents=True)
    (rusk / "Rusk.unitypackage").write_bytes(b"x")
    (rusk / "_thumbnail.png").write_bytes(b"\x89PNG")
    (root / "Booth" / "Kitsu Studio" / "Odd Link").mkdir()
    outside = d / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (root / "Booth" / "Kitsu Studio" / "Linked Away").symlink_to(outside, target_is_directory=True)
    (root / "Itch" / "Kitsu Studio" / "Paw Suit").mkdir(parents=True)
    (root / "Itch" / "Kitsu Studio" / "Paw Suit" / "PawSuit.unitypackage").write_bytes(b"x")
    good = [asset("Rusk Avatar Base", "Booth/Kitsu Studio/Rusk Avatar Base", "https://booth.pm/ja/items/1", ["Rusk.unitypackage"]),
            asset("Odd Link", "Booth/Kitsu Studio/Odd Link", "https://booth.pm.evil.example/x", []),
            asset("Linked Away", "Booth/Kitsu Studio/Linked Away", None, ["secret.txt"]),
            asset("Paw Suit", "Itch/Kitsu Studio/Paw Suit", "https://kitsu.itch.io/paw-suit", ["PawSuit.unitypackage"], store="Itch")]
    bad = [asset("Escaping", "../outside", None, []), asset("Absolute", "/etc", None, []),
           asset("Hidden \u202e name", "Booth/x", None, []), {**asset("Wrong Store", "Booth/y", None, []), "store": "Steam"},
           asset("", "Booth/z", None, []), "not an object"]
    catalog = {"format": "hoard-catalog", "version": 3, "generated_at": "2026-09-25T00:00:00+00:00", "assets": good + bad}
    (root / "catalog.json").write_text(json.dumps(safety.seal(catalog), ensure_ascii=False, indent=1), "utf-8")
    (d / "good_names.txt").write_text("|".join(a["name"] for a in good))
    (d / "left_out.txt").write_text(str(len(bad)))
    edited_root = d / "root_edited"
    edited_root.mkdir()
    sealed = safety.seal(catalog)
    sealed["assets"][0]["name"] = "Rusk Avatar Base (edited)"
    (edited_root / "catalog.json").write_text(json.dumps(sealed, ensure_ascii=False, indent=1), "utf-8")

    # a Unity package, as Unity builds them: a folder per asset with asset, asset.meta and pathname
    expected = {"0123456789abcdef0123456789abcdef": "Assets/Kitsu/Rusk/Rusk.prefab",
                "fedcba9876543210fedcba9876543210": "Assets/Kitsu/Rusk/Textures/ラスク_body.png",
                "00000000000000000000000000000001": "Assets/" + "Very Long Folder Name/" * 8 + "deep.mat"}
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for guid, path in expected.items():
            for name, data in (("asset", b"\0" * 1500), ("asset.meta", b"fileFormatVersion: 2\n"),
                               ("pathname", (path + "\n00\n").encode())):
                # Unity writes "./<guid>/..." or "<guid>/...": both forms are here
                info = tarfile.TarInfo(f"./{guid}/{name}" if guid.startswith("0123") else f"{guid}/{name}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        long_info = tarfile.TarInfo("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/" + "n" * 120)   # a long name, stored as a GNU 'L' entry
        long_info.size = 3
        tar.addfile(long_info, io.BytesIO(b"abc"))
    (d / "test.unitypackage").write_bytes(gzip.compress(raw.getvalue()))
    (d / "package_expected.txt").write_text("\n".join(sorted(f"{g} {p}" for g, p in expected.items())), "utf-8")
    (d / "not_a_package.unitypackage").write_bytes(gzip.compress(b"hello, this is not a tar file" * 3))
    # hostile packages (S-03, 2.3.1 review): headers claiming far more than follows them
    (d / "huge_name.unitypackage").write_bytes(gzip.compress(tar_header("././@LongLink", 8 ** 11 - 1, b"L") + b"x" * 100))
    (d / "too_big.unitypackage").write_bytes(gzip.compress(tar_header("0123456789abcdef0123456789abcdef/asset",
                                                                       8 ** 12 - 1, b"0") + b"x" * 100))


def tar_header(name: str, size: int, kind: bytes) -> bytes:
    """A GNU tar header claiming whatever size it's given, whatever follows it, the way a hostile package could."""
    h = bytearray(512)
    h[0:len(name)] = name.encode()
    h[100:108], h[108:116], h[116:124], h[136:148] = b"0000644\0", b"0000000\0", b"0000000\0", b"00000000000\0"
    h[124:136] = (f"{size:011o}\0" if size < 8 ** 11 else f"{size:012o}").encode()
    h[156:157], h[257:265] = kind, b"ustar  \0"
    h[148:156] = b" " * 8
    h[148:156] = f"{sum(h):06o}\0 ".encode()
    return bytes(h)


@unittest.skipUnless(HAVE_CSHARP, "needs a C# compiler and runtime (mono-mcs, mono-runtime)")
class UnityCore(unittest.TestCase):

    def test_core_against_hoards_own_material(self):
        d = Path(tempfile.mkdtemp(prefix="hoard-unity-"))
        build_material(d)
        # the release's .unitypackage, built by the release script, for the reader to read back
        built = subprocess.run([sys.executable, str(REPO / "scripts" / "build_vpm.py")], capture_output=True, text=True, timeout=120)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        version = json.loads((PACKAGE / "package.json").read_text("utf-8"))["version"]
        shutil.copy(REPO / "dist" / "vpm" / f"soloflighter.hoard-{version}.unitypackage", d / "release.unitypackage")
        import re
        expected = []
        for meta in PACKAGE.rglob("*.meta"):
            guid = re.search(r"^guid: ([0-9a-f]{32})\r?$", meta.read_text("utf-8"), re.M).group(1)
            rel = meta.relative_to(PACKAGE).as_posix()[:-5]
            expected.append(f"{guid} Packages/soloflighter.hoard/{rel}")
        (d / "release_expected.txt").write_text("\n".join(sorted(expected)), "utf-8")
        exe = d / "CoreTests.exe"
        build = subprocess.run(["mcs", "-langversion:7.2", "-out:" + str(exe), "-r:System.dll", "-r:System.Core.dll",
                                *map(str, sorted(CORE.glob("*.cs"))), str(REPO / "tests" / "unity" / "CoreTests.cs")],
                               capture_output=True, text=True, timeout=180)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        run = subprocess.run(["mono", str(exe), str(d)], capture_output=True, text=True, timeout=120)
        failed = [line for line in run.stdout.splitlines() if line.startswith("FAIL")]
        self.assertEqual(failed, [], run.stdout[-3000:])
        self.assertIn("ALL PASSED", run.stdout, run.stdout + run.stderr)

    def test_core_has_no_unity_references(self):
        """The core must compile without Unity, so it can be tested here; Unity-only code lives in Editor/."""
        for f in CORE.glob("*.cs"):
            text = f.read_text("utf-8")
            self.assertNotIn("using UnityEngine", text, f.name)
            self.assertNotIn("using UnityEditor", text, f.name)


class UnityPackage(unittest.TestCase):
    """The package VCC installs: complete, with fixed GUIDs, editor-only, and built the same way every time."""
    PKG = PACKAGE

    def test_manifest(self):
        m = json.loads((self.PKG / "package.json").read_text("utf-8"))
        self.assertEqual((m["name"], m["author"]["name"], m["unity"]), ("soloflighter.hoard", "SoloFlighter", "2022.3"))
        self.assertRegex(m["version"], r"^\d+\.\d+\.\d+$")
        self.assertIn(f"## {m['version']}", (self.PKG / "CHANGELOG.md").read_text("utf-8"), "each version has changelog notes")

    def test_editor_only(self):
        for asmdef in self.PKG.rglob("*.asmdef"):
            d = json.loads(asmdef.read_text("utf-8"))
            self.assertEqual(d["includePlatforms"], ["Editor"], f"{asmdef.name}: nothing may reach an upload")
        core = json.loads((CORE / "SoloFlighter.Hoard.Core.asmdef").read_text("utf-8"))
        self.assertTrue(core["noEngineReferences"], "the core stays testable outside Unity")

    def test_metas(self):
        sys.path.insert(0, str(REPO / "scripts"))
        import build_vpm
        seen = set()
        for p in self.PKG.rglob("*"):
            if p.suffix == ".meta":
                continue
            meta = p.with_name(p.name + ".meta").read_text("utf-8")
            guid = build_vpm.meta_guid(p)
            self.assertIn(f"guid: {guid}", meta, f"{p.name}: GUIDs come from the path, so they never change")
            self.assertNotIn(guid, seen)
            seen.add(guid)

    def test_build(self):
        import zipfile
        out = subprocess.run([sys.executable, str(REPO / "scripts" / "build_vpm.py")], capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        version = json.loads((self.PKG / "package.json").read_text("utf-8"))["version"]
        dist = REPO / "dist" / "vpm"
        z = zipfile.ZipFile(dist / f"soloflighter.hoard-{version}.zip")
        names = z.namelist()
        self.assertIn("package.json", names, "package.json at the zip's root, as VCC and package-list-action expect")
        self.assertTrue(all(n + ".meta" in names for n in names if not n.endswith(".meta")))
        self.assertEqual((dist / "package.json").read_bytes(), (self.PKG / "package.json").read_bytes())
        with tarfile.open(dist / f"soloflighter.hoard-{version}.unitypackage", "r:gz") as tar:
            paths = [tar.extractfile(m).read().decode() for m in tar.getmembers() if m.name.endswith("/pathname")]
        self.assertTrue(paths and all(p.startswith("Packages/soloflighter.hoard/") for p in paths))
        self.assertIn("Packages/soloflighter.hoard/Editor/HoardWindow.cs", paths)


class TemplateLayout(unittest.TestCase):
    """VRChat's template-package layout: a Unity project at the root, the package in Packages/, the listing's
    details in source.json, and the two workflows (pinned) that release and list it."""

    def test_layout(self):
        self.assertIn("!soloflighter.hoard", (REPO / "Packages" / ".gitignore").read_text())
        self.assertTrue((REPO / "ProjectSettings" / "ProjectVersion.txt").read_text().startswith("m_EditorVersion: 2022.3"))
        source = json.loads((REPO / "source.json").read_text("utf-8"))
        self.assertEqual(source["url"], "https://soloflighter1010.github.io/Hoard-Asset-Manager/index.json")
        self.assertEqual(source["githubRepos"], ["Soloflighter1010/Hoard-Asset-Manager"])
        self.assertIn(source["url"], (REPO / "README.md").read_text("utf-8"))

    def test_workflows(self):
        import re
        release = (REPO / ".github" / "workflows" / "unity-release.yml").read_text()
        listing = (REPO / ".github" / "workflows" / "build-listing.yml").read_text()
        self.assertEqual(re.search(r"^name: (.+)$", release, re.M).group(1), "Build Release",
                         "build-listing waits for a workflow by this name")
        self.assertIn("workflows: [Build Release]", listing)
        self.assertRegex(listing, r"repository: vrchat-community/package-list-action\s+ref: [0-9a-f]{40}")
        self.assertIn("--current-listing-url", listing, "rebuild from every release, so no version drops out")

    def test_website_loads_nothing_from_other_sites(self):
        import re
        for f in ("index.html", "app.js", "styles.css"):
            text = (REPO / "Website" / f).read_text("utf-8")
            loads = re.findall(r'(?:src=|from |url\()\s*["\']?(https?://[^"\')\s]+)', text)
            self.assertEqual(loads, [], f)

if __name__ == "__main__":
    unittest.main()
