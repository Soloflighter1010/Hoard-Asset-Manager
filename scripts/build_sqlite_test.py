"""Build a portable local SQLite test app without changing the normal build default.

Use an unchanged released Tauri host with a newly compiled backend:
  python scripts/build_sqlite_test.py --python .atlas/build-venv/Scripts/python.exe --shell /path/to/Hoard.exe
The generated app uses normal Hoard app-data; verification uses disposable homes.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def main():
    """Stage and compile a local SQLite-default backend, verify it, and package a portable app."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="Python with the locked runtime/Nuitka dependencies")
    parser.add_argument("--shell", type=Path, required=True, help="released, compatible Tauri Hoard.exe")
    parser.add_argument("--shell-ref", default="v5.2.0-beta.9")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    python, shell = args.python.resolve(), args.shell.resolve()
    if not python.is_file() or not shell.is_file():
        parser.error("Python and the Tauri executable must exist")
    if subprocess.check_output(["git", "diff", args.shell_ref, "--", "shell"], cwd=ROOT):
        parser.error("The Tauri host source changed; compile a matching host before using this recipe")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    short = commit[:7]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    stage = (ROOT / ".atlas" / ("sqlite-build-" + stamp)).resolve()
    output = (args.output or ROOT / "dist" / ("Hoard-SQLite-local-" + short)).resolve()
    if not stage.is_relative_to(ROOT) or not output.is_relative_to(ROOT):
        parser.error("Keep the stage and output inside the workspace")
    if stage.exists() or output.exists():
        parser.error("Stage/output already exists; choose a fresh output rather than overwriting a build")
    stage.mkdir(parents=True)
    files = subprocess.check_output(["git", "ls-files", "-z", "--", "hoard", "packaging", "scripts/build_nuitka.py",
                                     "CHANGELOG.md", "LICENSE"], cwd=ROOT).decode("utf-8").split("\0")
    for name in filter(None, files):
        source, target = ROOT / name, stage / name
        if source.is_symlink() or not target.resolve().is_relative_to(stage):
            raise RuntimeError("Build inputs must be ordinary tracked workspace files")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    init = stage / "hoard" / "__init__.py"
    original = init.read_text("utf-8")
    base = re.search(r'__version__ = "([^"]+)"', original).group(1)
    version = base + "+sqlite.local." + short
    init.write_text(original.replace(f'__version__ = "{base}"', f'__version__ = "{version}"'), "utf-8", newline="\n")
    storage = stage / "hoard" / "storage.py"
    text = storage.read_text("utf-8")
    needle = 'return os.environ.get("HOARD_METADATA", "").strip().lower() == "sqlite"'
    if text.count(needle) != 1:
        raise RuntimeError("Review the SQLite activation boundary before updating this build recipe")
    storage.write_text(text.replace(needle, 'return os.environ.get("HOARD_METADATA", "sqlite").strip().lower() == "sqlite"'),
                       "utf-8", newline="\n")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["NUITKA_CACHE_DIR"] = str(ROOT / ".atlas" / "nuitka-cache")
    print(f"Compiling {version}; stage: {stage}", flush=True)
    subprocess.run([str(python), str(stage / "scripts" / "build_nuitka.py")], cwd=stage, env=env, check=True)
    server = stage / "build" / "nuitka" / "server"
    exe = server / "hoard-server.exe"
    # Prove the compiled default without setting HOARD_METADATA or touching a user home.
    with tempfile.TemporaryDirectory(prefix="hoard-local-sqlite-check-") as folder:
        verify_env = {**env, "HOARD_DATA_DIR": folder}
        verify_env.pop("HOARD_METADATA", None)
        subprocess.run([str(exe), "self-test"], cwd=server, env=verify_env, check=True, timeout=120)
        database = Path(folder) / "metadata.sqlite3"
        if not database.is_file():
            raise RuntimeError("Compiled test app did not enable SQLite by default")
        connection = sqlite3.connect(database)
        try:
            if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
                raise RuntimeError("Unexpected metadata schema in the compiled test app")
        finally:
            connection.close()
    subprocess.run([str(python), str(ROOT / "scripts" / "check_storage_compat.py"), "--legacy-root", str(ROOT),
                    "--current-sidecar", str(exe)], cwd=ROOT, env=env, check=True, timeout=180)
    output.mkdir(parents=True)
    shutil.copy2(shell, output / "Hoard.exe")
    shutil.copytree(server, output / "server")
    shutil.copy2(ROOT / "LICENSE", output / "LICENSE")
    info = {"version": version, "source_commit": commit, "sqlite_default": True,
            "normal_release_default_changed": False, "tauri_host_ref": args.shell_ref,
            "tauri_host_sha256": hashlib.sha256(shell.read_bytes()).hexdigest(),
            "backend": "newly compiled Nuitka standalone", "built_at_utc": stamp,
            "checks": ["compiled self-test", "SQLite default with no environment flag", "JSON round trip", "lost/foreign-key recovery"]}
    (output / "BUILD-INFO.json").write_text(json.dumps(info, indent=2) + "\n", "utf-8", newline="\n")
    (output / "TESTING.txt").write_text(
        f"Hoard {version} - local SQLite test build\n\n"
        "Close the installed Hoard before running this copy. Open Hoard.exe in this folder.\n"
        "This build uses your normal Hoard app-data and downloads; first access migrates private JSON metadata to SQLite.\n"
        "Current JSON mirrors and original .pre-sqlite-v1 files are retained. Keep the entire folder together.\n"
        "No installer is run and your installed app is not replaced. The released Tauri host wraps a newly compiled backend.\n"
        "To test an empty, separate profile instead, set HOARD_DATA_DIR to a new folder before launching.\n"
        "SQLite is enabled in this local build only; an explicit HOARD_METADATA environment setting still overrides it.\n",
        "utf-8", newline="\n")
    archive = shutil.make_archive(str(output), "zip", root_dir=output.parent, base_dir=output.name)
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    Path(archive + ".sha256").write_text(digest + "  " + Path(archive).name + "\n", "ascii")
    print(json.dumps({"app": str(output / "Hoard.exe"), "archive": archive, "sha256": digest}), flush=True)


if __name__ == "__main__":
    main()
