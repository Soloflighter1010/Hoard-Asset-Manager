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

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

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


def unitypackage(assets: dict, previews: dict | None = None, long_names: bool = False, asset_first: bool = False) -> bytes:
    """A .unitypackage as Unity makes one: {guid: (project path, file bytes or None for a folder)}; each asset's
    entries as Unity writes them (asset, asset.meta, pathname) with asset_first, else its .meta first."""
    raw = io.BytesIO()
    fmt = tarfile.GNU_FORMAT if long_names else tarfile.USTAR_FORMAT
    with tarfile.open(fileobj=raw, mode="w", format=fmt) as tar:
        def add(name: str, data: bytes):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for guid, (path, data) in assets.items():
            meta = b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n"
            if asset_first:
                if data is not None:
                    add(f"{guid}/asset", data)
                add(f"{guid}/asset.meta", meta)
                add(f"{guid}/pathname", path.encode())
                continue
            add(f"{guid}/pathname", path.encode())
            add(f"{guid}/asset.meta", meta)
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

    def test_previews_kept_up_to_a_limit(self):
        """Previews have a size limit each, but none in all: a 1 MB package of compressed blank "previews" left a
        GB of them in the cache. Past the limit the rest have none (and none is served)."""
        guids = [f"{n:032x}" for n in range(4)]
        self.file.write_bytes(unitypackage({g: (f"Assets/{n}.mat", b"m") for n, g in enumerate(guids)},
                                           {g: PNG for g in guids}))
        with mock.patch.object(packages, "MAX_PREVIEW_BYTES", len(PNG) * 2 + 1):
            got = packages.look_inside(self.file)
        shown = [i["guid"] for i in got["items"] if i["preview"]]
        self.assertEqual(len(shown), 2)
        for g in guids:
            self.assertEqual(packages.preview(got["id"], f"0-{g}.png") is not None, g in shown, g)

    def test_the_cache_kept_to_a_size(self):
        ids = []
        for n in range(3):
            f = Path(self.tmp.name) / f"p{n}.unitypackage"
            f.write_bytes(unitypackage({G1: (f"Assets/{n}.mat", b"m")}, {G1: PNG}))
            ids.append(packages.look_inside(f)["id"])
            time_ns = 10 ** 9 * (n + 1)
            os.utime(packages.cache_dir() / ids[-1] / "inside.json", ns=(time_ns, time_ns))
        packages._prune(40, 1)
        self.assertEqual({p.name for p in packages.cache_dir().iterdir()}, {ids[-1]}, "the newest always stays")


class Extract(unittest.TestCase):
    """Look inside's Extract: the chosen files, or all of them, taken out of a package or a zip into a folder of
    their own, where their paths say, and never anywhere else, whatever a package's paths claim."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(self.home / "data")})   # (Look inside's cache)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def package(self, assets: dict, **how) -> Path:
        path = self.home / "Hoodie.unitypackage"
        path.write_bytes(unitypackage(assets, **how))
        return path

    def out(self, name="out") -> Path:
        dest = self.home / name
        dest.mkdir()
        return dest

    def files(self, dest: Path) -> dict:
        return {p.relative_to(dest).as_posix(): p.read_bytes() for p in sorted(dest.rglob("*")) if p.is_file()}

    def test_chosen_files_and_folders(self):
        path = self.package(SAMPLE)
        dest = self.out()
        done = packages.extract(path, dest, ["p:0:Assets/Creator/Hoodie.prefab"])
        self.assertEqual(self.files(dest), {"Assets/Creator/Hoodie.prefab": SAMPLE[G2][1]})
        self.assertEqual((done["files"], done["bytes"]), (1, len(SAMPLE[G2][1])))
        dest = self.out("out2")
        packages.extract(path, dest, ["d:0:Assets/Creator/Textures"], metas=True)
        self.assertEqual(self.files(dest), {"Assets/Creator/Textures/hoodie.png": SAMPLE[G3][1],
                                            "Assets/Creator/Textures/hoodie.png.meta": b"fileFormatVersion: 2\nguid: " + G3.encode() + b"\n"})
        dest = self.out("out3")
        packages.extract(path, dest, ["all"])
        self.assertEqual(set(self.files(dest)), {"Assets/Creator/Hoodie.prefab", "Assets/Creator/Textures/hoodie.png"}, "no .meta unless asked")
        with self.assertRaises(packages.CantExtract):
            packages.extract(path, self.out("none"), ["p:0:Assets/Not/There.png"])

    def test_a_path_never_leads_out(self):
        """A package is a file anyone could make: "../", an absolute path, a drive, a name Windows can't have, the
        same path twice: each lands inside the folder, under a safe name, and nothing is overwritten."""
        evil = {"1" * 32: ("../../escaped.txt", b"climb"), "2" * 32: ("/etc/cron.d/evil", b"absolute"),
                "3" * 32: ("C:\\Windows\\evil.dll", b"drive"), "4" * 32: ("Assets/CON.txt", b"reserved"),
                "5" * 32: ("Assets/same.txt", b"one"), "6" * 32: ("Assets/same.txt", b"two")}
        path = self.package(evil)
        dest = self.out()
        packages.extract(path, dest, ["all"])
        got = self.files(dest)
        self.assertFalse((self.home / "escaped.txt").exists())
        self.assertNotIn("escaped", " ".join(got), "a path that climbs out isn't taken out at all")
        self.assertEqual(got["etc/cron.d/evil"], b"absolute")
        self.assertEqual(got["C_/Windows/evil.dll"], b"drive")
        self.assertEqual(got["Assets/_CON.txt"], b"reserved")
        self.assertEqual(sorted(v for k, v in got.items() if k.startswith("Assets/same")), [b"one", b"two"])
        self.assertTrue(all((dest / k).resolve().is_relative_to(dest.resolve()) for k in got))

    def test_never_through_a_link(self):
        outside = self.home / "outside"
        outside.mkdir()
        dest = self.out()
        (dest / "Assets").symlink_to(outside, target_is_directory=True)   # (planted where it would write)
        with self.assertRaises(packages.CantExtract):
            packages.extract(self.package(SAMPLE), dest, ["all"])
        self.assertEqual(list(outside.iterdir()), [])

    def test_only_with_room_for_it(self):
        with mock.patch.object(packages.shutil, "disk_usage", lambda p: mock.Mock(free=packages.ROOM_TO_SPARE + 10)):
            with self.assertRaises(packages.CantExtract) as e:
                packages.extract(self.package(SAMPLE), self.out(), ["all"])
        self.assertIn("room", str(e.exception))

    def test_a_zip_and_a_package_in_it(self):
        path = self.home / "Hoodie.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("Hoodie/Hoodie_v2.unitypackage", unitypackage(SAMPLE))
            zf.writestr("Hoodie/利用規約.txt", "terms")
            zf.writestr("../evil.txt", "climb")
        dest = self.out()
        done = packages.extract(path, dest, ["z:Hoodie/利用規約.txt", "p:0:Assets/Creator/Hoodie.prefab"])
        self.assertEqual(self.files(dest), {"Hoodie/利用規約.txt": "terms".encode(),
                                            "Hoodie/Hoodie_v2/Assets/Creator/Hoodie.prefab": SAMPLE[G2][1]},
                         "a zip's file where its name says; a package's assets in a folder named after it, where it is")
        self.assertEqual(done["skipped"], [])
        dest = self.out("all")
        done = packages.extract(path, dest, ["all"])
        self.assertEqual(set(self.files(dest)), {"Hoodie/Hoodie_v2.unitypackage", "Hoodie/利用規約.txt"}, "every file, as it is")
        self.assertEqual(done["skipped"], [("../evil.txt", "its name leads outside the folder")])
        self.assertFalse((self.home / "evil.txt").exists())

    def meta(self, guid: str) -> bytes:
        return b"fileFormatVersion: 2\nguid: " + guid.encode() + b"\n"

    def test_a_meta_always_beside_its_own_file(self):
        """With Unity's .meta files: each beside the file it's for, under the same name, even when that name was
        taken and the file renamed, in either order a package lists them; and nothing is ever written over, even a
        file named like another's .meta (issue #172)."""
        clash = {"1" * 32: ("Assets/same.txt", b"one"), "2" * 32: ("Assets/same.txt", b"two"),
                 "3" * 32: ("Assets/a.txt.meta", b"a file, not a .meta"), "4" * 32: ("Assets/a.txt", b"a")}
        for asset_first in (True, False):
            with self.subTest(asset_first=asset_first):
                dest = self.out(f"out{asset_first}")
                done = packages.extract(self.package(clash, asset_first=asset_first), dest, ["all"], metas=True)
                got = self.files(dest)
                self.assertEqual(done["files"], len(got), "every file counted was written, once")
                self.assertEqual(len(got), 8)
                for name, data in got.items():
                    if data.startswith(b"fileFormatVersion"):   # a .meta: beside the file it's for, by name
                        mine = next(g for g in clash if data == self.meta(g))
                        self.assertEqual(got[name[:-len(".meta")]], clash[mine][1], name)
                self.assertIn(b"a file, not a .meta", got.values(), "never written over")

    def test_a_folders_meta_too(self):
        """A folder's .meta holds its GUID, which Unity keeps: with .meta files, a chosen folder's comes out beside
        it (issue #173)."""
        dest = self.out()
        packages.extract(self.package(SAMPLE, asset_first=True), dest, ["d:0:Assets/Creator"], metas=True)
        self.assertEqual(self.files(dest)["Assets/Creator.meta"], self.meta(G1))
        self.assertEqual(self.files(dest)["Assets/Creator/Hoodie.prefab.meta"], self.meta(G2))

    def test_what_cant_be_written_is_left_out_and_the_rest_come_out(self):
        """One file that can't be written (a file where its folder should be, a path too long for the system)
        is left out, with why, and the rest still come out; one that climbs out is said too. A full disk stops it
        all (issue #174)."""
        import errno
        assets = {"1" * 32: ("Assets/Foo", b"a file"), "2" * 32: ("Assets/Foo/bar.txt", b"in a folder of that name"),
                  "3" * 32: ("../climb.txt", b"out"), "4" * 32: ("Assets/Deep/x.txt", b"deep"),
                  "5" * 32: ("Assets/fine.txt", b"fine")}
        real = packages.tempfile.mkstemp

        def mkstemp(dir=None, prefix=None):
            if "Deep" in str(dir):
                raise OSError(errno.ENAMETOOLONG, "File name too long")
            return real(dir=dir, prefix=prefix)
        dest = self.out()
        with mock.patch.object(packages.tempfile, "mkstemp", mkstemp):
            done = packages.extract(self.package(assets, asset_first=True), dest, ["all"])
        self.assertEqual(self.files(dest), {"Assets/Foo": b"a file", "Assets/fine.txt": b"fine"})
        self.assertEqual(sorted(done["skipped"]), [("../climb.txt", "its path leads outside the folder"),
                                                   ("Assets/Deep/x.txt", "its path is too long for this system"),
                                                   ("Assets/Foo/bar.txt", "a file of the same name is in the way")])

        def full(dir=None, prefix=None):
            raise OSError(errno.ENOSPC, "No space left on device")
        with mock.patch.object(packages.tempfile, "mkstemp", full), self.assertRaises(packages.CantExtract) as e:
            packages.extract(self.package(assets, asset_first=True), self.out("full"), ["all"])
        self.assertIn("No space left", str(e.exception))

    def test_packages_of_the_same_name_in_a_zip_stay_apart(self):
        """Two packages of the same name in a zip, in different folders or not: each one's files in a folder of its
        own, where it is in the zip (issue #175)."""
        path = self.home / "Avatar.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("PC/Avatar.unitypackage", unitypackage({G2: ("Assets/Avatar.prefab", b"pc")}))
            zf.writestr("Quest/Avatar.unitypackage", unitypackage({G2: ("Assets/Avatar.prefab", b"quest")}))
            zf.writestr("Avatar.unitypackage", unitypackage({G2: ("Assets/Avatar.prefab", b"one")}))
            with self.assertWarns(UserWarning):   # (a zip can hold two of the same name; zipfile says so)
                zf.writestr("Avatar.unitypackage", unitypackage({G2: ("Assets/Avatar.prefab", b"two")}))
        dest = self.out()
        packages.extract(path, dest, [f"p:{n}:Assets/Avatar.prefab" for n in range(4)])
        self.assertEqual(self.files(dest), {"PC/Avatar/Assets/Avatar.prefab": b"pc", "Quest/Avatar/Assets/Avatar.prefab": b"quest",
                                            "Avatar/Assets/Avatar.prefab": b"one", "Avatar (2)/Assets/Avatar.prefab": b"two"})

    @unittest.skipIf(os.name == "nt", "permissions as POSIX has them")
    def test_files_get_a_new_files_permissions(self):
        """Taken out, a file has the permissions any new file has here (the umask's), not mkstemp's owner-only ones
        (issue #176)."""
        dest = self.out()
        packages.extract(self.package(SAMPLE), dest, ["all"])
        mode = (dest / "Assets" / "Creator" / "Hoodie.prefab").stat().st_mode & 0o777
        self.assertEqual(mode, packages.FILE_MODE)
        mask = os.umask(0)
        os.umask(mask)
        self.assertEqual(packages.FILE_MODE, 0o666 & ~mask)

    def test_reading_stops_once_the_chosen_files_are_out(self):
        """One small file from the start of a large package: the rest of it isn't read (issue #182)."""
        big = {G2: ("Assets/Small.prefab", b"small"), G3: ("Assets/Big.bin", os.urandom(2 << 20))}
        path = self.package(big, asset_first=True)
        packages.look_inside(path)   # (as Look inside has, before Extract)
        real, read = packages.read_unitypackage, []

        class Counted:
            def __init__(self, stream):
                self.stream = stream

            def read(self, n=-1):
                data = self.stream.read(n)
                read.append(len(data))
                return data
        with mock.patch.object(packages, "read_unitypackage", lambda stream, **kw: real(Counted(stream), **kw)):
            done = packages.extract(path, self.out(), ["p:0:Assets/Small.prefab"])
        self.assertEqual(done["files"], 1)
        self.assertLess(sum(read), path.stat().st_size // 4)


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

    def test_extract_what_you_choose(self):
        """Look inside can take files out, not just list them: choose files and folders (a folder brings what's in
        it), or Extract everything; they go in a folder of their own in Hoard Edits, which opens."""
        from hoard import server
        opened = []
        edits = Path(self.tmp.name) / "Hoard Edits" / "Extracted"
        with mock.patch.object(server, "reveal", lambda p: opened.append(p) or "your file manager"):
            page = self.open_hoodie()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.locator("#detail .files li", has_text="Hoodie.unitypackage").locator("[data-act='inside']").click()
            win = page.locator("#insideWin")
            win.locator(".sum", has_text="2 files, ").wait_for()
            extract = win.locator("[data-x=extract][data-what=chosen]")
            self.assertTrue(extract.is_disabled(), "nothing chosen yet")
            win.locator("summary", has_text="Assets").click()
            creator = win.locator("summary", has_text="Creator")
            creator.locator("input.pick").check()   # a folder: everything in it
            self.assertFalse(creator.evaluate("s => s.parentElement.open"), "choosing a folder doesn't open it")
            self.assertEqual(extract.inner_text(), "Extract the 2 chosen files")
            creator.locator("span", has_text="Creator").click()
            self.assertTrue(win.locator("li.f", has_text="Hoodie.prefab").locator("input.pick").is_disabled(), "chosen with its folder")
            extract.click()
            page.get_by_text("Took 2 files out, into").wait_for()
            first = edits / "Hoodie"
            self.assertEqual(sorted(p.relative_to(first).as_posix() for p in first.rglob("*") if p.is_file()),
                             ["Assets/Creator/Hoodie.prefab", "Assets/Creator/Textures/hoodie.png"])
            self.assertEqual(opened, [first])
            # again, every file, with Unity's .meta files: a new folder beside the first
            page.locator("#insideMetas").check()
            win.locator("[data-x=extract][data-what=all]").click()
            page.get_by_text("Took 5 files out, into").wait_for()   # (two files, their .meta files, and the folder's)
            self.assertTrue((edits / "Hoodie (2)" / "Assets" / "Creator" / "Hoodie.prefab.meta").is_file())
            self.assertTrue((edits / "Hoodie (2)" / "Assets" / "Creator.meta").is_file())
            self.assertEqual(errors, [])

    def test_only_files_in_the_downloads(self):
        import json, urllib.request
        for path in ("../../etc/passwd.zip", "Booth/Kitsu Studio/Hoodie/readme.txt", "Booth/Kitsu Studio/Hoodie/gone.zip"):
            for action in ("/api/look-inside", "/api/look-inside/extract"):   # (taking files out, as reading them)
                req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{action}", method="POST",
                                             data=json.dumps({"path": path, "picks": ["all"]}).encode(),
                                             headers={"Content-Type": "application/json", "X-Hoard-Key": self.srv.key})
                with self.subTest(path=path, action=action), self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(req)
                self.assertEqual(e.exception.code, 404)

    def test_while_files_are_being_taken_out(self):
        """While Extract runs: ticking a box (which draws the bar again) doesn't turn its buttons back on; closing
        the window says how it went, without an error; and an empty folder counts as no files (issue #177)."""
        import threading
        from hoard import server
        go, real = threading.Event(), server.packages.extract

        def slow(*a, **k):
            go.wait(15)
            return real(*a, **k)
        with mock.patch.object(server, "reveal", lambda p: None), mock.patch.object(server.packages, "extract", slow):
            page = self.open_hoodie()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.locator("#detail .files li", has_text="Hoodie.unitypackage").locator("[data-act='inside']").click()
            win = page.locator("#insideWin")
            win.locator(".sum", has_text="2 files, ").wait_for()
            win.locator("[data-x=extract][data-what=all]").click()
            win.locator("[data-x=extract][data-what=chosen]", has_text="Taking them out").wait_for()
            win.locator("summary", has_text="Assets").click()
            win.locator("summary", has_text="Creator").locator("input.pick").check()   # (the bar, drawn again)
            self.assertTrue(win.locator("[data-x=extract][data-what=all]").is_disabled(), "still taking them out")
            self.assertTrue(win.locator("[data-x=extract][data-what=chosen]").is_disabled())
            win.locator(".win-x").click()   # closed before it's done
            go.set()
            page.get_by_text("Took 2 files out, into").wait_for()
            page.locator("#detail .files li", has_text="Hoodie.unitypackage").locator("[data-act='inside']").click()
            win.locator(".sum", has_text="2 files, ").wait_for()
            empty = page.evaluate("""() => {
                const d = document.createElement("details");
                d.innerHTML = '<summary><input class="pick" type="checkbox" data-pick="d:0:Assets/Empty" data-count="0"></summary>';
                const box = d.querySelector("input");
                box.checked = true;
                pickChanged(box);
                return [INSIDE.pick.get("d:0:Assets/Empty"), document.querySelector("#insideWin [data-what=chosen]").textContent];
            }""")
            self.assertEqual(empty, [0, "Choose files to extract"])
            self.assertEqual(errors, [])

    def test_when_nothing_could_be_taken_out_it_says_why(self):
        """Every chosen file left out: Extract says why, and leaves no empty folder behind (issue #174)."""
        import json, urllib.request
        from hoard import server
        edits = Path(self.tmp.name) / "Hoard Edits" / "Extracted"
        before = set(edits.iterdir()) if edits.is_dir() else set()
        nothing = {"files": 0, "bytes": 0, "skipped": [("../climb.txt", "its path leads outside the folder")]}
        req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}/api/look-inside/extract", method="POST",
                                     data=json.dumps({"path": "Booth/Kitsu Studio/Hoodie/Hoodie.unitypackage", "picks": ["all"]}).encode(),
                                     headers={"Content-Type": "application/json", "X-Hoard-Key": self.srv.key})
        with mock.patch.object(server.packages, "extract", lambda *a, **k: nothing), \
                self.assertRaises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        self.assertEqual((e.exception.code, json.loads(e.exception.read())),
                         (400, {"error": "Nothing could be taken out.",
                                "skipped": [{"name": "../climb.txt", "why": "its path leads outside the folder"}]}))
        self.assertEqual(set(edits.iterdir()) if edits.is_dir() else set(), before, "no empty folder left behind")

    def test_a_hidden_products_files_stay_shut_while_locked(self):
        """Look inside and Extract refuse a hidden product's file while the hidden library is locked, as Make an
        editable copy does, however the path is spelled; unlocked, they work (issue #171)."""
        import json, shutil, urllib.request
        from hoard import marks, server, tags

        def ask(action, path):
            req = urllib.request.Request(f"http://127.0.0.1:{self.srv.server_address[1]}{action}", method="POST",
                                         data=json.dumps({"path": path, "picks": ["all"]}).encode(),
                                         headers={"Content-Type": "application/json", "X-Hoard-Key": self.srv.key})
            try:
                with urllib.request.urlopen(req) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read() or b"{}")
        st = marks.MarkStore()
        st.set_pin("4821")
        st.change("hidden", {tags.tag_key("Booth", "Hoodie")}, True)
        self.addCleanup(lambda: st.path.unlink(missing_ok=True))
        with mock.patch.object(server, "reveal", lambda p: None):
            for path in ("Booth/Kitsu Studio/Hoodie/Hoodie.unitypackage", "Booth/Kitsu Studio/./Hoodie//Hoodie.unitypackage"):
                for action in ("/api/look-inside", "/api/look-inside/extract"):
                    with self.subTest(path=path, action=action):
                        self.assertEqual(ask(action, path), (403, {"error": "Unlock your hidden library first."}))
            with mock.patch.object(server.Handler, "_unlocked", lambda self: True):
                self.assertEqual(ask("/api/look-inside", "Booth/Kitsu Studio/Hoodie/Hoodie.unitypackage")[0], 200)
                status, done = ask("/api/look-inside/extract", "Booth/Kitsu Studio/Hoodie/Hoodie.unitypackage")
                self.assertEqual((status, done["ok"]), (200, True))
                shutil.rmtree(done["folder"])


if __name__ == "__main__":
    unittest.main()
