#!/bin/sh
# Start Hoard in the Flatpak (shell/flatpak): its window with no arguments, or one of Hoard's commands (hoard sync,
# hoard verify, hoard self-test, ...), which its server runs as hoard-cli does elsewhere.
if [ "$#" -eq 0 ]; then
  exec /app/bin/Hoard
fi
exec /app/lib/Hoard/server/hoard-server "$@"
