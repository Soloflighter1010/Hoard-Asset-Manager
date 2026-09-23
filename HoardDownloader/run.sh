#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./setup.sh
exec .venv/bin/python asset_dl.py "$@"
