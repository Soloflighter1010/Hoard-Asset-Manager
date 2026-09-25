"""Hoard.exe: Hoard in its own window, with no console. (Commands are for hoard-cli.exe.)"""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from hoard.cli import main
    main([a for a in sys.argv[1:] if a == "--browser"])
