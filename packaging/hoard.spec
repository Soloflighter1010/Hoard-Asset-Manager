# PyInstaller build: pyinstaller packaging/hoard.spec  ->  dist/Hoard/ with Hoard.exe (the app, no console) and
# hoard-cli.exe (the command line), sharing one set of libraries. Run packaging/version_info.py first on Windows.
# On macOS it also makes dist/Hoard.app (Hoard, with hoard-cli beside it in Contents/MacOS), which
# .github/workflows/release.yml puts in a .pkg. Works on Linux too, which is how the packaging is tested there.
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO = Path(SPECPATH).parent
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
VERSION = re.search(r'__version__ = "([^"]+)"', (REPO / "hoard" / "__init__.py").read_text("utf-8")).group(1)
NUMBERS = ".".join(re.findall(r"\d+", VERSION)[:3])   # macOS wants numbers only: a beta, 3.1.0-beta.1, is 3.1.0
APP_ID = "io.github.soloflighter1010.Hoard"   # the same as the Flatpak's (packaging/flatpak)
version_file = REPO / "build" / "version_info.txt"

datas = [
    (str(REPO / "hoard" / "web"), "hoard/web"),                          # the pages and their fonts
    (str(REPO / "hoard" / "recovery_words.txt"), "hoard"),                # the hidden library's recovery words
    (str(REPO / "hoard" / "known_tools.json"), "hoard"),                  # What it needs: the tools Hoard knows (hoard/needs.py)
    (str(REPO / "CHANGELOG.md"), "."),                                    # What's new, in the app (hoard/changelog.py)
]
datas += collect_data_files("playwright")                                 # Playwright's driver (Node and its package)
hidden = collect_submodules("hoard")
if WINDOWS or MAC:
    datas += collect_data_files("webview")   # pywebview's parts (WebView2, or the Mac's WebKit; its build rules do the rest)


def analysis(script):
    return Analysis([str(REPO / "packaging" / script)], pathex=[str(REPO)], datas=datas, hiddenimports=hidden,
                    excludes=["tkinter", "unittest", "pydoc", "test"], noarchive=False)


def program(a, name, console):
    return EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True, name=name, console=console,
               icon=str(REPO / "packaging" / ("hoard.icns" if MAC else "hoard.ico")), upx=False,
               version=str(version_file) if WINDOWS and version_file.exists() else None)


app, cli = analysis("hoard_app.py"), analysis("hoard_cli.py")
coll = COLLECT(program(app, "Hoard", console=False), app.binaries, app.datas,
               program(cli, "hoard-cli", console=True), cli.binaries, cli.datas,
               name="Hoard", upx=False)
if MAC:
    BUNDLE(coll, name="Hoard.app", icon=str(REPO / "packaging" / "hoard.icns"), bundle_identifier=APP_ID,
           version=VERSION, info_plist={
               "CFBundleName": "Hoard", "CFBundleDisplayName": "Hoard",
               "CFBundleShortVersionString": NUMBERS, "CFBundleVersion": NUMBERS,
               "LSMinimumSystemVersion": "11.0", "NSHighResolutionCapable": True,
               "LSApplicationCategoryType": "public.app-category.utilities",
               "NSHumanReadableCopyright": "MIT licensed. Not affiliated with VRChat or any store.",
           })
