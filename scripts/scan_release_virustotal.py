"""Scan a release's files with VirusTotal before the release is published (.github/workflows/release.yml, and
unity-release.yml for Hoard for Unity).

Every file people download from the release (the zips, the Windows installer, the Mac packages, the Flatpak, and
Hoard for Unity's .zip and .unitypackage) is
looked up on VirusTotal by its SHA-256, and uploaded when VirusTotal hasn't seen it. Once every new file is sent,
their scans are waited for together (VirusTotal runs them side by side), up to VT_WAIT_MINUTES (40), saying how
they're getting on as it goes. A scan still unfinished then fails the job; run it again later and the files already
scanned are only looked up.
The results go in dist/VT_REPORT.md (added to the release notes) and the job summary. When any engine flags a
file as malicious or suspicious, this fails, so the release stays a draft for a person to look at; a run with
VT_ALLOW_DETECTIONS=true (the workflow's "publish anyway" choice, after checking the report) reports the same
results but lets it through.

Uses VirusTotal's public API: 4 requests a minute (so one every 16 seconds) and 500 a day, enough for a release.
Needs VT_API_KEY (a repository secret), TAG, and GITHUB_REPOSITORY. Standard library only.

    python3 scripts/scan_release_virustotal.py          (with the release's files in dist/)
    python3 scripts/scan_release_virustotal.py --notes NOTES.md dist/VT_REPORT.md   (put the results in the notes)
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = "https://www.virustotal.com/api/v3"
SCANNED = (".zip", ".exe", ".pkg", ".flatpak", ".unitypackage")   # what people download; not checksums or package.json
SPACING = 16                                     # seconds between requests: the public API allows 4 a minute
MAX_UPLOAD = 650 * 1024 * 1024                   # VirusTotal's limit
DIRECT_UPLOAD = 32 * 1024 * 1024                 # bigger files go to an upload address VirusTotal gives out
WAIT_MINUTES = 40                                # how long the scans are waited for, all together
POLL_WAIT = 20                                   # seconds between rounds of checking on them (plus SPACING each)


class VirusTotal:
    """VirusTotal's API, one request at a time, never faster than the public API allows."""

    def __init__(self, key: str, opener=urllib.request.urlopen, sleep=time.sleep, clock=time.monotonic):
        self.key, self.opener, self.sleep, self.clock = key, opener, sleep, clock
        self.last = None

    def request(self, method: str, url: str, data: bytes | None = None, content_type: str | None = None,
                missing_ok: bool = False) -> dict | None:
        if self.last is not None:
            wait = SPACING - (self.clock() - self.last)
            if wait > 0:
                self.sleep(wait)
        headers = {"x-apikey": self.key, "Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        self.last = self.clock()
        try:
            with self.opener(req, timeout=300) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            detail = exc.read(300).decode("utf-8", "replace")
            raise RuntimeError(f"VirusTotal answered HTTP {exc.code} for {method} {url.split('?')[0]}: {detail}") from None

    def known(self, digest: str) -> dict | None:
        """VirusTotal's last results for a file it has seen (its stats), or None."""
        got = self.request("GET", f"{BASE}/files/{digest}", missing_ok=True)
        if not got:
            return None
        attrs = got.get("data", {}).get("attributes", {})
        stats = attrs.get("last_analysis_stats")
        return stats if stats and attrs.get("last_analysis_date") else None

    def upload(self, path: Path) -> str:
        """Send a file to be scanned. Returns the analysis id."""
        size = path.stat().st_size
        if size > MAX_UPLOAD:
            raise RuntimeError(f"{path.name} is bigger than VirusTotal's {MAX_UPLOAD // 1024 // 1024} MB limit")
        url = self.request("GET", f"{BASE}/files/upload_url")["data"] if size > DIRECT_UPLOAD else f"{BASE}/files"
        boundary = uuid.uuid4().hex
        head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n").encode()
        body = head + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        return self.request("POST", url, body, f"multipart/form-data; boundary={boundary}")["data"]["id"]

    def digest(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()

    def wait_all(self, pending: dict[str, str], minutes: float = WAIT_MINUTES) -> dict[str, dict]:
        """Each file's finished scan stats, for {file name: analysis id}, checked on in rounds until all are done."""
        done: dict[str, dict] = {}
        start = self.clock()
        while True:
            states = {}
            for name, analysis_id in pending.items():
                if name in done:
                    continue
                attrs = self.request("GET", f"{BASE}/analyses/{analysis_id}")["data"]["attributes"]
                if attrs.get("status") == "completed":
                    done[name] = attrs.get("stats", {})
                    say(f"{name}: scanned")
                else:
                    states[name] = attrs.get("status") or "waiting"
            if not states:
                return done
            waited = (self.clock() - start) / 60
            if waited >= minutes:
                raise RuntimeError(
                    f"VirusTotal hadn't finished scanning {', '.join(sorted(states))} after {waited:.0f} minutes. The "
                    "files it has keep being scanned there: run this job again later (Re-run failed jobs) and they're "
                    "only looked up, not sent again.")
            say(f"Waiting for VirusTotal ({waited:.0f} min so far): "
                + ", ".join(f"{n} {st}" for n, st in sorted(states.items())))
            self.sleep(POLL_WAIT)


def say(text: str) -> None:
    print(text, flush=True)


def files_to_scan(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SCANNED)


def report(results: list[tuple[str, str, dict, bool]], allowed: bool) -> tuple[str, bool]:
    """The release notes' section, and whether anything was flagged."""
    lines = [HEADING, "",
             "Each file was checked by VirusTotal before this release was published. Results are a snapshot, "
             "not a guarantee: open a file's report for the details.", ""]
    flagged = False
    for name, digest, stats, _known in results:
        bad, odd = int(stats.get("malicious", 0)), int(stats.get("suspicious", 0))
        engines = sum(int(v) for k, v in stats.items() if k in ("malicious", "suspicious", "undetected", "harmless"))
        flagged |= bool(bad or odd)
        lines.append(f"- [{name}](https://www.virustotal.com/gui/file/{digest}): {bad} malicious, {odd} suspicious"
                     + (f" (of {engines} engines)" if engines else ""))
    if flagged and allowed:
        lines += ["", "Some engines flagged a file. It was checked by hand and published anyway: see each report."]
    return "\n".join(lines) + "\n", flagged


HEADING = "## VirusTotal scan results"


def with_results(notes: str, results: str) -> str:
    """Release notes with the scan results at the end, in place of any from an earlier run."""
    kept = notes.split("\n" + HEADING, 1)[0] if not notes.startswith(HEADING) else ""
    return kept.rstrip() + "\n\n" + results.strip() + "\n" if kept.strip() else results.strip() + "\n"


def main(folder: Path = Path("dist"), vt: VirusTotal | None = None, env=os.environ) -> int:
    key = env.get("VT_API_KEY", "")
    if not key and vt is None:
        raise RuntimeError("VT_API_KEY isn't set: add it as a repository secret (Settings > Secrets and variables > Actions)")
    vt = vt or VirusTotal(key)
    allowed = env.get("VT_ALLOW_DETECTIONS", "").lower() == "true"
    files = files_to_scan(folder)
    if not files:
        raise RuntimeError(f"No release files in {folder}/ to scan, so the release isn't published")
    digests, stats, pending = {}, {}, {}
    for path in files:   # look each one up, and send the ones VirusTotal hasn't seen
        digests[path.name] = vt.digest(path)
        say(f"{path.name}: looking it up")
        known = vt.known(digests[path.name])
        if known is not None:
            stats[path.name] = known
            continue
        say(f"{path.name}: sending it to be scanned ({path.stat().st_size / 1024 / 1024:.1f} MB)")
        pending[path.name] = vt.upload(path)
    if pending:          # then wait for all their scans at once
        stats.update(vt.wait_all(pending, float(env.get("VT_WAIT_MINUTES") or WAIT_MINUTES)))
    results = []
    for path in files:
        name, st = path.name, stats[path.name]
        say(f"{name}: {st.get('malicious', 0)} malicious, {st.get('suspicious', 0)} suspicious"
            + ("" if name in pending else " (already known to VirusTotal)"))
        results.append((name, digests[name], st, name not in pending))
    text, flagged = report(results, allowed)
    (folder / "VT_REPORT.md").write_text(text, encoding="utf-8")
    # The flagged files, by name, for the workflow to hand over for a false-positive report (see release.yml): a
    # browser on Windows won't download a file Defender flags, so the draft's own copy can't be sent to Microsoft.
    names = [n for n, _d, st, _k in results if int(st.get("malicious", 0)) or int(st.get("suspicious", 0))]
    if names:
        (folder / "VT_FLAGGED.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(text)
    if flagged and not allowed:
        print("::error::VirusTotal flagged a release file, so the release stays a draft. Check each report; if they're "
              "false positives, run the workflow again for this tag with \"Publish even if VirusTotal flags a "
              "file\" ticked (Release for the app, Build Release for Hoard for Unity).", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1:2] == ["--notes"]:
            notes_file, results_file = Path(sys.argv[2]), Path(sys.argv[3])
            notes_file.write_text(with_results(notes_file.read_text("utf-8"), results_file.read_text("utf-8")), "utf-8")
            sys.exit(0)
        sys.exit(main())
    except (RuntimeError, OSError) as exc:
        print(f"::error::{exc}", flush=True)
        sys.exit(1)
