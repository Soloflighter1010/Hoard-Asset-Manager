"""Issue #416: a Local product edited (its name, creator, note and page on a store), filled in from that page, Local's
tabs by store, and a BB's Library Manager library brought in."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import bblm, config, downloader, downloads, local, storage
from hoard.marks import MarkStore
from hoard.sets import SetStore
from hoard.tags import TagStore, legacy_tag_key, tag_key

def index(cfg: dict, root: Path) -> dict:
    """Downloads' data, as the page has it."""
    return downloads.build_index(root, downloader.collect_catalog(cfg, root)[0])


def fresh_metadata() -> list[Path]:
    """Tags, marks, sets and what's been brought in from BB's Library Manager start empty in each test (a class's tests
    share one home); returns the files, to remove again after."""
    files = [TagStore().path, MarkStore().path, SetStore().path, bblm.remembered_file(), downloader.integrity_file()]
    for f in files:
        storage.remove(f, missing_ok=True)
    return files


PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
       b"\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")


class Edit(IsolatedTestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        self.root.mkdir()
        src = self.base / "Kit"
        src.mkdir()
        (src / "Kit.unitypackage").write_bytes(b"pkg")
        self.cfg = {**config.load_config(), "root": str(self.root)}
        for f in fresh_metadata():   # (one home for the class: each test starts with none)
            self.addCleanup(storage.remove, f, missing_ok=True)
        self.rec = local.add(self.cfg, self.root, str(src), name="Kit", creator="Me", copy=True)
        self.key = self.rec["key"]

    def asset(self):
        [a] = [a for a in index(self.cfg, self.root)["assets"] if a["store"] == "Local"]
        return a

    def test_renamed_its_tags_note_marks_and_sets_go_with_it(self):
        old = legacy_tag_key("local", "Kit")
        TagStore().change({"action": "assign", "keys": [old], "add": ["fox"]})
        TagStore().change({"action": "note", "keys": [old], "note": "Mine"})
        MarkStore().change("adult", {old}, True)
        made = SetStore().change({"action": "create", "name": "Outfit", "items": [old]})["made"]
        rec = local.edit(self.cfg, self.root, self.key, name="Fox Kit", creator="Ash", note="A commission")
        self.assertEqual((rec["name"], rec["creator"], rec["note"]), ("Fox Kit", "Ash", "A commission"))
        new = legacy_tag_key("local", "Fox Kit")
        tags = TagStore().load()
        self.assertEqual((tags["items"].get(new), tags["notes"].get(new)), (["fox"], "Mine"))
        self.assertNotIn(old, tags["items"])
        self.assertIn(new, MarkStore().keys("adult"))
        self.assertNotIn(old, MarkStore().keys("adult"))
        s = next(x for x in SetStore().load()["sets"] if x["id"] == made)
        self.assertEqual(s["items"], [new])
        a = self.asset()
        self.assertEqual((a["name"], a["creator"], a["tag_key"]), ("Fox Kit", "Ash", new))
        self.assertTrue(a["folder"].endswith(self.rec["folder"]), "its folder isn't moved")

    def test_its_page_on_a_store(self):
        local.edit(self.cfg, self.root, self.key, link="https://booth.pm/ja/items/123456?ref=x")
        a = self.asset()
        self.assertEqual((a["page"], a["source"]), ("https://booth.pm/ja/items/123456", "booth"))
        for bad in ("https://example.com/items/1", "javascript:alert(1)", "https://booth.pm/", "file:///etc/passwd"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                local.edit(self.cfg, self.root, self.key, link=bad)
        local.edit(self.cfg, self.root, self.key, link="")
        a = self.asset()
        self.assertEqual((a["page"], a["source"]), (None, None))
        with self.assertRaises(ValueError):
            local.edit(self.cfg, self.root, self.key, name="   ")
        with self.assertRaises(ValueError):
            local.edit(self.cfg, self.root, "local-000000000000", name="Gone")

    def test_a_page_written_into_the_manifest_by_hand_is_dropped(self):
        manifest = downloader.Manifest(local.local_dir(self.root))
        manifest.assets[self.key].update(page="https://evil.example/items/1", page_store="booth")
        manifest.save()
        self.assertIsNone(self.asset()["page"])
        rec = downloader.Manifest(local.local_dir(self.root)).assets[self.key]
        self.assertNotIn("page", rec)

    def test_filled_in_from_its_page(self):
        local.edit(self.cfg, self.root, self.key, link="https://booth.pm/en/items/42")
        got = {"store": "booth", "name": "Fox Hoodie", "creator": "Kitsu Works", "store_tags": ["hoodie", "Fox", "  "]}
        self.assertTrue(local.fill_in(self.cfg, self.root, self.key, got, PNG)[1], "its picture used")
        a = self.asset()
        self.assertEqual((a["name"], a["creator"]), ("Fox Hoodie", "Kitsu Works"))
        self.assertEqual(sorted(a["suggested"]), ["fox", "hoodie"])
        self.assertTrue(a["thumb"] and a["thumb"].endswith("_thumbnail.png"), "its picture, from the page")
        written = json.loads((self.root / "catalog.json").read_text("utf-8"))
        [entry] = [e for e in written["assets"] if e["store"] == "Local"]
        self.assertEqual((entry["name"], sorted(entry.get("suggested_tags") or [])), ("Fox Hoodie", ["fox", "hoodie"]),
                         "catalog.json, as written, has them")

    def test_its_suggested_tags_go_with_its_page(self):
        local.edit(self.cfg, self.root, self.key, link="https://booth.pm/en/items/42")
        local.fill_in(self.cfg, self.root, self.key, {"store": "booth", "store_tags": ["hoodie", "fox"]})
        self.assertEqual(sorted(self.asset()["suggested"]), ["fox", "hoodie"])
        local.fill_in(self.cfg, self.root, self.key, {"store": "booth", "store_tags": []})
        self.assertEqual(self.asset()["suggested"], [], "a page with none: the old ones go")
        local.fill_in(self.cfg, self.root, self.key, {"store": "booth", "store_tags": ["hoodie"]})
        local.edit(self.cfg, self.root, self.key, link="https://ash.gumroad.com/l/hat")
        self.assertEqual(self.asset()["suggested"], [], "another page: its old page's go")

    def test_a_picture_you_chose_stays(self):
        local.choose_picture(self.cfg, self.root, self.key, __import__("base64").b64encode(PNG).decode())
        chosen = local._chosen(self.key).read_bytes()
        other = PNG[:-12] + b"\x00" * 12   # (another picture, as far as Hoard can tell)
        _, used = local.fill_in(self.cfg, self.root, self.key, {"store": "booth", "name": "Kit"}, other)
        self.assertFalse(used)
        self.assertEqual(local._chosen(self.key).read_bytes(), chosen, "yours, still")

    def test_a_manifests_suggested_tags_are_checked(self):
        for bad in (1, True, "fox", {"a": 1}, [1, None, "  "]):
            with self.subTest(bad=bad):
                manifest = downloader.Manifest(local.local_dir(self.root))
                manifest.assets[self.key]["suggested_tags"] = bad
                manifest.save()
                self.assertEqual(self.asset()["suggested"], [], "left out, and the catalog still made")

    def test_page_tags_you_refused_arent_suggested(self):
        self.cfg["tags"] = {**self.cfg["tags"], "blocklist": ["free"]}
        TagStore().change({"action": "hide", "name": "secret"})
        local.fill_in(self.cfg, self.root, self.key, {"store": "booth", "store_tags": ["free", "fox", "secret"]})
        self.assertEqual(self.asset()["suggested"], ["fox"], "neither a word you blocked nor a suggestion you hid")

    def test_a_rename_is_all_or_none(self):
        old = legacy_tag_key("local", "Kit")
        TagStore().change({"action": "assign", "keys": [old], "add": ["fox"]})
        with mock.patch.object(MarkStore, "rekey", side_effect=TimeoutError("tags.lock is busy")):
            with self.assertRaises(ValueError):
                local.edit(self.cfg, self.root, self.key, name="Fox Kit")
        self.assertEqual(self.asset()["name"], "Kit", "not renamed")
        self.assertEqual(TagStore().load()["items"].get(old), ["fox"], "its tags put back")
        self.assertNotIn(legacy_tag_key("local", "Fox Kit"), TagStore().load()["items"])

    def test_a_rename_onto_a_choice_the_other_way(self):
        old, new = legacy_tag_key("local", "Kit"), legacy_tag_key("local", "Fox Kit")
        MarkStore().change("adult", {old}, True)
        MarkStore().change("not_adult", {new}, True)   # (a leftover, from a product gone)
        local.edit(self.cfg, self.root, self.key, name="Fox Kit")
        self.assertIn(new, MarkStore().keys("adult"))
        self.assertNotIn(new, MarkStore().keys("not_adult"), "one or the other: what it had wins")

    def test_filled_in_keeps_it_isnt_for_adults(self):
        local.edit(self.cfg, self.root, self.key, link="https://booth.pm/en/items/42")
        mark = tag_key("local", "Kit", self.key)
        MarkStore().change("not_adult", {mark}, True)
        done = local.fill_from_page(self.cfg, self.root, self.key, {"store": "booth", "name": "Kit", "adult": True})
        self.assertFalse(done["adult"])
        self.assertIn(mark, MarkStore().keys("not_adult"), "your word wins over its store's")
        self.assertNotIn(mark, MarkStore().keys("adult"))

    def test_a_name_another_product_in_local_has(self):
        src = self.base / "Other"
        src.mkdir()
        (src / "Other.unitypackage").write_bytes(b"pkg")
        local.add(self.cfg, self.root, str(src), name="Hat", creator="Me", copy=True)
        with self.assertRaises(ValueError):
            local.edit(self.cfg, self.root, self.key, name="hat")
        fox = self.base / "Fox"
        fox.mkdir()
        (fox / "Fox.unitypackage").write_bytes(b"pkg")
        local.add(self.cfg, self.root, str(fox), name="Fox Kit", creator="Me", copy=True)
        with self.assertRaises(ValueError, msg="kept in JSON, 'Fox Kit [v2]' is known as Fox Kit: it'd take on its tags"):
            local.edit(self.cfg, self.root, self.key, name="Fox Kit [v2]")
        self.assertEqual(local.edit(self.cfg, self.root, self.key, name="KIT")["name"], "KIT", "its own name in another case")
        got = {"store": "booth", "name": "Hat", "creator": "Kitsu Works"}
        rec, used = local.fill_in(self.cfg, self.root, self.key, got)
        self.assertFalse(used, "no picture given")
        self.assertEqual((rec["name"], rec["creator"]), ("KIT", "Kitsu Works"), "the rest filled in all the same")

    def test_renamed_from_a_name_another_product_shares(self):
        src = self.base / "Kit2"
        src.mkdir()
        (src / "Kit.unitypackage").write_bytes(b"pkg")
        local.add(self.cfg, self.root, str(src), name="Kit", creator="Me", copy=True)
        old = legacy_tag_key("local", "Kit")
        TagStore().change({"action": "assign", "keys": [old], "add": ["fox"]})
        MarkStore().change("adult", {old}, True)
        made = SetStore().change({"action": "create", "name": "Outfit", "items": [old]})["made"]
        local.edit(self.cfg, self.root, self.key, name="Fox Kit")
        new = legacy_tag_key("local", "Fox Kit")
        tags = TagStore().load()["items"]
        self.assertEqual((tags.get(old), tags.get(new)), (["fox"], ["fox"]), "the other Kit keeps its tags")
        self.assertTrue({old, new} <= MarkStore().keys("adult"))
        s = next(x for x in SetStore().load()["sets"] if x["id"] == made)
        self.assertEqual(s["items"], [old, new])


def _meta(folder: Path, **fields) -> None:
    folder.mkdir(parents=True)
    (folder / "meta.json").write_text(json.dumps({"id": folder.name, "files": [], "thumbnail": None, "tags": [],
                                                   "isAdult": False, **fields}), "utf-8")


class BringInFromBBLM(IsolatedTestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        self.root = self.base / "Hoard"
        self.root.mkdir()
        self.cfg = {**config.load_config(), "root": str(self.root)}
        for f in fresh_metadata():   # (one home for the class: each test starts with none)
            self.addCleanup(storage.remove, f, missing_ok=True)
        self.lib = self.base / "BBLM"
        owned = self.lib / "8549623"
        _meta(owned, name="Rusk Outfit", originUrl="https://booth.pm/ja/items/8549623", tags=["outfit"], isAdult=True)
        (owned / "rusk.zip").write_bytes(b"zip")
        free = self.lib / "1111"
        _meta(free, name="Free Shader", originUrl="https://shop.booth.pm/items/1111", tags=["shader", "free"],
              thumbnail="thumbnail.png")
        (free / "shader.zip").write_bytes(b"zip")
        (free / "thumbnail.png").write_bytes(PNG)
        gum = self.lib / "ash.hat"
        _meta(gum, name="Hat", originUrl="https://ash.gumroad.com/l/hat")
        (gum / "hat.zip").write_bytes(b"zip")
        _meta(self.lib / "2222", name="Still Downloading", downloadStatus="pending")
        _meta(self.lib / "3333", name="No Files", originUrl="https://booth.pm/ja/items/3333")
        (self.lib / ".blm-index.json").write_text("{}", "utf-8")
        self.library = [{"store": "booth", "id": "8549623", "name": "Rusk Outfit [v2]"}]

    def test_its_root_folder(self):
        self.assertEqual(bblm.check_folder(str(self.lib)), self.lib)
        self.assertEqual(bblm.check_folder(str(self.lib / "1111")), self.lib, "a product's folder: the one above")
        for bad in ("", "relative/path", str(self.base / "nope"), str(self.root)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bblm.check_folder(bad)

    def test_booth_items(self):
        self.assertEqual(bblm.booth_item("https://booth.pm/ja/items/8549623"), "8549623")
        self.assertEqual(bblm.booth_item("https://kitsu.booth.pm/items/12"), "12")
        self.assertIsNone(bblm.booth_item("https://booth.pm.evil.example/items/12"))
        self.assertIsNone(bblm.booth_item("https://gumroad.com/l/x"))

    def test_what_it_would_do_then_bringing_it_in(self):
        s = bblm.summary(bblm.plan(self.lib, self.library))
        self.assertEqual((s["total"], s["matched"], s["local"], s["left_out"]), (4, 1, 2, 1), "the pending one isn't counted")
        self.assertEqual(s["left_out_names"], ["No Files"])
        self.assertEqual(s["adult"], 1)
        before = {p.name: p.read_bytes() for p in self.lib.rglob("*") if p.is_file()}
        done = bblm.bring_in(self.cfg, self.root, self.lib, self.library)
        self.assertEqual((done["matched"], done["local"], done["adult"]), (1, 2, 1))
        self.assertEqual({p.name: p.read_bytes() for p in self.lib.rglob("*") if p.is_file()}, before, "nothing of BBLM's changed")
        owned = tag_key("booth", "Rusk Outfit [v2]", "8549623")
        self.assertEqual(TagStore().load()["items"].get(owned), ["outfit"])
        self.assertIn(owned, MarkStore().keys("adult"))
        mine = {a["name"]: a for a in index(self.cfg, self.root)["assets"] if a["store"] == "Local"}
        self.assertEqual(sorted(mine), ["Free Shader", "Hat"])
        self.assertEqual((mine["Free Shader"]["source"], mine["Hat"]["source"]), ("booth", "gumroad"))
        self.assertTrue(mine["Free Shader"]["linked"], "left where it is")
        self.assertTrue(mine["Free Shader"]["thumb"].endswith("_thumbnail.png"), "BBLM's picture")
        self.assertEqual(TagStore().load()["items"].get(legacy_tag_key("local", "Free Shader")), ["free", "shader"])
        again = bblm.summary(bblm.plan(self.lib, self.library))
        self.assertEqual((again["before"], again["matched"], again["local"]), (3, 0, 0), "only what's new, next time")

    def test_the_server(self):
        import http.client
        import threading
        from hoard import server
        from hoard.safety import ACCESS_HEADER
        srv = server.AppServer(("127.0.0.1", 0), self.cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

        def call(path, body):
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=20)
            c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json", ACCESS_HEADER: srv.key})
            r = c.getresponse()
            data = json.loads(r.read() or b"{}")
            c.close()
            return r.status, data
        status, s = call("/api/bblm/preview", {"path": str(self.lib)})
        self.assertEqual((status, s["local"]), (200, 3), "nothing in this library yet: the owned one is Local too")
        self.assertEqual(call("/api/bblm/preview", {"path": str(self.root)})[0], 400)
        self.assertEqual(call("/api/bblm/bring-in", {"path": str(self.lib)})[0], 404, "only when confirmed")
        rec = local.add(self.cfg, self.root, str(self.lib / "ash.hat"), name="Hat", copy=False)
        folder = next(a["folder"] for a in index(self.cfg, self.root)["assets"] if a["store"] == "Local")
        status, data = call("/api/local/edit", {"folder": folder, "name": "Ash's Hat", "link": "https://ash.gumroad.com/l/hat"})
        self.assertEqual((status, data["name"], data["link"]), (200, "Ash's Hat", "https://ash.gumroad.com/l/hat"))
        self.assertEqual(call("/api/local/edit", {"folder": folder, "link": "https://example.com"})[0], 400)
        with mock.patch.dict(srv.side_jobs.state, {"running": True, "task": "bblm"}):   # (an import changing Local)
            self.assertEqual(call("/api/local/edit", {"folder": folder, "name": "Busy Hat"})[0], 409)
        with local.WRITING:   # (Local's records being changed elsewhere: the sync folder's look, say)
            held = threading.Thread(target=lambda: self.assertEqual(call("/api/local/edit", {"folder": folder, "name": "Busy Hat"})[0], 409))
            held.start()
            held.join(10)
        page = {"store": "gumroad", "name": "Felt Hat", "creator": "ash", "thumbnail": "https://public-files.gumroad.com/x.png",
                "store_tags": [], "adult": True}
        with mock.patch.object(server.wishlists, "from_product_page", lambda link, fetch: page), \
                mock.patch("hoard.library.fetch_picture", lambda url, referer, hosts=None: (PNG, "image/png")):
            status, data = call("/api/local/from-page", {"folder": folder})
        self.assertEqual((status, data["name"], data["picture"], data["adult"]), (200, "Felt Hat", True, True))
        self.assertIn(tag_key("local", "Felt Hat"), MarkStore().keys("adult"))
        self.assertEqual(rec["key"], local.by_folder(self.root, folder)[0])

    def test_with_local_turned_off_it_asks_first(self):
        import threading
        import unittest
        if not BROWSER:
            raise unittest.SkipTest("needs Playwright's Chromium")
        from playwright.sync_api import sync_playwright
        from hoard import server
        cfg = {**self.cfg, "setup_done": True, "ui": {"toured": True, "features": {"local": False}}}
        srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        with mock.patch.object(server, "save_config"), sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            started = []
            page.on("request", lambda r: started.append(r.url) if "/api/bblm/bring-in" in r.url else None)
            page.goto(srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(srv.url)
            page.wait_for_function("() => typeof bblmBringIn === 'function' && typeof featureOn === 'function'")
            page.evaluate("p => { window.askFolder = async () => p; bblmBringIn(); }", str(self.lib))
            page.locator("#askDialog", has_text="Local is turned off").wait_for()
            page.locator("#askDialog button", has_text="Cancel").click()
            page.wait_for_timeout(300)
            self.assertEqual(started, [], "not brought in")
            self.assertFalse(page.evaluate("() => featureOn('local')"), "and Local left off")
            browser.close()


try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False


class InThePage(IsolatedTestCase):
    """Edit... in a Local product's details, and Local's tabs by store."""

    def setUp(self):
        import threading
        import unittest
        if not BROWSER:
            raise unittest.SkipTest("needs Playwright's Chromium")
        from hoard import server
        self.base = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.base, True)
        root = self.base / "Hoard"
        root.mkdir()
        cfg = {**config.load_config(), "root": str(root), "setup_done": True, "ui": {"toured": True}}
        for f in fresh_metadata():   # (one home for the class: each test starts with none)
            self.addCleanup(storage.remove, f, missing_ok=True)
        for name, link in (("Kit", "https://booth.pm/en/items/77"), ("Hat", None), ("Ears", "https://ash.gumroad.com/l/ears")):
            src = self.base / name
            src.mkdir()
            (src / f"{name}.unitypackage").write_bytes(b"pkg")
            rec = local.add(cfg, root, str(src), name=name, copy=True)
            if link:
                local.edit(cfg, root, rec["key"], link=link)
        self.srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def test_edit_and_tabs(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1300, "height": 860})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(self.srv.entry_url())
            page.wait_for_function("() => localStorage.getItem('hoard-key')")
            page.goto(self.srv.url + "downloads#store=Local")
            page.locator("#grid .slot", has_text="Kit").wait_for()
            tabs = page.locator("#drives [data-source]")
            self.assertEqual(tabs.evaluate_all("l => l.map(b => b.dataset.source + ' ' + b.querySelector('.n').textContent)"),
                             ["booth 1", "gumroad 1", "none 1"], "a tab for each store, and one for those with no page")
            page.click('#drives [data-source="gumroad"]')
            page.wait_for_timeout(200)
            self.assertEqual(page.locator("#grid .slot .nm").all_inner_texts(), ["Ears"])
            self.assertIn("from=gumroad", page.url, "kept in the address")
            page.click('#drives [data-source="gumroad"]')   # (chosen again: every store)
            page.locator("#grid .slot", has_text="Hat").click()
            page.locator('#detail [data-act="local-edit"]').click()
            page.locator("#editName").wait_for()
            page.fill("#editName", "Felt Hat")
            page.fill("#editLink", "https://kitsu.booth.pm/items/88")
            page.locator(".hd-card button", has_text="Save").click()
            page.locator("#askDialog, .hd-card", has_text="Fill in its name").first.wait_for()
            page.locator(".hd-card button", has_text="Not now").click()
            page.locator("#grid .slot", has_text="Felt Hat").wait_for()
            self.assertEqual(tabs.evaluate_all("l => l.map(b => b.dataset.source + ' ' + b.querySelector('.n').textContent)"),
                             ["booth 2", "gumroad 1"], "no product without a page now: no tab for it")
            self.assertEqual(page.locator('#detail [data-act="local-fill"]').count(), 1, "its page given: Fill in from its page")
            opens = page.locator("#detail .d-store a")
            self.assertEqual((opens.inner_text(), opens.get_attribute("href")), ("Open on Booth", "https://kitsu.booth.pm/items/88"),
                             "its details open its page")
            self.assertEqual(errors, [])
            browser.close()
