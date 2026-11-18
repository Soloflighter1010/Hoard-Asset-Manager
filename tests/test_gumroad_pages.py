"""Gumroad products link to their own pages, not their creators': Gumroad's library cards name only the creator, so
each purchase's download page (which says its product's permalink) is read once, signed in, and what it says is kept.
Every page here is made up."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from html import escape
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.isolation import IsolatedTestCase

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from hoard import config, library  # noqa: E402

TOKEN = "0123456789abcdef0123456789abcdef"


def page(component: str, props: dict) -> str:
    """A page as Gumroad serves it: its data in the app div's data-page attribute."""
    return f'<html><body><div id="app" data-page="{escape(json.dumps({"component": component, "props": props}))}"></div></body></html>'


def card(n: int, creator: str | None = "examplecreator") -> dict:
    """A library card as Gumroad's library page gives it: no link to the product's own page."""
    return {"product": {"name": f"Fluff {n}", "creator": {"name": creator or "Shop",
                                                           "profile_url": f"https://{creator}.gumroad.com" if creator else None},
                        "thumbnail_url": None, "native_type": "digital"},
            "purchase": {"id": f"p{n}==", "is_archived": False, "variants": "",
                         "download_url": f"https://app.gumroad.com/d/{TOKEN[:-2]}{n:02d}"}}


def download_page(permalink: str, long_url: str) -> str:
    """A purchase's download page: its purchase says its product's permalink and address."""
    return page("UrlRedirects/DownloadPage", {"purchase": {"product_permalink": permalink, "product_long_url": long_url,
                                                          "product_name": "Fluff"}})


class _Gumroad:
    """Hoard's signed-in browser, as Gumroad answers it: the library page, and each purchase's download page."""

    def __init__(self, cards, pages):
        self.cards, self.pages, self.asked = cards, pages, []

    def get(self, url, params=None, timeout=None):
        self.asked.append(url)
        if url == library.GR_LIBRARY:
            body, at = page("Library/Index", {"results": self.cards, "pagination": {"pages": 1}}), url
        elif url in self.pages:
            got = self.pages[url]
            if isinstance(got, Exception):
                raise got
            body, at = got
        else:
            body, at = "not found", url
        return SimpleNamespace(url=at, ok=body != "not found", status=200, text=lambda: body)

    @property
    def ctx(self):
        return SimpleNamespace(request=self)


class ProductPages(IsolatedTestCase):

    def setUp(self):
        self.cfg = {**config.load_config(), "request_delay": 0}
        p = mock.patch.object(library, "pause", lambda s: None)
        p.start()
        self.addCleanup(p.stop)

    def read(self, store, **cfg):
        return library.fetch_gumroad(store.ctx, {**self.cfg, **cfg}, lambda m: None)

    def test_each_product_links_to_its_own_page(self):
        cards = [card(1), card(2, creator=None)]
        store = _Gumroad(cards, {
            cards[0]["purchase"]["download_url"]: (download_page("fluffone", "https://examplecreator.gumroad.com/l/fluffone"), "x"),
            # a creator on a domain of their own: Gumroad's own address for the product
            cards[1]["purchase"]["download_url"]: (download_page("flufftwo", "https://shop.example.com/l/flufftwo"), "x")})
        items = self.read(store)
        self.assertEqual([i["page"] for i in items], ["https://examplecreator.gumroad.com/l/fluffone",
                                                      "https://gumroad.com/l/flufftwo"])
        self.assertEqual(items[0]["creator_url"], "https://examplecreator.gumroad.com", "its creator's page stays its creator's")

    def test_a_page_found_before_isnt_read_again(self):
        cards = [card(1), card(2)]
        store = _Gumroad(cards, {c["purchase"]["download_url"]: (download_page(f"f{n}", f"https://examplecreator.gumroad.com/l/f{n}"), "x")
                                 for n, c in enumerate(cards, 1)})
        items = self.read(store, _known_pages={"gumroad:p1==": "https://examplecreator.gumroad.com/l/kept"})
        self.assertEqual(items[0]["page"], "https://examplecreator.gumroad.com/l/kept")
        self.assertNotIn(cards[0]["purchase"]["download_url"], store.asked)
        self.assertIn(cards[1]["purchase"]["download_url"], store.asked)

    def test_at_most_so_many_in_one_refresh(self):
        cards = [card(n) for n in range(1, 6)]
        store = _Gumroad(cards, {c["purchase"]["download_url"]: (download_page(f"f{n}", ""), "x") for n, c in enumerate(cards, 1)})
        with mock.patch.object(library, "GR_PAGE_VISITS", 2):
            items = self.read(store)
        self.assertEqual(sum(1 for i in items if i["page"]), 2)

    def test_one_that_cant_be_read_keeps_its_creators_page_and_its_link_stays_out_of_the_log(self):
        cards = [card(1), card(2)]
        store = _Gumroad(cards, {cards[0]["purchase"]["download_url"]: RuntimeError(f"failed {cards[0]['purchase']['download_url']}"),
                                 cards[1]["purchase"]["download_url"]: (download_page("f2", "https://examplecreator.gumroad.com/l/f2"), "x")})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            items = self.read(store)
        self.assertEqual([i["page"] for i in items], [None, "https://examplecreator.gumroad.com/l/f2"])
        self.assertNotIn("/d/", out.getvalue())
        from hoard.sets import public_page
        self.assertEqual(public_page("gumroad", items[0]["page"], items[0]["url"], items[0]["creator_url"]),
                         "https://examplecreator.gumroad.com", "until a later refresh finds it")

    def test_signed_out_on_the_way_stops_asking(self):
        cards = [card(1), card(2)]
        store = _Gumroad(cards, {c["purchase"]["download_url"]: ("", "https://app.gumroad.com/login") for c in cards})
        items = self.read(store)
        self.assertEqual([i["page"] for i in items], [None, None])
        self.assertEqual(store.asked.count(cards[1]["purchase"]["download_url"]), 0)

    def test_a_page_that_says_no_permalink(self):
        self.assertIsNone(library.gumroad_product_page({"props": {"purchase": {}}}, "https://x.gumroad.com"))
        self.assertIsNone(library.gumroad_product_page(None, None))
        self.assertIsNone(library.gumroad_product_page({"props": {"purchase": {"product_permalink": "../../evil"}}}, None))
