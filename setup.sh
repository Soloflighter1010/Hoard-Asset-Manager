#!/usr/bin/env sh
# Linux / macOS setup: a private Python environment plus the browser used for store sign-ins.
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 3.10 or newer is needed."; exit 1; }
# Only your account may change this folder, so no other account can swap in code that would run with your sign-ins.
chmod -R go-w . && echo "Only your account can change the files in this folder now."
[ -x .venv/bin/python ] || "$PY" -m venv .venv
echo "Installing packages (each one checked against the hash recorded in requirements.txt)..."
.venv/bin/python -m pip install --disable-pip-version-check -q --require-hashes -r requirements.txt
.venv/bin/python -m playwright install chromium
echo "Setup finished. Start Hoard with ./run.sh"
echo "On Linux, if the browser won't start: .venv/bin/python -m playwright install-deps chromium"
echo "On Linux, sign-ins are only saved when a keyring (GNOME Keyring, KeePassXC or KWallet) can protect them."
