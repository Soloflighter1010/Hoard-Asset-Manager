"""Downloads, Disk space: the same file kept more than once (hoard/space.py), and /api/space."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from hoard import downloader, space
from hoard.tags import tag_key

BIG = b"\x00" * (space.MIN_SIZE + 10)


def put(base: Path, store_dir: str, key: str, creator: str, name: str, files: dict, check=True, **extra) -> Path:
    """A product downloaded into base, its files fingerprinted as the integrity check leaves them (or not)."""
    man = downloader.Manifest(base / store_dir)
    rec = man.record(key, creator, name)
    rec.update(name=name, creator=creator, **extra)
    folder = base / store_dir / rec["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    for n, (path, data) in enumerate(files.items()):
        (folder / path).write_bytes(data)
        f = {"path": path, "size": len(data)}
        if check:
            f.update(sha256=hashlib.sha256(data).hexdigest(), mtime_ns=os.stat(folder / path).st_mtime_ns)
        rec["files"][f"f{n}"] = f
    man.save()
    return folder


class Copies(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.main, self.other = Path(self.tmp.name) / "main", Path(self.tmp.name) / "other"
        self.main.mkdir(), self.other.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_same_file_in_two_products_and_two_folders(self):
        put(self.main, "Booth", "1", "Kitsu", "Rusk", {"base.unitypackage": BIG, "readme.txt": b"small"})
        put(self.main, "Gumroad", "g", "Kitsu", "Rusk Bundle", {"rusk.unitypackage": BIG, "own.zip": BIG + b"x"})
        put(self.other, "Booth", "2", "Kitsu", "Rusk Again", {"base.unitypackage": BIG})
        found = space.copies([self.main, self.other])
        self.assertEqual(found["unchecked"], 0)
        self.assertEqual(len(found["groups"]), 1, "a small file, and a file kept once, aren't listed")
        g = found["groups"][0]
        self.assertEqual(g["size"], len(BIG))
        self.assertEqual(sorted((c["library"], c["folder"], c["file"]) for c in g["copies"]),
                         [(0, "Booth/Kitsu/Rusk", "base.unitypackage"), (0, "Gumroad/Kitsu/Rusk Bundle", "rusk.unitypackage"),
                          (1, "Booth/Kitsu/Rusk Again", "base.unitypackage")])

    def test_biggest_saving_first(self):
        twice, thrice = BIG + b"a" * 100, BIG
        put(self.main, "Booth", "1", "K", "A", {"a": twice, "b": thrice})
        put(self.main, "Booth", "2", "K", "B", {"a": twice, "b": thrice})
        put(self.main, "Booth", "3", "K", "C", {"b": thrice})
        sizes = [len(g["copies"]) for g in space.copies([self.main])["groups"]]
        self.assertEqual(sizes, [3, 2], "two copies to free beat one, though each is a little smaller")

    def test_unchecked_or_changed_files_are_only_counted(self):
        put(self.main, "Booth", "1", "K", "A", {"a.zip": BIG})
        put(self.main, "Booth", "2", "K", "B", {"a.zip": BIG}, check=False)
        folder = put(self.main, "Booth", "3", "K", "C", {"a.zip": BIG})
        os.utime(folder / "a.zip", ns=(1, 1))   # changed since its fingerprint: it might not be the same any more
        found = space.copies([self.main])
        self.assertEqual(found, {"groups": [], "unchecked": 2})

    def test_hidden_and_listed_in_place_are_left_out(self):
        put(self.main, "Booth", "1", "K", "A", {"a.zip": BIG})
        put(self.main, "Booth", "2", "K", "Secret", {"a.zip": BIG})
        mine = os.path.normpath(os.path.abspath(Path(self.tmp.name) / "mine"))   # (absolute as each system writes it)
        put(self.main, "Local", "l", "Me", "Mine", {"a.zip": BIG}, location=mine)
        self.assertEqual(downloader.Manifest(self.main / "Local").assets["l"].get("location"), mine)
        self.assertEqual(space.copies([self.main], hidden={tag_key("Booth", "Secret")})["groups"], [])
        self.assertEqual(len(space.copies([self.main])["groups"][0]["copies"]), 2, "your own folder isn't Hoard's to free")

    def test_a_missing_folder_or_a_planted_link_is_skipped(self):
        put(self.main, "Booth", "1", "K", "A", {"a.zip": BIG})
        folder = put(self.main, "Booth", "2", "K", "B", {"a.zip": BIG})
        (folder / "a.zip").unlink()
        (folder / "a.zip").symlink_to(self.main / "Booth" / "K" / "A" / "a.zip")
        found = space.copies([self.main, Path(self.tmp.name) / "unplugged"])
        self.assertEqual(found, {"groups": [], "unchecked": 0})


if __name__ == "__main__":
    unittest.main()
