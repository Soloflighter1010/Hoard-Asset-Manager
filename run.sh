#!/usr/bin/env sh
# Start Hoard (it opens in your browser), or run one of its commands: ./run.sh sync, ./run.sh verify, ...
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./setup.sh
exec .venv/bin/python -m hoard "$@"
