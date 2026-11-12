"""hoard-server: Hoard for its Tauri shell (shell/), compiled by Nuitka (scripts/build_nuitka.py). The shell starts
it with --shell and is its window (hoard/shell.py); with a command (self-test, say) it's Hoard's command line."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "__compiled__" in globals():   # (Nuitka: an installed copy, as PyInstaller's say, for its log and updates)
        sys.frozen = True
    from hoard import shell
    shell.BUILD = True
    if "--shell" in sys.argv[1:]:
        shell.claim_pipes()   # (before anything prints)
    from hoard.cli import main
    main(sys.argv[1:])
