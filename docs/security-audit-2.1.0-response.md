# Response to the 2.1.0 security audit

The audit (24 September 2026) reviewed the 2.1.0 source and reported twelve findings. All twelve are
fixed in 2.1.1. For each: what we found when checking it, what changed, and the test that keeps it
fixed. Tests are in `tests/`; run them with `python -m unittest discover -s tests -v`.

## H-01 (High): the asset downloader bypassed the public-address guard

**Confirmed.** Product pictures were fetched through `safety.fetch_public`, which checks every address
and connects to exactly the address it checked. Files were downloaded through a plain `requests`
session that followed redirects on its own, so a redirect to `127.0.0.1` or a private address would
have been followed.

**Fixed.** New module `hoard/egress.py` is the only path for store pages, data and files. Its sessions
connect through a connection class that looks the host up once, refuses the request unless every
address is public, and connects to exactly the checked address (`safety._connect_public`, the same
check pictures use). Redirects are never automatic: each hop is checked before it's opened. System
proxies and `.netrc` are ignored. The old `http_download` is removed.

**Tests:** `Egress.test_redirects_to_this_computer_or_network_are_refused` covers redirects to
`127.0.0.1` over http and https, `localhost`, `169.254.169.254`, `10.0.0.1`, `192.168.1.1`, `[::1]`,
`file:` and `ftp:`, each directly and at the end of a multi-hop chain. It also checks that nothing is
written and the refused address is never contacted. `Egress.test_no_other_way_out` fails if any
module other than `egress.py` and `safety.py` makes its own HTTP requests.

## H-02 (Medium): authenticated store requests allowed HTTP

**Confirmed** in `downloader.store_url`. **Fixed.** Store links must be https with no user name, and
`egress` refuses any non-https hop: plain-http requests are refused by the session itself, not only
checked beforehand. **Test:** `Egress.test_plain_http_and_credentials_are_refused`.

## H-03 (Medium): download redirects weren't centrally validated

**Confirmed** (Booth's redirect address was handed to the generic downloader). **Fixed** with H-01:
Booth's first request and its redirect both go through `egress`. Store pages and APIs refuse any
redirect off the store's own sites. Store cookies are sent only to the store's own sites; any other
host (CDNs, storage buckets) gets a separate cookie-free session.

**Tests:** `Egress.test_store_cookies_never_leave_the_store` checks that a redirect to another host
receives no cookie header. `Egress.test_api_redirects_stay_on_the_store` checks the off-site refusal.
The Gumroad stand-in test confirms files on its storage host come through the cookie-free session.

## H-04 (Medium): .part files were open to a link or reparse race

**Confirmed.** **Fixed:**
- `safety.open_part` creates a fresh part file with `O_CREAT | O_EXCL | O_NOFOLLOW`, after removing
  (never following) whatever was there. It resumes with `O_NOFOLLOW`, and confirms that the open file
  is a plain file with a single link, and is the object at that path.
- On Windows, where `os.open` can't refuse links, it compares the open file's real path
  (`GetFinalPathNameByHandle`) with the expected one.
- `safety.move_into_place` renames only if the part file is still the very file that was written, and
  removes (never follows) anything swapped in between the check and the rename.
- Downloads made by the store window are saved into a new private folder (`mkdtemp`) and moved in
  the same checked way.

**Tests:** `FileRaces.test_a_planted_link_is_never_written_through` and
`FileRaces.test_a_swapped_part_file_is_not_used`.

## H-05 (Medium): /files/ had a check-then-read gap

**Confirmed.** **Fixed:** `safety.open_under` opens the file one folder at a time from a handle on the
downloads folder, with `O_NOFOLLOW` at every step (POSIX `dir_fd`). On Windows, it checks the open
file's real path. The server then serves the bytes read from that open file, up to a size limit.

**Test:** `FileRaces.test_served_files_never_follow_links`, which covers a linked folder, a linked
file and `..` paths. A live check also returned 404 for a link planted in the downloads folder.

## H-06 (Medium): imported HTML was rendered with JavaScript enabled

**Confirmed:** in a test, an `onerror` handler in an imported page ran. **Fixed:**
- Imported pages open in a browser context with JavaScript disabled (`safety.offline_page`). Hoard's
  own readers still run, through Playwright, independent of the page's scripts.
- As a second layer, `safety.inert_html` removes scripts, frames, plugins, `<base>`, meta refreshes,
  inline event handlers and `javascript:` links.

**Test:** `BoothAndPayhip.test_imported_pages_run_nothing` checks that a page whose handlers would
change its title leaves it unchanged, with and without the stripping.

## H-07 (Medium): imported Payhip pages could add trusted shop origins

**Confirmed.** **Fixed:**
- Importing a page from a shop that isn't in your list stops with `NewShop`. The app then shows the
  exact address and asks. The command line needs `--trust-shop <address>`. The downloader's saved-page
  option only accepts shops already listed.
- Shop names must be ASCII domain names with valid labels. IP addresses, ports, user names and
  internationalised `xn--` names are refused.

**Tests:** `BoothAndPayhip.test_importing_a_shop_page_needs_your_say_so` covers refusal, a
confirmation for the wrong shop, and the right confirmation.
`SmallerFindings.test_deceptive_shop_names_are_refused` covers the name rules.

## H-08 (Medium): sanitised names could collide

**Partly confirmed:**
- Folders were already made unique, but only by exact spelling. On Windows and macOS, `Creator/Asset`
  and `creator/asset` are the same folder.
- Files could be overwritten: a new file whose name cleaned up like an existing one was treated as
  that file's update.

**Fixed:**
- Folders are compared as a case-insensitive, Unicode-normalised file system would see them. A
  colliding product gets a stable tag derived from its store id.
- Files: when two files that are both still offered clean up to the same name, the newer one gets a
  stable tag from its id instead of replacing the other. A name held by a file the store no longer
  offers is still treated as its update. This applies to Booth, Gumroad, Jinxxy and Payhip.

**Tests:** `NameCollisions.test_folders` and `NameCollisions.test_files`.

## H-09 (Low-Medium): diagnostics could contain sensitive data

**Confirmed.** **Fixed:**
- `debug` and `probe` now save pages passed through `safety.scrub`. It removes email addresses, form
  values (license keys, codes), CSRF tokens, `data-*` keys, ids and tokens, every URL query value
  (where signed links keep their signatures), and long opaque tokens. The page's structure is kept.
- There are no screenshots by default, and the reader's findings are saved as a summary (counts and
  which fields were filled) instead of your purchases.
- `--raw` saves everything as it is, with a `SENSITIVE-README.txt` explaining what it contains.

**Test:** `Diagnostics.test_scrub`. It was also checked against a real Payhip product page: the email
address, license key, transaction key and file ids were all removed, and both download buttons and
every link remained.

## H-10 (Low-Medium): manifest status parsing was less defensive

**Confirmed** in `downloads.library_status`. **Fixed:** it uses the same size-limited reader as every
other data file (`read_json_file`), checks types before walking the data, and treats anything odd as
unreadable. **Test:** `SmallerFindings.test_odd_manifests_dont_break_the_index`, which covers wrong
types and deeply nested input.

## H-11 (Low-Medium): LAN mode transport and availability

The transport part is by design: loopback is the default, and network mode needs HTTPS unless you
explicitly say the network is already encrypted (a VPN). **Added:**
- a 30-second idle limit on every connection
- a cap of 64 simultaneous connections; extra ones are closed at once
- a shorter listen queue

The access key was already new on every start; the command-line guide now says plainly that it isn't a
substitute for encryption. **Test:** `SmallerFindings.test_server_limits`.

## H-12 (Low-Medium): custom sign-in locations could weaken the default

**Confirmed.** **Fixed:** `profile_dir` is ignored, with a note, unless `advanced_signin_location` is
also `true`. Even then, network shares and mapped network drives are refused, and the sign-in status
says protection depends on the chosen drive. **Test:** `SmallerFindings.test_sign_in_location`.

## What's still true

Like any source review, this one can't prove the absence of other problems, and the threat model's
limits are unchanged: malware already running as your user, and administrators of your computer, are
outside what any app can defend against. Windows has no `O_NOFOLLOW`, so there the file-race protections
rely on checking the open file's real path. They were written to the documented Windows APIs, but the
tests exercise the POSIX path; a Windows CI job would confirm the Windows path.
