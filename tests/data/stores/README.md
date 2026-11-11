These are synthetic, account-free recordings of layouts exercised by Hoard's
store readers. They retain the markup and response shape that caused earlier
reader bugs, with made-up products, creators and download tokens.

Each store has `library.html` and `expected.json`. Stores with wishlist support
also have `wishlist*.html`. `test_store_adapters.py` verifies every registered
adapter has recordings and that its library parser still reads the expected
identities. `test_wishlists.py` exercises all the wishlist recordings, including
pagination, prices and merges. The larger generated variants in
`test_readers.py` and `test_quick.py` cover navigation and stopping boundaries.

When a layout changes, add a sanitized recording and an expected result before
changing its parser. Never copy a real cookie, purchase token, account address,
or private download URL into a fixture.
