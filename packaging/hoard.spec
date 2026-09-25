# PyInstaller build: pyinstaller packaging/hoard.spec  ->  dist/Hoard/ with Hoard.exe (the app, no console) and
# hoard-cli.exe (the command line), sharing one set of libraries. Run packaging/version_info.py first on Windows.
# Works on Linux and macOS too (as Hoard and hoard-cli), which is how the packaging is tested off Windows.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

REPO = Path(SPECPATH).parent
WINDOWS = sys.platform == "win32"
version_file = REPO / "build" / "version_info.txt"

datas = [
    (str(REPO / "hoard" / "web"), "hoard/web"),                          # the pages and their fonts
    (str(REPO / "hoard" / "recovery_words.txt"), "hoard"),                # the hidden library's recovery words
]
datas += collect_data_files("playwright")                                 # Playwright's driver (Node and its package)
hidden = collect_submodules("hoard")
if WINDOWS:
    datas += collect_data_files("webview")   # pywebview's WebView2 parts (its own build rules handle the rest)


def analysis(script):
    return Analysis([str(REPO / "packaging" / script)], pathex=[str(REPO)], datas=datas, hiddenimports=hidden,
                    excludes=["tkinter", "unittest", "pydoc", "test"], noarchive=False)


def program(a, name, console):
    return EXE(PYZ(a.pure), a.scripts, [], exclude_binaries=True, name=name, console=console,
               icon=str(REPO / "packaging" / "hoard.ico"), upx=False,
               version=str(version_file) if WINDOWS and version_file.exists() else None)


app, cli = analysis("hoard_app.py"), analysis("hoard_cli.py")
COLLECT(program(app, "Hoard", console=False), app.binaries, app.datas,
        program(cli, "hoard-cli", console=True), cli.binaries, cli.datas,
        name="Hoard", upx=False)
