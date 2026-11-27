#!/bin/sh
# Start Hoard in the Flatpak (shell/flatpak): its window with no arguments, a hoard:// link (the desktop entry's %u:
# issue #396) or what a file manager's right-click option asks for (--hoard-add, --hoard-sync-now, --hoard-open-local:
# issue #411), or one of Hoard's commands (hoard sync, hoard verify, hoard self-test, ...), which its server runs as
# hoard-cli does elsewhere.
if [ "$#" -eq 0 ]; then
  exec /app/bin/Hoard
fi
case "$1" in
  [hH][oO][aA][rR][dD]:*) exec /app/bin/Hoard "$1" ;;
  --hoard-add|--hoard-sync-now|--hoard-open-local) exec /app/bin/Hoard "$@" ;;
esac
exec /app/lib/Hoard/server/hoard-server "$@"
