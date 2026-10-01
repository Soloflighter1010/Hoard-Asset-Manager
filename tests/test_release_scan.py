"""The release's VirusTotal gate (scripts/scan_release_virustotal.py, the virustotal job in release.yml), against a
stand-in VirusTotal: files it knows are only looked up, new ones are uploaded and waited for, the public API's rate
is kept, a flagged file keeps the release a draft unless a person chose to publish anyway, and the key stays out
of everything but the scan."""
from __future__ import annotations

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import scan_release_virustotal as vt  # noqa: E402

KEY = "test-key-not-real"


class FakeVirusTotal:
    """Answers as VirusTotal's API v3 does, and records every request and wait."""

    def __init__(self, known=None, verdicts=None, polls_before_done=1):
        self.known = dict(known or {})          # sha256 -> stats VirusTotal already has
        self.verdicts = dict(verdicts or {})    # file name -> stats a new scan finds
        self.polls_before_done = polls_before_done
        self.requests, self.sleeps, self.now = [], [], 1000.0
        self.analyses = {}

    # time, as the scanner sees it
    def clock(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s

    def opener(self, req, timeout=None):
        self.requests.append((req.get_method(), req.full_url, dict(req.header_items())))
        self.now += 0.5
        url = req.full_url
        if url.startswith(vt.BASE + "/files/") and req.get_method() == "GET" and not url.endswith("upload_url"):
            digest = url.rsplit("/", 1)[1]
            if digest not in self.known:
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b'{"error":{"code":"NotFoundError"}}'))
            return self.answer({"data": {"attributes": {"last_analysis_date": 1, "last_analysis_stats": self.known[digest]}}})
        if url.endswith("/files/upload_url"):
            return self.answer({"data": "https://bigfiles.virustotal.test/upload"})
        if req.get_method() == "POST":
            name = re.search(rb'filename="([^"]+)"', req.data).group(1).decode()
            aid = f"a{len(self.analyses)}"
            self.analyses[aid] = [name, 0]
            return self.answer({"data": {"type": "analysis", "id": aid}})
        if "/analyses/" in url:
            aid = url.rsplit("/", 1)[1]
            self.analyses[aid][1] += 1
            name, polls = self.analyses[aid]
            done = polls > self.polls_before_done
            stats = self.verdicts.get(name, {"malicious": 0, "suspicious": 0, "undetected": 70, "harmless": 0})
            return self.answer({"data": {"attributes": {"status": "completed" if done else "queued", "stats": stats}}})
        raise AssertionError(f"unexpected request {req.get_method()} {url}")

    @staticmethod
    def answer(obj):
        return io.BytesIO(json.dumps(obj).encode())


def release_folder(files: dict[str, bytes]) -> Path:
    d = Path(tempfile.mkdtemp(prefix="hoard-release-"))
    for name, data in files.items():
        (d / name).write_bytes(data)
    return d


def run(fake: FakeVirusTotal, folder: Path, allow: bool = False) -> int:
    client = vt.VirusTotal(KEY, opener=fake.opener, sleep=fake.sleep, clock=fake.clock)
    return vt.main(folder, client, env={"VT_ALLOW_DETECTIONS": "true" if allow else "false"})


class Scanning(unittest.TestCase):

    def test_new_files_are_uploaded_and_waited_for(self):
        folder = release_folder({"Hoard-Setup-2.11.0.exe": b"MZ installer", "Hoard-2.11.0.zip": b"PK zip",
                                 "SHA256SUMS.txt": b"sums", "RELEASE_NOTES.md": b"notes"})
        fake = FakeVirusTotal(polls_before_done=2)
        self.assertEqual(run(fake, folder), 0)
        uploads = [r for r in fake.requests if r[0] == "POST"]
        self.assertEqual(len(uploads), 2, "only what people download: not the checksums or notes")
        self.assertTrue(all(r[2].get("X-apikey") == KEY for r in fake.requests), "the key goes in its header")
        self.assertTrue(all(KEY not in r[1] for r in fake.requests), "never in an address")
        text = (folder / "VT_REPORT.md").read_text("utf-8")
        self.assertIn("## VirusTotal scan results", text)
        self.assertIn("[Hoard-Setup-2.11.0.exe](https://www.virustotal.com/gui/file/", text)
        self.assertIn("0 malicious, 0 suspicious (of 70 engines)", text)

    def test_a_file_virustotal_knows_is_only_looked_up(self):
        import hashlib
        data = b"PK same zip as last time"
        folder = release_folder({"Hoard-2.11.0.zip": data})
        known = {hashlib.sha256(data).hexdigest(): {"malicious": 0, "suspicious": 0, "undetected": 66}}
        fake = FakeVirusTotal(known=known)
        self.assertEqual(run(fake, folder), 0)
        self.assertEqual([r[0] for r in fake.requests], ["GET"], "one lookup, no upload: the daily quota is kept")

    def test_the_public_apis_rate_is_kept(self):
        """At most 4 requests a minute: each at least SPACING seconds after the one before."""
        fake, times = FakeVirusTotal(), []
        answer = fake.opener

        def timed(req, timeout=None):
            times.append(fake.now)
            return answer(req, timeout)
        fake.opener = timed
        run(fake, release_folder({f"Hoard-{n}.zip": bytes([n]) for n in range(3)}))
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertGreater(len(gaps), 6)
        self.assertGreaterEqual(min(gaps), vt.SPACING - 0.01, gaps)

    def test_big_files_go_to_the_upload_address(self):
        folder = release_folder({"Hoard-2.11.0-linux-x86_64.flatpak": b"x" * (vt.DIRECT_UPLOAD + 1)})
        fake = FakeVirusTotal()
        self.assertEqual(run(fake, folder), 0)
        posts = [r[1] for r in fake.requests if r[0] == "POST"]
        self.assertEqual(posts, ["https://bigfiles.virustotal.test/upload"])

    def test_a_scan_that_never_finishes(self):
        folder = release_folder({"Hoard-2.11.0.zip": b"PK"})
        fake = FakeVirusTotal(polls_before_done=10 ** 6)
        with contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "hadn't finished scanning Hoard-2.11.0.zip after 40 minutes.*again later"):
            run(fake, folder)
        self.assertLess(fake.now - 1000, 42 * 60, "it gives up after VT_WAIT_MINUTES, not hours later")

    def test_the_scans_are_waited_for_together(self):
        """Each file used to be waited for before the next was sent, silently: with a few new files that ran for most
        of an hour saying nothing, and looked stuck. Now every file is sent first, then all are waited for at once,
        and it says how they're getting on."""
        folder = release_folder({f"Hoard-{n}.zip": bytes([n]) for n in range(3)})
        fake = FakeVirusTotal(polls_before_done=3)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(run(fake, folder), 0)
        kinds = ["upload" if r[0] == "POST" else "check" if "/analyses/" in r[1] else "lookup" for r in fake.requests]
        self.assertEqual(kinds[:6], ["lookup", "upload"] * 3, "every file is sent before any scan is waited for")
        self.assertEqual(set(kinds[6:]), {"check"})
        self.assertEqual(kinds.count("check"), 3 * 4, "each scan checked once a round, and no more once it's done")
        text = out.getvalue()
        self.assertIn("Hoard-0.zip: sending it to be scanned", text)
        self.assertIn("Waiting for VirusTotal (", text)
        self.assertIn("Hoard-2.zip queued", text)
        self.assertIn("Hoard-1.zip: scanned", text)

    def test_virustotal_errors_are_said_plainly(self):
        folder = release_folder({"Hoard-2.11.0.zip": b"PK"})
        fake = FakeVirusTotal()

        def refuses(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error":{"code":"WrongCredentialsError"}}'))
        fake.opener = refuses
        with self.assertRaisesRegex(RuntimeError, "HTTP 401"):
            run(fake, folder)

    def test_nothing_to_scan_is_never_published(self):
        with self.assertRaisesRegex(RuntimeError, "No release files"):
            run(FakeVirusTotal(), release_folder({"SHA256SUMS.txt": b"sums"}))

    def test_no_key(self):
        with self.assertRaisesRegex(RuntimeError, "VT_API_KEY isn't set"):
            vt.main(release_folder({"a.zip": b"PK"}), None, env={})


class TheGate(unittest.TestCase):

    def flagged(self):
        folder = release_folder({"Hoard-Setup-2.11.0.exe": b"MZ", "Hoard-2.11.0.zip": b"PK"})
        return folder, FakeVirusTotal(verdicts={"Hoard-Setup-2.11.0.exe": {"malicious": 1, "suspicious": 2, "undetected": 67}})

    def test_a_flagged_file_keeps_the_release_a_draft(self):
        folder, fake = self.flagged()
        self.assertEqual(run(fake, folder), 1)
        self.assertIn("Hoard-Setup-2.11.0.exe](https://www.virustotal.com/gui/file/", (folder / "VT_REPORT.md").read_text("utf-8"))
        self.assertIn("1 malicious, 2 suspicious", (folder / "VT_REPORT.md").read_text("utf-8"),
                      "the report is still written, for the person who checks it")

    def test_flagged_files_are_named_for_the_false_positive_report(self):
        folder, fake = self.flagged()
        run(fake, folder)
        self.assertEqual((folder / "VT_FLAGGED.txt").read_text("utf-8"), "Hoard-Setup-2.11.0.exe\n")
        clean = release_folder({"Hoard-2.11.0.zip": b"PK"})
        run(FakeVirusTotal(), clean)
        self.assertFalse((clean / "VT_FLAGGED.txt").exists(), "nothing flagged, nothing kept")

    def test_publishing_anyway_is_a_persons_choice(self):
        folder, fake = self.flagged()
        self.assertEqual(run(fake, folder, allow=True), 0)
        self.assertIn("checked by hand and published anyway", (folder / "VT_REPORT.md").read_text("utf-8"))

    def test_results_replace_an_earlier_runs_in_the_notes(self):
        first = vt.with_results("## What's new\n\n- Things.\n", "## VirusTotal scan results\n\n- old\n")
        again = vt.with_results(first, "## VirusTotal scan results\n\n- new\n")
        self.assertEqual(again, "## What's new\n\n- Things.\n\n## VirusTotal scan results\n\n- new\n")


class TheWorkflow(unittest.TestCase):

    def setUp(self):
        self.text = (REPO / ".github" / "workflows" / "release.yml").read_text("utf-8")
        self.jobs = {m.group(1): m.group(2) for m in re.finditer(r"^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)", self.text, re.M | re.S)}

    def test_the_scan_has_a_time_limit(self):
        limit = int(re.search(r"timeout-minutes: (\d+)", self.jobs["virustotal"]).group(1))
        self.assertGreater(limit, vt.WAIT_MINUTES, "room to wait for the scans, and to report on them")
        self.assertLessEqual(limit, 90)

    def test_publishing_waits_for_the_scan(self):
        self.assertIn("needs: [release, windows, macos, flatpak-release]", self.jobs["virustotal"], "every file is attached first")
        self.assertIn("virustotal", re.search(r"needs: \[([^\]]*)\]", self.jobs["publish"]).group(1))

    def test_only_the_scan_sees_the_key(self):
        self.assertEqual(self.text.count("secrets.VT_API_KEY"), 1)
        step = self.jobs["virustotal"].split("- name: Scan them with VirusTotal", 1)[1].split("- name:", 1)[0]
        self.assertIn("VT_API_KEY: ${{ secrets.VT_API_KEY }}", step)
        self.assertNotIn("VT_API_KEY", self.jobs["virustotal"].split("steps:", 1)[0], "not the whole job's")

    def test_flagged_files_are_kept_where_they_can_be_downloaded(self):
        """Defender stops a browser downloading a file it flags, so the release's own copy can't be sent to Microsoft
        as a false positive. The run keeps flagged files in a zip encrypted with "infected", as antivirus makers ask."""
        job = self.jobs["virustotal"]
        step = job.split("- name: Keep any flagged files, for a false-positive report", 1)[1].split("- name:", 1)[0]
        self.assertIn("always() && hashFiles('dist/VT_FLAGGED.txt') != ''", step, "kept even when the scan step fails")
        self.assertIn('zip -j -P infected "../flagged-$TAG.zip" "${flagged[@]}"', step)
        self.assertRegex(step, r"uses: actions/upload-artifact@[0-9a-f]{40} # v")
        self.assertNotIn("VT_API_KEY", step)
        self.assertLess(job.index("Scan them with VirusTotal"), job.index("Keep any flagged files"))

    def test_publish_anyway_is_only_by_hand(self):
        self.assertRegex(self.text, r"allow_detections:\n\s+description: .+\n\s+type: boolean\n\s+default: false")
        self.assertIn("VT_ALLOW_DETECTIONS: ${{ inputs.allow_detections && 'true' || 'false' }}", self.text)

    def test_the_results_reach_the_notes_even_when_flagged(self):
        step = self.jobs["virustotal"].split("- name: Add the results to the release notes", 1)[1]
        self.assertIn("always()", step)
        self.assertIn("--notes dist/NOTES.md dist/VT_REPORT.md", step)


if __name__ == "__main__":
    unittest.main()
