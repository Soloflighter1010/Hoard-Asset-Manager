import json
import tempfile
import unittest
from pathlib import Path
from hoard import config, server

class OutlinedCards(unittest.TestCase):
    def test_accessibility_preference_persists_and_is_served_on_both_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            cfg = config.load_config(path)
            change = server.apply_settings(cfg, {"display": {"outlined_cards": True}})
            config.deep_merge(cfg, change)
            config.save_config(cfg, path)
            saved = config.load_config(path)
        self.assertTrue(server.display_settings(saved)["outlined_cards"], "outlined_cards preference was lost")
        for page in server.PAGES.values():
            html = server.page_source(page, saved).decode("utf-8")
            self.assertIn('data-outlined-cards="true"', html)
            self.assertIn("setOutlinedCards", html)

if __name__ == "__main__":
    unittest.main()
