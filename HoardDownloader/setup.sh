#!/usr/bin/env sh
# Linux / macOS setup: a private Python environment plus the browser used for store sign-ins.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is needed."; exit 1; }
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade -r requirements.txt
.venv/bin/python -m playwright install chromium
[ -f config.json ] || cp config.example.json config.json
echo "Setup finished. On Linux, if the browser won't start: .venv/bin/python -m playwright install-deps chromium"
