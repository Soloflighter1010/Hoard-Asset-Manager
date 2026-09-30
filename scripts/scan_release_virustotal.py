"""Upload release binaries to VirusTotal and wait for scan results."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = "https://www.virustotal.com/api/v3"
KEY = os.environ["VT_API_KEY"]
TAG = os.environ["TAG"]
REPO = os.environ["GITHUB_REPOSITORY"]
last_request = 0.0


def request(method, url, data=None, content_type=None):
    global last_request
    delay = 16 - (time.monotonic() - last_request)
    if delay > 0:
        time.sleep(delay)
    headers = {"x-apikey": KEY}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    last_request = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"VirusTotal returned HTTP {exc.code}: {exc.read(500)!r}") from exc


def scan(path):
    size = path.stat().st_size
    if size > 650 * 1024 * 1024:
        raise RuntimeError(f"{path.name} exceeds VirusTotal's 650 MB upload limit")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if size > 32 * 1024 * 1024:
        url = request("GET", f"{BASE}/files/upload_url")["data"]
    else:
        url = f"{BASE}/files"
    boundary = uuid.uuid4().hex
    data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode())
    analysis_id = request("POST", url, data, f"multipart/form-data; boundary={boundary}")["data"]["id"]
    for _ in range(30):
        result = request("GET", f"{BASE}/analyses/{analysis_id}")["data"]["attributes"]
        if result["status"] == "completed":
            stats = result["stats"]
            return digest, stats.get("malicious", 0), stats.get("suspicious", 0)
        time.sleep(20)
    raise RuntimeError(f"Timed out waiting for VirusTotal analysis of {path.name}")


def main():
    files = sorted(p for p in Path("dist").iterdir() if p.suffix.lower() in (".zip", ".exe", ".pkg", ".flatpak"))
    if not files:
        raise RuntimeError("No release binaries downloaded; refusing to publish")
    lines = ["## VirusTotal scan results", "", "VirusTotal results are a snapshot, not a guarantee of safety.", ""]
    failed = False
    for path in files:
        digest, malicious, suspicious = scan(path)
        lines.append(f"- [{path.name}](https://www.virustotal.com/gui/file/{digest}): {malicious} malicious, {suspicious} suspicious detections")
        failed |= bool(malicious or suspicious)
    report = "\n".join(lines) + "\n"
    Path("dist/VT_REPORT.md").write_text(report, encoding="utf-8")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
        summary.write(report)
    if failed:
        raise RuntimeError("VirusTotal detections found; leaving the release as a draft for review")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyError, urllib.error.URLError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
