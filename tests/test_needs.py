"""What a download needs (hoard/needs.py): the GUIDs a package's text assets name, and what has them."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import downloader, needs, packages
from tests.test_packages import unitypackage

LILTOON = "00795bf598b44dc4e9bd363348e77085"      # a lilToon shader (hoard/known_tools.json)
POIYOMI_81 = "034460dc851505a42baca2ba6514f9f0"   # a Poiyomi Toon 8.1 shader
SDK = "00520eb52e49b5b4e8d9870d6ff1aced"          # a VRChat SDK component
BASE_FBX, BASE_PREFAB = "b" * 31 + "1", "b" * 31 + "2"
ELSEWHERE = "e" * 32                              # something no package here has


def material(shader: str) -> bytes:
    return (f"%YAML 1.1\n%TAG !u! tag:unity3d.com,2011:\n--- !u!21 &2100000\nMaterial:\n  m_Name: Hoodie\n"
            f"  m_Shader: {{fileID: 4800000, guid: {shader}, type: 3}}\n").encode()


def prefab(*guids: str) -> bytes:
    body = "".join(f"  - component: {{fileID: 0}}\n    m_Script: {{fileID: 11500000, guid: {g}, type: 3}}\n" for g in guids)
    return ("%YAML 1.1\n--- !u!1001 &1\nPrefabInstance:\n" + body).encode()


def avatar() -> bytes:
    return unitypackage({BASE_FBX: ("Assets/Kitsu/Rusk.fbx", b"Kaydara FBX Binary  \x00" + b"\x00" * 50),
                         BASE_PREFAB: ("Assets/Kitsu/Rusk.prefab", prefab(SDK, BASE_FBX))})


def outfit() -> bytes:
    return unitypackage({
        "a" * 32: ("Assets/Mochi/Hoodie.mat", material(LILTOON)),
        "c" * 32: ("Assets/Mochi/Hoodie_Poi.mat", material(POIYOMI_81)),
        "d" * 32: ("Assets/Mochi/Hoodie.prefab", prefab(SDK, BASE_PREFAB, ELSEWHERE, "a" * 32, "0" * 16 + "e" + "0" * 15)),
        "f" * 32: ("Assets/Mochi/hoodie.png", b"\x89PNG" + b"guid: " + b"9" * 32),   # not text: not looked through
    })


class Reading(unittest.TestCase):
    def test_a_package_names_what_its_text_assets_use(self):
        refs = set()
        assets = packages.read_unitypackage(io.BytesIO(outfit()), refs=refs)
        self.assertIn(LILTOON, refs)
        self.assertIn(BASE_PREFAB, refs)
        self.assertNotIn("9" * 32, refs, "a picture isn't looked through")
        self.assertEqual(len(assets), 4)

    def test_a_guid_across_a_chunk_boundary_is_found(self):
        refs = set()
        filler = b"x" * ((1 << 16) - 20)
        data = b"%YAML 1.1\n" + filler + f"m_Shader: {{guid: {LILTOON}}}\n".encode()
        packages.read_unitypackage(io.BytesIO(unitypackage({"a" * 32: ("Assets/a.mat", data)})), refs=refs)
        self.assertIn(LILTOON, refs)

    def test_read_file_leaves_out_its_own_and_unitys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Hoodie.unitypackage"
            p.write_bytes(outfit())
            e = needs.read_file(p)
        [pkg] = e["packages"]
        self.assertIsNone(pkg["member"])
        self.assertNotIn("a" * 32, pkg["refs"], "its own material isn't needed from elsewhere")
        self.assertFalse(any(g.startswith(needs.BUILT_IN) for g in pkg["refs"]), "nor Unity's own resources")
        self.assertEqual(set(pkg["refs"]), {LILTOON, POIYOMI_81, SDK, BASE_PREFAB, ELSEWHERE})

    def test_packages_in_a_zip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "Hoodie.zip"
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("Hoodie/Hoodie.unitypackage", outfit())
                zf.writestr("Hoodie/readme.txt", "hi")
            e = needs.read_file(p)
        self.assertEqual([x["member"] for x in e["packages"]], ["Hoodie/Hoodie.unitypackage"])
        self.assertIn(LILTOON, e["packages"][0]["refs"])


class WorkingOut(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(self.tmp.name) / "data")})
        self.env.start()
        root = Path(self.tmp.name) / "dl"
        (root / "Booth" / "Kitsu" / "Rusk").mkdir(parents=True)
        (root / "Booth" / "Mochi" / "Hoodie").mkdir(parents=True)
        (root / "Booth" / "Kitsu" / "Rusk" / "Rusk.unitypackage").write_bytes(avatar())
        with zipfile.ZipFile(root / "Booth" / "Mochi" / "Hoodie" / "Hoodie.zip", "w") as zf:
            zf.writestr("Hoodie.unitypackage", outfit())
        self.root = root
        self.assets = [
            {"id": 0, "name": "Rusk", "creator": "Kitsu", "store": "Booth", "tag_key": "booth:rusk", "catalog_folder": "Booth/Kitsu/Rusk",
             "abs_folder": str(root / "Booth" / "Kitsu" / "Rusk"), "files": [{"path": "Rusk.unitypackage", "size": 1}]},
            {"id": 1, "name": "Hoodie for Rusk", "creator": "Mochi", "store": "Booth", "tag_key": "booth:hoodie for rusk",
             "catalog_folder": "Booth/Mochi/Hoodie", "abs_folder": str(root / "Booth" / "Mochi" / "Hoodie"),
             "files": [{"path": "Hoodie.zip", "size": 1}, {"path": "readme.txt", "size": 1}]},
        ]

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def read_all(self) -> needs.NeedsIndex:
        index = needs.NeedsIndex()
        reader = needs.NeedsReader(index, lambda: self.assets, lambda: False)
        self.assertEqual(reader.run_once(), 2)
        return index

    def test_other_products_arent_named_for_now(self):
        got = needs.work_out(self.assets, self.read_all())[1]
        self.assertEqual([t["name"] for t in got["tools"]], ["lilToon", "Poiyomi Toon", "VRChat SDK"])
        self.assertEqual((got["products"], got["unknown"]), ([], 2), "the avatar's prefab is only counted")

    @mock.patch.object(needs, "MATCH_PRODUCTS", True)   # (off for now: these keep its working tested)
    def test_an_outfit_needs_its_shaders_the_sdk_and_its_avatar(self):
        got = needs.work_out(self.assets, self.read_all())[1]
        self.assertTrue(got["read"])
        self.assertEqual([(t["name"], t["versions"], t["common"]) for t in got["tools"]],
                         [("lilToon", [], False), ("Poiyomi Toon", ["8.1"], False), ("VRChat SDK", [], True)])
        self.assertEqual([(o["name"], o["guids"]) for o in got["products"]], [("Rusk", [BASE_PREFAB])])
        self.assertEqual(got["unknown"], 1, "the one GUID nothing here has is counted")

    def test_the_avatar_needs_only_the_sdk(self):
        got = needs.work_out(self.assets, self.read_all())[0]
        self.assertEqual([t["name"] for t in got["tools"]], ["VRChat SDK"])
        self.assertEqual((got["products"], got["unknown"]), ([], 0), "its own model isn't needed from elsewhere")

    def test_read_once_and_again_when_changed(self):
        index = self.read_all()
        reader = needs.NeedsReader(needs.NeedsIndex(), lambda: self.assets, lambda: False)
        self.assertEqual(reader.run_once(), 0, "kept from last time (sealed), so nothing's read again")
        pkg = self.root / "Booth" / "Kitsu" / "Rusk" / "Rusk.unitypackage"
        pkg.write_bytes(unitypackage({BASE_FBX: ("Assets/Kitsu/Rusk.fbx", b"x")}))
        os.utime(pkg, ns=(5, 5))
        self.assertEqual(reader.run_once(), 1)
        self.assertEqual(needs.work_out(self.assets, reader.index)[1]["unknown"], 2, "the avatar's prefab is gone from it")
        self.assertTrue(index.path.is_file())

    def test_not_read_yet(self):
        got = needs.work_out(self.assets, needs.NeedsIndex())
        self.assertEqual({i: g["read"] for i, g in got.items()}, {0: False, 1: False})

    def test_an_edited_index_is_read_again(self):
        self.read_all()
        raw = json.loads(needs.index_file().read_text("utf-8"))
        next(iter(raw["files"].values()))["packages"][0]["refs"] = []
        needs.index_file().write_text(json.dumps(raw), "utf-8")
        self.assertEqual(needs.NeedsIndex().files, {}, "not as Hoard sealed it: started again")

    def test_waits_while_a_job_runs(self):
        busy = iter([True, True, False] + [False] * 10)
        with mock.patch.object(needs.time, "sleep") as slept:
            needs.NeedsReader(needs.NeedsIndex(), lambda: self.assets, lambda: next(busy)).run_once()
        self.assertEqual(slept.call_count, 2)

    @mock.patch.object(needs, "MATCH_PRODUCTS", True)   # (off for now: these keep its working tested)
    def test_in_the_catalog(self):
        self.read_all()
        catalog = [{"store": "Booth", "name": a["name"], "creator": a["creator"], "folder": a["catalog_folder"],
                    "files": [f["path"] for f in a["files"]], "tags": [], "suggested_tags": [], "url": None, "variants": None}
                   for a in self.assets]
        needs.add_to_catalog(self.root, catalog)
        hoodie = catalog[1]["needs"]
        self.assertEqual([(n["kind"], n["name"]) for n in hoodie],
                         [("tool", "lilToon"), ("tool", "Poiyomi Toon"), ("tool", "VRChat SDK"), ("product", "Rusk")])
        self.assertEqual(hoodie[3]["folder"], "Booth/Kitsu/Rusk")
        self.assertEqual(downloader.validate_catalog_entry(catalog[1]), [])
        for bad in ({**hoodie[0], "url": "https://evil.example/"}, {**hoodie[0], "guids": ["nope"]},
                    {**hoodie[3], "folder": "../x"}, {**hoodie[0], "versions": ["8.1; rm"]}, {**hoodie[0], "kind": "script"}):
            with self.subTest(bad=bad):
                self.assertNotEqual(downloader.validate_catalog_entry({**catalog[1], "needs": [bad]}), [])


@mock.patch.object(needs, "MATCH_PRODUCTS", True)   # (off for now: these keep its working tested)
class WeakMatches(unittest.TestCase):
    """What other products a product needs leaves out what's noise: a creator's shared files that many products carry,
    and a few files from another product by the same creator (most often their own files used again)."""

    class Index:   # what's been read of each package: {path: (own, refs)}
        def __init__(self, read):
            self.read = read

        def get(self, path):
            own, refs = self.read[os.path.basename(path)]
            return {"packages": [{"own": sorted(own), "refs": sorted(refs)}]}

        def fresh(self, path):
            return True

    @staticmethod
    def g(n):
        return f"{n:032x}"

    def products(self, *rows):
        """rows: (name, creator, own GUIDs, refs)"""
        assets, read = [], {}
        for i, (name, creator, own, refs) in enumerate(rows):
            assets.append({"id": i, "name": name, "creator": creator, "store": "Booth", "tag_key": f"booth:{name.lower()}",
                           "catalog_folder": f"Booth/{creator}/{name}", "abs_folder": f"/x/{i}",
                           "files": [{"path": f"p{i}.unitypackage", "size": 1}]})
            read[f"p{i}.unitypackage"] = ({self.g(n) for n in own}, {self.g(n) for n in refs})
        return assets, self.Index(read)

    def named(self, assets, index, pid=0):
        got = needs.work_out(assets, index)[pid]
        return [o["name"] for o in got["products"]], got["unknown"]

    def test_files_many_products_carry_name_none_of_them(self):
        shared = [1, 2, 3]
        assets, index = self.products(("Nardo Necklace", "Loco", [10], shared),
                                      *[(f"Free {n}", "Loco", [20 + n] + shared, []) for n in range(5)])
        self.assertEqual(self.named(assets, index), ([], 3), "five products carrying the same files: noise, counted")

    def test_the_one_that_has_more_is_still_named(self):
        shared = [1, 2, 3]
        assets, index = self.products(("Nardo Necklace", "Loco", [10], shared + [4, 5]),
                                      *[(f"Free {n}", "Loco", [20 + n] + shared, []) for n in range(3)],
                                      ("Nardo", "Loco", shared + [4, 5, 6, 7, 8], []))
        self.assertEqual(self.named(assets, index), (["Nardo"], 0), "the base avatar has a file only it carries")

    def test_a_few_files_from_the_same_creator_arent_a_need(self):
        assets, index = self.products(("Stargazer", "Antistar", [10], [1, 2, 9]), ("Red Line", "Antistar", [1, 2], []))
        self.assertEqual(self.named(assets, index), ([], 3))

    def test_the_same_creators_base_avatar_is(self):
        base = list(range(1, 9))
        assets, index = self.products(("Hoodie for Nardo", "Loco", [10], base), ("Nardo", "Loco", base, []))
        self.assertEqual(self.named(assets, index), (["Nardo"], 0), "many of its files: a real need")

    def test_another_creators_avatar_is_named_for_one_file(self):
        assets, index = self.products(("Hoodie for Rusk", "Mochi", [10], [1]), ("Rusk", "Kitsu", [1, 2], []))
        self.assertEqual(self.named(assets, index), (["Rusk"], 0))

    def test_copies_on_two_stores_are_one_product(self):
        assets, index = self.products(("Hoodie for Rusk", "Mochi", [10], [1]), ("Rusk", "Kitsu", [1], []),
                                      ("RUSK", "kitsu", [1], []), ("Rusk!", "Kitsu", [1], []))
        names, unknown = self.named(assets, index)
        self.assertTrue(names and unknown == 0, "three copies of Rusk aren't three products carrying it")

    def test_no_creator_isnt_the_same_creator(self):
        assets, index = self.products(("Hoodie", "", [10], [1]), ("Rusk", "", [1], []))
        self.assertEqual(self.named(assets, index), (["Rusk"], 0))


class KnownTools(unittest.TestCase):
    def test_the_table(self):
        k = needs.known()
        self.assertEqual(set(k["tools"]), {"liltoon", "poiyomi", "modular-avatar", "vrcfury", "ndmf", "avatar-optimizer", "vrchat-sdk"})
        self.assertGreater(len(k["guids"]), 1000)
        for g, v in k["guids"].items():
            self.assertRegex(g, r"^[0-9a-f]{32}$")
            self.assertIn(v[0], k["tools"])
        for t in k["tools"].values():
            self.assertTrue(t["url"].startswith("https://"), t)

    def test_hoard_for_unity_links_to_the_same_websites(self):
        import re
        from urllib.parse import urlparse
        cs = (Path(__file__).resolve().parent.parent / "Packages" / "soloflighter.hoard" / "Editor" / "Core" / "Catalog.cs").read_text("utf-8")
        sites = re.search(r"ToolSites = \{([^}]*)\}", cs).group(1)
        self.assertEqual(set(re.findall(r'"([^"]+)"', sites)), {urlparse(t["url"]).hostname for t in needs.known()["tools"].values()})


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Page(unittest.TestCase):
    """Downloads: a product's What it needs, and a hidden product left out of it while the hidden library is locked."""

    @classmethod
    def setUpClass(cls):
        import threading
        from playwright.sync_api import sync_playwright
        from hoard import config, server
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(cls.tmp.name) / "data")})
        cls.env.start()
        root = Path(cls.tmp.name) / "downloads"
        for creator, name, file, data in (("Kitsu", "Rusk", "Rusk.unitypackage", avatar()),
                                          ("Mochi", "Hoodie for Rusk", "Hoodie.unitypackage", outfit())):
            folder = root / "Booth" / creator / name
            folder.mkdir(parents=True)
            (folder / file).write_bytes(data)
            man = downloader.Manifest(root / "Booth")
            rec = man.record(name, creator, name)
            rec.update(name=name, creator=creator)
            rec["files"]["f"] = {"path": file, "size": len(data)}
            man.save()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
        cls.srv.needs_reader.on_read = None
        assert cls.srv.needs_reader.run_once() == 2
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.env.stop()
        cls.tmp.cleanup()

    def test_what_the_hoodie_needs(self):
        page = self.browser.new_page()
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot", has_text="Hoodie").click()
        rows = page.locator("#detail .needs li")
        rows.first.wait_for()
        self.assertEqual([r.split("\n")[0] for r in rows.all_inner_texts()],
                         ["lilToon", "Poiyomi Toon 8.1", "VRChat SDK (every VRChat project has it)"],
                         "other products aren't named, for now")
        self.assertEqual(rows.nth(0).locator("a").get_attribute("href"), "https://lilxyzw.github.io/lilToon/")
        self.assertIn("It also uses files from other products", page.locator("#detail").inner_text())
        self.assertEqual(page.locator("#detail [data-act='goto']").count(), 0)

    @mock.patch.object(needs, "MATCH_PRODUCTS", True)   # (off for now: these keep its working tested)
    def test_a_hidden_product_isnt_named(self):
        from hoard.marks import MarkStore
        from hoard.tags import tag_key
        view = MarkStore.view
        with mock.patch.object(MarkStore, "view", lambda self: {**view(self), "hidden": {tag_key("Booth", "Rusk")}}):
            status, data = self.call("/api/assets")
        hoodie = next(a for a in data["assets"] if a["name"] == "Hoodie for Rusk")
        self.assertEqual(hoodie["needs"]["products"], [])
        self.assertFalse(any(a["name"] == "Rusk" for a in data["assets"]))

    def call(self, path):
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{path}", headers={"X-Hoard-Key": self.srv.key})
        with urllib.request.urlopen(req) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                import gzip
                body = gzip.decompress(body)
            return r.status, json.loads(body)


if __name__ == "__main__":
    unittest.main()
