#!/bin/sh
# Start Hoard in the Flatpak: its window with no arguments, or one of its commands (hoard sync, hoard verify, ...).
export PYTHONPATH="/app/lib/hoard${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONDONTWRITEBYTECODE=1   # /app can't be written to
exec python3 -m hoard "$@"
