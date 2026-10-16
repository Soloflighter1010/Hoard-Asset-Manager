A certificate and key for the tests only: they let tests/test_security.py run Hoard's real HTTPS
download path against a server on this computer. They protect nothing and are never used by Hoard itself.

vcc-sample.liteDb.gz: a VRChat Creator Companion database (vcc.liteDb, gzipped) for tests/test_vpm_core.py, which
checks Hoard's reader (hoard/vpm/litedb.py) against it: 41 projects, one document large enough to span pages, and a
Unity version. It was written with vrc-get's own LiteDB writer (vrc-get-litedb), and holds made-up paths only.
