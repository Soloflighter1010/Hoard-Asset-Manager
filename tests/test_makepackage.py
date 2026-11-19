"""A Unity package made from a Local item without Unity (hoard/makepackage.py, issue #382): read back by Hoard's own
importer, each file where it goes, those with their own .meta keeping their GUIDs."""
import shutil
import tarfile
import tempfile
from pathlib import Path

from tests.isolation import IsolatedTestCase

from hoard import makepackage
from hoard.vpm import unitypackage

KEPT = "0123456789abcdef0123456789abcdef"


class MakingOne(IsolatedTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        item = self.item = self.tmp / "My Hoodie"
        (item / "Textures").mkdir(parents=True)
        (item / "Textures" / "hoodie.png").write_bytes(b"\x89PNG picture")
        (item / "Textures" / "hoodie.png.meta").write_text(f"fileFormatVersion: 2\nguid: {KEPT}\nTextureImporter:\n  mipmaps: 1\n")
        (item / "Hoodie.fbx").write_bytes(b"model")
        (item / ".hidden").write_text("x")
        (item / "notes.txt~").write_text("x")
        (item / "Gone.prefab.meta").write_text(f"fileFormatVersion: 2\nguid: {'f' * 32}\n")
        self.files = ["Textures/hoodie.png", "Textures/hoodie.png.meta", "Hoodie.fbx", ".hidden", "notes.txt~", "Gone.prefab.meta"]

    def test_read_back_by_unitys_way_of_putting_it_in(self):
        out = self.tmp / "out" / "My Hoodie.unitypackage"
        done = makepackage.make(self.item, self.files, "My Hoodie", out)
        self.assertEqual((done["assets"], done["kept_ids"], done["new_ids"]), (2, 1, ["Hoodie.fbx"]))
        self.assertEqual(sorted(p for p, _ in done["left_out"]), [".hidden", "Gone.prefab.meta", "notes.txt~"])
        self.assertFalse(out.with_name(out.name + ".part").exists())
        project = self.tmp / "Project"
        (project / "Assets").mkdir(parents=True)
        placed = unitypackage.place_file(project, out)
        self.assertEqual(placed.placed, 4, "the item's folder, Textures, and the two files")
        self.assertEqual((project / "Assets/My Hoodie/Textures/hoodie.png").read_bytes(), b"\x89PNG picture")
        meta = (project / "Assets/My Hoodie/Textures/hoodie.png.meta").read_text()
        self.assertIn(f"guid: {KEPT}", meta, "its own GUID, so what refers to it still finds it")
        self.assertIn("TextureImporter", meta, "and its import settings")
        self.assertRegex((project / "Assets/My Hoodie/Hoodie.fbx.meta").read_text(), r"^fileFormatVersion: 2\nguid: [0-9a-f]{32}\n$")
        self.assertIn("folderAsset: yes", (project / "Assets/My Hoodie/Textures.meta").read_text())
        self.assertIn("folderAsset: yes", (project / "Assets/My Hoodie.meta").read_text())
        self.assertFalse((project / "Assets/My Hoodie/.hidden").exists())

    def test_two_copies_of_one_guid(self):
        (self.item / "Copy").mkdir()
        (self.item / "Copy" / "hoodie.png").write_bytes(b"same")
        shutil.copy(self.item / "Textures" / "hoodie.png.meta", self.item / "Copy" / "hoodie.png.meta")
        p = makepackage.plan(self.item, self.files + ["Copy/hoodie.png", "Copy/hoodie.png.meta"])
        guids = [g for _, g, _, _ in p["assets"] + p["folders"]]
        self.assertEqual(len(guids), len(set(guids)), "every asset its own GUID")
        self.assertIn(("Textures/hoodie.png.meta", "its GUID is another file's too, so this one gets a new GUID"), p["left_out"])

    def test_names_and_nothing_to_put_in(self):
        self.assertEqual(makepackage.folder_name('a/b:c*d?"e'), "a_b_c_d__e")
        self.assertEqual(makepackage.folder_name(" .. "), "Local asset")
        with self.assertRaisesRegex(ValueError, "nothing in it"):
            makepackage.make(self.item, [".hidden"], "X", self.tmp / "x.unitypackage")
        self.assertFalse((self.tmp / "x.unitypackage").exists())

    def test_only_its_own_files(self):
        """A path in the record that climbs out of the item's folder is never read into the package."""
        outside = self.tmp / "secret.txt"
        outside.write_text("not yours to pack")
        with self.assertRaises(Exception):
            makepackage.make(self.item, ["../secret.txt"], "X", self.tmp / "y.unitypackage")
        self.assertFalse((self.tmp / "y.unitypackage").exists())
        with tarfile.open(makepackage.make(self.item, self.files, "X", self.tmp / "z.unitypackage")["path"]) as tar:
            self.assertNotIn(b"not yours", b"".join(tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()))
        try:
            (self.item / "link.txt").symlink_to(outside)
        except OSError:
            self.skipTest("this system can't make links")
        done = makepackage.make(self.item, [*self.files, "link.txt"], "X", self.tmp / "l.unitypackage")
        self.assertIn(("link.txt", "it's a link to somewhere outside its folder"), done["left_out"])
        with tarfile.open(done["path"]) as tar:
            self.assertNotIn(b"not yours", b"".join(tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()))
