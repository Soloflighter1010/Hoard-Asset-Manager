"""Issue #305: bringing in a KonoAsset library, from made-up KonoAsset data folders in its current shape (version 3)
and older ones (2 and 1): matched to your library by the BOOTH item, the rest as Local products listed where they are,
their tags, categories and avatars as your tags, their memos as notes; KonoAsset's folder never changed; and bringing
in again adds nothing."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))

from hoard import config, downloader, konoasset, library, local, tags  # noqa: E402

RUSK, HOODIE, SKIN, LOST, WORLD = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222",
                                   "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444",
                                   "55555555-5555-4555-8555-555555555555")
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def description(name, creator, **more):
    return {"name": name, "creator": creator, "imageFilename": None, "tags": [], "memo": None, "boothItemId": None,
            "dependencies": [], "createdAt": 1735689600000, "publishedAt": None, **more}


def make_folder(base: Path, version: int = 3) -> Path:
    """A KonoAsset data folder: an avatar on BOOTH that's in your library, a hoodie for it that isn't (with its files
    and picture), a skin with only a memo, an asset with no files, and a world object."""
    d = base / "KonoAsset"
    (d / "metadata").mkdir(parents=True)
    (d / "images").mkdir()
    (d / "images" / "hoodie.png").write_bytes(PNG)
    for asset, files in ((HOODIE, {"Hoodie.unitypackage": b"pkg", "Textures/hoodie.png": PNG}),
                         (SKIN, {"Skin.unitypackage": b"skin"}), (WORLD, {"Bench.unitypackage": b"bench"})):
        for rel, data in files.items():
            (d / "data" / asset / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / "data" / asset / rel).write_bytes(data)
    (d / "data" / LOST).mkdir(parents=True)   # (nothing in it)
    avatars = [{"id": RUSK, "description": description("Rusk", "Kitsu Studio", boothItemId=1001, tags=["base", "kemono"],
                                                        memo="My main avatar")}]
    wearables = [{"id": HOODIE, "description": description("Winter Hoodie", "Mochi Works", boothItemId=2002,
                                                           imageFilename="hoodie.png", tags=["Winter"], memo="Hue +20",
                                                           dependencies=[RUSK]),
                  "category": "Outerwear", "supportedAvatars": ["Rusk", "Anko"]},
                 {"id": LOST, "description": description("Lost Thing", "Someone"), "category": "", "supportedAvatars": []}]
    others = [{"id": SKIN, "description": description("Freckle Skin", "", memo="Only the face"), "category": "Texture"}]
    worlds = [{"id": WORLD, "description": description("Park Bench", "Prop Shop", tags=["prop"]), "category": "Furniture"}]
    if version < 3:   # (version 2: no dependencies)
        for a in avatars + wearables + others + worlds:
            a["description"].pop("dependencies")
    if version == 1:   # a bare list, no memos, the picture's whole path
        for a in avatars + wearables + others + worlds:
            a["description"].pop("memo")
            if a["description"]["imageFilename"]:
                a["description"]["imagePath"] = str(d / "images" / a["description"].pop("imageFilename"))
    for name, data in (("avatars.json", avatars), ("avatarWearables.json", wearables), ("otherAssets.json", others),
                       ("worldObjects.json", worlds)):
        (d / "metadata" / name).write_text(json.dumps(data if version == 1 else {"version": version, "data": data}), "utf-8")
    return d


def hashes(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


class BringingIn(unittest.TestCase):

    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        self.root.mkdir()
        self.cfg = {**config.load_config(), "root": str(self.root)}
        self.library = [library.item("booth", "1001", name="Rusk", creator="Kitsu Studio")]
        for f in (konoasset.remembered_file(), tags.tags_file(), downloader.integrity_file()):
            f.unlink(missing_ok=True)
            self.addCleanup(f.unlink, missing_ok=True)
        self.addCleanup(shutil.rmtree, local.pictures_dir(), True)

    def bring_in(self, folder):
        return konoasset.bring_in(self.cfg, self.root, konoasset.check_folder(str(folder)), self.library)

    def check(self, version):
        folder = make_folder(self.base, version)
        before = hashes(folder)
        seen = konoasset.summary(konoasset.plan(konoasset.check_folder(str(folder)), self.library))
        self.assertEqual({k: seen[k] for k in ("total", "matched", "local", "left_out", "before")},
                         {"total": 5, "matched": 1, "local": 3, "left_out": 1, "before": 0})
        self.assertEqual(seen["left_out_names"], ["Lost Thing"])
        self.assertFalse(tags.tags_file().exists(), "looking changes nothing")

        done = self.bring_in(folder)
        self.assertEqual((done["matched"], done["local"], done["left_out"]), (1, 3, ["Lost Thing"]))
        data = tags.TagStore().load()
        rusk, hoodie = tags.tag_key("booth", "Rusk"), tags.tag_key("local", "Winter Hoodie")
        skin, bench = tags.tag_key("local", "Freckle Skin"), tags.tag_key("local", "Park Bench")
        self.assertEqual(data["items"][rusk], ["base", "kemono"], "matched by its BOOTH item")
        self.assertEqual(data["items"][hoodie], ["anko", "outerwear", "rusk", "winter"], "its category and avatars too")
        self.assertEqual(data["items"][bench], ["furniture", "prop"])
        self.assertEqual(data["types"], {rusk: "avatar", bench: "world"}, "what an avatar and a world object are")
        if version > 1:
            self.assertEqual(data["notes"][rusk], "My main avatar")
            self.assertEqual(data["notes"][skin], "Only the face")
        hoodie_note = data["notes"][hoodie]
        self.assertIn("https://booth.pm/ja/items/2002", hoodie_note, "a Local product's BOOTH page")
        self.assertEqual("Needs: Rusk" in hoodie_note, version == 3, "what it needs (version 3 has them)")
        self.assertEqual(hoodie_note.startswith("Hue +20"), version > 1)

        listed = {e["name"]: e for e in downloader.collect_catalog(self.cfg, self.root)[0]}
        self.assertEqual(sorted(listed), ["Freckle Skin", "Park Bench", "Winter Hoodie"])
        self.assertEqual(listed["Winter Hoodie"]["location"], str(folder / "data" / HOODIE), "left where it is")
        self.assertEqual(sorted(listed["Winter Hoodie"]["files"]), ["Hoodie.unitypackage", "Textures/hoodie.png"])
        self.assertEqual(listed["Winter Hoodie"]["creator"], "Mochi Works")
        self.assertEqual(listed["Freckle Skin"].get("your_note"), "Only the face" if version > 1 else None, "the note, for Hoard for Unity")
        pictures = list(local.pictures_dir().glob("*.png"))
        self.assertEqual([p.read_bytes() for p in pictures], [PNG], "KonoAsset's picture, as the one chosen")
        self.assertEqual(hashes(folder), before, "nothing in KonoAsset's folder changed")

        again = self.bring_in(folder)
        self.assertEqual((again["matched"], again["local"], again["tags"], again["notes"]), (0, 0, 0, 0), "nothing twice")
        self.assertEqual(len(downloader.collect_catalog(self.cfg, self.root)[0]), 3)
        self.assertEqual(konoasset.summary(konoasset.plan(folder, self.library))["before"], 4)
        self.assertEqual(hashes(folder), before)

    def test_the_current_shape(self):
        self.check(3)

    def test_version_2(self):
        self.check(2)

    def test_version_1(self):
        self.check(1)

    def test_a_note_you_wrote_stays(self):
        folder = make_folder(self.base)
        rusk = tags.tag_key("booth", "Rusk")
        tags.TagStore().change({"action": "note", "keys": [rusk], "note": "Mine"})
        tags.TagStore().change({"action": "set-type", "keys": [rusk], "type": "other"})
        self.bring_in(folder)
        data = tags.TagStore().load()
        self.assertEqual((data["notes"][rusk], data["types"][rusk]), ("Mine", "other"))

    def test_not_konoassets_folder(self):
        for bad in ("", "relative/path", str(self.base / "nowhere"), str(self.base)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                konoasset.check_folder(bad)
        folder = make_folder(self.base)
        self.assertEqual(konoasset.check_folder(str(folder / "metadata")), folder, "its metadata folder means the one above")
        (folder / "metadata" / "avatars.json").write_text('{"version": 9, "data": {}}', "utf-8")
        with self.assertRaises(ValueError):
            konoasset.read(folder)

    def test_what_cant_be_read_is_left_out(self):
        folder = make_folder(self.base)
        (folder / "metadata" / "otherAssets.json").write_text(json.dumps({"version": 3, "data": [
            {"id": "not-a-uuid", "description": description("Bad Id", "x")},
            {"id": SKIN, "description": description("Name‮flipped", "x", boothItemId=-4, imageFilename="../../secret.png",
                                                    tags=["ok", 7, "<b>"], dependencies=["nope"]), "category": "Texture"},
            {"id": LOST.replace("4", "6"), "description": {"name": ""}}]}), "utf-8")
        found = {a["id"]: a for a in konoasset.read(folder)}
        self.assertNotIn("not-a-uuid", found)
        skin = found[SKIN]
        self.assertEqual((skin["name"], skin["booth"], skin["picture"], skin["needs"]), ("Nameflipped", None, None, []))
        self.assertEqual(skin["tags"], ["ok", "b", "texture"])


if __name__ == "__main__":
    unittest.main()
