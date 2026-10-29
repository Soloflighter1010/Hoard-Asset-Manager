# Contributing to Hoard

Thank you for helping. Hoard keeps people's own files and signs in to their store accounts, so a change is held to
a few rules, most of which the tests check for you.

## Where to start

- **How Hoard fits together:** [docs/HOW-HOARD-WORKS.md](docs/HOW-HOARD-WORKS.md) is the map, part by part, with a
  sync walked through end to end. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has each part in depth, and
  [docs/DATA-FORMATS.md](docs/DATA-FORMATS.md) the files Hoard writes.
- **Running it from source, the tests, and the rules that keep Hoard safe:** the wiki's
  [Development](https://github.com/Soloflighter1010/Hoard-Asset-Manager/wiki/Development) page.
- **Something to work on:** the [issues](https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues). Say on
  one that you'd like to take it before you start, so two people don't do the same work.

## Proposing a change

1. Open an issue first for anything bigger than a small fix, so the approach can be agreed before you write it.
   Use the templates: a bug, a feature, a store's integration, or a translation fix.
2. Fork the repository and make your change on a branch of its own.
3. Run the tests (`python -m unittest discover -s tests`). Add a test for what you changed: a bug fixed has a test
   that failed before it.
4. Open a pull request against `main`, saying what it changes and why, with `Fixes #<number>` for the issue it
   closes. The **Check** workflow runs every test on Ubuntu and Windows, and builds every app.

A pull request is reviewed and merged by the maintainer. Only the maintainer's release workflow signs anything
([CODE_SIGNING.md](CODE_SIGNING.md)).

## What a change needs

- **Tests.** Everything is tested without a network or a store account: stores are stand-ins serving pages made
  up for the test. Never commit a real customer's page, purchase list or receipt.
- **The safety rules.** Every store request goes through `hoard/egress.py`; files are written with
  `write_file_safely`; store text is escaped; every page request goes through `api()`. The wiki's Development page
  lists them all, and the security tests enforce them.
- **Words, translated.** Everything the pages show is in Japanese and Korean too (`hoard/web/i18n/ja.json` and
  `ko.json`): `tests/test_i18n.py` finds what isn't. If you don't speak them, say so in the pull request, and a
  translation will be added before it's merged.
- **The wiki.** A change people will see is described in `wiki/` (in plain words: what happens and what to do,
  buttons named as they appear). When an English page changes, its Japanese and Korean pages are updated too;
  `python3 scripts/wiki_translations.py` shows which are behind.
- **Comments.** Each module, class and function says what it's for, in a sentence or two; anything that isn't
  obvious says why.
- **Dependencies.** Avoid new ones. When one is needed, change `requirements.in` and regenerate every locked list
  (each `.in` file says how); never edit a `.txt` by hand.

## Reporting a security problem

Privately, as [SECURITY.md](SECURITY.md) says: never in a public issue.

## Code of conduct

Be kind and patient: everyone here is helping in their own time. Harassment, or anything that targets a person,
isn't welcome, and gets a contribution or an account blocked.
