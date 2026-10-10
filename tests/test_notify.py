"""A notification from the system when the routine check finds something (hoard/notify.py)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))

from hoard import notify


class Notify(unittest.TestCase):
    def test_what_it_says(self):
        self.assertEqual(notify.found_text({"new": 1, "updates": 0}),
                         "Found 1 new product. Open Hoard to choose what to download.")
        self.assertEqual(notify.found_text({"new": 1200, "updates": 3}),
                         "Found 1,200 new products and 3 updates. Open Hoard to choose what to download.")
        self.assertEqual(notify.found_text({"new": 0, "updates": 1}), "Found 1 update. Open Hoard to choose what to download.")

    def test_in_hoards_language(self):
        self.assertEqual(notify.found_text({"new": 2, "updates": 1}, "ja"),
                         "新しい商品2件とアップデート1件が見つかりました。Hoardを開いて、ダウンロードするものを選んでください。")
        self.assertEqual(notify.found_text({"new": 0, "updates": 3}, "ko"),
                         "업데이트 3개를 찾았어요. Hoard를 열어 다운로드할 것을 고르세요.")
        self.assertEqual(notify.found_text({"new": 1, "updates": 0}, "fr"), "Found 1 new product. Open Hoard to choose what to download.")

    def sent(self, platform, which=lambda name: "/usr/bin/" + name):
        """The command each system is sent, run straight away rather than in the background."""
        runs = []
        with mock.patch.object(notify.sys, "platform", platform), mock.patch.object(notify.shutil, "which", which), \
                mock.patch.object(notify.subprocess, "run", lambda args, **k: runs.append((args, k))), \
                mock.patch.object(notify.threading, "Thread", lambda target, args, **k: mock.Mock(start=lambda: target(*args))):
            shown = notify.show("Found 'it'; $(rm -rf ~)", "Hoard")
        return shown, runs

    def test_the_text_is_an_argument_never_a_script(self):
        shown, [(args, k)] = self.sent("darwin")
        self.assertTrue(shown)
        self.assertEqual(args[0], "osascript")
        self.assertEqual(args[-2:], ["Hoard", "Found 'it'; $(rm -rf ~)"], "as argv, not inside the AppleScript")
        self.assertNotIn("shell", k)
        shown, [(args, k)] = self.sent("linux")
        self.assertEqual(args[0], "notify-send")
        self.assertEqual(args[-3:], ["--", "Hoard", "Found 'it'; $(rm -rf ~)"])

    def test_linux_without_notify_send(self):
        shown, [(args, k)] = self.sent("linux", lambda name: "/usr/bin/gdbus" if name == "gdbus" else None)
        self.assertEqual(args[:2], ["gdbus", "call"])
        self.assertIn("'Found \\'it\\'; $(rm -rf ~)'", args, "quoted as a GVariant string")
        self.assertEqual(self.sent("linux", lambda name: None), (False, []), "no way to show one: none shown")

    def test_a_failure_is_only_noted(self):
        with mock.patch.object(notify.sys, "platform", "darwin"), \
                mock.patch.object(notify.subprocess, "run", side_effect=OSError("no osascript")), \
                mock.patch.object(notify.threading, "Thread", lambda target, args, **k: mock.Mock(start=lambda: target(*args))):
            self.assertTrue(notify.show("x"))


if __name__ == "__main__":
    unittest.main()
