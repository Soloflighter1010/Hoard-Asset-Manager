"""Inside a download (hoard/packages.py): reading a .unitypackage, and the .unitypackage files in a .zip."""
import gzip
import io
import os
import tarfile
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest import mock

from hoard import packages

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as _p:
        _p.chromium.launch().close()
    BROWSER = True
except Exception:  # no Playwright browser here
    BROWSER = False

PNG = packages.PNG + b"\x00\x00\x00\rIHDR" + b"\x00" * 40


def _png_1x1() -> bytes:
    import struct
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (packages.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" * 5)) + chunk(b"IEND", b""))


PNG_1x1 = _png_1x1()


def unitypackage(assets: dict, previews: dict | None = None, long_names: bool = False) -> bytes:
    """A .unitypackage as Unity makes one: {guid: (project path, file bytes or None for a folder)}."""
    raw = io.BytesIO()
    fmt = tarfile.GNU_FORMAT if long_names else tarfile.USTAR_FORMAT
    with tarfile.open(fileobj=raw, mode="w", format=fmt) as tar:
        def add(name: str, data: bytes):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for guid, (path, data) in assets.items():
            add(f"{guid}/pathname", path.encode())
            add(f"{guid}/asset.meta", b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n")
            if data is not None:
                add(f"{guid}/asset", data)
            if previews and guid in previews:
                add(f"{guid}/preview.png", previews[guid])
    return gzip.compress(raw.getvalue())


G1, G2, G3 = "a" * 32, "b" * 32, "c" * 32
SAMPLE = {G1: ("Assets/Creator", None), G2: ("Assets/Creator/Hoodie.prefab", b"%YAML 1.1\n" + b"x" * 100),
          G3: ("Assets/Creator/Textures/hoodie.png", b"\x89PNG" + b"y" * 300)}


class UnityPackages(unittest.TestCase):
    def test_reads_paths_sizes_and_previews(self):
        got = {}
        assets = packages.read_unitypackage(io.BytesIO(unitypackage(SAMPLE, {G2: PNG, G3: b"not a png"})),
                                            lambda g, d: got.__setitem__(g, d))
        self.assertEqual(assets[G1], {"path": "Assets/Creator", "size": None, "preview": False})
        self.assertEqual(assets[G2], {"path": "Assets/Creator/Hoodie.prefab", "size": 110, "preview": True})
        self.assertEqual(assets[G3]["size"], 304)
        self.assertFalse(assets[G3]["preview"])        # a "preview" that isn't a picture isn't one
        self.assertEqual(got, {G2: PNG})

    def test_long_names(self):
        deep = "Assets/" + "/".join(["folder"] * 30) + "/thing.mat"
        assets = packages.read_unitypackage(io.BytesIO(unitypackage({G1: (deep, b"m")}, long_names=True)))
        self.assertEqual(assets[G1]["path"], deep)

    def test_not_a_package(self):
        for data in (b"", b"hello", gzip.compress(b"x" * 700), unitypackage(SAMPLE)[:200]):
            with self.subTest(data=data[:10]), self.assertRaises(packages.NotAPackage):
                packages.read_unitypackage(io.BytesIO(data))

    def test_a_long_name_claiming_too_much_is_refused_before_reading_it(self):
        header = bytearray(512)
        header[0:13] = b"././@LongLink"
        header[124:136] = b"%011o\x00" % (1 << 30)
        header[156] = ord("L")
        header[148:156] = b"        "
        with self.assertRaises(packages.NotAPackage):
            packages.read_unitypackage(io.BytesIO(gzip.compress(bytes(header))))

    def test_stops_at_the_size_no_real_package_reaches(self):
        with mock.patch.object(packages, "MAX_UNPACKED", 2000), self.assertRaises(packages.NotAPackage):
            packages.read_unitypackage(io.BytesIO(unitypackage({G1: ("Assets/big.bin", b"z" * 5000)})))


class Zips(unittest.TestCase):
    def make_zip(self, members: dict, utf8: bool = True) -> Path:
        path = Path(self.tmp.name) / "download.zip"
        swaps = []
        with zipfile.ZipFile(path, "w") as zf:
            for n, (name, data) in enumerate(members.items()):
                if utf8:
                    zf.writestr(name, data)
                else:   # as a Japanese computer makes one: Shift-JIS names, and no flag saying what they are
                    raw = name.encode("cp932")   # (Python writes any name it can't put in ASCII as UTF-8, flagged)
                    stand_in = (f"{n:03d}" * len(raw))[:len(raw)].encode()
                    zf.writestr(stand_in.decode(), data)
                    swaps.append((stand_in, raw))
        data = path.read_bytes()
        for stand_in, raw in swaps:
            data = data.replace(stand_in, raw)
        path.write_bytes(data)
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_files_and_reads_the_packages_in_it(self):
        path = self.make_zip({"Hoodie/Hoodie_v1.2.unitypackage": unitypackage(SAMPLE, {G2: PNG}),
                              "Hoodie/README.txt": b"hi", "Hoodie/broken.unitypackage": b"nope"})
        seen = []
        z = packages.read_zip(path, lambda n, g, d: seen.append((n, g)))
        self.assertEqual([f["name"] for f in z["files"]],
                         ["Hoodie/broken.unitypackage", "Hoodie/Hoodie_v1.2.unitypackage", "Hoodie/README.txt"])
        good = next(p for p in z["packages"] if p["name"].endswith("v1.2.unitypackage"))
        self.assertEqual([i["path"] for i in good["items"]],
                         ["Assets/Creator", "Assets/Creator/Hoodie.prefab", "Assets/Creator/Textures/hoodie.png"])
        bad = next(p for p in z["packages"] if p["name"].endswith("broken.unitypackage"))
        self.assertEqual(bad["error"], "It isn't a Unity package, or it's damaged.")
        self.assertEqual(seen, [(z["packages"].index(good), G2)])

    def test_japanese_names(self):
        path = self.make_zip({"衣装/マヌカ対応.unitypackage": unitypackage(SAMPLE), "衣装/利用規約.txt": b"terms"}, utf8=False)
        names = [f["name"] for f in packages.read_zip(path)["files"]]
        self.assertEqual(names, ["衣装/マヌカ対応.unitypackage", "衣装/利用規約.txt"])

    def test_not_a_zip(self):
        path = Path(self.tmp.name) / "fake.zip"
        path.write_bytes(b"PK\x03\x04 not really")
        with self.assertRaises(packages.NotAPackage):
            packages.read_zip(path)


class LookInside(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(self.tmp.name) / "data")})
        self.env.start()
        self.file = Path(self.tmp.name) / "Hoodie.unitypackage"
        self.file.write_bytes(unitypackage(SAMPLE, {G2: PNG}))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_read_once_then_from_the_cache_with_its_previews(self):
        first = packages.look_inside(self.file)
        self.assertEqual(first["kind"], "unitypackage")
        self.assertEqual(len(first["items"]), 3)
        self.assertEqual(packages.preview(first["id"], f"0-{G2}.png"), PNG)
        with mock.patch.object(packages, "read_unitypackage", side_effect=AssertionError("read again")):
            self.assertEqual(packages.look_inside(self.file)["items"], first["items"])

    def test_a_changed_file_is_read_again(self):
        first = packages.look_inside(self.file)
        self.file.write_bytes(unitypackage({G1: ("Assets/Other.mat", b"m")}))
        os.utime(self.file, ns=(1, 1))
        again = packages.look_inside(self.file)
        self.assertNotEqual(again["id"], first["id"])
        self.assertEqual([i["path"] for i in again["items"]], ["Assets/Other.mat"])

    def test_a_damaged_package_says_so(self):
        self.file.write_bytes(b"\x1f\x8b damaged")
        got = packages.look_inside(self.file)
        self.assertEqual(got["error"], "It isn't a Unity package, or it's damaged.")
        self.assertNotIn("items", got)

    def test_previews_only_by_the_names_given(self):
        cid = packages.look_inside(self.file)["id"]
        for name in ("../inside.json", "inside.json", f"0-{G2}.PNG", f"0-{G2}.png/..", f"100-{G2}.png"):
            self.assertIsNone(packages.preview(cid, name), name)
        self.assertIsNone(packages.preview("../" + cid, f"0-{G2}.png"))

    def test_keeps_only_the_most_recently_looked_at(self):
        with mock.patch.object(packages, "KEEP", 2):
            ids = []
            for n in range(3):
                f = Path(self.tmp.name) / f"p{n}.unitypackage"
                f.write_bytes(unitypackage({G1: (f"Assets/{n}.mat", b"m")}))
                os.utime(f, ns=(n + 1, n + 1))
                ids.append(packages.look_inside(f)["id"])
                time_ns = 10 ** 9 * (n + 1)
                os.utime(packages.cache_dir() / ids[-1] / "inside.json", ns=(time_ns, time_ns))
            packages._prune(2)
        left = {p.name for p in packages.cache_dir().iterdir()}
        self.assertEqual(left, set(ids[1:]))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class LookInsidePage(unittest.TestCase):
    """Downloads: Look inside on a product's .unitypackage, and on a .zip with one in it."""

    @classmethod
    def setUpClass(cls):
        import threading
        from hoard import config, downloader, server
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(Path(cls.tmp.name) / "data")})
        cls.env.start()
        root = Path(cls.tmp.name) / "downloads"
        folder = root / "Booth" / "Kitsu Studio" / "Hoodie"
        folder.mkdir(parents=True)
        (folder / "Hoodie.unitypackage").write_bytes(unitypackage(SAMPLE, {G2: PNG_1x1}))
        with zipfile.ZipFile(folder / "Hoodie_zip.zip", "w") as zf:
            zf.writestr("Hoodie/Hoodie_v2.unitypackage", unitypackage({G1: ("Assets/Kitsu/Hoodie v2.prefab", b"p" * 50)}))
            zf.writestr("Hoodie/利用規約.txt", "terms")
        (folder / "readme.txt").write_text("hi")
        man = downloader.Manifest(root / "Booth")
        rec = man.record("111", "Kitsu Studio", "Hoodie")
        rec.update(name="Hoodie", creator="Kitsu Studio")
        for n, f in enumerate(("Hoodie.unitypackage", "Hoodie_zip.zip", "readme.txt")):
            rec["files"][f"f{n}"] = {"path": f, "size": (folder / f).stat().st_size}
        man.save()
        cls.srv = server.AppServer(("127.0.0.1", 0), {**config.load_config(), "root": str(root), "setup_done": True}, lan=False)
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

    def open_hoodie(self):
        page = self.browser.new_page()
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        page.click("nav.apptabs a[href='/downloads']")
        page.click("#grid .slot")
        return page

    def test_a_unitypackage(self):
        page = self.open_hoodie()
        rows = page.locator("#detail .files li")
        self.assertEqual(rows.filter(has_text="readme.txt").locator("[data-act='inside']").count(), 0)
        rows.filter(has_text="Hoodie.unitypackage").locator("[data-act='inside']").click()
        win = page.locator("#insideWin")
        win.locator(".sum", has_text="2 files, ").wait_for()
        win.locator("summary", has_text="Assets").click()
        win.locator("summary", has_text="Creator").click()
        win.get_by_text("Hoodie.prefab").wait_for()
        page.wait_for_function("() => [...document.querySelectorAll('#insideWin img.pv')].some(i => i.complete && i.naturalWidth === 1)")
        page.fill("#insideQ", "textures png")
        win.get_by_text("1 file matches.").wait_for()
        self.assertIn("Assets/Creator/Textures/hoodie.png", win.locator(".found").inner_text())
        page.keyboard.press("Escape")
        self.assertTrue(win.is_hidden())

    def test_a_zip_with_a_package_in_it(self):
        page = self.open_hoodie()
        page.locator("#detail .files li", has_text="Hoodie_zip.zip").locator("[data-act='inside']").click()
        win = page.locator("#insideWin")
        win.get_by_text("This zip holds 2 files").wait_for()
        win.locator("summary", has_text="Assets").click()   # its one package is open already
        win.locator("summary", has_text="Kitsu").click()
        win.get_by_text("Hoodie v2.prefab").wait_for()
        win.locator("summary", has_text="Every file in the zip").click()
        win.get_by_text("Hoodie/利用規約.txt").wait_for()

    def test_only_files_in_the_downloads(self):
        import json, urllib.request
        for path in ("../../etc/passwd.zip", "Booth/Kitsu Studio/Hoodie/readme.txt", "Booth/Kitsu Studio/Hoodie/gone.zip"):
            req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}/api/look-inside", method="POST",
                                         data=json.dumps({"path": path}).encode(),
                                         headers={"Content-Type": "application/json", "X-Hoard-Key": self.srv.key})
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(req)
            self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
