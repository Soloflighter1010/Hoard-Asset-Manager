"""Hoard's server for its apps (from 5.2.0 beta 6): Hoard compiled by Nuitka into a folder of its own, with what
packaging/hoard.spec ships for PyInstaller (the pages, words, templates, changelog, Playwright's driver, Apprise's
services and each library's license), to go inside the Tauri shell (shell/) as its resources.

    python scripts/build_nuitka.py            ->  build/nuitka/server/ with hoard-server (hoard-server.exe)

Needs requirements.txt and requirements-nuitka.txt installed, and a C compiler (MSVC on Windows, Xcode's on a Mac,
gcc and patchelf on Linux). hoard-server is Hoard's command line as well: hoard-server self-test checks the build.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "nuitka"
WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
VERSION = re.search(r'__version__ = "([^"]+)"', (REPO / "hoard" / "__init__.py").read_text("utf-8")).group(1)
NUMBERS = ".".join(re.findall(r"\d+", VERSION)[:3])   # (Windows' file version takes numbers only)


# What Hoard imports (and Apprise's services do), which Nuitka follows by itself: only the rest are put in by name.
# (Putting all of Playwright in by name compiles its async API too, which Hoard never uses, and whose one huge module
# runs Windows' compiler out of memory.)
FOLLOWED = {"playwright", "greenlet", "pyee", "requests", "urllib3", "certifi", "charset_normalizer", "idna", "tqdm",
            "apprise", "requests_oauthlib", "oauthlib", "markdown", "yaml", "_yaml"}


def metadata() -> list[str]:
    """Each library's own details, with its license files, for Acknowledgements (as the PyInstaller spec ships), and
    its code: Nuitka ships a library's details only with the library (one Hoard doesn't import on this system, as
    colorama off Windows, would be left out otherwise)."""
    import importlib.util
    from importlib import metadata as md
    tops: dict[str, list[str]] = {}   # a distribution's name -> the modules and packages it installs
    for top, dists in md.packages_distributions().items():
        for d in dists:
            tops.setdefault(d.lower().replace("_", "-"), []).append(top)
    out = []
    for group in json.loads((REPO / "hoard" / "credits.json").read_text("utf-8"))["groups"]:
        for credit in group["items"]:
            if credit.get("package") and credit["in"] != "build":
                try:
                    name = md.distribution(credit["package"]).metadata["Name"]   # (its own spelling: PyYAML)
                except md.PackageNotFoundError:   # (one this build doesn't have: pywebview, PyObjC)
                    continue
                for top in sorted(set(tops.get(name.lower().replace("_", "-"), []))):
                    spec = importlib.util.find_spec(top)
                    if spec and not top.startswith("__") and top not in FOLLOWED:
                        kind = "package" if spec.submodule_search_locations is not None else "module"
                        out.append(f"--include-{kind}={top}")
                out.append(f"--include-distribution-metadata={name}")
    return out


def command() -> list[str]:
    """Nuitka's command line for hoard-server."""
    data = [("hoard/recovery_words.txt", "hoard/recovery_words.txt"), ("hoard/known_tools.json", "hoard/known_tools.json"),
            ("hoard/credits.json", "hoard/credits.json"), ("CHANGELOG.md", "CHANGELOG.md")]
    cmd = [sys.executable, "-m", "nuitka", "--mode=standalone", f"--output-dir={OUT}", "--output-filename=hoard-server",
           "--assume-yes-for-downloads", "--remove-output", "--no-deployment-flag=self-execution",
           "--include-package=hoard", "--include-package=apprise", "--include-package-data=apprise",
           "--include-package-data=tzdata",   # (its time zones: Apprise on Windows; Playwright's driver comes with Nuitka's own rules)
           f"--include-data-dir={REPO / 'hoard' / 'web'}=hoard/web",
           f"--include-data-dir={REPO / 'hoard' / 'vpm' / 'templates'}=hoard/vpm/templates",
           *(f"--include-data-files={REPO / src}={dest}" for src, dest in data),
           # not in this build: its window is the Tauri shell's, not pywebview's
           "--nofollow-import-to=webview", "--nofollow-import-to=pythonnet", "--nofollow-import-to=clr_loader",
           "--nofollow-import-to=tkinter", "--nofollow-import-to=pydoc",
           "--nofollow-import-to=*.tests",   # (a library's own tests: greenlet's, say)
           "--nofollow-import-to=playwright.async_api",   # (Hoard uses its sync API)
           *metadata()]
    if WINDOWS:
        cmd += ["--windows-console-mode=attach", f"--windows-icon-from-ico={REPO / 'packaging' / 'hoard.ico'}",
                "--company-name=SoloFlighter", "--product-name=Hoard", f"--file-version={NUMBERS}",
                f"--product-version={NUMBERS}", "--file-description=Hoard (its server, for its Tauri window)",
                "--copyright=MIT licensed. Not affiliated with VRChat or any store."]
    return cmd + [str(REPO / "packaging" / "hoard_shell.py")]


def main() -> int:
    """Build hoard-server, ship Apprise's service folders beside it, and say how big it came out."""
    if OUT.exists():
        shutil.rmtree(OUT)
    print("$ " + " ".join(command()), flush=True)
    subprocess.run(command(), check=True, cwd=REPO)
    dist = OUT / "hoard_shell.dist"
    # Apprise finds its services by listing these folders, then imports each by name (the compiled one): they're
    # shipped as they are, as the PyInstaller build does (without them it knows no service: issue #237)
    import apprise
    source = Path(apprise.__file__).parent
    for folder in ("plugins", "attachment", "config"):
        shutil.copytree(source / folder, dist / "apprise" / folder, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    server = OUT / "server"
    dist.rename(server)
    exe = server / ("hoard-server.exe" if WINDOWS else "hoard-server")
    print(f"Built {exe} ({sum(f.stat().st_size for f in server.rglob('*') if f.is_file()) / 1e6:.0f} MB in "
          f"{sum(1 for f in server.rglob('*') if f.is_file())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
