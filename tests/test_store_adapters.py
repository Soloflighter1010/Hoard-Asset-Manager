"""The store contract, account-free health reports, and each store's saved page recordings."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.isolation import IsolatedTestCase
from tests.test_packages import BROWSER
from hoard import config, downloader, library, storage
from hoard.common import Cancelled, NotLoggedIn
from hoard.paths import data_dir
from hoard.stores import adapters, health
from hoard.stores.base import UnsupportedOperation

RECORDINGS = Path(__file__).parent / "data" / "stores"


class Contract(IsolatedTestCase):
    def setUp(self):
        storage.remove(data_dir() / "store-health.json", missing_ok=True)

    def test_every_store_declares_operations_and_has_recordings(self):
        self.assertEqual(set(adapters()), set(library.STORES))
        for key, adapter in adapters().items():
            self.assertTrue((RECORDINGS / key / "library.html").is_file(), key)
            self.assertTrue((RECORDINGS / key / "expected.json").is_file(), key)
            self.assertEqual(adapter.downloads, key in library.DOWNLOADABLE)
            if adapter.wishlists:
                self.assertTrue(list((RECORDINGS / key).glob("wishlist*.html")), key)
        self.assertEqual(adapters()["jinxxy"].limits({})["requests_per_minute"], 120)
        self.assertFalse(adapters()["payhip"].capabilities["download_file"])
        with self.assertRaises(UnsupportedOperation):
            adapters()["payhip"].list_files({}, None, SimpleNamespace(), downloader.Report())

    def test_modes_preserve_selected_files_and_never_download_during_a_check(self):
        args = SimpleNamespace(keys={"booth:rusk"}, files={"booth:rusk": {"chosen": {"a.zip"}}}, dry_run=False)
        seen = []
        with mock.patch.object(downloader, "sync_booth", lambda cfg, root, options, report: seen.append(options)):
            for method in ("list_files", "check_updates", "download_file"):
                getattr(adapters()["booth"], method)({}, None, args, downloader.Report())
        self.assertEqual([(o.dry_run, o.listing) for o in seen], [(True, True), (True, False), (False, False)])
        self.assertTrue(all(o.files is args.files and o.keys is args.keys for o in seen))
        self.assertFalse(hasattr(args, "listing"), "the caller's selection is not changed")

    def test_health_retains_last_success_but_never_exception_details(self):
        adapter = adapters()["booth"]
        with mock.patch.object(library, "fetch_booth", return_value=[{"id": "sample"}]):
            adapter.read_library(None, {}, lambda message: None)
        success = health.snapshot()["booth"]["operations"]["library"]["last_success"]
        private = "customer@example.com https://booth.pm/private?token=SECRET"
        with mock.patch.object(library, "fetch_booth", side_effect=NotLoggedIn(private)):
            with self.assertRaises(NotLoggedIn):
                adapter.read_library(None, {}, lambda message: None)
        state = health.snapshot()["booth"]["operations"]["library"]
        self.assertEqual((state["last_success"], state["problem"]), (success, "signin"))
        self.assertIn("issues/new?", state["report_url"])
        raw = json.dumps(storage.read_document(data_dir() / "store-health.json")) + json.dumps(state)
        for secret in ("customer", "SECRET", "private?", "token="):
            self.assertNotIn(secret, raw)

    def test_stop_is_not_recorded_as_store_failure(self):
        with mock.patch.object(library, "fetch_booth", side_effect=Cancelled):
            with self.assertRaises(Cancelled):
                adapters()["booth"].read_library(None, {}, lambda message: None)
        self.assertEqual(health.snapshot()["booth"]["operations"], {})

    def test_partial_download_does_not_claim_success(self):
        def failed(cfg, root, args, report):
            report.failed.append("private filename")
        with mock.patch.object(downloader, "sync_booth", failed):
            adapters()["booth"].transfer({}, None, SimpleNamespace(dry_run=False), downloader.Report())
        state = health.snapshot()["booth"]["operations"]["download_file"]
        self.assertEqual((state["last_success"], state["problem"]), ("", "partial"))

    def test_an_empty_replacement_does_not_claim_a_successful_read(self):
        with mock.patch.object(library, "fetch_booth", return_value=[]):
            adapters()["booth"].read_library(None, {"_previous_count": 3}, lambda message: None)
        state = health.snapshot()["booth"]["operations"]["library"]
        self.assertEqual((state["last_success"], state["problem"]), ("", "empty"))


@unittest.skipUnless(BROWSER, "needs Playwright's Chromium")
class Recordings(IsolatedTestCase):
    def test_each_library_recording_still_reads(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for key, adapter in adapters().items():
                    with self.subTest(store=key):
                        folder = RECORDINGS / key
                        expected = json.loads((folder / "expected.json").read_text())
                        html = (folder / "library.html").read_text()
                        cfg = copy.deepcopy(config.DEFAULT_CONFIG)
                        if key == "gumroad":
                            # Gumroad returns this HTML to its request API; no live account is needed.
                            response = SimpleNamespace(url=expected["url"], ok=True, text=lambda: html)
                            ctx = SimpleNamespace(request=SimpleNamespace(get=lambda *a, **kw: response))
                            cfg["gumroad"]["include_archived"] = False
                            items = adapter.read_library(ctx, cfg, lambda message: None)
                        else:
                            page = library.offline_page(browser)
                            try:
                                page.route(lambda url: url == expected["url"],
                                           lambda route: route.fulfill(content_type="text/html", body=html))
                                page.goto(expected["url"])
                                items = adapter.read_saved(page, cfg, {"base": expected["url"], **expected})
                            finally:
                                page.context.close()
                        self.assertEqual([item["id"] for item in items], expected["ids"])
                        self.assertTrue(all(item["name"] and item["creator"] for item in items))
            finally:
                browser.close()
