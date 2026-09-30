"""Hoard for macOS (Hoard.app in a .pkg) and Linux (a Flatpak): their builds, locked dependencies, sandbox and
release workflow. The builds themselves run in .github/workflows/check.yml (app-macos, flatpak)."""
from __future__ import annotations

import json
import os
import re
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HOARD_DATA_DIR", str(Path(tempfile.mkdtemp(prefix="hoard-tests-")) / "Hoard"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import hoard  # noqa: E402

APP_ID = "io.github.soloflighter1010.Hoard"
FLATPAK = REPO / "packaging" / "flatpak"
MANIFEST = FLATPAK / f"{APP_ID}.yml"


def pins(text: str) -> dict[str, str]:
    return dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)", text, re.M))


def blocks(text: str) -> list[str]:
    return [b for b in re.split(r"\n(?=[A-Za-z0-9_.-]+==)", text) if re.match(r"[A-Za-z0-9_.-]+==", b)]


class LockedDependencies(unittest.TestCase):

    def test_the_mac_app(self):
        lock = (REPO / "requirements-mac.txt").read_text("utf-8")
        self.assertTrue(all("--hash=sha256:" in b for b in blocks(lock)))
        mac, source, windows = pins(lock), pins((REPO / "requirements.txt").read_text("utf-8")), pins((REPO / "requirements-app.txt").read_text("utf-8"))
        for name in ("pywebview", "pyinstaller", "pyobjc-core", "pyobjc-framework-webkit", "pyobjc-framework-cocoa"):
            self.assertIn(name, mac)
        self.assertNotIn("pythonnet", mac, "Windows only")
        for name, version in source.items():
            self.assertEqual(mac.get(name), version, f"{name}: the Mac app and a source install use the same version")
        for name in ("pywebview", "pyinstaller"):
            self.assertEqual(mac[name], windows[name], f"{name}: the same on Windows and the Mac")

    def test_the_flatpak(self):
        lock = (REPO / "requirements-flatpak.txt").read_text("utf-8")
        self.assertTrue(all("--hash=sha256:" in b for b in blocks(lock)))
        flatpak, source = pins(lock), pins((REPO / "requirements.txt").read_text("utf-8"))
        self.assertIn("pywebview", flatpak)
        self.assertNotIn("pyinstaller", flatpak, "the Flatpak runs Hoard's code with the runtime's Python")
        for name, version in source.items():
            self.assertEqual(flatpak.get(name), version, f"{name}: the Flatpak and a source install use the same version")

    def test_the_flatpaks_files_are_the_locked_ones(self):
        """python3-deps.json (made by scripts/flatpak_deps.py) installs the locked packages, from files whose hash
        is in the lock, on PyPI's file host: one file each, or a wheel for each Python the runtime may have."""
        import flatpak_deps
        locked = flatpak_deps.locked((REPO / "requirements-flatpak.txt").read_text("utf-8"))
        module = json.loads((FLATPAK / "python3-deps.json").read_text("utf-8"))
        norm = lambda n: re.sub(r"[-_.]+", "-", n).lower()  # noqa: E731
        by_name: dict[str, list[dict]] = {}
        for src in module["sources"]:
            self.assertEqual(src["type"], "file")
            self.assertTrue(src["url"].startswith("https://files.pythonhosted.org/"), src["url"])
            filename = src["url"].rsplit("/", 1)[1]
            by_name.setdefault(norm(re.split(r"-\d", filename, maxsplit=1)[0]), []).append(src)
        self.assertEqual(set(by_name), {norm(n) for n in locked})
        for name, (version, hashes) in locked.items():
            for src in by_name[norm(name)]:
                self.assertIn(src["sha256"], hashes, name)
                self.assertIn(version, src["url"], name)
        greenlet = [s["url"].rsplit("/", 1)[1] for s in by_name["greenlet"]]
        self.assertEqual([flatpak_deps.python_of(f) for f in greenlet], list(flatpak_deps.PYTHONS),
                         "compiled: one for each Python the runtime may have")
        self.assertIn("--no-index", module["build-commands"][0], "installed from those files only")

    def test_choosing_a_packages_file(self):
        import flatpak_deps
        rank = flatpak_deps.rank
        self.assertEqual(rank("greenlet-3.5.6-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl"), 0)
        self.assertEqual(rank("requests-2.34.2-py3-none-any.whl"), 1)
        self.assertEqual(rank("proxy_tools-0.1.0.tar.gz"), 3)
        self.assertEqual(rank("playwright-1.63.0-py3-none-manylinux1_x86_64.whl"), 0)
        for usable in ("greenlet-3.5.6-cp313-cp313-manylinux_2_28_x86_64.whl",
                       "greenlet-3.5.6-cp314-cp314-manylinux_2_28_x86_64.whl",
                       "charset_normalizer-3.5.1-cp37-abi3-manylinux_2_28_x86_64.whl"):
            self.assertEqual(rank(usable), 0, usable)
        self.assertEqual(flatpak_deps.python_of("charset_normalizer-3.5.1-cp37-abi3-manylinux_2_28_x86_64.whl"), "abi3")
        for unusable in ("greenlet-3.5.6-cp311-cp311-manylinux_2_28_x86_64.whl",
                         "greenlet-3.5.6-cp314-cp314t-manylinux_2_28_x86_64.whl",
                         "greenlet-3.5.6-cp312-cp312-manylinux_2_28_aarch64.whl",
                         "greenlet-3.5.6-cp312-cp312-musllinux_1_2_x86_64.whl",
                         "greenlet-3.5.6-cp312-cp312-win_amd64.whl",
                         "greenlet-3.5.6-cp312-cp312-macosx_11_0_universal2.whl"):
            self.assertIsNone(rank(unusable), unusable)


class TheFlatpak(unittest.TestCase):

    def setUp(self):
        self.manifest = MANIFEST.read_text("utf-8")

    def finish_args(self):
        part = self.manifest.split("finish-args:", 1)[1].split("modules:", 1)[0]
        return re.findall(r"^\s*-\s*(--\S+)", part, re.M)

    def test_the_manifest(self):
        m = self.manifest
        self.assertIn(f"app-id: {APP_ID}", m)
        self.assertIn("runtime: org.gnome.Platform", m)
        version = re.search(r"runtime-version: '(\d+)'", m).group(1)
        for workflow in ("check.yml", "release.yml"):
            text = (REPO / ".github" / "workflows" / workflow).read_text("utf-8")
            self.assertEqual(re.findall(r"flatpak-github-actions:gnome-(\d+)@", text), [version],
                             f"{workflow} builds in the runtime's own container")
        self.assertIn("sdk: org.gnome.Sdk", m)
        self.assertIn("command: hoard", m)
        self.assertIn("- python3-deps.json", m)
        self.assertIn("hoard self-test", m, "the build runs Hoard's self-test in the sandbox")
        self.assertIn("gi.require_version('WebKit2', '4.1')", m, "and fails without the window's WebKitGTK")
        self.assertRegex(m, r"type: dir\s+path: \.\./\.\.")

    def test_the_sandbox(self):
        """Only what Hoard needs: the network, a window, the keyring for sign-ins, and your files for the downloads
        folder. Never the host system, or the whole session bus."""
        self.assertEqual(set(self.finish_args()), {
            "--share=network", "--share=ipc", "--socket=wayland", "--socket=fallback-x11", "--device=dri",
            "--talk-name=org.freedesktop.secrets", "--talk-name=org.kde.kwalletd5", "--talk-name=org.kde.kwalletd6",
            "--filesystem=home", "--filesystem=/media", "--filesystem=/run/media", "--filesystem=/mnt",
            "--env=PYWEBVIEW_GUI=gtk"})

    def test_what_software_centres_show(self):
        desktop = (FLATPAK / f"{APP_ID}.desktop").read_text("utf-8")
        for line in ("Type=Application", "Name=Hoard", "Exec=hoard", f"Icon={APP_ID}", "Terminal=false"):
            self.assertIn(line, desktop.splitlines())
        info = ET.parse(FLATPAK / f"{APP_ID}.metainfo.xml").getroot()
        self.assertEqual(info.get("type"), "desktop-application")
        self.assertEqual(info.findtext("id"), APP_ID)
        self.assertEqual(info.findtext("launchable"), f"{APP_ID}.desktop")
        self.assertEqual(info.findtext("project_license"), "MIT")
        self.assertEqual(info.findtext("metadata_license"), "CC0-1.0")
        self.assertIsNotNone(info.find("content_rating"))
        self.assertEqual(info.find("releases/release").get("version"), hoard.__version__,
                         "the newest release listed is this version")
        for size in (128, 256, 512):
            self.assertIn(f"hoard-{size}.png ${{FLATPAK_DEST}}/share/icons/hicolor/{size}x{size}/apps/{APP_ID}.png", self.manifest)

    def test_the_launcher(self):
        sh = FLATPAK / "hoard.sh"
        self.assertTrue(os.access(sh, os.X_OK) or os.name == "nt")
        text = sh.read_text("utf-8")
        self.assertIn('PYTHONPATH="/app/lib/hoard', text)
        self.assertIn('exec python3 -m hoard "$@"', text)

    def test_the_flatpak_keeps_a_log(self):
        """Started from the desktop, what it prints goes nowhere you'd look: it writes its log, like the other apps."""
        from hoard import app, paths
        with mock.patch.dict(os.environ, {"FLATPAK_ID": APP_ID}):
            self.assertTrue(paths.in_flatpak())
            self.assertFalse(app.has_console())

    def test_the_flatpak_keeps_hoards_usual_folder(self):
        """Not the Flatpak's own (~/.var/app/...): the one every Linux Hoard uses, so a library carries over from
        a source install, and Hoard for Unity (Packages/.../HoardLocation.cs) finds its catalog key."""
        from hoard import paths
        if sys.platform in ("win32", "darwin"):
            self.skipTest("Linux only")
        home = Path.home()
        sandboxed = {"HOARD_DATA_DIR": "", "FLATPAK_ID": APP_ID, "XDG_DATA_HOME": str(home / ".var/app" / APP_ID / "data")}
        with mock.patch.dict(os.environ, sandboxed):
            os.environ.pop("HOST_XDG_DATA_HOME", None)
            self.assertEqual(paths.data_dir(), home / ".local" / "share" / "Hoard")
            os.environ["HOST_XDG_DATA_HOME"] = "/data/sam"
            self.assertEqual(paths.data_dir(), Path("/data/sam/Hoard"), "your own XDG_DATA_HOME, as Flatpak passes it on")


class Updating(unittest.TestCase):
    """The Mac app and the Flatpak can't install an update themselves: they say which file to get."""

    def test_the_flatpak(self):
        from hoard import updater
        with mock.patch.dict(os.environ, {"FLATPAK_ID": APP_ID}):
            self.assertIn("Hoard-2.11.0-linux-x86_64.flatpak", updater.how_to_update("2.11.0"))

    def test_the_mac_app(self):
        from hoard import updater
        with mock.patch.dict(os.environ, {"FLATPAK_ID": ""}), mock.patch.object(updater.sys, "platform", "darwin"), \
                mock.patch.object(updater.sys, "frozen", True, create=True), \
                mock.patch("hoard.paths.Path.exists", return_value=False):
            for machine, chip in (("arm64", "apple-silicon"), ("x86_64", "intel")):
                with mock.patch("platform.machine", return_value=machine):
                    self.assertIn(f"Hoard-2.11.0-macos-{chip}.pkg", updater.how_to_update("2.11.0"))

    def test_the_view_says_it(self):
        from hoard import updater
        u = updater.Updates({})
        u.state["latest"] = {"version": "99.0.0", "url": "https://github.com/x", "has_installer": True}
        with mock.patch.dict(os.environ, {"FLATPAK_ID": APP_ID}):
            view = u.view(False)
        self.assertTrue(view["available"])
        self.assertIn("Hoard-99.0.0-linux-x86_64.flatpak", view["how"])
        self.assertIn("u.how", (REPO / "hoard" / "web" / "library.html").read_text("utf-8"), "Settings shows it")


class TheMacApp(unittest.TestCase):

    def test_the_bundle(self):
        spec = (REPO / "packaging" / "hoard.spec").read_text("utf-8")
        self.assertIn(f'APP_ID = "{APP_ID}"', spec)
        self.assertIn('BUNDLE(coll, name="Hoard.app"', spec)
        self.assertIn('"LSMinimumSystemVersion": "11.0"', spec)
        self.assertIn('"hoard.icns" if MAC else "hoard.ico"', spec)

    def test_the_package(self):
        script = (REPO / "scripts" / "build_macos_pkg.sh").read_text("utf-8")
        self.assertIn(f"--identifier {APP_ID}", script)
        self.assertIn('plutil -replace "$i.BundleIsRelocatable" -bool NO', script,
                      "every bundle in it (Hoard.app, its Python.framework) installed where it says, never moved "
                      "onto another copy such as python.org's Python")
        self.assertIn('while plutil -extract "$i" xml1', script, "each of them")
        self.assertIn('mkdir -p "$root/Applications"', script)
        self.assertIn("Hoard-$version-macos-$chip.pkg", script)
        self.assertTrue(os.access(REPO / "scripts" / "build_macos_pkg.sh", os.X_OK) or os.name == "nt")


class Icons(unittest.TestCase):

    def test_sizes(self):
        for size in (128, 256, 512):
            data = (REPO / "packaging" / "icons" / f"hoard-{size}.png").read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(struct.unpack(">II", data[16:24]), (size, size))
        icns = (REPO / "packaging" / "hoard.icns").read_bytes()
        self.assertEqual(icns[:4], b"icns")
        self.assertEqual(struct.unpack(">I", icns[4:8])[0], len(icns))


class Workflows(unittest.TestCase):

    def setUp(self):
        self.release = (REPO / ".github" / "workflows" / "release.yml").read_text("utf-8")
        self.check = (REPO / ".github" / "workflows" / "check.yml").read_text("utf-8")

    def test_every_action_and_container_is_pinned(self):
        for text in (self.release, self.check):
            for use in re.findall(r"uses:\s*(\S+)", text):
                self.assertRegex(use, r"@[0-9a-f]{40}$", use)
            for image in re.findall(r"image:\s*(\S+)", text):
                self.assertRegex(image, r"@sha256:[0-9a-f]{64}$", image)

    def test_the_release_builds_every_package(self):
        r = self.release
        self.assertIn("runner: [macos-15, macos-15-intel]", r, "Apple Silicon and Intel")
        self.assertIn("--require-hashes -r requirements-mac.txt", r)
        self.assertIn("dist/Hoard.app/Contents/MacOS/hoard-cli self-test", r)
        self.assertIn("scripts/build_macos_pkg.sh", r)
        self.assertIn(f"manifest-path: packaging/flatpak/{APP_ID}.yml", r)
        self.assertIn("Hoard-${TAG#v}-linux-x86_64.flatpak", r)
        self.assertIn("needs: [release, windows, macos, flatpak-release]", r, "published once every file is on it")

    def test_every_pull_request_builds_them(self):
        c = self.check
        for job in ("app-windows:", "app-macos:", "flatpak:"):
            self.assertIn(job, c)
        self.assertIn("scripts/build_macos_pkg.sh", c)


if __name__ == "__main__":
    unittest.main()
