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

## Svelte trial: Look inside

The trial owns Look inside's filename, code summary, search field and extraction
controls in `ui/LookInside.svelte`. It mounts once and updates its model without
replacing the search field or open folders. The existing lazy package tree is
attached as an owned DOM fragment while that part is migrated separately. The
trial uses no `{@html}` and accepts no raw user text as markup. The existing
server-side extraction validation is unchanged.

`ui/inside.js` exposes only mount/update, extraction-progress update and unmount.
`node scripts/build_ui.mjs` compiles it into `hoard/web/inside.generated.js` and
copies the licenses of the bundled runtime packages. The bundle is checked in;
Python launches, PyInstaller and source releases require no Node runtime. Changes
to the component require `npm ci --ignore-scripts` and a rebuild. CI runs the
builder with `--check`, including license drift. The parser for translation keys
uses Svelte's syntax tree for `.svelte` sources and Acorn for JavaScript; generated
minified code is not treated as the translation source.

Measured locally on Linux with Node 24, Svelte 5.57.3 and esbuild 0.28.2:

| Cost | Result |
| --- | --- |
| Generated script | 57,407 bytes |
| Gzip script | 21,340 bytes |
| Three warm build/check runs | 66–94 ms |
| New runtime dependencies in Python/app installer | None |
| Bundled JS runtime packages | Svelte, clsx, esm-env; MIT texts shipped |
| Translation calls found in component source | 10 |
| Existing Look inside browser tests | 8 tests, two shuffled runs; both passed |

Decision: keep this bounded trial and its existing browser tests; do not migrate
more windows to Svelte in this change. The trial improves ownership of controls
and focus, but adds a compiler/build dependency and about 21 KB compressed while
the legacy tree remains. A wider migration should follow a complete tree
conversion and a measured comparison on the actual desktop runtimes. This Linux
browser result does not establish performance on WebView2 or WebKit.
