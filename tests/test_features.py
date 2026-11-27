"""Issues #421 and #422: Settings as cards, with Find a setting, and Features: a switch for each part of Hoard you may
not use (Local, Sets and Wishlists, wishlists alone, prices, Projects, notifications, products for adults). A part
turned off leaves the bar, the views' tabs, the menus and the right-click menu, and what's its own leaves the lists;
nothing it keeps is deleted, and turned on again it's all back. The choice is kept, and what relies on a part that's
off says so, with a way to turn it on."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.isolation import IsolatedTestCase
from hoard import alerts, config, downloader, library, local, server, sets, wishlists
from hoard.marks import MarkStore
from hoard.tags import tag_key
from tests.browsing import menu

try:
    from tests.test_packages import BROWSER
except ImportError:
    BROWSER = False

FEATURES = ("local", "sets", "wishlists", "prices", "projects", "notifications", "adult")


class Kept(IsolatedTestCase):
    """What's kept of the switches, and what Hoard itself does with a part off."""

    def test_only_whats_off_is_read_back_and_on_again_clears_it(self):
        cfg = {"ui": {}}
        config.deep_merge(cfg, server.apply_settings(cfg, {"ui": {"features": {"sets": False, "adult": False, "nope": False,
                                                                              "local": "no"}}}))
        self.assertEqual(server.ui_settings(cfg)["features"], {"sets": False, "adult": False}, "a part's key, on or off")
        config.deep_merge(cfg, server.apply_settings(cfg, {"ui": {"features": {"sets": True}}}))
        self.assertEqual(server.ui_settings(cfg)["features"], {"adult": False}, "on again: no longer off")
        config.deep_merge(cfg, server.apply_settings(cfg, {"ui": {"features": {"adult": True}}}))
        self.assertNotIn("features", server.ui_settings(cfg), "everything on: nothing to say")

    def test_a_part_is_off_with_the_part_its_in(self):
        self.assertEqual(set(config.FEATURES), set(FEATURES))
        on = {"ui": {}}
        self.assertTrue(all(config.feature_on(on, k) for k in FEATURES))
        no_sets = {"ui": {"features": {"sets": False}}}
        self.assertEqual([k for k in FEATURES if not config.feature_on(no_sets, k)], ["sets", "wishlists", "prices"])
        no_wishes = {"ui": {"features": {"wishlists": False}}}
        self.assertEqual([k for k in FEATURES if not config.feature_on(no_wishes, k)], ["wishlists", "prices"])
        self.assertTrue(config.feature_on({"ui": {"features": "off"}}, "sets"), "a damaged setting: on")

    def test_the_sync_folder_is_left_alone_with_local_off(self):
        from hoard import localsync
        srv = mock.Mock(cfg={"local_sync": "/somewhere", "ui": {"features": {"local": False}}})
        with mock.patch.object(localsync, "scan") as scan:
            self.assertIsNone(localsync.tick(srv))
        scan.assert_not_called()
        srv.jobs.busy.acquire.assert_not_called()

    def test_wishlists_off_quick_refresh_reads_only_the_libraries(self):
        from hoard import jobs
        job = jobs.Jobs.__new__(jobs.Jobs)
        job.cfg, job._forced, job.state = {"ui": {"features": {"sets": False}}}, False, {}
        with mock.patch.object(jobs.Jobs, "_refresh", return_value=[]) as refresh, \
                mock.patch.object(jobs.Jobs, "_wishlists") as wishes:
            job._quick_refresh(["booth"])
        refresh.assert_called_once()
        wishes.assert_not_called()

    def test_notifications_off_sends_nothing(self):
        cfg = {"apprise_events": list(alerts.EVENTS), "ui": {}}
        sent = []
        with mock.patch.object(alerts, "available", lambda: True), mock.patch.object(alerts, "_kept", 1), \
                mock.patch.object(alerts, "_out") as out:
            out.put_nowait.side_effect = sent.append
            with mock.patch.object(alerts, "_worker", mock.Mock(is_alive=lambda: True)):
                self.assertTrue(alerts.send(cfg, "new", "1 new product"))
                cfg["ui"] = {"features": {"prices": False}}
                self.assertFalse(alerts.send(cfg, "prices", "cheaper"), "Prices off: not the news of one")
                self.assertTrue(alerts.send(cfg, "tasks", "a task finished"), "the rest still")
                cfg["ui"] = {"features": {"notifications": False}}
                for event in alerts.EVENTS:
                    self.assertFalse(alerts.send(cfg, event, "anything"), event)
        self.assertEqual(len(sent), 2)

    def test_queued_wishlist_reads_and_links_stop_once_turned_off(self):
        from hoard import jobs
        job = jobs.Jobs.__new__(jobs.Jobs)
        job.cfg = {"ui": {"features": {"wishlists": False}}}
        with mock.patch.object(jobs.Jobs, "_set") as said, mock.patch.object(sets.SetStore, "put_wishlists") as put:
            job._wishlists(["booth"])
        put.assert_not_called()
        self.assertIn("turned off", said.call_args.kwargs["message"])
        wish = sets.SetStore().change({"action": "create", "name": "Wants", "kind": "wishlist"})["made"]
        with mock.patch.object(jobs.Jobs, "_set") as said, mock.patch.object(sets.SetStore, "add_products") as add:
            job._links(["payhip"], {"set": wish, "links": ["https://payhip.com/b/AbC12"]})
        add.assert_not_called()
        self.assertIn("nothing was added", said.call_args.kwargs["message"])

    def test_file_explorer_adds_nothing_with_local_off(self):
        from hoard import explorer
        srv = mock.Mock(cfg={"ui": {"features": {"local": False}}, "local_sync": "/somewhere"})
        with mock.patch.object(explorer, "add") as add:
            for do in ("add", "sync"):
                self.assertEqual(explorer.do(srv, {"do": do, "path": "/somewhere/a.png"}), {"said": "local-off"}, do)
        add.assert_not_called()
        srv.start_worker.assert_not_called()

    def test_cheaper_news_leaves_out_products_for_adults_with_them_off(self):
        items = [{"key": "booth:nightdress", "store": "booth", "name": "Night Dress", "url": "https://booth.pm/ja/items/2",
                  "was": "1,000 JPY", "now": "800 JPY", "adult": True},
                 {"key": "booth:foxhoodie", "store": "booth", "name": "Fox Hoodie", "url": "https://booth.pm/ja/items/5",
                  "was": "1,200 JPY", "now": "900 JPY"}]
        srv = mock.Mock(cfg={"ui": {"features": {"adult": False}}})
        with mock.patch.object(alerts, "send") as send:
            server.AppServer._news(srv, "cheaper", {"count": 2, "items": items})
            text = send.call_args.args[2]
            self.assertIn("Fox Hoodie", text)
            self.assertNotIn("Night Dress", text)
            send.reset_mock()
            server.AppServer._news(srv, "cheaper", {"count": 1, "items": items[:1]})
            send.assert_not_called()   # (only one for adults: nothing to say)

    def test_a_set_holding_a_product_for_adults(self):
        s = {"items": ["booth:a", "booth:b"], "products": {"booth:b": {"adult": True}}}
        self.assertTrue(sets.holds_adult(s, set(), set()), "its store said so")
        self.assertFalse(sets.holds_adult(s, set(), {"booth:b"}), "you said it isn't")
        self.assertTrue(sets.holds_adult({"items": ["booth:a"]}, {"booth:a"}, set()), "one for adults in your library")


def _record(root: Path, store: str, creator: str, name: str, key: str) -> None:
    folder = root / store / creator / name
    folder.mkdir(parents=True)
    (folder / "p.unitypackage").write_bytes(b"x")
    man = downloader.Manifest(root / store)
    rec = man.record(key, creator, name)
    rec.update(name=name, creator=creator)
    rec["files"]["f"] = {"path": "p.unitypackage", "size": 1}
    man.save()


def _wished(name: str, price: str, id_: str) -> dict:
    return {"store": "booth", "name": name, "creator": "Kitsu", "url": f"https://booth.pm/en/items/{id_}",
            "price": wishlists.parse_price(price)}


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium (python -m playwright install chromium)")
class Switches(IsolatedTestCase):
    """Each switch, in the page: what it hides, and that it all comes back."""

    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = Path(tempfile.mkdtemp())
        cls.env = mock.patch.dict(os.environ, {"HOARD_DATA_DIR": str(cls.tmp / "data")})
        cls.env.start()
        root = cls.tmp / "dl"
        _record(root, "Booth", "Kitsu", "Rusk", "1")
        _record(root, "Booth", "Shy", "Night Dress", "2")
        mine = cls.tmp / "My Textures"
        mine.mkdir()
        (mine / "a.png").write_bytes(b"x")
        cfg = {**config.load_config(), "root": str(root), "setup_done": True, "ui": {"toured": True}}
        local.add(cfg, root, str(mine), name="My Textures", creator="Me", catalog=False)
        cls.srv = server.AppServer(("127.0.0.1", 0), cfg, lan=False)
        with cls.srv.lib.lock:   # (in memory only)
            cls.srv.lib.data["items"] = [
                library.item("booth", "1", name="Rusk", creator="Kitsu", url="https://booth.pm/ja/items/1"),
                library.item("booth", "2", name="Night Dress", creator="Shy", url="https://booth.pm/ja/items/2")]
        MarkStore().change("adult", {tag_key("booth", "Night Dress")}, True)
        store = sets.SetStore()
        store.put_wishlists([{"store": "booth", "list": "Loved items", "url": "u",
                              "products": [_wished("Fox Hoodie", "1,200 JPY", "5001"), _wished("Fox Ears", "800 JPY", "5002")]}])
        cls.saving = mock.patch.object(server, "save_config")   # (the switches are kept in cfg; nothing's written)
        cls.saving.start()
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.saving.stop()
        cls.env.stop()
        __import__("shutil").rmtree(cls.tmp, True)

    def setUp(self):
        self.srv.cfg.setdefault("ui", {})["features"] = {}   # (every part on, as each test starts)
        self.errors = []

    def open(self, where="/"):
        page = self.browser.new_page(viewport={"width": 1280, "height": 860})
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.goto(self.srv.entry_url())
        page.wait_for_function("() => localStorage.getItem('hoard-key')")
        if where != "/":
            page.goto(self.srv.entry_url().split("/#")[0] + where)
        page.locator("#grid").wait_for(state="attached")
        page.wait_for_function("() => document.querySelector('#count') && /\\d/.test(document.querySelector('#count').textContent)")
        self.addCleanup(page.close)
        return page

    def flip(self, page, key, on):
        """Turn a part on or off in Settings' Features, as you would, and wait for Hoard to keep it."""
        self.open_settings(page)
        switch = page.locator(f'[data-feature-switch="{key}"] input')
        switch.wait_for()
        (switch.check if on else switch.uncheck)()
        self.kept(key, on)
        self.close_settings(page)

    def kept(self, key, on):
        """Wait for Hoard to keep a part as on or off (the page saves its layout a moment after a change)."""
        deadline = time.time() + 10
        while time.time() < deadline and ((self.srv.cfg.get("ui") or {}).get("features") or {}).get(key) is not on:
            time.sleep(0.1)
        self.assertIs(self.srv.cfg["ui"]["features"].get(key), on, f"{key} kept as {on}")

    def shown(self, page):
        """The products' names on the grid (the Library's tiles, and Downloads')."""
        page.wait_for_timeout(200)   # (drawn again as the switch is kept)
        return page.locator("#grid .slot :is(.nm-t, .nm)").all_inner_texts()

    def open_settings(self, page):
        """Open Settings from the Menu, as you would. (Closing it goes back a step in the page's history, as Back does,
        which can land just after a quick click on Settings and close it again: a person is never that quick.)"""
        for _ in range(3):
            if page.locator("#settingsPanel").is_visible():
                break
            menu(page, "#settingsBtn")
            try:
                page.locator("#settingsPanel").wait_for(state="visible", timeout=3000)
            except Exception:
                continue
            page.wait_for_timeout(300)
        page.locator("#card-features").wait_for()

    def close_settings(self, page):
        """Close Settings as you would, with Escape, and let its step back in the page's history land."""
        page.keyboard.press("Escape")
        page.locator("#settingsPanel").wait_for(state="hidden")
        page.wait_for_timeout(600)

    def menu_groups(self, page, tile):
        """The right-click menu's groups for this tile."""
        page.locator("#grid .slot", has_text=tile).click(button="right")
        page.locator(".selmenu").wait_for()
        names = page.locator(".selmenu [role=menuitem]").all_inner_texts()
        page.keyboard.press("Escape")
        page.locator(".selmenu").wait_for(state="detached")
        return names

    def test_settings_lists_each_switch_on(self):
        page = self.open()
        self.open_settings(page)
        switches = page.locator("[data-feature-switch]")
        switches.first.wait_for()
        self.assertEqual(switches.evaluate_all("l => l.map(s => s.dataset.featureSwitch)"), list(FEATURES))
        self.assertTrue(all(page.locator(f'[data-feature-switch="{k}"] input').is_checked() for k in FEATURES))
        self.assertEqual(page.locator('[data-feature-switch] input[role="switch"]').count(), len(FEATURES))
        self.assertEqual(self.errors, [])

    def test_local(self):
        page = self.open("/downloads")
        page.locator("#grid .slot", has_text="My Textures").wait_for()
        self.flip(page, "local", False)
        self.assertNotIn("My Textures", self.shown(page))
        self.assertIn("Rusk", self.shown(page), "the rest stay")
        self.assertTrue(page.locator('.apptabs a[href="/downloads#store=Local"]').is_hidden(), "not in the bar")
        self.assertTrue(page.locator('#storeSeg [data-store="Local"]').is_hidden(), "nor Downloads' tabs")
        self.assertTrue(page.locator("#localAdd").is_hidden())
        self.open_settings(page)
        self.assertTrue(page.locator("#part-sync").is_hidden(), "nor the Local sync folder in Settings")
        self.close_settings(page)
        self.flip(page, "local", True)
        page.locator("#grid .slot", has_text="My Textures").wait_for()
        self.assertTrue(page.locator('.apptabs a[href="/downloads#store=Local"]').is_visible())
        self.assertEqual(self.errors, [])

    def test_kept_when_hoard_opens_again(self):
        page = self.open("/downloads")
        self.flip(page, "local", False)
        page.wait_for_timeout(500)   # (the page's own copy of its layout, saved with the switch)
        again = self.open("/downloads")
        again.locator("#grid .slot", has_text="Rusk").wait_for()
        self.assertNotIn("My Textures", self.shown(again))
        self.assertTrue(again.locator('.apptabs a[href="/downloads#store=Local"]').is_hidden())
        self.open_settings(again)
        self.assertFalse(again.locator('[data-feature-switch="local"] input').is_checked())

    def test_sets_and_wishlists(self):
        page = self.open()
        page.locator("#grid .slot", has_text="Rusk").wait_for()
        self.assertIn("New set from these...", self.menu_groups(page, "Rusk"))
        self.flip(page, "sets", False)
        self.assertTrue(page.locator('.apptabs a[href="/#store=Sets"]').is_hidden())
        self.assertTrue(page.locator('#storeSeg [data-store="Sets"]').is_hidden())
        self.assertNotIn("New set from these...", self.menu_groups(page, "Rusk"), "nothing about sets in the right-click menu")
        self.open_settings(page)
        wishes = page.locator('[data-feature-switch="wishlists"]')
        self.assertTrue(wishes.locator("input").is_disabled(), "wishlists are a part of it")
        self.assertIn("Turn on Sets and Wishlists first.", wishes.inner_text())
        self.assertIn("Turn on Sets and Wishlists first.", page.locator('[data-feature-switch="prices"]').inner_text(),
                      "the one to turn on, not Wishlists, whose switch is greyed")
        self.close_settings(page)
        page.locator("#grid .slot", has_text="Rusk").click()
        page.locator("#detail.open").wait_for()
        self.assertNotIn("Sets", page.locator("#detail h3").all_inner_texts(), "no Sets in a product's details")
        page.keyboard.press("Escape")
        page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")   # (an address for it, as Back gives one)
        page.locator("#grid .slot", has_text="Rusk").wait_for()   # (Everything, not an empty Sets)
        self.assertEqual(page.evaluate("""() => featureSets({sets: [{kind: 'set', items: [{local: true, placeholder: true}]}]})"""),
                         {"sets": []}, "every set left out while Sets is off")
        # a link to a set asks to turn it on, and nothing is opened when you say no
        page.evaluate("() => { openLink({do: 'set', code: 'abc'}); }")   # (not waited for: it waits for the question)
        page.locator("#askDialog").wait_for()
        self.assertIn("Sets and Wishlists is turned off", page.locator("#askDialog").inner_text())
        page.locator("#askDialog button", has_text="Cancel").click()
        self.assertIs(self.srv.cfg["ui"]["features"]["sets"], False)
        self.flip(page, "sets", True)
        page.goto(self.srv.entry_url().split("/#")[0] + "/#store=Sets")
        page.locator(".settile", has_text="Loved items").wait_for()
        self.assertEqual(self.errors, [])

    def test_wishlists_alone(self):
        page = self.open("/#store=Sets")
        page.locator(".settile", has_text="Loved items").wait_for()
        self.flip(page, "wishlists", False)
        page.locator(".setfind").wait_for()
        self.assertEqual(page.locator(".settile", has_text="Loved items").count(), 0)
        self.assertEqual(page.locator('[data-setx="readwish"]').count(), 0, "nor reading them")
        self.assertTrue(page.locator('#storeSeg [data-store="Sets"]').is_visible(), "sets stay")
        got = page.evaluate("apiPost('/api/wishlists/read', {stores: ['booth']})")
        self.assertEqual(got["status"], 409)
        self.assertEqual(sets.SetStore().load()["sets"][0]["name"], "Booth: Loved items", "nothing deleted")
        self.flip(page, "wishlists", True)
        page.locator(".settile", has_text="Loved items").wait_for()
        self.assertEqual(self.errors, [])

    def test_prices(self):
        page = self.open("/#store=Sets")
        page.locator(".settile", has_text="Loved items").click()
        buy = page.locator('details[data-fold="wish-buy"]')
        buy.wait_for()
        self.assertEqual(buy.locator(".price").count(), 2)
        self.assertEqual(page.locator(".wishbar").count(), 1)
        self.flip(page, "prices", False)
        buy.wait_for()
        self.assertEqual(buy.locator(".price").count(), 0)
        self.assertEqual(page.locator(".wishbar, .price-total").count(), 0, "nor the range or the total")
        self.assertEqual(buy.locator(".slot.ext").count(), 2, "the products stay")
        self.open_settings(page)
        self.assertTrue(page.locator('[data-apprise-event="prices"]').is_hidden(), "nor its news")
        self.close_settings(page)
        self.flip(page, "prices", True)
        buy.locator(".price").first.wait_for()
        self.assertEqual(self.errors, [])

    def test_projects(self):
        page = self.open()
        page.locator("#grid .slot", has_text="Rusk").wait_for()
        self.assertIn("Put in a project...", self.menu_groups(page, "Rusk"))
        self.flip(page, "projects", False)
        self.assertTrue(page.locator("#projectsTab").is_hidden())
        self.assertNotIn("Put in a project...", self.menu_groups(page, "Rusk"))
        self.flip(page, "projects", True)
        self.assertTrue(page.locator("#projectsTab").is_visible())
        self.assertEqual(self.errors, [])

    def test_notifications(self):
        page = self.open()
        self.open_settings(page)
        self.assertTrue(page.locator("#card-notify").is_visible())
        self.close_settings(page)
        self.flip(page, "notifications", False)
        self.open_settings(page)
        self.assertTrue(page.locator("#card-notify").is_hidden())
        self.assertTrue(page.locator('[data-jump="card-notify"]').is_hidden(), "nor listed")
        self.close_settings(page)
        self.flip(page, "notifications", True)
        self.assertEqual(self.errors, [])

    def test_products_for_adults(self):
        page = self.open()
        page.locator("#grid .slot", has_text="Night Dress").wait_for()
        self.flip(page, "adult", False)
        self.assertEqual(self.shown(page), ["Rusk"], "the Library")
        self.assertNotIn("Mark as 18+", self.menu_groups(page, "Rusk"))
        self.open_settings(page)
        self.assertTrue(page.locator("#setBlurAdult").is_hidden())
        self.close_settings(page)
        page.click("nav.apptabs a[href='/downloads']")
        page.locator("#grid .slot", has_text="Rusk").wait_for()
        self.assertNotIn("Night Dress", self.shown(page), "Downloads")
        # turned on and off again from here (its switch alone): the Library's products, out of sight, are filtered again
        library = "() => APP.views.library.DATA.items.map(a => a.name)"
        page.evaluate("setFeature('adult', true)")
        page.wait_for_function(f"() => ({library})().includes('Night Dress')", timeout=5000)
        page.evaluate("setFeature('adult', false)")
        page.wait_for_function(f"() => !({library})().includes('Night Dress')", timeout=5000)
        self.kept("adult", False)
        page.fill("#q", "night")
        page.wait_for_timeout(300)
        self.assertEqual(self.shown(page), [], "nor found")
        page.fill("#q", "")
        # its link asks to turn it on, and shows it once it is
        key = page.evaluate("APP.cache.library.items.find(a => a.name === 'Night Dress').key")
        page.evaluate(f"() => {{ openFromLink({key!r}); }}")
        page.locator("#askDialog").wait_for()
        self.assertIn("Products for adults is turned off", page.locator("#askDialog").inner_text())
        page.locator("#askDialog button", has_text="Turn it on").click()
        page.locator("#detail.open").wait_for()
        self.assertIn("Night Dress", page.locator("#detail").inner_text())
        self.kept("adult", True)
        self.assertEqual(self.errors, [])

    def test_find_a_setting(self):
        page = self.open()
        self.open_settings(page)
        page.fill("#setFind", "apprise")
        self.assertTrue(page.locator("#card-notify").is_visible())
        self.assertTrue(page.locator("#card-folders").is_hidden())
        self.assertTrue(page.locator('[data-jump="card-folders"]').is_hidden(), "only the parts it's in are listed")
        page.fill("#setFind", "SYNC FOLDER")   # (any case)
        self.assertTrue(page.locator("#part-sync").is_visible())
        self.assertTrue(page.locator("#part-folders").is_hidden(), "only its row in the card")
        page.fill("#setFind", "products for adults")
        self.assertTrue(page.locator('[data-feature-switch="adult"]').is_visible(), "a switch, by its name")
        self.assertTrue(page.locator('[data-feature-switch="local"]').is_hidden())
        page.fill("#setFind", "zzzz nothing")
        self.assertTrue(page.locator(".set-none").is_visible())
        page.fill("#setFind", "")
        self.assertEqual(page.locator(".set-card:visible").count(), 8, "every card again")
        page.fill("#setFind", "minimizes hoard")   # (Closing Hoard is only in Hoard's own window: hidden here)
        self.assertTrue(page.locator(".set-none").is_visible(), "what's hidden isn't found")
        page.fill("#setFind", "hoard itself")   # (its card, by its title: every row of it, but the one hidden)
        self.assertTrue(page.locator("#part-updates").is_visible())
        self.assertEqual(page.locator("#card-hoard .set-row:visible").count(), 3, "no empty row for Closing Hoard")
        page.fill("#setFind", "apprise")
        self.close_settings(page)
        names = [p["name"] for p in page.evaluate("settingsPlaces().map(p => ({name: p.name}))")]
        self.assertIn("Backup", names, "the bar's settings: search finds each setting by its name, with Find's words left")
        self.assertIn("Local", names, "and a switch by its own name")
        self.open_settings(page)
        self.assertEqual(page.input_value("#setFind"), "", "Find starts empty again")
        self.assertEqual(page.locator(".set-card:visible").count(), 8)
        self.assertEqual(self.errors, [])

    def test_a_sets_placeholder_stays_with_local_off(self):
        page = self.open()
        self.flip(page, "local", False)
        got = page.evaluate("""() => featureSets({sets: [{kind: 'set', items: [{local: true, placeholder: true, name: 'Hair'},
                                                                                 {local: true, name: 'My Textures'}]}]})""")
        self.assertEqual([i["name"] for i in got["sets"][0]["items"]], ["Hair"], "a placeholder isn't a Local product")
        page.goto(self.srv.entry_url().split("/#")[0] + "/downloads#store=Local")
        page.locator("#grid .slot", has_text="Rusk").wait_for()   # (Everything, not an empty Local)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
