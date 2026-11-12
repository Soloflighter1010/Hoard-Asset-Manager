# Library and Downloads in one app

Issue #321 replaces page navigation with one document. `/`, `/index.html` and
`/downloads` serve the same shell; links and Back/Forward retain their public
addresses and hash parameters. Modified clicks and external links retain browser
behavior. The bar, windows, details element, access key and polling survive a view
change. Product selection is cleared when moving between views.

## Ownership

- `hoard/web/library.html` contains the common markup. `downloads.html` contains
  Downloads' styles, a template for its store tabs, and its additional windows.
  The two older stylesheets remain separate during this incremental migration;
  only the active view's stylesheet applies. Downloads now uses `#storeSeg`, as
  Library does; `#stores` consistently identifies the Stores window.
- `app.js` owns navigation and the data cache. One authenticated request for each
  existing API projection populates the cache. A tab change does not request the
  products, tags, sets or settings again. Successful mutations invalidate both
  projections; concurrent refreshes coalesce, and a response overtaken by a
  mutation is refreshed before publication. Progress and UI-only state do not
  invalidate the product cache. Explicit refreshes and completed jobs still do.
- `library.js` and `downloads.js` keep view filters and indexes in closures.
  `view-common.js` owns the formerly duplicated request, tag-manager, settings,
  download-progress and window wiring helpers. Shared windows are wired once;
  view listeners are admitted only for their active view, with persistent windows
  retaining their owner's handlers.
- `products.js` renders one tile and one details frame for both projections.
  Names, creators, notes, paths and other dynamic values use text nodes and DOM
  attributes. View models provide badges, facts and actions. Existing escaped
  detail sections and the package tree cross `legacyFragment`, a deliberately
  narrow migration boundary; new sections must not introduce HTML interpolation.
- `shared.js` retains existing window behavior and translation helpers. The
  shell's property getters adapt those helpers to the active view. This is a
  compatibility boundary, not a new general-purpose component API; new components
  should take explicit models, as `products.js` does.

Initial navigation fetches both projections, so first load does more work than
one of the former pages alone. Subsequent tab changes avoid document, script and
product reloads. This tradeoff is covered by request-count and DOM-identity tests,
not a claim that every initial-load workload is faster.

## Svelte: Look inside and the pop-ups

`ui/` holds the pages' Svelte components; `ui/main.js` exposes them as one global, `HoardUI`, with a small boundary
for each:

- **Look inside** (`ui/LookInside.svelte`, `HoardUI.inside`): the window's filename, code summary, search field and
  extraction controls. It mounts once and updates its model without replacing the search field or open folders. The
  existing lazy package tree is attached as an owned DOM fragment while that part is migrated separately.
- **The pop-ups** (`ui/Dialog.svelte`, `HoardUI.dialogs`): a question (`ask`), a name or a tag (`askName`), a folder
  (`askFolder`) and a choice from a list (the set picker), as one card like a product's details: an icon, the title in
  the display font, a line under it, a close button, and the buttons under a hairline. `open(spec)` returns a promise
  of the answer; `heading(text)` turns a translated question into its title and what follows (at its `?` or `？`, else
  its first sentence; a box's title also at a colon). The wrappers in `shared.js` keep their signatures, so their
  callers didn't change, and the ids the pages and tests know (`#askDialog`, `#askText`, `#askName`, `#askFolder`,
  buttons valued `yes` and `no`). The tag prompt offers your tags as chips, in place of the browser's own list.
  The card's styles live in the component; a style's corners come from `--dlg-radius` and `--dlg-field-radius`
  (`web/looks.css`). The pop-ups still built in `shared.js` (`pjDialog`: Projects, Git, backups, KonoAsset) and the
  pages' own (support, PIN) take the same ground, outline, corners and backdrop from the pages' CSS until they move
  over. The style guide draws the component itself, in place (`dialogs.example`).

Neither uses `{@html}` or accepts user text as markup. `node scripts/build_ui.mjs` compiles `ui/main.js` into
`hoard/web/ui.generated.js` and copies the licenses of the bundled runtime packages to `hoard/web/ui.LICENSE.txt`. The
bundle is checked in; Python launches and the Nuitka builds need no Node runtime. Changes to the components require
`npm ci --ignore-scripts` and a rebuild. CI runs the builder with `--check`, including license drift. The parser for
translation keys uses Svelte's syntax tree for `.svelte` sources and Acorn for JavaScript; generated minified code is
not treated as the translation source.

Measured locally on Linux with Node 22, Svelte 5.57.3 and esbuild 0.28.2:

| Cost | Look inside alone | With the pop-ups |
| --- | --- | --- |
| Generated script | 57,407 bytes | 85,924 bytes |
| Gzip script | 21,340 bytes | 31,512 bytes |
| Build/check run | 66–94 ms | about 190–230 ms |
| New runtime dependencies in Python/app installer | None | None |
| Bundled JS runtime packages | Svelte, clsx, esm-env | the same; MIT texts shipped |

The trial's first decision kept Svelte to Look inside until a wider move was measured on the desktop runtimes. With
the apps now built on Tauri (WebView2 on Windows, WebKit on macOS and Linux), the pop-ups moved over as the second
part: about 10 KB compressed on top of the runtime already shipped, for one look and one place for every pop-up's
behaviour (focus, Escape, a click outside, an input method's Enter). `tests/test_dialogs.py` covers them in Chromium.
`scripts/ui_engines.py` checks each pop-up's answers and times them in another engine, and the Engines workflow
(`.github/workflows/engines.yml`) runs it on WebKit (macOS, and Linux as WebKitGTK's stand-in) and on Edge, whose
engine is WebView2's, whenever `ui/` or the pages change; each run's summary has its table.

| Engine (where measured) | Bundle read and run, once | A pop-up made and shown (first; middle; 90th percentile) | To its next frame |
| --- | --- | --- | --- |
| Chromium 153 (Playwright's, Linux, this change) | 15.5 ms | 15.0; 4.0; 5.7 ms | 12.9 ms |
| WebKit (macOS), Edge (Windows), WebKit (Linux) | from the Engines workflow's first run | | |
