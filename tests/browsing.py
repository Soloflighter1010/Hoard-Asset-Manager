"""What the tests that drive Hoard's pages share (not tests themselves: unittest only collects test_*.py)."""
from __future__ import annotations


def menu(page, item: str) -> None:
    """Choose Tags, Stores, Rescan or Settings (item, as a selector) from the bar's Menu (issue #219)."""
    if not page.locator(item).is_visible():
        page.click("#menuBtn")
    page.click(item)
