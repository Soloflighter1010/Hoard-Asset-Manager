"""Projects (hoard/vpm): placing .unitypackage files, templates, the shared project list, your library in a project,
backups and Unity editors. Every test uses its own Creator Companion folder (HOARD_VCC_DIR), never a real one."""
import gzip
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard.vpm import backup, environment, listing, preload, templates, unity, unitypackage
from hoard.vpm.project import AVATARS, UnityProject
from hoard.vpm.version import UnityVersion, VersionRange

G1, G2, G3, G4 = "a" * 32, "b" * 32, "c" * 32, "d" * 32


def make_unitypackage(assets: dict, raw_paths: dict | None = None) -> bytes:
    """{guid: (path, bytes or None for a folder)}; raw_paths: {guid: pathname bytes as written}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for guid, (path, data) in assets.items():
            add(f"{guid}/pathname", (raw_paths or {}).get(guid, path.encode()))
            add(f"{guid}/asset.meta", b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n")
            if data is not None:
                add(f"{guid}/asset", data)
            add(f"{guid}/preview.png", b"\x89PNG not really")
    return gzip.compress(buf.getvalue())


SAMPLE = {G1: ("Assets/Creator", None), G2: ("Assets/Creator/Hoodie.prefab", b"%YAML 1.1\nprefab"),
          G3: ("Assets/Creator/Textures/hoodie.png", b"\x89PNGpicture")}


class Temp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.vcc = self.tmp / "VRChatCreatorCompanion"
        patch = mock.patch.dict(os.environ, {"HOARD_VCC_DIR": str(self.vcc), "HOARD_DATA_DIR": str(self.tmp / "Hoard")})
        patch.start()
        self.addCleanup(patch.stop)

    def project(self, name="Project") -> Path:
        p = self.tmp / name
        for sub in ("Assets", "Packages", "ProjectSettings"):
            (p / sub).mkdir(parents=True)
        (p / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2022.3.22f1\n")
        return p


class Placing(Temp):
    def test_into_a_new_project(self):
        p = self.project()
        r = unitypackage.place(p, io.BytesIO(make_unitypackage(SAMPLE)))
        self.assertEqual(r.placed, 3)
        self.assertEqual((p / "Assets/Creator/Hoodie.prefab").read_bytes(), b"%YAML 1.1\nprefab")
        self.assertIn(G3, (p / "Assets/Creator/Textures/hoodie.png.meta").read_text())
        self.assertTrue((p / "Assets/Creator.meta").is_file())
        self.assertEqual([x.name for x in (p / "Library").iterdir()], [], "nothing left in Library")

    def test_nothing_already_there_is_replaced(self):
        p = self.project()
        (p / "Assets/Creator").mkdir()
        (p / "Assets/Creator/Hoodie.prefab").write_text("my edited prefab")
        (p / "Assets/Creator/Hoodie.prefab.meta").write_text(f"guid: {G2}\n")
        (p / "Assets/Moved.png").write_text("moved by me")
        (p / "Assets/Moved.png.meta").write_text(f"guid: {G3}\n")
        (p / "Assets/Taken.cs").write_text("mine")
        (p / "Assets/Taken.cs.meta").write_text(f"guid: {'e' * 32}\n")
        pkg = dict(SAMPLE, **{G4: ("Assets/Taken.cs", b"theirs")})
        r = unitypackage.place(p, io.BytesIO(make_unitypackage(pkg)), unitypackage.project_guids(p))
        self.assertEqual((r.placed, r.skipped_same, r.skipped_taken), (1, 2, 1))
        self.assertEqual((p / "Assets/Creator/Hoodie.prefab").read_text(), "my edited prefab")
        self.assertEqual((p / "Assets/Taken.cs").read_text(), "mine")
        self.assertFalse((p / "Assets/Creator/Textures/hoodie.png").exists(), "its GUID is already in the project")

    def test_bad_packages_place_nothing(self):
        for name, raw in (("traversal", b"Assets/../../evil.txt"), ("absolute", b"/etc/evil"),
                          ("banned", b"Assets/a:b.txt"), ("dot", b"Assets/./x")):
            with self.subTest(name):
                p = self.project(name)
                with self.assertRaises(unitypackage.NotAPackage):
                    unitypackage.place(p, io.BytesIO(make_unitypackage({G1: ("x", b"evil")}, {G1: raw})))
                self.assertFalse(any((p / "Assets").iterdir()))
                self.assertFalse((self.tmp / "evil.txt").exists())
        p = self.project("other")
        r = unitypackage.place(p, io.BytesIO(make_unitypackage({G1: ("ProjectSettings/x.asset", b"x")})))
        self.assertEqual(r.placed, 0, "only Assets and Packages")
        with self.assertRaises(unitypackage.NotAPackage):
            unitypackage.place(p, io.BytesIO(b"not gzip at all"))

    def test_a_pathname_cut_at_its_line_break(self):
        p = self.project()
        unitypackage.place(p, io.BytesIO(make_unitypackage({G1: ("x", b"1")}, {G1: b"Assets/A.txt\n00"})))
        self.assertEqual((p / "Assets/A.txt").read_bytes(), b"1")

    def test_from_inside_a_zip(self):
        p = self.project()
        z = self.tmp / "product.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("Hoodie/Hoodie.unitypackage", make_unitypackage(SAMPLE))
        self.assertEqual(unitypackage.place_file(p, z, "Hoodie/Hoodie.unitypackage").placed, 3)


class Templates(Temp):
    def test_builtin_templates_are_all_there(self):
        for kind in ("avatars", "worlds"):
            for u in templates.VRCHAT_UNITY:
                self.assertTrue((templates.BUILTIN / f"{kind}-{u}.tar.gz").is_file(), (kind, u))
        self.assertTrue((templates.BUILTIN / "LICENSE-vrc-get.txt").is_file())

    def test_create_from_avatars(self):
        p = templates.create(self.vcc, ["2022.3.22f1"], templates.AVATARS, self.tmp / "Projects", "My Avatar",
                             UnityVersion.parse("2022.3.22f1"), {"nadena.dev.modular-avatar": VersionRange.parse("^1.10.0")})
        self.assertEqual(str(p.unity), "2022.3.22f1")
        self.assertEqual(set(p.dependencies), {"com.vrchat.avatars", "nadena.dev.modular-avatar"})
        settings = (p.folder / "ProjectSettings" / "ProjectSettings.asset").read_text()
        self.assertIn('productName: "My Avatar"', settings)
        self.assertNotIn("productGUID: 00000000000000000000000000000000", settings)
        self.assertTrue((p.folder / "Packages" / "manifest.json").is_file())

    def test_blank_and_names(self):
        p = templates.create(self.vcc, ["6000.0.23f1"], templates.BLANK, self.tmp, "Blank One", UnityVersion.parse("6000.0.23f1"))
        self.assertEqual((p.folder / "ProjectSettings" / "ProjectVersion.txt").read_text(), "m_EditorVersion: 6000.0.23f1\n")
        for bad in ("", "CON", "a/b", "a:b", "..", "x" * 300, "name."):
            self.assertIsNotNone(templates.check_name(self.tmp, bad)[0], bad)
        self.assertEqual(templates.check_name(self.tmp, "Blank One")[0], "A folder with that name is already there.")
        with self.assertRaises(templates.TemplateError):
            templates.create(self.vcc, [], templates.AVATARS, self.tmp, "Wrong Unity", UnityVersion.parse("6000.0.23f1"))
        self.assertFalse((self.tmp / "Wrong Unity").exists(), "nothing is left of a project that couldn't be made")

    def test_alcom_templates(self):
        pkg = self.tmp / "Extra.unitypackage"
        pkg.write_bytes(make_unitypackage(SAMPLE))
        folder = self.vcc / "vrc-get" / "templates"
        folder.mkdir(parents=True)
        data = templates.write_alcomtemplate("With MA", templates.AVATARS, {"nadena.dev.modular-avatar": VersionRange.parse("1.x")},
                                             [str(pkg)], unity="2022.x.x")
        (folder / "with-ma.alcomtemplate").write_bytes(data)
        listed = {t["name"]: t for t in templates.templates(self.vcc, [])}
        mine = listed["With MA"]
        self.assertEqual((mine["kind"], mine["available"]), ("alcom", True))
        self.assertEqual(mine["unity"], ["2022.3.22f1", "2022.3.6f1"], "only the base's 2022 versions")
        p = templates.create(self.vcc, [], mine["id"], self.tmp, "From ALCOM", UnityVersion.parse("2022.3.22f1"))
        self.assertEqual(set(p.dependencies), {"com.vrchat.avatars", "nadena.dev.modular-avatar"})
        self.assertTrue((p.folder / "Assets/Creator/Hoodie.prefab").is_file())
        for bad in (b"{}", b'{"$type": "other"}', json.dumps({"$type": templates.MAGIC, "formatVersion": "2.0", "base": "x"}).encode()):
            with self.assertRaises(templates.TemplateError):
                templates.parse_alcomtemplate(bad)


class ProjectList(Temp):
    def test_add_and_remove_keep_one_list(self):
        self.vcc.mkdir()
        (self.vcc / "settings.json").write_text(json.dumps({"userProjects": ["/a/One"], "other": True}))
        p = self.project("Two")
        listing.add(str(p))
        saved = json.loads((self.vcc / "settings.json").read_text())
        self.assertEqual(saved["userProjects"], [str(p), "/a/One"])
        self.assertTrue(saved["other"])
        shown = listing.projects()
        two = next(x for x in shown if x["path"] == str(p))
        self.assertEqual((two["name"], two["exists"], two["unity"]), ("Two", True, "2022.3.22f1"))
        self.assertFalse(next(x for x in shown if x["path"] == "/a/One")["exists"])
        self.assertTrue(listing.remove("/a/One"))
        self.assertEqual(json.loads((self.vcc / "settings.json").read_text())["userProjects"], [str(p)])

    def test_with_no_list_in_settings_the_database_is_kept_whole(self):
        self.vcc.mkdir()
        (self.vcc / "settings.json").write_text("{}")
        (self.vcc / "vcc.liteDb").write_bytes(gzip.decompress((Path(__file__).parent / "data" / "vcc-sample.liteDb.gz").read_bytes()))
        self.assertEqual(len(listing.projects()), 41)
        listing.add(str(self.project("New")))
        saved = json.loads((self.vcc / "settings.json").read_text())["userProjects"]
        self.assertEqual(len(saved), 42, "every project the database had, and the new one")
        self.assertEqual(saved[0], str(self.tmp / "New"))

    def test_notes(self):
        listing.note("/x/P", favorite=True)
        listing.add_preloaded("/x/P", [{"tag_key": "booth/hoodie", "file": "Hoodie.unitypackage", "name": "Hoodie"}])
        listing.add_preloaded("/x/P", [{"tag_key": "booth/hoodie", "file": "Hoodie.unitypackage", "name": "Hoodie"}])
        state = listing.load_state()["projects"][listing._key("/x/P")]
        self.assertTrue(state["favorite"])
        self.assertEqual(len(state["preloaded"]), 1)


class Library(Temp):
    def asset(self, files: dict, **extra) -> dict:
        folder = self.tmp / "downloads" / "Booth" / "Product"
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(data)
        return {"abs_folder": str(folder), "name": "Product", "store": "Booth", "tag_key": "booth/product",
                "files": [{"path": n, "size": len(d)} for n, d in files.items()], **extra}

    def zipped(self, members: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return buf.getvalue()

    def test_what_a_product_holds(self):
        vpm = self.zipped({"package.json": json.dumps({"name": "com.creator.tool", "version": "1.2.0", "displayName": "Tool"}),
                           "Editor/Tool.cs": "//"})
        a = self.asset({"Avatar.unitypackage": make_unitypackage(SAMPLE),
                        "Outfits.zip": self.zipped({"Outfits/PC.unitypackage": make_unitypackage(SAMPLE),
                                                    "Outfits/Quest.unitypackage": make_unitypackage(SAMPLE),
                                                    "Outfits/tool-1.2.0.zip": vpm, "readme.txt": "hi"}),
                        "Wrapped.zip": self.zipped({"com.creator.tool/package.json": json.dumps({"name": "com.creator.tool", "version": "1.3.0"})})})
        found = preload.contents(a)
        kinds = [(c["kind"], c["file"], c["member"], c.get("package")) for c in found]
        self.assertIn(("unitypackage", "Avatar.unitypackage", None, None), kinds)
        self.assertIn(("unitypackage", "Outfits.zip", "Outfits/Quest.unitypackage", None), kinds)
        self.assertIn(("vpm", "Outfits.zip", "Outfits/tool-1.2.0.zip", "com.creator.tool"), kinds)
        self.assertIn(("vpm", "Wrapped.zip", None, "com.creator.tool"), kinds)

    def test_putting_it_in(self):
        vpm = self.zipped({"tool/package.json": json.dumps({"name": "com.creator.tool", "version": "1.2.0",
                                                            "vpmDependencies": {"nadena.dev.ndmf": "^1.0.0"}}),
                           "tool/Editor/Tool.cs": "//", "tool/../../escape.txt": "x"})
        a = self.asset({"Avatar.unitypackage": make_unitypackage(SAMPLE), "Tool.zip": vpm})
        p = self.project()
        picks = [(a, c) for c in preload.contents(a)]
        done = preload.apply(p, picks, new_project=True)
        self.assertEqual(done["placed"], 3)
        self.assertEqual(done["failed"][0]["what"], "Product: com.creator.tool", "the package with an escaping file isn't added")
        self.assertFalse((p / "Packages" / "com.creator.tool").exists())
        good = self.zipped({"tool/package.json": json.dumps({"name": "com.creator.tool", "version": "1.2.0",
                                                             "vpmDependencies": {"nadena.dev.ndmf": "^1.0.0"}}),
                            "tool/Editor/Tool.cs": "//"})
        a = self.asset({"Tool.zip": good})
        done = preload.apply(p, [(a, c) for c in preload.contents(a)], new_project=False)
        self.assertEqual(done["packages"], [{"name": "com.creator.tool", "label": "com.creator.tool", "result": "added"}])
        self.assertEqual((p / "Packages/com.creator.tool/Editor/Tool.cs").read_text(), "//")
        project = UnityProject.load(p)
        self.assertEqual([(n, x.name) for n, x in project.unlocked], [("com.creator.tool", "com.creator.tool")])
        again = preload.apply(p, [(a, c) for c in preload.contents(a)], new_project=False)
        self.assertEqual(again["packages"][0]["result"], "already-there")

    def test_tools_as_packages(self):
        from hoard import needs
        for key in needs.known()["tools"]:
            self.assertIn(key, preload.TOOL_PACKAGES, f"{key}: which VPM package provides it?")
        self.assertEqual(preload.suggested_packages(["modular-avatar"])[0]["package"], "nadena.dev.modular-avatar")


class Backups(Temp):
    def test_backup_leaves_out_what_unity_rebuilds(self):
        p = self.project()
        (p / "Assets" / "a.txt").write_text("a")
        for junk in ("Library/big.bin", "Temp/x", "Logs/l.txt", "obj/o", "Library-Android/x"):
            (p / junk).parent.mkdir(parents=True, exist_ok=True)
            (p / junk).write_text("junk")
        (p / "Packages" / "com.vrchat.base").mkdir()
        (p / "Packages" / "com.vrchat.base" / "package.json").write_text("{}")
        out = backup.back_up(p, self.tmp / "Backups", {"com.vrchat.base"})
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        self.assertEqual(names, {"Assets/a.txt", "ProjectSettings/ProjectVersion.txt"})
        self.assertTrue(out.name.startswith("Project-") and out.suffix == ".zip")
        self.assertEqual([b["path"] for b in backup.found(self.tmp / "Backups")], [str(out)], "a new backup is listed")

    def backups(self, folder: Path, *names: str) -> list[Path]:
        folder.mkdir(parents=True, exist_ok=True)
        out = []
        for n in names:
            (folder / n).write_bytes(b"PK\x05\x06" + bytes(18) + n.encode())
            out.append(folder / n)
        return out

    def test_the_panel_lists_backups_and_which_are_old(self):
        """The backup manager: the newest few of each project are kept, the rest are old once they're old enough;
        only zips named as a backup are listed."""
        f = self.tmp / "Backups"
        self.backups(f, *[f"Avatar-2025-0{m}-01T10-00-00.zip" for m in range(1, 6)], "World-2025-01-01T10-00-00.zip",
                     "notes.zip", "Avatar.zip", "Avatar-2025-07-01T10-00-00.zip.part")
        (f / "Sub-2025-01-01T10-00-00.zip").mkdir()
        found = backup.found(f)
        self.assertEqual([b["name"] for b in found][:2], ["Avatar-2025-05-01T10-00-00.zip", "Avatar-2025-04-01T10-00-00.zip"])
        self.assertEqual(len(found), 6, "only zips named <project>-<date>T<time>.zip")
        self.assertEqual((found[0]["project"], found[0]["when"]), ("Avatar", "2025-05-01T10:00:00"))
        now = 1767225600   # 2026-01-01
        old = {b["name"] for b in backup.mark_old(found, keep=3, days=30, now=now) if b["old"]}
        self.assertEqual(old, {"Avatar-2025-01-01T10-00-00.zip", "Avatar-2025-02-01T10-00-00.zip"},
                         "past the newest three of Avatar; World's only one stays")
        self.assertFalse(any(b["old"] for b in backup.mark_old(found, keep=3, days=365, now=now)), "not old enough yet")
        view = backup.overview(f, None, 3, 30)
        self.assertEqual((view["keep"], view["days"], len(view["backups"])), (3, 30, 6))
        self.assertIn("free", view["room"])

    def test_only_backups_can_be_deleted_or_moved(self):
        """What a page asks to delete or move is checked: a backup-named zip, directly in the backups folder or the
        one old ones were moved to, and not a link."""
        f, away = self.tmp / "Backups", self.tmp / "Elsewhere"
        a, b = self.backups(f, "Avatar-2025-01-01T10-00-00.zip", "Avatar-2025-02-01T10-00-00.zip")
        (other,) = self.backups(self.tmp / "Other", "Avatar-2025-03-01T10-00-00.zip")
        self.assertEqual(backup.chosen([str(a)], [f, None]), [a])
        for bad in (str(other), str(f / "notes.zip"), "Avatar-2025-01-01T10-00-00.zip", str(f / ".." / "Other" / other.name)):
            with self.assertRaises(ValueError, msg=bad):
                backup.chosen([bad], [f, None])
        (f / "notes.zip").write_bytes(b"x")
        with self.assertRaises(ValueError):
            backup.chosen([str(f / "notes.zip")], [f])
        if hasattr(os, "symlink"):
            try:
                os.symlink(other, f / "Link-2025-04-01T10-00-00.zip")
            except OSError:
                pass
            else:
                with self.assertRaises(ValueError, msg="a link"):
                    backup.chosen([str(f / "Link-2025-04-01T10-00-00.zip")], [f])
        count, freed, problems = backup.move([a], away)
        self.assertEqual((count, problems), (1, []))
        self.assertFalse(a.exists())
        self.assertTrue((away / a.name).is_file())
        self.assertEqual(freed, (away / a.name).stat().st_size)
        self.assertEqual(backup.chosen([str(away / a.name)], [f, away]), [away / a.name], "a moved one, there")
        (away / b.name).write_bytes(b"already here")
        count, _, problems = backup.move([b], away)
        self.assertEqual(count, 0)
        self.assertTrue(b.exists(), "one already there by that name is left, and this one kept")
        self.assertIn("already", problems[0])
        self.assertEqual(backup.delete([b])[0], 1)
        self.assertFalse(b.exists())
        self.assertFalse(list(away.glob("*.part")), "no half-made copy left")

    def test_a_drive_low_on_room(self):
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=5 << 30, total=500 << 30)):
            self.assertTrue(backup.room(self.tmp)["low"], "under 10 GB")
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=40 << 30, total=500 << 30)):
            self.assertTrue(backup.room(self.tmp)["low"], "under 10%")
        with mock.patch("shutil.disk_usage", return_value=mock.Mock(free=200 << 30, total=500 << 30)):
            self.assertFalse(backup.room(self.tmp / "not made yet")["low"])

    def test_the_rule_is_kept(self):
        self.assertEqual(listing.backup_prefs(), {"keep": 3, "days": 30, "moved_to": ""})
        listing.set_backup_prefs(keep=5, days=90, moved_to=str(self.tmp / "E"))
        self.assertEqual(listing.backup_prefs(), {"keep": 5, "days": 90, "moved_to": str(self.tmp / "E")})
        listing.set_backup_prefs(keep=4)   # not one of the choices
        self.assertEqual(listing.backup_prefs()["keep"], 3)


class Editors(Temp):
    def test_found_in_hubs_folder_and_located_ones(self):
        hub = self.tmp / "Hub" / "Editor"
        for v in ("2022.3.22f1", "2019.4.31f1", "2022.3.22f1-x86_64", "not-a-version"):
            exe = unity.editor_in(hub / v)
            exe.parent.mkdir(parents=True, exist_ok=True)
            exe.touch() if sys.platform != "darwin" else exe.mkdir(parents=True)
        located = self.tmp / "Elsewhere" / "Unity"
        located.parent.mkdir()
        located.touch()
        data = self.tmp / "hubdata"
        data.mkdir()
        (data / "editors-v2.json").write_text(json.dumps({"data": [{"version": "6000.0.23f1", "location": [str(located)]}]}))
        with mock.patch.object(unity, "_hub_install_folder", return_value=hub), \
                mock.patch.object(unity, "_hub_user_data", return_value=data):
            found = unity.find_editors([{"Version": "2021.3.0f1", "Path": str(self.tmp / "gone")}])
        self.assertEqual([e["version"] for e in found], ["6000.0.23f1", "2022.3.22f1", "2022.3.22f1", "2019.4.31f1"])
        self.assertEqual(unity.editor_for(UnityVersion.parse("2019.4.31f1"), found)["version"], "2019.4.31f1")
        self.assertIsNone(unity.editor_for(UnityVersion.parse("2021.3.0f1"), found))

    @unittest.skipIf(sys.platform == "win32", "Windows locks differently (checked there by opening the file)")
    def test_open_in_unity(self):
        import fcntl
        p = self.project()
        self.assertFalse(unity.project_open_in_unity(p))
        (p / "Temp").mkdir()
        lock = p / "Temp" / "UnityLockFile"
        lock.touch()
        self.assertFalse(unity.project_open_in_unity(p), "left behind by a Unity that's closed")
        import subprocess
        holder = subprocess.Popen([sys.executable, "-c", "import fcntl,sys,time; f=open(sys.argv[1],'r+b'); "
                                   "fcntl.lockf(f, fcntl.LOCK_EX); print('locked', flush=True); time.sleep(30)", str(lock)],
                                  stdout=subprocess.PIPE)
        try:
            holder.stdout.readline()
            self.assertTrue(unity.project_open_in_unity(p))
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()


if __name__ == "__main__":
    unittest.main()
