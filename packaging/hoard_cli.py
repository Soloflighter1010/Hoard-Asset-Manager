"""hoard-cli.exe: Hoard's command line (sync, verify, login, ...), for scripts and power users."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from hoard.cli import main
    main()
