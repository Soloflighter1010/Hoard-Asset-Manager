// One app lifetime: shared windows and listeners, cached projections, and history across Library/Downloads.
// View closures keep their filters and details; global getters are a compatibility boundary for shared.js while
// older sections are migrated to explicit models. New product components receive their inputs as arguments.
const APP = { active: /\/downloads$/.test(location.pathname) ? "downloads" : "library", views: {}, generation: 0, pending: null,
  cache: null, dirty: true, revision: 0, rescan: false, turn: 0, given: {} };

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
  if (/^\/api\/(?:tasks\/pictures|tasks\/background|touch|ui|loading|support|link)(?:\/|$)/.test(url)) return;
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
  // (the Menu's version line: its own mark, as a project's packages carry data-version for theirs, issue #398)
  for (const node of document.querySelectorAll("[data-hoard-version]")) node.textContent = `Hoard ${current.version || ""}`;
  if (!UPDATE) showUpdate();
  // Inactive indexes are prepared first so shared windows can access either kind of product immediately. One that
  // already has this snapshot isn't prepared again: changing tabs did it for both views each time (issue #435).
  // (prepared for the parts of Hoard turned on now, too: a part turned off or on in Settings filters it again)
  const other = APP.active === "library" ? "downloads" : "library";
  const off = featuresOff(), had = APP.given[other];
  if (!had || had.data !== data[other] || had.off !== off) { APP.given[other] = { data: data[other], off }; await APP.views[other].refreshView(data[other]); }
  if (generation !== APP.generation) return;
  APP.given[APP.active] = { data: current, off };
  await APP.views[APP.active].refreshView(current);
  syncBrowse();   // canPick reads the active view's DATA, which refreshView has now replaced
  drawHeap();
  return (current.assets || current.items || []).length;
}
// Change the view without replacing the document, windows, access key, data cache or background polling. The last
// tab asked for wins (issue #435): its tab is marked first, and the view is shown and drawn from what Hoard has read
// before the click is done (the pages, and their tests, count on that), then read again; a switch whose read is still
// under way when another is asked for stops there, so it never finishes after the later one, or draws a view no
// longer wanted. A switch overtaken by another isn't done until that one is: what waits on it (a link opening a
// product, Downloads opened to choose for a project) carries on once the page is where it ends up.
function activateView(restoreWindows = true) {
  const run = switchView(restoreWindows);
  APP.latest = run;
  return run;
}
// The switch itself (activateView): undefined once it's done, or the one that overtook it, to wait for.
async function switchView(restoreWindows) {
  const turn = ++APP.turn;
  const next = /\/downloads$/.test(location.pathname) ? "downloads" : "library";
  markBar(next === "library" ? "/" : "/downloads");   // (until the view says which of its pages it's on)
  const tab = document.querySelector(`.apptabs a[href="${CSS.escape(location.pathname + location.hash)}"]`);
  if (tab) markBar(tab.getAttribute("href"));   // (a tab for this very page, as Local's and Sets': marked as it's chosen)
  // Until it's shown, the address is the place asked for: nothing the page draws meanwhile (a product's details still
  // open, as Back closes them) writes its own place over it. A later switch's own, once it's begun.
  NAV.quiet = true;
  try {
    if (next !== APP.active) {
      APP.views[APP.active].closeDetail();
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
    if (next === "downloads" && !$("#drives")) $("#storeSeg").replaceChildren($("#downloadsStores").content.cloneNode(true));
    const tile = UI[next === "downloads" ? "dl_tile_size" : "tile_size"];
    if (tile) setZoom(tile);
    APP.views[next].readHash();
    if (APP.cache) APP.views[next].render();
    await load(false, true);
  } finally { if (turn === APP.turn) NAV.quiet = false; }   // (a later switch's own, until it's done)
  if (turn !== APP.turn) return APP.latest;
  if (restoreWindows) goToAddress();
  else { NAV.at = null; saveHash(); }   // a fresh launch keeps the established behavior: windows start closed
  tourResume();
  if (next === "downloads") pickResume();
  else { try { sessionStorage.removeItem(PICK_KEY); } catch (e) { /* no storage: nothing kept */ } }   // (Downloads, left before it opened)
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
  addEventListener("popstate", () => {
    // A step Hoard went back over itself (a window closed: setAddress, shared.js) is already shown, and its address
    // is the older one until goToAddress puts the newer in its place. Reading it would undo what's changed since:
    // a search typed as Settings closed came back empty when this arrived late.
    if (NAV.back !== null) { goToAddress(); return; }
    activateView();
  });
  const askedSetup = /(^|[#&])setup\b/.test(location.hash);
  try {
    await activateView(false);
    if (APP.active === "library" && (askedSetup || (!DATA.setup_done && !DATA.items.length && !DATA.error))) openSetup();
  } finally { hideSplash(); }
}
startApp();
