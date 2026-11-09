// One app lifetime: shared windows and listeners, cached projections, and history across Library/Downloads.
// View closures keep their filters and details; global getters are a compatibility boundary for shared.js while
// older sections are migrated to explicit models. New product components receive their inputs as arguments.
const APP = { active: /\/downloads$/.test(location.pathname) ? "downloads" : "library", views: {}, generation: 0, pending: null,
  cache: null, dirty: true, revision: 0, rescan: false };

// Shared listeners have one owner and are installed exactly once.
function shellListen(target, type, callback, options) { target.addEventListener(type, callback, options); }
// Keep legacy view handlers installed once. Persistent windows continue to work when the underlying view changes.
function viewListen(view, target, type, callback, options) {
  const persistent = target instanceof Element && target.closest("#stores, #setup, #itchDialog, #localPanel, #insideWin");
  target.addEventListener(type, event => {
    if (APP.active === view || persistent) return callback.call(target, event);
  }, options);
}
// A successful mutation invalidates both projections. Progress, touches and UI-only state do not reload products.
function invalidateAppData(url, options = {}) {
  if (url === "/api/settings") {
    try {
      const body = JSON.parse(options.body || "{}");
      if (Object.keys(body).length === 1 && body.ui) return;
    } catch (error) { /* An unfamiliar body must invalidate the cache. */ }
  }
  if (/^\/api\/(?:tasks\/pictures|tasks\/background|touch|ui|loading|support)(?:\/|$)/.test(url)) return;
  APP.revision++; APP.dirty = true;
}
// Fetch one complete projection with the authenticated transport and consistent, safe error messages.
async function fetchProjection(url) {
  const response = await api(url);
  if (!response.ok) throw new Error(response.status === 401 ? NEEDS_KEY : `The library server answered ${response.status}.`);
  return response.json();
}
// Coalesce concurrent refreshes and discard a response made stale by a mutation while it was in flight.
async function appData(rescan = false, force = false) {
  APP.rescan ||= rescan;
  if (force) APP.dirty = true;
  if (APP.pending) { await APP.pending; return appData(false); }
  if (APP.cache && !APP.dirty && !APP.rescan) return APP.cache;
  const revision = APP.revision, scanning = APP.rescan;
  APP.rescan = false;
  // Both server projections report the same loading counter. Finish the library read before reading assets
  // so one request cannot clear the other's progress while the splash is still waiting.
  APP.pending = (async () => {
    const library = await fetchProjection("/api/library");
    const downloads = await fetchProjection("/api/assets" + (scanning ? "?rescan=1" : ""));
    APP.cache = { library, downloads }; APP.dirty = APP.revision !== revision;
  })();
  try { await APP.pending; } finally { APP.pending = null; }
  return APP.dirty || APP.rescan ? appData(false) : APP.cache;
}
// Refresh both indexes from one cached snapshot, rendering only the active projection. Existing callers request
// fresh data; navigation calls this with cached=true so changing tabs never reloads products, tags or settings.
async function load(rescan = false, cached = false) {
  const generation = APP.generation;
  let data;
  try { data = await appData(rescan, !cached); }
  catch (error) {
    const message = error instanceof TypeError ? "Hoard isn't running. Open it again." : error.message;
    data = { library: { items: [], stores: {}, labels: {}, job: {}, error: message }, downloads: { assets: [], error: message } };
  }
  if (generation !== APP.generation) return;
  const current = data[APP.active];
  watchUnlock(current.privacy);
  $("#quitRow").hidden = !current.can_quit;
  applyDisplay(current.display); applyUi(current.ui);
  for (const [key, value] of Object.entries(current.store_sites || {})) STORE_SITES[key] = value;
  $("#version").textContent = current.version || "";
  for (const node of document.querySelectorAll("[data-version]")) node.textContent = `Hoard ${current.version || ""}`;
  if (!UPDATE) showUpdate();
  // Inactive indexes are prepared first so shared windows can access either kind of product immediately.
  const other = APP.active === "library" ? "downloads" : "library";
  await APP.views[other].refreshView(data[other]);
  if (generation !== APP.generation) return;
  await APP.views[APP.active].refreshView(current);
  syncBrowse();   // canPick reads the active view's DATA, which refreshView has now replaced
  drawHeap();
  return (current.assets || current.items || []).length;
}
// Change the view without replacing the document, windows, access key, data cache or background polling.
async function activateView(restoreWindows = true) {
  const next = /\/downloads$/.test(location.pathname) ? "downloads" : "library";
  const changing = next !== APP.active;
  if (changing) {
    NAV.quiet = true;
    try { APP.views[APP.active].closeDetail(); } finally { NAV.quiet = false; }
    APP.active = next; APP.generation++;
    closeBarMenu();
    sel.ids.clear(); sel.on = false; sel.anchor = null;
    if (selMenu) closeSelMenu();
  }
  document.documentElement.dataset.appView = next;
  $("#libraryStyles").media = next === "library" ? "all" : "not all";
  $("#downloadsStyles").media = next === "downloads" ? "all" : "not all";
  for (const node of document.querySelectorAll("[data-app-view]")) if (node !== document.documentElement)
    node.hidden = node.dataset.appView !== next;
  for (const link of document.querySelectorAll('.apptabs a[href="/"], .apptabs a[href="/downloads"], .apptabs a[href="/downloads#store=Local"]')) link.removeAttribute("aria-current");
  if (next === "library") $('.apptabs a[href="/"]').setAttribute("aria-current", "page");
  if (next === "downloads" && !$("#drives")) $("#storeSeg").replaceChildren($("#downloadsStores").content.cloneNode(true));
  const tile = UI[next === "downloads" ? "dl_tile_size" : "tile_size"];
  if (tile) setZoom(tile);
  NAV.quiet = true;
  try {
    APP.views[next].readHash();
    if (APP.cache) APP.views[next].render();
    await load(false, true);
  } finally { NAV.quiet = false; }
  if (restoreWindows) goToAddress();
  else { NAV.at = null; saveHash(); }   // a fresh launch keeps the established behavior: windows start closed
  tourResume(); if (next === "downloads") pickResume();
}
// Preserve / and /downloads links, modifiers, downloads and external links, but keep ordinary navigation in-app.
function navigateApp(raw) {
  const url = new URL(raw, location.href);
  if (url.origin !== location.origin || !["/", "/index.html", "/downloads"].includes(url.pathname)) { location.href = raw; return; }
  if (url.href !== location.href) history.pushState(null, "", url.pathname + url.search + url.hash);
  NAV.at = null; NAV.back = null;
  return activateView();
}
// Adapt old shared helpers to the active view; a unique window (Stores/Look inside) uses its owning view.
function connectViews() {
  APP.views = { library: createLibraryView(), downloads: createDownloadsView() };
  const names = new Set(Object.values(APP.views).flatMap(view => Object.keys(view)));
  for (const name of names) {
    if (["wire", "refreshView"].includes(name)) continue;
    Object.defineProperty(window, name, { configurable: true,
      get() { return (name in APP.views[APP.active] ? APP.views[APP.active] : APP.views.library[name] !== undefined ? APP.views.library : APP.views.downloads)[name]; },
      set(value) { const view = name in APP.views[APP.active] ? APP.views[APP.active] : APP.views.library[name] !== undefined ? APP.views.library : APP.views.downloads; view[name] = value; },
    });
  }
}
// Bootstrap once; direct links and later Back/Forward both use the same activation path.
async function startApp() {
  connectViews();
  document.documentElement.dataset.appView = APP.active;
  for (const view of Object.values(APP.views)) view.wire();
  wireTags(); wireApp(); wireTour();
  afterSetMade = () => load();
  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target || link.hasAttribute("download")) return;
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin || !["/", "/index.html", "/downloads"].includes(url.pathname)) return;
    event.preventDefault(); navigateApp(url.href);
  });
  addEventListener("popstate", () => activateView());
  const askedSetup = /(^|[#&])setup\b/.test(location.hash);
  try {
    await activateView(false);
    if (APP.active === "library" && (askedSetup || (!DATA.setup_done && !DATA.items.length && !DATA.error))) openSetup();
  } finally { hideSplash(); }
}
startApp();
