"""Changing a project's packages (hoard/vpm/resolve.py), against vrc-get's own cases.

Each test here is one of vrc-get's (vrc-get-vpm/tests: add_package_to_project.rs, remove_package.rs,
resolve_project.rs; MIT), with the same project, the same packages and the same expected result, so Hoard's resolver
is checked to decide exactly as ALCOM's does. As there, a test collection gives the first version that fits, in the
order its packages were added.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hoard.vpm import resolve
from hoard.vpm.manifest import Package
from hoard.vpm.project import UnityProject
from hoard.vpm.repos import Info
from hoard.vpm.version import DependencyRange, Version


def pkg(name, version, deps=None, legacy_packages=(), legacy_folders=None, legacy_files=None):
    return Package.parse({"name": name, "version": version, "vpmDependencies": deps or {},
                          "legacyPackages": list(legacy_packages), "legacyFolders": legacy_folders or {},
                          "legacyFiles": legacy_files or {}})


class Collection:
    """vrc-get's test PackageCollection: packages in the order added; a search gives the first that fits."""

    def __init__(self, *packages, root=None):
        self.infos = [Info(p, folder=(root or Path("/nonexistent")) / p.name / str(p.version)) for p in packages]

    def find(self, name, selector):
        return next((i for i in self.infos if i.name == name and selector.satisfies(i.package)), None)

    def get(self, name, version):
        return next(i for i in self.infos if i.name == name and i.version == Version.parse(version))


class Case(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)

    def project(self, dependencies=None, locked=None, files=None, dirs=(), unity="2019.4.31f1"):
        """vrc-get's VirtualProjectBuilder: dependencies {name: range}, locked {name: (version, {dep: range})}."""
        folder = self.root / "project"
        (folder / "Packages").mkdir(parents=True)
        (folder / "ProjectSettings").mkdir()
        manifest = {"dependencies": {n: {"version": v} for n, v in (dependencies or {}).items()},
                    "locked": {n: {"version": v, "dependencies": d} for n, (v, d) in (locked or {}).items()}}
        (folder / "Packages" / "vpm-manifest.json").write_text(json.dumps(manifest))
        (folder / "ProjectSettings" / "ProjectVersion.txt").write_text(
            f"m_EditorVersion: {unity}\nm_EditorVersionWithRevision: {unity} (bd5abf232a62)\n")
        for name, text in (files or {}).items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(text)
        for name in dirs:
            (folder / name).mkdir(parents=True, exist_ok=True)
        return UnityProject.load(folder)

    # vrc-get's assertions

    def counts(self, changes, packages, conflicts=0, folders=0, files=0):
        self.assertEqual(len(changes.packages), packages, changes.packages)
        self.assertEqual(len(changes.conflicts), conflicts)
        self.assertEqual(len(changes.legacy_folders), folders)
        self.assertEqual(len(changes.legacy_files), files)

    def removed(self, changes, name, reason):
        c = changes.packages[name]
        self.assertIsInstance(c, resolve.Remove)
        self.assertEqual(c.reason, reason)

    def install_only(self, changes, info):
        c = changes.packages[info.name]
        self.assertIsInstance(c, resolve.Install)
        self.assertFalse(c.add_to_locked)
        self.assertIsNone(c.to_dependencies)
        self.assertIs(c.package.package, info.package)

    def to_locked_only(self, changes, info):
        c = changes.packages[info.name]
        self.assertIsInstance(c, resolve.Install)
        self.assertTrue(c.add_to_locked, info.name)
        self.assertIsNone(c.to_dependencies, info.name)
        self.assertIs(c.package.package, info.package)

    def to_both(self, changes, info):
        c = changes.packages[info.name]
        self.assertIsInstance(c, resolve.Install)
        self.assertTrue(c.add_to_locked)
        self.assertEqual(c.to_dependencies, DependencyRange.version(info.version))
        self.assertIs(c.package.package, info.package)

    def to_dependencies_only(self, changes, name, version):
        c = changes.packages[name]
        self.assertIsInstance(c, resolve.Install)
        self.assertFalse(c.add_to_locked)
        self.assertIsNone(c.package)
        self.assertEqual(c.to_dependencies, DependencyRange.version(Version.parse(version)))


AVATARS_ON_BASE = {"com.vrchat.avatars": ("1.0.0", {"com.vrchat.base": "1.0.0"}), "com.vrchat.base": ("1.0.0", {})}


class Add(Case):
    # basic operations

    def test_add_to_dependencies(self):
        project = self.project()
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}), pkg("com.vrchat.base", "1.0.0"))
        avatars, base = c.get("com.vrchat.avatars", "1.0.0"), c.get("com.vrchat.base", "1.0.0")
        r = resolve.add(project, c, [avatars], resolve.INSTALL)
        self.counts(r, 2)
        self.to_both(r, avatars)
        self.to_locked_only(r, base)

    def test_install_already_installed_in_locked_to_locked(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE)
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}), pkg("com.vrchat.base", "1.0.0"))
        self.counts(resolve.add(project, c, [c.get("com.vrchat.avatars", "1.0.0")], resolve.UPGRADE), 0)

    def test_install_already_installed_in_locked_to_dependencies(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE)
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}), pkg("com.vrchat.base", "1.0.0"))
        r = resolve.add(project, c, [c.get("com.vrchat.base", "1.0.0")], resolve.INSTALL)
        self.counts(r, 1)
        self.to_dependencies_only(r, "com.vrchat.base", "1.0.0")

    def test_install_already_installed_in_dependencies_to_dependencies(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE)
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}), pkg("com.vrchat.base", "1.0.0"))
        self.counts(resolve.add(project, c, [c.get("com.vrchat.avatars", "1.0.0")], resolve.INSTALL), 0)

    def test_upgrading_unused_packages(self):
        project = self.project(locked=AVATARS_ON_BASE)
        c = Collection(pkg("com.vrchat.avatars", "1.1.0", {"com.vrchat.base": "1.1.0"}), pkg("com.vrchat.base", "1.1.0"))
        avatars, base = c.get("com.vrchat.avatars", "1.1.0"), c.get("com.vrchat.base", "1.1.0")
        r = resolve.add(project, c, [avatars], resolve.UPGRADE)
        self.counts(r, 2)
        self.to_locked_only(r, avatars)
        self.to_locked_only(r, base)

    # removing what's no longer used

    def test_transitive_unused_remove_with_upgrade(self):
        project = self.project({"com.anatawa12.package": "1.0.0"},
                               {"com.anatawa12.package": ("1.0.0", {"com.anatawa12.library": "1.0.0"}),
                                "com.anatawa12.library": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.1.0"))
        package = c.get("com.anatawa12.package", "1.1.0")
        r = resolve.add(project, c, [package], resolve.UPGRADE)
        self.counts(r, 2)
        self.to_locked_only(r, package)
        self.removed(r, "com.anatawa12.library", resolve.UNUSED)

    def test_do_not_remove_transitively_when_untouched(self):
        project = self.project({"com.anatawa12.package": "1.0.0"},
                               {"com.anatawa12.package": ("1.0.0", {"com.anatawa12.library": "1.0.0"}),
                                "com.anatawa12.library": ("1.0.0", {}),
                                "com.anatawa12.untouched_library": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.1.0"))
        package = c.get("com.anatawa12.package", "1.1.0")
        r = resolve.add(project, c, [package], resolve.UPGRADE)
        self.counts(r, 2)
        self.to_locked_only(r, package)
        self.removed(r, "com.anatawa12.library", resolve.UNUSED)

    def test_remove_legacy_package_when_install(self):
        project = self.project({"com.anatawa12.legacy-package": "1.0.0"}, {"com.anatawa12.legacy-package": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.1.0", legacy_packages=["com.anatawa12.legacy-package"]))
        package = c.get("com.anatawa12.package", "1.1.0")
        r = resolve.add(project, c, [package], resolve.INSTALL)
        self.counts(r, 2)
        self.to_both(r, package)
        self.removed(r, "com.anatawa12.legacy-package", resolve.LEGACY)

    def test_remove_legacy_package_when_upgrade(self):
        project = self.project({"com.anatawa12.package": "1.0.0"},
                               {"com.anatawa12.legacy-package": ("1.0.0", {}), "com.anatawa12.package": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.1.0", legacy_packages=["com.anatawa12.legacy-package"]))
        package = c.get("com.anatawa12.package", "1.1.0")
        r = resolve.add(project, c, [package], resolve.UPGRADE)
        self.counts(r, 2)
        self.to_locked_only(r, package)
        self.removed(r, "com.anatawa12.legacy-package", resolve.LEGACY)

    def test_remove_referenced_legacy_package_when_install(self):
        project = self.project({"com.anatawa12.user": "1.0.0", "com.anatawa12.legacy-package": "1.0.0"},
                               {"com.anatawa12.user": ("1.0.0", {"com.anatawa12.legacy-package": "^1.0.0"}),
                                "com.anatawa12.legacy-package": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.1.0", legacy_packages=["com.anatawa12.legacy-package"]))
        package = c.get("com.anatawa12.package", "1.1.0")
        r = resolve.add(project, c, [package], resolve.INSTALL)
        self.counts(r, 2)
        self.to_both(r, package)
        self.removed(r, "com.anatawa12.legacy-package", resolve.LEGACY)

    # legacy assets

    def test_legacy_assets_by_path(self):
        project = self.project(dirs=["Assets/LegacyFolder", "Packages/legacy.package"],
                               files={"Assets/LegacyAsset.cs": "// empty file"})
        c = Collection(pkg("com.anatawa12.package", "1.0.0",
                           legacy_folders={"Assets\\LegacyFolder": "", "Assets\\NotExists": "",
                                           "Packages\\legacy.package": ""},
                           legacy_files={"Assets\\LegacyAsset.cs": ""}))
        r = resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL)
        self.assertEqual(len(r.packages), 1)
        self.assertEqual(set(r.legacy_folders), {("Assets/LegacyFolder", "com.anatawa12.package"),
                                                 ("Packages/legacy.package", "com.anatawa12.package")})
        self.assertEqual(set(r.legacy_files), {("Assets/LegacyAsset.cs", "com.anatawa12.package")})

    def test_legacy_assets_by_guid(self):
        project = self.project(dirs=["Assets/MovedLegacyFolder"],
                               files={"Assets/MovedLegacyFolder.meta": "guid: 1c54b633da4d4d2abc01c6dedae67e09",
                                      "Assets/MovedLegacyAsset.cs": "// empty file",
                                      "Assets/MovedLegacyAsset.cs.meta": "guid: ca06b0788d62432083b3577cc2346126"})
        c = Collection(pkg("com.anatawa12.package", "1.0.0",
                           legacy_folders={"Assets\\LegacyFolder": "1c54b633da4d4d2abc01c6dedae67e09",
                                           "Assets\\NotExists": "62a9615044174c818622c19d0181d036"},
                           legacy_files={"Assets\\LegacyAsset.cs": "ca06b0788d62432083b3577cc2346126"}))
        r = resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL)
        self.assertEqual(len(r.packages), 1)
        self.assertEqual(r.legacy_folders, [("Assets/MovedLegacyFolder", "com.anatawa12.package")])
        self.assertEqual(r.legacy_files, [("Assets/MovedLegacyAsset.cs", "com.anatawa12.package")])

    def test_deny_remove_files_not_in_assets_or_packages(self):
        project = self.project(dirs=["Assets1/LegacyFolder", "Packages1/legacy.package"],
                               files={"Assets1/LegacyAsset.cs": "// empty file"})
        c = Collection(pkg("com.anatawa12.package", "1.0.0",
                           legacy_folders={"Assets1\\LegacyFolder": "", "Assets1\\NotExists": "",
                                           "Packages1\\legacy.package": ""},
                           legacy_files={"Assets1\\LegacyAsset.cs": ""}))
        self.counts(resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL), 1)

    def test_deny_remove_parent_folders_and_absolute_paths(self):
        project = self.project()
        c = Collection(pkg("com.anatawa12.package", "1.0.0",
                           legacy_folders={"..": "", "Assets/..": "", "": "", "/": "", "Assets/../..": "",
                                           "C:\\Windows": "", "Assets/./x/../..": ""}))
        self.counts(resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL), 1)

    def test_deny_a_path_that_leads_outside_through_a_link(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "precious.txt").write_text("keep me")
        project = self.project(dirs=["Assets"])
        try:
            (project.folder / "Assets" / "Linked").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("this system can't make the link")
        c = Collection(pkg("com.anatawa12.package", "1.0.0", legacy_files={"Assets/Linked/precious.txt": ""},
                           legacy_folders={"Assets/Linked": ""}))
        r = resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL)
        self.assertEqual((r.legacy_files, r.legacy_folders), ([], []))

    def test_do_remove_legacy_files_that_guid_mismatches(self):
        project = self.project(
            dirs=["Assets/LegacyGuidMismatchFolder", "Assets/LegacyGuidMatchFolder"],
            files={"Assets/LegacyGuidMismatchFolder.meta": "guid: 75ead46ee7514680afd1ed9008423371",
                   "Assets/LegacyGuidMatchFolder.meta": "guid: cbac8a2877e64d75af9b3b61fe946b40",
                   "Assets/LegacyGuidMismatchAsset.cs": "// empty file",
                   "Assets/LegacyGuidMismatchAsset.cs.meta": "guid: 85cc942c4a8a487ebe7df9937d15bdf8",
                   "Assets/LegacyGuidMatchAsset.cs": "// empty file",
                   "Assets/LegacyGuidMatchAsset.cs.meta": "guid: 85cc942c4a8a487ebe7df9937d15bdf8"})
        c = Collection(pkg("com.anatawa12.package", "1.0.0",
                           legacy_folders={"Assets\\LegacyGuidMismatchFolder": "39bfddf4f3ac48c6845997a81fc5262c",
                                           "Assets\\LegacyGuidMatchFolder": "cbac8a2877e64d75af9b3b61fe946b40"},
                           legacy_files={"Assets\\LegacyGuidMismatchAsset.cs": "417a8085479b433792a67b2dfefb1982",
                                         "Assets\\LegacyGuidMatchAsset.cs": "85cc942c4a8a487ebe7df9937d15bdf8"}))
        r = resolve.add(project, c, [c.get("com.anatawa12.package", "1.0.0")], resolve.INSTALL)
        by = "com.anatawa12.package"
        self.assertEqual(set(r.legacy_folders), {("Assets/LegacyGuidMatchFolder", by), ("Assets/LegacyGuidMismatchFolder", by)})
        self.assertEqual(set(r.legacy_files), {("Assets/LegacyGuidMatchAsset.cs", by), ("Assets/LegacyGuidMismatchAsset.cs", by)})

    def test_do_not_remove_udonsharp_folder_if_guid_mismatch(self):
        project = self.project(dirs=["Assets/UdonSharp"], files={"Assets/UdonSharp.meta": "guid: e2095dec983b4d9481723c263fd5b6c0"})
        c = Collection(pkg("com.vrchat.worlds", "1.0.0", legacy_folders={"Assets\\UdonSharp": "b031f928e5c709b4887f6513084aaa51"}))
        self.counts(resolve.add(project, c, [c.get("com.vrchat.worlds", "1.0.0")], resolve.INSTALL), 1)

    # errors

    def test_not_found(self):
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}))
        with self.assertRaises(resolve.ResolveError) as e:
            resolve.add(self.project(), c, [c.get("com.vrchat.avatars", "1.0.0")], resolve.INSTALL)
        self.assertEqual(list(e.exception.missing), ["com.vrchat.base"])

    def test_updating_non_locked_package_is_an_error(self):
        c = Collection(pkg("com.vrchat.avatars", "1.0.0"))
        with self.assertRaisesRegex(resolve.ResolveError, "isn't installed"):
            resolve.add(self.project(), c, [c.get("com.vrchat.avatars", "1.0.0")], resolve.UPGRADE)

    def test_downgrade_basic(self):
        project = self.project({"com.vrchat.base": "1.0.0"}, {"com.vrchat.base": ("1.1.0", {})})
        c = Collection(pkg("com.vrchat.base", "1.0.0"))
        base = c.get("com.vrchat.base", "1.0.0")
        r = resolve.add(project, c, [base], resolve.DOWNGRADE)
        self.counts(r, 1)
        self.to_locked_only(r, base)

    def test_downgrade_dependencies(self):
        project = self.project({"com.vrchat.base": "1.1.0"}, {"com.vrchat.base": ("1.1.0", {})})
        c = Collection(pkg("com.vrchat.base", "1.0.0"))
        base = c.get("com.vrchat.base", "1.0.0")
        r = resolve.add(project, c, [base], resolve.DOWNGRADE)
        self.counts(r, 1)
        self.to_both(r, base)

    # conflicts

    def collection_with_tool(self):
        return Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}), pkg("com.vrchat.base", "1.0.0"),
                          pkg("com.vrchat.base", "1.1.0"), pkg("com.anatawa12.tool", "1.0.0", {"com.vrchat.base": "^1.1.0"}))

    def test_conflict_requirements_of_installed_and_installing(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE)
        c = self.collection_with_tool()
        tool = c.get("com.anatawa12.tool", "1.0.0")
        r = resolve.add(project, c, [tool], resolve.INSTALL)
        self.counts(r, 2, conflicts=1)
        self.to_both(r, tool)
        self.to_locked_only(r, c.get("com.vrchat.base", "1.1.0"))
        self.assertEqual(r.conflicts["com.vrchat.base"].packages, ["com.vrchat.avatars"])

    def test_conflict_already_conflicted_and_no_new_conflict(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"},
                               {"com.vrchat.avatars": ("1.0.0", {"com.vrchat.base": "1.0.0"}),
                                "com.vrchat.base": ("1.1.0", {})})
        c = self.collection_with_tool()
        tool = c.get("com.anatawa12.tool", "1.0.0")
        r = resolve.add(project, c, [tool], resolve.INSTALL)
        self.counts(r, 1)
        self.to_both(r, tool)

    def test_conflict_requirements_of_installed_and_installing_related_to_dependencies(self):
        project = self.project({"com.vrchat.avatars": "~3.5.x"},
                               {"com.vrchat.avatars": ("3.4.2", {"com.vrchat.base": "3.4.2"}),
                                "com.vrchat.base": ("3.4.2", {})})
        c = Collection(pkg("com.vrchat.base", "3.4.2", {"com.vrchat.avatars": "3.4.2"}), pkg("com.vrchat.base", "3.4.2"),
                       pkg("com.anatawa12.tool", "1.0.0", {"com.vrchat.avatars": "^3.3.0"}))
        tool = c.get("com.anatawa12.tool", "1.0.0")
        r = resolve.add(project, c, [tool], resolve.INSTALL)
        self.counts(r, 1)
        self.to_both(r, tool)

    # the project's own package folders

    def test_install_depends_on_unlocked(self):
        project = self.project(files={"Packages/base/package.json": '{"name":"com.vrchat.base","version":"1.0.0"}'})
        c = Collection(pkg("com.vrchat.avatars", "1.0.0", {"com.vrchat.base": "1.0.0"}))
        avatars = c.get("com.vrchat.avatars", "1.0.0")
        r = resolve.add(project, c, [avatars], resolve.INSTALL)
        self.counts(r, 1)
        self.to_both(r, avatars)

    def test_install_conflict_with_unlocked(self):
        project = self.project(files={"Packages/base/package.json": '{"name":"com.vrchat.base","version":"1.0.0"}'})
        c = Collection(pkg("com.vrchat.avatars", "1.1.0", {"com.vrchat.base": "1.1.0"}))
        avatars = c.get("com.vrchat.avatars", "1.1.0")
        r = resolve.add(project, c, [avatars], resolve.INSTALL)
        self.counts(r, 1, conflicts=1)
        self.to_both(r, avatars)
        self.assertEqual(r.conflicts["com.vrchat.base"].packages, ["com.vrchat.avatars"])


class Remove(Case):
    def test_basic_remove(self):
        project = self.project({"com.anatawa12.gists": "1.0.0"}, {"com.anatawa12.gists": ("1.0.0", {})})
        r = resolve.remove(project, ["com.anatawa12.gists"])
        self.counts(r, 1)
        self.removed(r, "com.anatawa12.gists", resolve.REQUESTED)

    def test_transitive_unused_remove(self):
        r = resolve.remove(self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE), ["com.vrchat.avatars"])
        self.counts(r, 2)
        self.removed(r, "com.vrchat.avatars", resolve.REQUESTED)
        self.removed(r, "com.vrchat.base", resolve.UNUSED)

    def test_do_not_remove_transitively_when_untouched(self):
        project = self.project({"com.vrchat.avatars": "1.0.0"},
                               dict(AVATARS_ON_BASE, **{"com.anatawa12.untouched_library": ("1.0.0", {})}))
        r = resolve.remove(project, ["com.vrchat.avatars"])
        self.counts(r, 2)
        self.removed(r, "com.vrchat.base", resolve.UNUSED)

    def test_remove_referenced_legacy_package(self):
        project = self.project(
            {"com.anatawa12.user": "1.0.0", "com.anatawa12.legacy-package": "1.0.0"},
            {"com.anatawa12.user": ("1.0.0", {"com.anatawa12.legacy-package": "^1.0.0"}),
             "com.anatawa12.legacy-package": ("1.0.0", {}), "com.anatawa12.package": ("1.1.0", {})},
            files={"Packages/com.anatawa12.package/package.json": json.dumps(
                {"name": "com.anatawa12.package", "version": "1.1.0", "legacyPackages": ["com.anatawa12.legacy-package"]})})
        r = resolve.remove(project, ["com.anatawa12.legacy-package"])
        self.counts(r, 1)
        self.removed(r, "com.anatawa12.legacy-package", resolve.REQUESTED)

    def test_removing_what_another_needs_is_a_conflict(self):
        r = resolve.remove(self.project({"com.vrchat.avatars": "1.0.0"}, AVATARS_ON_BASE), ["com.vrchat.base"])
        self.assertEqual(r.conflicts["com.vrchat.base"].packages, ["com.vrchat.avatars"])

    def test_not_installed(self):
        with self.assertRaises(resolve.ResolveError):
            resolve.remove(self.project(), ["com.vrchat.avatars"])


UNLOCKED_PACKAGE = json.dumps({"name": "com.anatawa12.package", "version": "1.0.0",
                               "vpmDependencies": {"com.anatawa12.library": "^1.0.0"}})


class Repair(Case):
    def test_simple_resolve_fully_locked(self):
        project = self.project({"com.anatawa12.package": "1.0.0"},
                               {"com.anatawa12.package": ("1.0.0", {"com.anatawa12.library": "1.0.0"}),
                                "com.anatawa12.library": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.package", "1.0.0", {"com.anatawa12.library": "1.0.0"}),
                       pkg("com.anatawa12.library", "1.0.0"))
        self.assertTrue(resolve.needs_repair(project))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.install_only(r, c.get("com.anatawa12.package", "1.0.0"))
        self.install_only(r, c.get("com.anatawa12.library", "1.0.0"))

    def test_resolve_ranged(self):
        project = self.project({"com.anatawa12.package": "^1.0.0"})
        c = Collection(pkg("com.anatawa12.package", "1.0.0", {"com.anatawa12.library": "1.0.0"}),
                       pkg("com.anatawa12.library", "1.0.0"))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.to_both(r, c.get("com.anatawa12.package", "1.0.0"))
        self.to_locked_only(r, c.get("com.anatawa12.library", "1.0.0"))

    def test_resolve_dependencies_of_unlocked(self):
        project = self.project(files={"Packages/unlocked/package.json": UNLOCKED_PACKAGE})
        c = Collection(pkg("com.anatawa12.library", "1.0.0"))
        r = resolve.repair(project, c)
        self.counts(r, 1)
        self.to_locked_only(r, c.get("com.anatawa12.library", "1.0.0"))

    def test_resolve_unlocked_satisfies_all(self):
        project = self.project(files={"Packages/unlocked/package.json": UNLOCKED_PACKAGE,
                                      "Packages/unlocked2/package.json": '{"name":"com.anatawa12.library","version":"2.0.0"}'})
        self.assertFalse(resolve.needs_repair(project))
        self.counts(resolve.repair(project, Collection()), 0)

    def test_resolve_both_dependencies_of_unlocked_and_locked(self):
        project = self.project(locked={"com.anatawa12.library2": ("1.0.0", {})},
                               files={"Packages/unlocked/package.json": UNLOCKED_PACKAGE})
        c = Collection(pkg("com.anatawa12.library", "1.0.0"), pkg("com.anatawa12.library2", "1.0.0"))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.to_locked_only(r, c.get("com.anatawa12.library", "1.0.0"))
        self.install_only(r, c.get("com.anatawa12.library2", "1.0.0"))

    def test_resolve_both_dependencies_of_unlocked_and_dependencies(self):
        project = self.project({"com.anatawa12.library2": "^1.0.0"},
                               files={"Packages/unlocked/package.json": UNLOCKED_PACKAGE})
        c = Collection(pkg("com.anatawa12.library", "1.0.0"), pkg("com.anatawa12.library2", "1.0.0"))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.to_locked_only(r, c.get("com.anatawa12.library", "1.0.0"))
        self.to_both(r, c.get("com.anatawa12.library2", "1.0.0"))

    def test_dependencies_only_package_require_newer_version_than_locked_version(self):
        # vrc-get issue 2728
        project = self.project({"com.anatawa12.dependency": "1.1.0"}, {"com.anatawa12.locked": ("1.0.0", {})})
        c = Collection(pkg("com.anatawa12.locked", "1.0.0"), pkg("com.anatawa12.locked", "1.1.0"),
                       pkg("com.anatawa12.dependency", "1.1.0", {"com.anatawa12.locked": "^1.1.0"}))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.to_locked_only(r, c.get("com.anatawa12.locked", "1.1.0"))
        self.to_both(r, c.get("com.anatawa12.dependency", "1.1.0"))

    def test_dependencies_of_unlocked_package_require_newer_version_than_locked_version(self):
        project = self.project(locked={"com.anatawa12.locked": ("1.0.0", {})}, files={
            "Packages/unlocked/package.json": json.dumps({"name": "com.anatawa12.package", "version": "1.0.0",
                                                          "vpmDependencies": {"com.anatawa12.dependency": "^1.1.0"}})})
        c = Collection(pkg("com.anatawa12.locked", "1.0.0"), pkg("com.anatawa12.locked", "1.1.0"),
                       pkg("com.anatawa12.dependency", "1.1.0", {"com.anatawa12.locked": "^1.1.0"}))
        r = resolve.repair(project, c)
        self.counts(r, 2)
        self.to_locked_only(r, c.get("com.anatawa12.locked", "1.1.0"))
        self.to_locked_only(r, c.get("com.anatawa12.dependency", "1.1.0"))


class Apply(Case):
    def avatars_342(self):
        return self.project({"com.vrchat.avatars": "~3.5.x"},
                            {"com.vrchat.avatars": ("3.4.2", {"com.vrchat.base": "3.4.2"}), "com.vrchat.base": ("3.4.2", {})},
                            files={"Packages/com.vrchat.avatars/package.json": '{"name":"com.vrchat.avatars","version":"3.4.2"}',
                                   "Packages/com.vrchat.avatars/content.txt": "text"})

    def test_no_temp_folder_after_remove(self):
        project = self.avatars_342()
        resolve.apply(project, resolve.remove(project, ["com.vrchat.avatars"]), self.root / "vcc")
        self.assertFalse((project.folder / "Temp").exists())
        self.assertFalse((project.folder / "Packages" / "com.vrchat.avatars").exists())
        saved = json.loads((project.folder / "Packages" / "vpm-manifest.json").read_text())
        self.assertEqual(saved["locked"], {}, "base went too: nothing used it")
        self.assertEqual(saved["dependencies"], {})

    def test_error_in_install_does_not_break_project(self):
        project = self.avatars_342()
        c = Collection(pkg("com.vrchat.avatars", "3.10.0"))   # (its folder isn't there: installing it fails)
        changes = resolve.add(project, c, [c.get("com.vrchat.avatars", "3.10.0")], resolve.AUTO, True)
        with self.assertRaises(OSError):
            resolve.apply(project, changes, self.root / "vcc")
        self.assertEqual((project.folder / "Packages" / "com.vrchat.avatars" / "content.txt").read_text(), "text")
        saved = json.loads((project.folder / "Packages" / "vpm-manifest.json").read_text())
        self.assertEqual(saved["locked"]["com.vrchat.avatars"]["version"], "3.4.2")
        self.assertFalse((project.folder / "Temp").exists())

    def test_install_from_a_package_folder_and_legacy_cleanup(self):
        source = self.root / "packages" / "com.anatawa12.package"
        source.mkdir(parents=True)
        (source / "package.json").write_text('{"name":"com.anatawa12.package","version":"1.0.0"}')
        (source / "Runtime.cs").write_text("// code")
        project = self.project(dirs=["Assets/OldTool"], files={"Assets/OldTool.meta": "guid: 0", "Assets/Old.cs": "x"})
        p = pkg("com.anatawa12.package", "1.0.0", legacy_folders={"Assets/OldTool": None}, legacy_files={"Assets/Old.cs": None})
        info = Info(p, folder=source)

        class One:
            def find(self, name, selector):
                return info if name == p.name and selector.satisfies(p) else None
        changes = resolve.add(project, One(), [info], resolve.INSTALL)
        resolve.apply(project, changes, self.root / "vcc")
        self.assertEqual((project.folder / "Packages" / "com.anatawa12.package" / "Runtime.cs").read_text(), "// code")
        self.assertFalse((project.folder / "Assets" / "OldTool").exists())
        self.assertFalse((project.folder / "Assets" / "OldTool.meta").exists())
        self.assertFalse((project.folder / "Assets" / "Old.cs").exists())
        again = UnityProject.load(project.folder)
        self.assertEqual(str(again.locked["com.anatawa12.package"][0]), "1.0.0")
        self.assertEqual(str(again.dependencies["com.anatawa12.package"]), "1.0.0")
        self.assertIn("com.anatawa12.package", again.installed)


if __name__ == "__main__":
    unittest.main()
