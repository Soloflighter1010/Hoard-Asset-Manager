#!/usr/bin/env sh
# Start Hoard (it opens in your browser), or run one of its commands: ./run.sh sync, ./run.sh verify, ...
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./setup.sh
# Python can keep running old compiled copies of files updated over an old install: always start from the files.
export PYTHONDONTWRITEBYTECODE=1
rm -rf hoard/__pycache__
exec .venv/bin/python -m hoard "$@"
