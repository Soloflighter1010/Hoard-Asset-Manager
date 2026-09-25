"""`python -m hoard` opens Hoard; with a command (sync, login, verify, ...) it runs that instead."""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__

# Python reuses its compiled copy of a file whose date and size haven't changed. Files updated over an old install
# can keep their old dates (copied from a zip), so an update could keep running old code. If the version running
# isn't the one on disk, the compiled copies are stale: clear them and start again, once.
_here = Path(__file__).resolve().parent
_init = _here / "__init__.py"   # (the installed app has no source files: nothing to compare)
_on_disk = re.search(r'__version__ = "([^"]+)"', _init.read_text("utf-8")) if _init.is_file() else None
if (not getattr(sys, "frozen", False) and _on_disk and _on_disk.group(1) != __version__
        and not os.environ.get("HOARD_RESTARTED")):
    for cache in _here.rglob("__pycache__"):
        shutil.rmtree(cache, ignore_errors=True)
    sys.exit(subprocess.call([sys.executable, "-m", "hoard", *sys.argv[1:]], env={**os.environ, "HOARD_RESTARTED": "1"}))

from .cli import main  # noqa: E402

main()
