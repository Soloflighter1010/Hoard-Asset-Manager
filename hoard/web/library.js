// Owned products and store management: a view over the app's cached data.
// The shell owns navigation, shared windows, requests and the product components.
function createLibraryView() {
// first, or it applies to nothing
const STORE_ORDER = ["booth", "gumroad", "jinxxy", "payhip", "itch"];
const shown = s => (DATA.enabled || {})[s] !== false;   // stores you don't use (Settings, or setup) are hidden
// The stores shown, in the page's order.
const usedStores = () => STORE_ORDER.filter(shown);
// The stores you can import saved pages for, and the ones Hoard downloads from (Payhip is only read). The server
// says which; these are the same, for before it has.
const importable = s => (DATA.importable || ["booth", "jinxxy", "payhip", "itch"]).includes(s);
// Whether Hoard downloads from a store.
const downloadable = s => (DATA.downloadable || ["booth", "gumroad", "jinxxy", "itch"]).includes(s);
let importStore = null, importing = null;
const state = { view: "library", q: "", store: "", set: "", tags: new Set(), creator: "", sort: "name", allTags: false, creatorFind: "", copies: null, disk: "", fresh: false, ptype: "" };
// Downloaded, or not yet (issue #17): "yes", "no", or "" for both
const DISK = { yes: "Downloaded", no: "Not downloaded yet" };
// Whether a product is downloaded.
const onDisk = a => a.on_disk != null;
let DATA = { items: [], stores: {}, labels: {}, job: {} }, byKey = new Map(), openKey = null, lastFocus = null, polling = null;

// A store's name.
const label = s => DATA.labels[s] || s;
// A tile's letters and colour, for a product with no picture.
const placeholder = a => `<span class="ph" style="--h:${hue(a.creator)}"><b>${esc(initials(a.name))}</b></span>`;
// A product's picture (or its letters).
const thumb = a => a.thumbnail ? `<img src="${keyed("/thumb/" + encodeURIComponent(a.key))}" alt="" loading="lazy" decoding="async">` : placeholder(a);
// How long ago a time was, in words ("5 min ago").

/* ---------- highlights and accessibility */

// Send a change to Hoard, as JSON, and return its answer. Throws with Hoard's reason when it says no.


/* ---------- data */
async function refreshView(response) {
  DATA = response;
  for (const a of DATA.items) withStoreTags(a).hay = norm([a.name, a.creator, label(a.store), a.variants, ...a.tags, ...a.suggested, a.your_note].join(" "));
  byKey = new Map(DATA.items.map(a => [a.key, a]));
  if (APP.active !== "library") return;
  renderStores(); render(); showJob(DATA.job);
  if (DATA.job && DATA.job.running) startPolling();
  if (openKey && byKey.has(openKey)) showDetail(byKey.get(openKey), false);
  else if (openKey) forgetDetail();   // no longer shown (a hidden item, once locked): its details go too
  // copies on two stores whose pictures may be one picture saved twice: how they look decides (then read again)
  const wanted = DATA.items.filter(a => a.look_for && a.thumbnail).map(a => ({ look_for: a.look_for, src: keyed("/thumb/" + encodeURIComponent(a.key)) }));
  tourOffer();   // (once there's something in the library)
  showSpots();   // (what's new, after an update: issue #244)
  if (wanted.length && await lookAtPictures(wanted)) load();
}

/* ---------- filtering */
function matches(a, skip) {
  if (inSets() && !state.set) return false;   // (every set's tile: no product's)
  if (!(inSets() ? setHas(a) : inView(a))) return false;   // a set's folder: all of it, archived or not
  if (state.copies && (a[state.copies.field] !== state.copies.key || (state.copies.store && a.store !== state.copies.store))) return false;
  if (skip !== "disk" && state.disk && (state.disk === "yes") !== onDisk(a)) return false;
  if (skip !== "fresh" && state.fresh && !a.new) return false;
  if (state.store && !inSets() && a.store !== state.store) return false;   // (Sets: every set's tile, or the one open)
  if (skip !== "creator" && state.creator && a.creator !== state.creator) return false;
  if (skip !== "ptype" && state.ptype && a.type !== state.ptype) return false;   // what it is (issue #223)
  if (!shown(a.store)) return false;
  for (const t of state.tags) if (!a.tags.includes(t) && !a.suggested.includes(t)) return false;
  if (state.q && !searchMatches(a, state.q)) return false;   // (words, and prefixes: creator:, tag:...)
  return true;
}
const SORTS = {
  name: (a, b) => coll.compare(a.name, b.name),
  creator: (a, b) => coll.compare(a.creator, b.creator) || coll.compare(a.name, b.name),
  store: (a, b) => STORE_ORDER.indexOf(a.store) - STORE_ORDER.indexOf(b.store) || coll.compare(a.name, b.name),
  // the newest first; items listed before Hoard kept the time they appeared go last (issue #18)
  added: (a, b) => (b.added || "").localeCompare(a.added || "") || coll.compare(a.name, b.name),
};
SORTS.season = seasonSort(SORTS.added);   // the season's first (issue #261: shared.js)
// Whether any search or filter is narrowing the library down.
const filtersActive = () => state.ptype || state.q || state.store || state.creator || state.tags.size || state.copies || state.disk || state.fresh;

/* ---------- rendering */
// issue #111: copies of the same product (bought more than once, in several versions, or on two stores, by the same
// picture, name and creator: hoard/library.py) show as one tile. Choosing it shows them all, as "Copies of". Not
// while selecting, so each can be chosen.
let STACK = true, stackSize = new Map(), stackStores = new Map();   // the first copy's key -> how many copies, and their stores
// The key a product's copies share, or null.
const stackKey = a => a.stack_key || null;
// Each stack's copies here: in this view, from stores you use, whatever the filters, as "Copies of" shows them (it
// clears the filters); in a set, those in it. One on another store's tab, or by the creator's other name, is still
// in its stack; one archived, removed or hidden isn't (issue #247).
function stacksHere(list) {
  const all = new Map();
  for (const a of inSets() ? list : DATA.items.filter(a => inView(a) && shown(a.store)))
    if (stackKey(a)) all.set(stackKey(a), [...(all.get(stackKey(a)) || []), a]);
  return all;
}
// The products with each one's copies shown as one tile (counting them), unless copies aren't stacked.
function stacked(list) {
  stackSize = new Map(); stackStores = new Map();
  if (!STACK || sel.on || state.copies) return list;
  const all = stacksHere(list), first = new Set(), out = [];
  for (const a of list) {
    const k = stackKey(a), copies = (k && all.get(k)) || [];
    if (copies.length > 1) {
      if (first.has(k)) continue;
      first.add(k); stackSize.set(a.key, copies.length); stackStores.set(a.key, new Set(copies.map(o => o.store)));
    }
    out.push(a);
  }
  return out;
}
// "Copies of": every copy, whatever the filters were: a stack's (stack_key), or the same product on any store ("others").
function showCopies(a, field = "match_key") {
  state.copies = { field, key: a[field], name: a.name, store: "" };
  state.q = ""; state.store = ""; state.creator = ""; state.disk = ""; state.fresh = false; state.tags.clear(); render();
}
// Draw the library as it is now: the tiles, filters, counts and status, and the address.
function render() {
  if (APP.active !== "library") return;
  if (!inSets()) state.set = "";
  wishScope();
  const list = DATA.items.filter(a => matches(a)).sort(SORTS[state.sort]);
  renderViews(); renderStoreSeg(); renderGrid(stacked(list)); markSelected(); renderFacets(list); renderStatus(list); syncControls(); saveHash(); renderTagPanel();
  drawSets();
}
// The store tabs count what's in the view you're in (Library, Archive...), so they're drawn with everything else: drawn
// only as the library loaded, a load while you were in another view (a routine check finishing, say) left them
// counting that view (all 0 in Hidden) once you came back.
let storeSegShown = "";
// The store tabs, each with how many products the view has from it.
function renderStoreSeg() {
  const counts = {};
  const here = DATA.items.filter(inView);
  for (const a of here) counts[a.store] = (counts[a.store] || 0) + 1;
  const html = `<button role="radio" data-store="" aria-checked="${!state.store}">Everything<span class="n">${here.length.toLocaleString()}</span></button>` +
    usedStores().filter(s => counts[s] || DATA.stores[s]).map(s =>
      `<button role="radio" class="${s}" data-store="${s}" aria-checked="${state.store === s}">` +
      `<span class="dot ${s}"></span>${label(s)}<span class="n">${(counts[s] || 0).toLocaleString()}</span></button>`).join("") +
    `<button role="radio" class="sets" data-store="Sets" aria-checked="${inSets()}"><span class="dot sets" aria-hidden="true"></span>${esc(tr("Sets and Wishlists"))}<span class="n">${(DATA.sets || []).length.toLocaleString()}</span></button>`;
  if (html !== storeSegShown) { $("#storeSeg").innerHTML = html; storeSegShown = html; }   // (not on every keystroke)
}
// The Stores panel: each store, whether you're signed in, its count, and its buttons.
function renderStores() {
  const job = DATA.job || {};
  $("#storeRows").innerHTML = usedStores().map(s => {
    const info = DATA.stores[s] || {};
    const busy = job.running;
    // Sign in or Sign out, whichever applies (itch.io's sign-in is its API key)
    const signedIn = s === "itch" ? !!DATA.itch_key : !!(DATA.signed_in || {})[s];
    const meta = (info.updated ? `${plural(info.count, "item", "items")}, ${info.source === "import" ? "imported" : "refreshed"} ${ago(info.updated)}` : "Not refreshed yet")
      + (downloadable(s) ? "" : ". Listed, not downloaded");
    return `<div class="store-row"><span class="nm"><span class="dot ${s}"></span>${label(s)}</span>` +
      `<span class="meta">${esc(meta)}</span>` +
      `<span class="btns">` + (s === "itch"
        ? `<button class="ghost sm" data-login="${s}" ${busy ? "disabled" : ""}>${DATA.itch_key ? "Change API key" : "Add API key"}</button>`
        : signedIn ? "" : `<button class="ghost sm" data-login="${s}" ${busy ? "disabled" : ""}>Sign in</button>`) +
      `<button class="ghost sm" data-refresh="${s}" ${busy ? "disabled" : ""}>Refresh</button>` +
      (info.source === "import" ? "" : `<button class="ghost sm" data-quick="${s}" ${busy ? "disabled" : ""}>Quick refresh</button>`) +
      (downloadable(s) ? `<button class="ghost sm" data-download="${s}" ${busy ? "disabled" : ""}>Download</button>` : "") +
      (importable(s) ? `<button class="ghost sm" data-import="${s}" ${importing ? "disabled" : ""}>Import pages</button>` : "") +
      (signedIn ? `<button class="ghost sm" data-logout="${s}" ${busy ? "disabled" : ""}>Sign out</button>` : "") + `</span>` +
      (info.error ? `<span class="err${/^Signed out/.test(info.error) ? " info" : ""}">${esc(info.error)}${!/^Signed out/.test(info.error) ? ` <button class="linkish" data-report-store="${esc(s)}">Create report</button>` : ""}</span>` : "") +
      ((info.found_shops || []).length ? `<span class="found">${esc(tr(info.found_shops.length === 1 ? "Your library has products from {0} more Payhip shop on its own address."
                                                                      : "Your library has products from {0} more Payhip shops on their own addresses.", info.found_shops.length))} ` +
        `<button class="linkish" data-review-shops>Review</button></span>` : "") +
      `</div>`;
  }).join("");
  renderStoreHealth();
  $("#refreshAll").disabled = $("#quickRefresh").disabled = !!job.running;
  $("#downloadAll").hidden = !usedStores().some(downloadable);
  $("#importPages").disabled = $("#importFolder").disabled = !!importing;
  $("#signOutAll").disabled = !!job.running;
  $("#signinsPath").textContent = DATA.signins ? ` (${DATA.signins})` : "";
  // switch between the two messages; never replace them, since every refresh updates the parts inside
  const unprotected = (DATA.signins_note || "").startsWith("not saved");
  $("#signinsText").hidden = unprotected;
  $("#signinsMissing").hidden = !unprotected;
  if (DATA.signins_note && !unprotected) $("#signinsNote").textContent = DATA.signins_note;
  $("#warnDot").hidden = !Object.values(DATA.stores).some(s => s.error && !/^Signed out/.test(s.error));
  $("#menuDot").hidden = $("#warnDot").hidden;   // (Stores is in the Menu)
  showSpots();   // (what's new here, after an update: issue #244)
}
// Health is made from bounded server categories. Use text nodes for every displayed value.
function renderStoreHealth() {
  const operations = { library: tr("Library"), wishlists: tr("Wishlists"), list_files: tr("Files"),
    download_file: tr("Downloads"), check_updates: tr("Updates") };
  const problems = { signin: tr("Sign in again, then retry."), blocked: tr("The store blocked its automated browser."),
    network: tr("The store could not be reached."), layout: tr("The store page could not be read."),
    empty: tr("The store returned no items; the previous library was kept."), partial: tr("Some items could not be read or downloaded.") };
  for (const [index, store] of usedStores().entries()) {
    const row = $("#storeRows").children[index], health = (DATA.store_health || {})[store] || {};
    const readings = Object.entries(health.operations || {});
    const success = readings.map(([, info]) => info.last_success).filter(Boolean).sort().pop();
    const status = document.createElement("span"); status.className = "store-health meta";
    status.textContent = success ? tr("Last read successfully: {0}", ago(success)) : tr("No successful read recorded yet.");
    row.append(status);
    for (const [operation, info] of readings) {
      if (!info.problem || !problems[info.problem]) continue;
      const detail = document.createElement("span"); detail.className = "store-health err";
      detail.append(document.createTextNode((operations[operation] || "") + ": " + problems[info.problem] + " "));
      // The server creates a fixed GitHub URL containing only store/version/operation/failure.
      const address = new URL(info.report_url || "", location.href);
      if (address.origin === "https://github.com" && address.pathname === "/Soloflighter1010/Hoard-Asset-Manager/issues/new") {
        const report = document.createElement("a"); report.href = address.href;
        report.target = "_blank"; report.rel = "noopener noreferrer";
        report.textContent = tr("Report a problem"); detail.append(report);
      }
      row.append(detail);
    }
  }
}
// Gifts (issue #263) are wrapped until you first open one; the ones you've opened are remembered (Hoard's config: ui).
let giftsOpened = null;
// Is this a gift not opened yet?
const isWrapped = a => a.gift && !(giftsOpened ||= new Set(UI.unwrapped || [])).has(a.key);
// Open a gift: remembered, and its tile's paper lifts away.
function unwrap(a) {
  if (!isWrapped(a)) return;
  giftsOpened.add(a.key);
  uiSave({ unwrapped: [...giftsOpened] });
  const tile = document.querySelector(`.slot[data-key="${CSS.escape(a.key)}"]`);
  if (tile) { tile.classList.replace("wrapped", "unwrapping"); setTimeout(() => tile.classList.remove("unwrapping"), 800); }
}
// A product's tile: its picture, name, creator, store and marks (copies, downloaded, new).
// The Library's values for the shared product tile; productTile owns its DOM and accessibility.
const slotHTML = a => {
  const n = stackSize.get(a.key) || 0, wrapped = isWrapped(a), store = label(a.store);
  const [status, statusKind] = onDisk(a) ? (a.update ? ["Update", "upd"] : ["Downloaded", "ok"])
    : !downloadable(a.store) ? ["Listed", ""] : a.new ? ["New", "new"] : ["Not downloaded yet", ""];
  return productTile(a, { key: "key", id: a.key, current: a.key === openKey, store: a.store, storeName: store,
    src: a.thumbnail ? keyed("/thumb/" + encodeURIComponent(a.key)) : "", count: n, wrapped, downloaded: onDisk(a),
    others: n > 1 ? [...a.also_in, ...(stackStores.get(a.key) || [])] : a.also_in,
    description: [tr("{0}, by {1}, from {2}", a.name, a.creator, store), n > 1 && tr("{0} copies: choose to see them all", n),
      a.also_in.length && tr("also on {0}", listed(a.also_in.map(label))), onDisk(a) && tr("downloaded"), a.new && tr("new"),
      wrapped && tr("a gift, not opened yet"), a.your_note && tr("has a note")],
    badges: [n > 1 && { kind: "count", text: `×${n}`, hidden: true }, a.new && { kind: "new", text: tr("New") },
      a.gift ? { text: tr("Gift") } : a.archived && { text: tr("Archived") }],
    status: tr(status), statusKind, added: shortDay(a.added),
  });
};
// Draw the tiles (or why there are none).
function renderGrid(list) {
  (cards = cards || lazyCards($("#grid"))).show(list, slotHTML);
  const empty = $("#empty");
  if (DATA.error) {
    empty.innerHTML = `<h2>Can't reach your hoard</h2><p>${esc(DATA.error)}</p>`;
  } else if (!DATA.items.length) {
    empty.innerHTML = `<svg viewBox="0 0 64 64" aria-hidden="true"><g class="boxes heap">${heapMarkup(heapBoxes())}</g></svg><h2>Your hoard is empty</h2><p>Sign in to the stores you buy from and refresh them. ` +
      `Hoard reads what you've bought with your own login and doesn't download anything.</p>` +
      `<p><button class="primary" id="openStores">Set up stores</button></p>`;
  } else if (!list.length) {
    empty.innerHTML = `<h2>Nothing in your hoard matches that</h2><p><button class="linkish" data-clear="all">Clear filters</button></p>`;
  }
  empty.hidden = list.length > 0 || (inSets() && !DATA.error && DATA.items.length > 0);   // (Sets says what it has)
}
// The filters for the products shown: tags, downloaded or not, and creators.
function renderFacets(list) {
  renderTagFacets(list);

  const dn = { yes: 0, no: 0 };
  for (const a of DATA.items) if (matches(a, "disk")) dn[onDisk(a) ? "yes" : "no"]++;
  const fresh = DATA.items.filter(a => a.new && matches(a, "fresh")).length;
  $("#disk").innerHTML = Object.entries(DISK).map(([k, l]) =>
    `<button class="chip" data-disk="${k}" aria-pressed="${state.disk === k}">${l}<span class="n">${dn[k]}</span></button>`).join("") +
    (fresh || state.fresh ? `<button class="chip" data-fresh aria-pressed="${state.fresh}">New<span class="n">${fresh}</span></button>` : "");
  const wish = openWish(), cc = wish ? wishCreators(wish) : new Map();   // (a wishlist open: its products' creators)
  if (!wish) for (const a of DATA.items) if (matches(a, "creator")) cc.set(a.creator, (cc.get(a.creator) || 0) + 1);
  if (state.creator && !cc.has(state.creator)) cc.set(state.creator, 0);
  const f = norm(state.creatorFind);
  $("#creators").innerHTML = [...cc].filter(([c]) => !f || norm(c).includes(f)).sort((x, y) => coll.compare(x[0], y[0]))
    .map(([c, n]) => `<li><button data-creator="${esc(c)}" aria-pressed="${state.creator === c}"><span>${esc(c)}</span><span class="n">${n}</span></button></li>`).join("");
  const both = DATA.items.filter(a => a.also_in.length).length;
  $("#totals").textContent = DATA.items.length
    ? `${DATA.items.filter(a => inView(a) && shown(a.store)).length} things from ${Object.keys(DATA.stores).filter(s => DATA.stores[s].count).length} stores.` +
      (both ? ` ${both} are owned on more than one store.` : "")
    : "";
}
// The status line: what's searched and filtered (each to clear), and how many things are shown.
function renderStatus(list) {
  const pills = [];
  if (state.copies) pills.push(["copies", "", "Copies of", state.copies.name]);
  if (state.q) pills.push(["q", "", "Search", state.q]);
  if (state.store && !inSets()) pills.push(["store", "", "Store", label(state.store)]);   // (Sets says where you are)
  if (state.creator) pills.push(["creator", "", "Creator", state.creator]);
  if (state.disk) pills.push(["disk", "", "Show", DISK[state.disk]]);
  if (state.fresh) pills.push(["fresh", "", "Show", "New"]);
  for (const t of state.tags) pills.push(["tag", t, "Tag", t]);
  if (state.ptype) pills.push(["ptype", "", "Product type", tr(PRODUCT_TYPES[state.ptype] || state.ptype)]);
  const total = DATA.items.filter(a => inView(a) && shown(a.store)).length;   // this view: Library, Archive, ...
  // "1 thing" or "n things".
  const things = n => `${n} ${n === 1 ? "thing" : "things"}`;
  for (const [a, here] of [[$('.apptabs a[href="/"]'), !inSets()], [$('.apptabs a[href="/#store=Sets"]'), inSets()]])
    if (a) { if (here) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
  document.title = inSets() ? tr("Hoard: Sets") : "Hoard";
  $("#count").hidden = !total || (inSets() && !!state.set);   // (a set open has its own heading)
  $("#count").innerHTML = inSets() ? esc(setsCountText()) : filtersActive()
    ? `${list.length} <span class="of">of ${things(total)}</span>`
    : `${things(total)} ${{ archive: "in your archive", removed: "removed", hidden: "hidden" }[state.view] || "in your hoard"}`;
  $("#status").innerHTML =
    pills.map(([k, v, l, text]) => `<button class="pill" data-clear="${k}" data-v="${esc(v)}" aria-label="Remove ${l.toLowerCase()} filter ${esc(text)}">` +
      `<b>${l}</b> ${esc(text)}<span aria-hidden="true">×</span></button>`).join("") +
    (pills.length > 1 ? `<button class="linkish" data-clear="all">Clear all</button>` : "");
}
// Put the search box, tabs and sort as the state says, and the glow in the store's colour.
function syncControls() {
  if ($("#q").value !== state.q) $("#q").value = state.q;
  for (const b of $("#storeSeg").children) b.setAttribute("aria-checked", String(b.dataset.store === state.store));
  // the stores you're signed in to (read, and not signed out since), for Everything's glow
  setGlow(inSets() ? "" : state.store, usedStores().filter(s => { const i = DATA.stores[s] || {};
    return i.updated && !/^(Not signed in|Signed out)/.test(i.error || ""); }));
  $("#sort").value = state.sort;
}

/* ---------- refresh and sign-in */
function showJob(job) {
  const el = $("#job");
  el.hidden = !(job && job.running && job.message);
  el.textContent = job && job.message || "";
  taskCount(job && job.running ? 1 + (job.queue || []).length : 0);
}
// Follow a job while it runs, reading the library again when its counts change.
function startPolling() {
  if (polling) return;
  let lastCounts = JSON.stringify(DATA.stores);
  polling = setInterval(async () => {
    try {
      const r = await api("/api/status"); const s = await r.json();
      DATA.job = s.job; showJob(s.job);
      const counts = JSON.stringify(s.stores);
      if (counts !== lastCounts) { lastCounts = counts; await load(); }
      else renderStores();
      if (!s.job.running) {
        clearInterval(polling); polling = null; await load();
        const errs = Object.entries(DATA.stores).filter(([, v]) => v.error && !/^Signed out/.test(v.error)).map(([k]) => label(k));
        if (s.job.error) toast(s.job.error);
        else if (s.job.message && /^Signed out/.test(s.job.message)) toast(s.job.message);
        else toast(errs.length ? `Updated. ${errs.join(" and ")} need attention in Stores.` : "Hoard updated");
        if (errs.length || s.job.error) openStores(true);
      }
    } catch (e) { clearInterval(polling); polling = null; showJob(null); }
  }, 1000);
}
// Start a sign-in, refresh or sign-out for some stores (all: every product, not only what's new).
async function runJob(url, stores, all = false, more = {}) {   // more: what else the job's asked (a quick refresh's quick)
  if (!navigator.onLine && !url.endsWith("logout")) {
    toast(url.endsWith("/login") ? "You're offline. Signing in needs a connection." : "You're offline. Refreshing needs a connection.");
    return;
  }
  try {
    const answer = await post(url, { ...more, stores, all });
    if (answer.queued) { toast("Queued: it starts when what's running now is done. See Tasks."); startPolling(); return; }
    DATA.job = { running: true, message: url.endsWith("/login") ? "Opening a browser window" : url.endsWith("logout") ? "Signing out" : "Starting" };
    showJob(DATA.job); renderStores(); startPolling();
    if (url.endsWith("/login")) toast(`Sign in to ${label(stores[0])} in the window that opened, then close it.`);
  } catch (e) { toast(e.message); }
}
// Open the Stores panel or close it (open: which; else the other way).
function openStores(open) {
  const p = $("#stores"); const show = open ?? p.hidden;
  p.hidden = !show; $("#storesBtn").setAttribute("aria-expanded", String(show));
}

/* ---------- detail */
// A Payhip purchase from a shop on its own address that isn't in your Payhip shops: Hoard opens no link of a shop you
// haven't added, so it has no Open on Payhip. Say why, and offer to add the shop (or, once added, to refresh).
function shopNote(a) {
  if (!a.payhip_shop) return "";
  const host = a.payhip_shop.replace(/^https:\/\//, "");
  return `<p class="note">${a.payhip_shop_added
    ? esc(tr("{0} is in your Payhip shops now: refresh Payhip to open this from here.", host))
    : esc(tr("This is from {0}, a Payhip shop on its own address that isn't in your Payhip shops, so Hoard doesn't open its links.", host)) +
      ` <button class="linkish" data-act="add-shop">${esc(tr("Add this shop"))}</button>`}</p>`;
}
// Add Payhip shops to the ones in your settings, read first: if they can't be, nothing is saved (it would replace them
// all). The response, or null.
async function addPayhipShops(add) {
  let current;
  try {
    const got = await api("/api/settings", { cache: "no-store" });
    if (!got.ok) throw new Error();
    current = (await got.json()).payhip_shops || [];
  } catch (e) { return null; }
  return apiPost("/api/settings", { payhip_shops: [...current, ...add] });
}
// Add a Payhip shop to read, once you say so.
async function addShop(shop) {
  const host = shop.replace(/^https:\/\//, "");
  if (!await ask(tr("Add {0} to your Payhip shops? Hoard will then open its products' links, and read your purchases there when you refresh Payhip. Only add a shop you bought from.", host), tr("Add it"))) return;
  const r = await addPayhipShops([shop]);
  toast(!r ? tr("Hoard didn't answer, so the shop wasn't added. Try again.")
    : r.ok ? tr("Added. Refresh Payhip to open its products from here.") : (r.data.error || tr("It wasn't added.")));
  if (r && r.ok) await load();
}
// Open a product's details: its picture, store, creator, tags, type, sets, files and buttons.
function showDetail(a, focus = true) {
  openKey = a.key;
  unwrap(a);   // (a gift, opened for the first time)
  markCurrent(`.slot[data-key="${CSS.escape(a.key)}"]`);
  const extra = [a.variants, a.gift && (a.gift_from ? tr("a gift from {0}", a.gift_from) : tr("gift")), a.archived && tr("archived on Gumroad")].filter(Boolean).join(", ");
  const store = label(a.store);
  // issue #108: one thing to do, in gold (download it, or see it in Downloads); the store's own pages, which open in
  // your browser, beside it and named for the store; archiving and the like under their own heading
  const outside = (raw, text) => `<a class="ghost" href="${esc(storeUrl(a.store, raw))}" target="_blank" rel="noopener noreferrer">${text}<span class="visually-hidden"> (opens in your browser)</span></a>`;
  const dlPage = storeUrl(a.store, a.download_url), page = storeUrl(a.store, a.url);
  const main = onDisk(a)
    ? `<a class="primary" href="/downloads#open=${a.on_disk}">Show in Downloads</a>` +
      (a.update ? `<a class="ghost" href="/downloads#view=updates&amp;open=${a.on_disk}">See the update</a>` : "")
    : downloadable(a.store) ? `<button class="primary" data-act="download">Download</button>`
    : dlPage ? `<a class="primary" href="${esc(storeUrl(a.store, a.download_url))}" target="_blank" rel="noopener noreferrer">Open on ${store}<span class="visually-hidden"> (opens in your browser)</span></a>` : "";
  const links = [downloadable(a.store) && dlPage && outside(a.download_url, `Open on ${store}`),
                 page && a.url !== a.download_url && outside(a.url, "Store page")].filter(Boolean).join("");
  const sections =
    (a.also_in.length ? `<p class="note">You also own this on ${a.also_in.map(label).join(" and ")}. ` +
      `<button class="linkish" data-act="others">Show all copies</button></p>` : "") +
    stackNote(a) +
    `<div class="actions">${main}</div>` +
    `<p class="copy">${onDisk(a) ? `<span class="ondisk">On disk${a.update ? ", with an update" : ""}</span>`
      : downloadable(a.store) ? `<span class="muted">Not downloaded yet. Hoard keeps the copy in your downloads folder.</span>`
      : `<span class="muted">Hoard lists what you own on ${store}, and doesn't download it: get the files on ${store}.</span>`}</p>` +
    shopNote(a) +
    (links ? `<div class="actions links">${links}</div>` : "") +
    `<h3>Organise</h3><div class="marks">${markButtons(a)}</div>` +
    noteSection(a) + tagSection(a) + setsSection(a) +
    (a.files.length ? `<h3>Files</h3><ul class="files">${a.files.filter(f => storeUrl(a.store, f.url)).map(f =>
      `<li><span class="fn">${esc(f.name)}</span><a class="ghost sm" href="${esc(storeUrl(a.store, f.url))}" target="_blank" rel="noopener noreferrer">Download</a></li>`).join("")}</ul>` : "");
  saveHash();   // (first: the step left behind keeps the page's place as it was, for Back to return to, issue #329)
  renderProductDetail(a, { store: a.store, storeName: store, creatorUrl: storeUrl(a.store, a.creator_url), extra,
    copyUrl: a.public,   // (its public page: never the purchase's own link, which opens its files)
    src: a.thumbnail ? keyed("/thumb/" + encodeURIComponent(a.key)) : "",
    facts: [["Store", store], ["Files", a.files.length || "—"], ["Added", shortDay(a.added) || "—"], ["Tags", a.tags.length]],
  }, sections, focus);
}
// Close the details, focusing the tile they were for.
function closeDetail() {
  if (!openKey) return;
  const back = document.querySelector(`.slot[data-key="${CSS.escape(openKey)}"]`) || lastFocus;
  keepTileInPlace(back && back.closest("#grid") ? back : null, () => {   // (its tile stays where it is on screen: #329)
    $("#detail").classList.remove("open"); document.body.classList.remove("panel-open"); $("#scrim").hidden = true;
  });
  openKey = null; markCurrent(null); glowBack(back); if (back) back.focus({ preventScroll: true });
  saveHash();
}
// Close the details and empty them, so nothing of the item stays in the page (it's only out of view once closed).
function forgetDetail() {
  closeDetail();
  $("#detail").innerHTML = "";
}

/* ---------- URL state */
function saveHash() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.store) p.set("store", state.store);
  if (state.set) p.set("set", state.set);
  if (state.creator) p.set("creator", state.creator);
  if (state.disk) p.set("downloaded", state.disk);
  if (state.fresh) p.set("new", "1");
  if (state.tags.size) p.set("tags", [...state.tags].join(","));
  if (state.sort !== "name") p.set("sort", state.sort);
  if (state.ptype) p.set("type", state.ptype);
  if (openKey) p.set("open", openKey);   // (a product's details: a place, for Back and Forward)
  setAddress(p);
}
// Read the search, filters and place from the address.
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get("q") || ""; state.store = p.get("store") || ""; state.creator = p.get("creator") || "";
  state.tags = new Set((p.get("tags") || "").split(",").filter(Boolean));
  state.disk = DISK[p.get("downloaded")] ? p.get("downloaded") : "";
  state.fresh = p.get("new") === "1";
  state.sort = sortFrom(p.get("sort"), SORTS);
  state.ptype = PRODUCT_TYPES[p.get("type")] ? p.get("type") : "";
  state.set = /^[0-9A-Za-z]{1,16}$/.test(p.get("set") || "") ? p.get("set") : "";
  if (state.set) state.store = "Sets";
  if (p.get("open")) openKey = p.get("open").slice(0, 400);   // a product, from a set's folder in Downloads
}


/* ---------- events */
let qTimer;







   // (issue #300)
// Download what's new from some stores (choosing what, in the downloads dialog).
const downloadNew = stores => pickNew(stores, keys => keys ? startDownload(storesOf(keys), null, null, keys) : startDownload(stores));

// issue #106: download what's selected, from every store it's on, as one job
function downloadSelected(list) {
  const chosen = list.filter(a => downloadable(a.store));
  if (!chosen.length) { toast("Hoard can't download those: Payhip's are listed, and you download them on Payhip."); return; }
  const keys = [...new Set(chosen.map(a => a.tag_key))];
  startDownload(storesOf(keys), null, null, keys);
}


/* ---------- itch.io's API key: checked with itch.io and kept by Hoard (POST /api/itch-key), never shown again */
let itchDone = null;
// Ask for an itch.io API key (done runs once it's saved).
function openItchKey(done) {
  itchDone = done || null;
  $("#itchKey").value = ""; $("#itchNote").textContent = ""; $("#itchSave").disabled = false;
  $("#itchDialog").showModal(); $("#itchKey").focus();
}
// Check the itch.io key with itch.io, then keep it.
async function saveItchKey() {
  const key = $("#itchKey").value.trim();
  if (!key) { $("#itchNote").textContent = "Paste the key from itch.io first."; return; }
  $("#itchSave").disabled = true; $("#itchNote").textContent = "Checking the key with itch.io";
  const r = await apiPost("/api/itch-key", { key });
  $("#itchKey").value = "";
  if (!r.ok) { $("#itchSave").disabled = false; $("#itchNote").textContent = r.data.error || "That key wasn't saved."; return; }
  $("#itchDialog").close();
  toast(`Signed in to itch.io${r.data.user ? " as " + r.data.user : ""}. Reading your library.`);
  DATA.job = { running: true, message: "Reading itch.io" }; showJob(DATA.job); renderStores(); startPolling();
  if (itchDone) itchDone();
}





/* ---------- the Save for Hoard bookmark (Payhip): run on a shop's library page in your usual browser, it reads every
   page of that shop's library, as you, from that shop only, and saves them as one file to import, instead of saving
   each page by hand. It sends nothing anywhere: the file goes to your downloads. (No backticks or "${" in it: it's
   kept in a String.raw template.) */
const PAYHIP_SAVER = String.raw`(async () => {
  // Show a message on the shop's page.
  const say = m => { note.textContent = m; };
  const note = document.createElement("div");
  note.style.cssText = "position:fixed;z-index:2147483647;left:50%;top:16px;transform:translateX(-50%);max-width:90vw;" +
    "padding:10px 16px;border-radius:10px;background:#211C18;color:#F4EDE3;font:600 14px/1.4 system-ui,sans-serif;" +
    "box-shadow:0 8px 30px rgba(0,0,0,.45)";
  if (!/\/b-account(\/|$)/.test(location.pathname)) {
    alert("Save for Hoard: open your library on this shop first (the shop's address followed by /b-account), then choose this bookmark again.");
    return;
  }
  document.body.appendChild(note);
  const start = location.href.split(/[?#]/)[0].split("/b-account")[0] + "/b-account";
  // An element's text, its spaces collapsed.
  const text = e => ((e && e.textContent) || "").replace(/\s+/g, " ").trim();
  // Whether a link is to one of your products in the shop's library.
  const isProduct = h => /\/b-account\/(digital|products?|downloads?)\/[^/?#]+\/?$/i.test(h);
  const parts = [], seen = new Set(), products = new Set();
  let url = start, first = null;
  try {
    while (url && !seen.has(url) && seen.size < 200) {
      seen.add(url);
      say("Save for Hoard: reading page " + seen.size + " of your library on this shop...");
      const r = await fetch(url, { credentials: "include" });
      if (!r.ok) throw new Error("page " + seen.size + " answered " + r.status);
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      for (const a of doc.querySelectorAll("a[href]")) {
        try { a.setAttribute("href", new URL(a.getAttribute("href"), url).href); } catch (e) { a.removeAttribute("href"); }
        if (isProduct(a.getAttribute("href") || "")) products.add(a.getAttribute("href").split(/[?#]/)[0].replace(/\/$/, ""));
      }
      for (const img of doc.querySelectorAll("img")) {
        const real = img.getAttribute("data-src") || img.getAttribute("data-lazy-src") || img.getAttribute("src");
        try { if (real) img.setAttribute("src", new URL(real, url).href); } catch (e) { img.removeAttribute("src"); }
        img.removeAttribute("srcset"); img.removeAttribute("loading");
      }
      const main = doc.querySelector("main, [role=main]") || doc.body;
      parts.push(main.innerHTML);
      if (!first) first = doc;
      const next = [...doc.querySelectorAll("a[rel=next], .pagination a, a.next")]   // (a last page's Next has no href)
        .find(x => x.getAttribute("href") && /next|\u203a|\u00bb/i.test(text(x) + " " + (x.getAttribute("rel") || "")));
      const here = url;
      url = null;
      if (next) {
        const n = new URL(next.getAttribute("href"), here);
        if (n.origin === location.origin && n.pathname.includes("/b-account")) url = n.href;
      }
    }
    for (const x of first.querySelectorAll("script, noscript, iframe, object, embed")) x.remove();
    (first.querySelector("main, [role=main]") || first.body).innerHTML = parts.join(" ");
    const html = "<!-- saved from url=(" + String(start.length).padStart(4, "0") + ")" + start + " -->\n<!DOCTYPE html>\n" +
      first.documentElement.outerHTML;
    const shop = start.replace(/^https?:\/\//, "").replace(/\/b-account$/, "").replace(/[\/:*?"<>|]+/g, " ").trim();
    const name = "Payhip library - " + shop + ".html";
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    link.download = name;
    document.body.appendChild(link);
    link.click();
    setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 10000);
    say("Save for Hoard: saved " + products.size + " products from " + seen.size + (seen.size === 1 ? " page" : " pages") +
        ' as "' + name + '". Import it in Hoard (Stores, Import pages).');
  } catch (e) {
    say("Save for Hoard couldn't read your library here: " + (e && e.message || e) + ". Try again, or save the page with Ctrl+S.");
  }
  setTimeout(() => note.remove(), 12000);
})()`;
// It runs in your usual browser, on a Payhip shop. A link can't be dragged out of Hoard's own window into another
// browser, so "get it from its page" opens the website's page for it there (site/save-for-hoard.html, the same
// bookmark: scripts/save_for_hoard.py), where it can; or it's copied from here.
const payhipSaverUrl = () => "javascript:void " + encodeURIComponent(PAYHIP_SAVER);


/* ---------- importing saved pages: any number at once, from the file picker, a folder, or dropped on the window.
   They go to Hoard a batch at a time, and each page gets its own result, so one bad page doesn't stop the rest. */
const PAGE_FILE = /\.(mhtml|mht|html|htm)$/i;
const IMPORT_BATCH = { pages: 10, bytes: 24 * 1024 * 1024 };   // per request, well inside what Hoard accepts
const MOST_PAGES = 2000;
// A count, with the word for one or many.
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const shopName = s => String(s).replace(/^https:\/\//, "");

// Import saved store pages (as many as MOST_PAGES), saying what was found in them.
async function importPages(files, store) {
  const all = files.filter(f => PAGE_FILE.test(f.name)), pages = all.slice(0, MOST_PAGES);
  if (!pages.length) {
    toast(files.length ? 'Those aren\'t saved pages. Save your library page as "Webpage, Single File" (.mhtml), and import that.'
                       : "There are no saved pages there.");
    return;
  }
  if (importing) { toast("Hoard is already importing pages. Wait for it to finish."); return; }
  importing = { stop: false };
  const done = { pages: 0, items: {}, totals: {}, problems: [], log: [], shops: new Map(), added: [] };
  if (all.length > pages.length) done.problems.push(`Only the first ${MOST_PAGES} pages were imported. Import the rest separately.`);
  renderStores();
  showImport(done, `Reading ${plural(pages.length, "page", "pages")}`);
  try {
    await sendPages(pages, store, [], done);
    if (done.shops.size && !importing.stop) {
      // Pages from Payhip shops that aren't in your list: a shop is only added when you say so, all of them at once
      const shops = [...done.shops.keys()], again = [...done.shops.values()].flat(), n = shops.length;
      done.shops = new Map();
      const head = again.length === 1
        ? (n === 1 ? tr("1 page is from a Payhip shop that isn't in your list:") : tr("1 page is from {0} Payhip shops that aren't in your list:", n))
        : (n === 1 ? tr("{0} pages are from a Payhip shop that isn't in your list:", again.length)
                   : tr("{0} pages are from {1} Payhip shops that aren't in your list:", again.length, n));
      const tail = n === 1 ? tr(again.length === 1 ? "Add it to your Payhip shops, and import that page?" : "Add it to your Payhip shops, and import those pages?")
                           : tr(again.length === 1 ? "Add them to your Payhip shops, and import that page?" : "Add them to your Payhip shops, and import those pages?");
      if (await ask(head + "\n\n" + shops.map(s => "   " + shopName(s)).join("\n") + "\n\n" + tail + " " + tr("Only add shops you bought from."),
          "Add and import")) {
        await sendPages(again, store, shops, done);
      } else {
        done.problems.push(tr("{0}: from {1}, which you didn't add to your Payhip shops, so not imported.", listed(again.map(f => f.name)), listed(shops.map(shopName))));
      }
    }
  } finally {
    const stopped = importing.stop;
    importing = null;
    await load();
    finishImport(done, files.length - all.length, stopped);
  }
}
// Send the pages to Hoard a few at a time, adding up what was found, until they're all sent or it's stopped.
async function sendPages(files, store, trust, done) {
  let i = 0;
  while (i < files.length && !importing.stop) {
    const batch = [];
    let bytes = 0;
    while (i < files.length && batch.length < IMPORT_BATCH.pages && (!batch.length || bytes + files[i].size <= IMPORT_BATCH.bytes)) {
      bytes += files[i].size;
      batch.push(files[i++]);
    }
    showImport(done, `Reading ${batch.length === 1 ? batch[0].name : plural(batch.length, "page", "pages")} (${i} of ${files.length})`);
    let sent;
    try {
      sent = await Promise.all(batch.map(async f => ({ filename: f.name, content: await f.text() })));
    } catch (e) {
      batch.forEach(f => done.problems.push(`${f.name}: couldn't be opened.`));
      continue;
    }
    const r = await apiPost("/api/import", { store: store || "auto", files: sent, trust_shops: trust });
    if (!r.ok) {
      batch.forEach(f => done.problems.push(`${f.name}: ${r.data.error || "couldn't be imported."}`));
      if (r.status === 0 || r.status === 401 || r.status >= 500) break;   // Hoard stopped, doesn't know this page, or can't read pages now
      continue;
    }
    (r.data.results || []).forEach((res, k) => {
      if (res.count != null) {
        done.pages += 1;
        done.items[res.label] = (done.items[res.label] || 0) + res.count;
        done.log.push(`${res.filename}: ${plural(res.count, `${res.label} item`, `${res.label} items`)}`);
      } else if (res.confirm_shop) {
        if (!done.shops.has(res.confirm_shop)) done.shops.set(res.confirm_shop, []);
        done.shops.get(res.confirm_shop).push(batch[k]);
      } else {
        done.problems.push(`${res.filename}: ${tr(res.error)}`);
      }
    });
    for (const s of Object.values(r.data.totals || {})) done.totals[s.label] = s.total;
    done.added.push(...(r.data.added_shops || []));
  }
}
// Show the import panel's progress.
function showImport(done, message, finished = false, title = "Importing pages") {
  $("#impPanel").hidden = false;
  $("#impTitle").textContent = title;
  $("#impMessage").textContent = message;
  $("#impStop").hidden = finished;
  $("#impClose").hidden = !finished;
  $("#impProblems").hidden = !done.problems.length;
  $("#impProblems").innerHTML = done.problems.map(p => `<li>${esc(p)}</li>`).join("");
  $("#impLog").textContent = done.log.join("\n");
}
// Say what an import found: the products from each store, and anything that couldn't be read.
function finishImport(done, notPages, stopped) {
  if (notPages) done.problems.push(notPages === 1 ? tr("{0} file isn't a saved page (.mhtml or .html), so it was left alone.", notPages)
                                                  : tr("{0} files aren't saved pages (.mhtml or .html), so they were left alone.", notPages));
  const got = Object.entries(done.items), totals = Object.entries(done.totals);
  const said = [stopped && tr("Stopped."), got.length
    ? tr("Imported {0} from {1}.", listed(got.map(([l, n]) => tr(n === 1 ? "{0} {1} item" : "{0} {1} items", n, l))),
         tr(done.pages === 1 ? "{0} page" : "{0} pages", done.pages))
    : tr("Nothing was imported."),
    totals.length && tr("Your library now has {0}.", listed(totals.map(([l, n]) => tr("{0} from {1}", n, l)))),
    done.added.length && tr("Added {0} to your Payhip shops.", listed(done.added.map(shopName)))].filter(Boolean).join(" ");
  showImport(done, said, true,
             stopped ? "Import stopped" : done.problems.length ? (got.length ? "Imported, with problems" : "Nothing imported") : "Imported");
}






// The files dropped on the window, with everything in the folders dropped (at most most of them).
async function filesIn(entries, most = 5000) {
  // Files and folders dropped on the window, with everything inside the folders
  const out = [];
  // Add a dropped file, or everything in a dropped folder.
  const walk = async entry => {
    if (out.length >= most) return;
    if (entry.isFile) { out.push(await new Promise((ok, fail) => entry.file(ok, fail))); return; }
    if (!entry.isDirectory) return;
    const reader = entry.createReader();
    for (;;) {
      const some = await new Promise((ok, fail) => reader.readEntries(ok, fail));
      if (!some.length) return;
      for (const e of some) await walk(e);
    }
  };
  for (const e of entries) {
    try { await walk(e); } catch (x) { /* one that can't be read is left out */ }
  }
  return out;
}
let dragDepth = 0;





// Set the tiles' size.


   // kept with the other layout choices

// Show copies as one tile, or each on its own.
function applyStack(on) { STACK = on !== false; $("#stackCopies").setAttribute("aria-pressed", String(STACK)); }


// Add a value to a set, or take it out when it's there.
const toggle = (set, v) => set.has(v) ? set.delete(v) : set.add(v);











/* ---------- how the tag code below finds its way around this page */
   // (shared.js: a set made from a project shows in Sets)
const T = {
  slotKey: "key",
  id: a => a.key,
  art: a => thumb(a),   // its picture (through Hoard's own copy) or its initials
  byId: id => byKey.get(id),
  open: () => (openKey ? byKey.get(openKey) : null),
  shown: () => DATA.items.filter(a => matches(a)),
  facets: () => renderFacets(DATA.items.filter(a => matches(a))),   // the filters drawn again, and nothing else
  reload: () => load(),
  closeDetail: () => closeDetail(),
  closeOtherPanels: () => {},   // windows stay open side by side
  render: () => render(),
  goTo: () => {   // Back or Forward (shared.js): the tab, set, filters and details the address names
    const want = new URLSearchParams(location.hash.slice(1)).get("open"), was = openKey;
    readHash();
    if (!want) { openKey = was; closeDetail(); }
    render();
    if (want && byKey.has(want) && (want !== was || !$("#detail").classList.contains("open"))) showDetail(byKey.get(want), false);
  },
  all: () => DATA.items,
  membersOf: key => {   // a stack's copies, all chosen together (as many as "Copies of" shows)
    const a = byKey.get(key), k = a && stackKey(a);
    return k && (stackSize.get(key) || 0) > 1 ? DATA.items.filter(x => stackKey(x) === k && inView(x) && shown(x.store)).map(x => x.key) : null;
  },
  download: keys => startDownload(storesOf(keys), null, null, keys),   // (the Sets tab)
  actions: () => ({   // what the selection bar and right-click offer here
    main: [{ label: "Download", primary: true, run: downloadSelected }],
    groups: [TAG_ACTIONS, SET_ACTIONS(), PROJECT_ACTIONS(), { name: "More", items: [...markActions(state.view), ...ADULT_ACTIONS(),
      ...(state.view === "removed" ? [{ label: "Delete for good", danger: true, run: list => purgeItems(list) }] : []),
      { label: "Delete downloaded files", danger: true, run: list => deleteFiles(list) }] }],
  }),
};
// Do what a button in the tag manager says: keep a suggestion, hide it, rename a tag or delete one.

// The tag manager's buttons and fields.


/* ---------- settings and downloading, the same in both views. T (above) connects this to the page. */
/* ---------- library folders, in Settings (as on the Downloads page, hoard/libraries.py) */
/* ---------- issue #113: what the routine check found. It downloads nothing itself: you choose, from the same list
   Download new shows, or put it off (Not now) until the next check finds something. */



/* ---------- local support reports: everything stays on this computer until the user chooses to share the ZIP. */


/* ---------- Browse: the system's own folder (or file) picker, in Hoard's window (not in a web browser, where
   there's no way to ask for one; the path is typed there) */
/* ---------- updates: checked with GitHub when you ask (or daily, if you turned that on); installed by Hoard itself
   only in the app Hoard-Setup installed on Windows */


// Follow the download running, showing its progress, until it's done.

// Show a download's progress: what it's doing, each file's transfer, and what it found when it's done.


/* ---------- the download panels beside the details (issue #85): the page's styles place them by these */


/* ---------- the glow behind the page: the store you're looking at, in its colour, rising from the bottom of the
   window. For Everything, each store you use in turn, drifting slowly across. */
/* ---------- the panel (issue #84): Tags, Stores, Settings and Tasks each open in one panel over the page, one at a
   time; opening another takes its place. Escape, the × or a click on the page around it closes it. */

/* ---------- the sidebar: folds away to a strip, and each section in it (tags, suggestions, creators...) folds on its own.
   Both are remembered. */
/* ---------- Settings save as you change them: a box or list straight away, a folder or the Payhip shops when you
   leave the field. Only what changed is sent, so a setting a running job needs doesn't hold up the others. */
/* ---------- a file downloading: how much has come in, how fast, and how long is left */
/* ---------- Tasks: what's running, what's waiting its turn (issue #49), and what finished, with its progress */
/* ---------- Projects (shared.js): your Unity projects, the same list as ALCOM's and the Creator Companion's, with their
   packages and your library in them; and what Hoard for Unity reports about each (its products, and credits) */
const storeLabel = s => s === "Itch" ? "itch.io" : s;
/* ---------- What's new: Hoard's changelog, in the app. Betas are left out unless you tick them (ticked to begin
   with when you get beta updates). The changelog's HTML is made from CHANGELOG.md with everything escaped first. */

/* ---------- closing Hoard while it's working: stop it first, carry on in the background, or close at once */
/* ---------- the setup assistant: on first start, and from Settings (Set up Hoard) */
const SETUP = { step: 0, st: null, timer: null, busy: false, watching: false, firstRun: false, picked: false,
  kono: "" };   // kono: a KonoAsset data folder to bring in once the stores are read (issue #305)
// Which stores the stores step ticks. The first time, only the ones you already have items from (all of them used to
// be ticked, so someone who'd never used Payhip was asked for Payhip shops); after that, the ones you chose.
function setupPicked(st, s) {
  if (SETUP.picked || !SETUP.firstRun) return !!st.stores[s].enabled;
  return !!((DATA.stores || {})[s] || {}).count;
}
// The setup assistant's steps (Payhip's, notifications and closing only when they apply).
const setupSteps = () => ["language", "access", "look", "welcome", "browser", "stores",
  ...(SETUP.st && SETUP.st.stores.payhip.enabled ? ["payhip"] : []), "signin", "folder",
  ...(SETUP.st && (SETUP.st.apprise || {}).available ? ["notifications"] : []),   // (issue #288: Apprise, where it's installed)
  ...(DATA.can_background ? ["closing"] : []), "done"];   // (Hoard's own window: in a browser, closing is the browser's)
// What the setup assistant needs to know (the stores, the browser, the folders...).
async function setupStatus() {
  SETUP.st = await (await api("/api/setup", { cache: "no-store" })).json();
  return SETUP.st;
}
// Open the setup assistant at its first step.
async function openSetup() {
  try { await setupStatus(); } catch (e) { toast("Hoard isn't running. Open it again."); return; }
  closeSettings(); openStores(false); openTagPanel(false);
  SETUP.step = 0; SETUP.picked = false;
  try {   // back after choosing a language (the page comes again in it): on to the next step
    const at = setupSteps().indexOf(sessionStorage.getItem("hoard-setup-step"));
    if (at > 0) SETUP.step = at;
    sessionStorage.removeItem("hoard-setup-step");
  } catch (e) { /* no storage: from the start */ }
  SETUP.firstRun = !SETUP.st.done;   // the first time, it's gone through to the end (issue #21); from Settings, it can be left
  $("#setup").hidden = false;
  renderSetup();
}
// Close the setup assistant, following any sign-in it started.
function closeSetup() {
  $("#setup").hidden = true; clearTimeout(SETUP.timer);
  // A sign-in or browser install the assistant started keeps going once it's closed: the library page follows it
  // from here, so what it reads still shows up (in 2.8.4 nothing watched it any more, and the counts stayed 0).
  if (SETUP.watching) { SETUP.watching = false; startPolling(); }
}

const PASSWORD_HELP = `<details><summary>Where are my saved passwords?</summary>
  <p class="muted">Hoard's window is its own browser, so it doesn't have the passwords your usual browser saved. Copy yours from there:</p>
  <ul><li><strong>Chrome:</strong> type <code>chrome://password-manager</code> in Chrome's address bar and search for the store.</li>
  <li><strong>Edge:</strong> go to <code>edge://settings/passwords</code> in Edge.</li>
  <li><strong>Firefox:</strong> go to <code>about:logins</code>.</li>
  <li><strong>Safari or iPhone:</strong> open the Passwords app.</li>
  <li><strong>A password manager</strong> such as Bitwarden or 1Password: open it and search for the store.</li></ul>
  <p class="muted">Paste it into the store's page in Hoard's window. It goes straight to the store; Hoard doesn't read or keep it.</p></details>
  <details><summary>Other ways to sign in</summary><ul>
  <li><strong>Forgot the password?</strong> Use the store's own "Forgot password" link in Hoard's window. The new password works everywhere.</li>
  <li><strong>Signed up with Google, Discord or X?</strong> Try the same button in Hoard's window. If it says the browser isn't supported, set a password for your store account in your usual browser, then sign in here with that.</li>
  <li><strong>Passkeys</strong> on Windows Hello or your phone work in Hoard's window too: choose the passkey option and follow the prompt.</li></ul></details>`;

// the first step, so someone who doesn't read English can set Hoard up in their own language. Each language is
// named in its own words; "Match my computer" says which one that is here.
const LANGUAGE_NAMES = { en: "English", ja: "日本語", ko: "한국어" };
const SETUP_VIEWS = {
  language: () => {
    const now = (DATA.display || {}).language || "system", here = LANGUAGE_NAMES[document.documentElement.lang] || "English";
    // A language to choose, in its own words.
    const choice = (v, label, own) => `<label><input type="radio" name="setupLang" value="${v}"${now === v ? " checked" : ""}>` +
      `<span>${own ? `<strong translate="no" lang="${v}">${label}</strong>` : `<strong>${label}</strong>`}</span></label>`;
    return `<h2 id="setupTitle">Choose your language</h2>
    <p class="muted" translate="no"><span lang="en">Choose your language</span> · <span lang="ja">言語を選んでください</span> · <span lang="ko">언어를 선택하세요</span></p>
    <div class="closepick langpick">
      <label><input type="radio" name="setupLang" value="system"${now === "system" ? " checked" : ""}><span><strong>Match my computer</strong>
        <span class="muted" translate="no">${esc(here)}</span></span></label>
      ${choice("en", "English", true)}${choice("ja", "日本語", true)}${choice("ko", "한국어", true)}
    </div>
    <p class="muted">The Japanese and Korean translations were made with AI help, so some wording may be off. <a href="https://github.com/Soloflighter1010/Hoard-Asset-Manager/issues/new?template=translation.yml" target="_blank" rel="noopener noreferrer">Tell us what reads wrong</a>.</p>
    <p class="muted">You can change it later in Settings, under Appearance.</p>`;
  },
  // easier to read and use, from the start: each choice shows at once, and is saved as it's made
  access: () => {
    const d = DATA.display || {}, opt = (v, label, now) => `<option value="${v}"${String(now) === String(v) ? " selected" : ""}>${label}</option>`;
    return `<h2 id="setupTitle">Make Hoard easier to use</h2>
    <p>Choose whatever helps. You see each one as you choose it.</p>
    <div class="access-pick">
      <label><span>Text size</span><select id="setupTextSize">${opt(100, "Normal", d.text_size)}${opt(115, "Larger", d.text_size)}${opt(130, "Large", d.text_size)}${opt(150, "Largest", d.text_size)}</select></label>
      <label><span>Font</span><select id="setupFont">${opt("standard", "Standard", d.font || "standard")}${opt("dyslexic", "OpenDyslexic, for dyslexia", d.font)}</select></label>
      <label><span>Light or dark</span><select id="setupMode">${opt("system", "Match my computer", d.mode || "system")}${opt("light", "Light", d.mode)}${opt("dark", "Dark", d.mode)}</select></label>
      <label><span>Store colours</span><select id="setupColours">${opt("standard", "Standard", d.colours === "custom" ? "standard" : d.colours)}${opt("colourblind", "Easier to tell apart (colour blindness)", d.colours)}</select></label>
      <label class="tick"><input type="checkbox" id="setupSpacing"${d.spacing ? " checked" : ""}> More space between letters, words and lines</label>
      <label class="tick"><input type="checkbox" id="setupCardOutlines"${d.card_outlines ? " checked" : ""}> Give product cards an outline and a faint background</label>
      <label class="tick"><input type="checkbox" id="setupMotion"${d.reduce_motion ? " checked" : ""}> Reduce motion</label>
      <label class="tick"><input type="checkbox" id="setupPause"${d.pause_animations ? " checked" : ""}> Pause animated pictures</label>
    </div>
    <p class="muted">There's more, and you can change these later, in Settings, under Appearance and Accessibility.</p>`;
  },
  // how Hoard lays everything out (issue #159): shown as it's chosen, and saved at once
  look: () => `<h2 id="setupTitle">Choose a style</h2>
    <p>How Hoard lays out your library, downloads and everything else. You see each one as you choose it.</p>
    <div class="style-choices" role="radiogroup" aria-labelledby="setupTitle">${styleChoices("setupStyle", (DATA.display || {}).style)}</div>
    <p class="muted">You can change it later in Settings, under Appearance.</p>`,
  welcome: () => `<h2 id="setupTitle">Welcome to Hoard</h2>
    <p>Let's get Hoard ready: choose your stores, sign in to them, and pick where downloads go. It takes a few minutes, and you can run this again from Settings.</p>
    <p class="muted">Hoard runs only on this computer. It never sees your passwords: you sign in on each store's own page, in a browser window that belongs to Hoard alone.</p>`,
  browser: st => `<h2 id="setupTitle">The browser Hoard signs in with</h2>
    <p>Hoard reads your stores through a browser it controls, kept apart from the one you browse with.</p>
    <div class="status${st.browser.ready ? " ok" : ""}">${esc(st.browser.name)} ${st.browser.ready ? "is ready." : "isn't installed yet."}</div>
    ${!st.browser.ready && st.browser.can_install ? `<button class="primary" id="installBrowser">Install Hoard's browser</button>
      <span class="muted">About 150 MB, downloaded once.</span><div class="progress" id="installProgress" aria-live="polite"></div>` : ""}
    ${st.browser.note ? `<p class="muted">${esc(st.browser.note)}</p>` : ""}`,
  stores: st => `<h2 id="setupTitle">Which stores have you bought from?</h2>
    <p>Hoard only shows and reads the stores you pick. You can change this later in Settings.</p>
    <div class="storepick">${STORE_ORDER.map(s => `<label><input type="checkbox" data-pick="${s}"${setupPicked(st, s) ? " checked" : ""}>
      <span class="dot ${s}"></span>${esc(st.stores[s].label)}</label>`).join("")}</div>
    <p class="muted">Hoard lists what you own on each of them, and keeps copies from all but Payhip: for Payhip, it lists
      what you bought and where to download it, and you download it from Payhip yourself.</p>`,
  payhip: st => `<h2 id="setupTitle">Your Payhip shops</h2>
    <p>Payhip keeps your purchases in each shop you bought from, not in one library. Add each shop's address, one per line.
      It's in your purchase email: a shop's own address such as <code>myshop.store</code>, or <code>payhip.com/ShopName</code>.</p>
    <textarea id="setupShops" spellcheck="false" aria-label="Payhip shops" placeholder="myshop.store">${esc(st.payhip_shops.map(s => s.replace(/^https:\/\//, "")).join("\n"))}</textarea>
    <p class="muted">Rather not sign in to Payhip? Save each shop's library from your usual browser, and import them all
      from the Stores panel: the Save for Hoard bookmark there saves every page of a shop in one go. Importing a shop's
      page adds that shop for you too.</p>`,
  signin: st => `<h2 id="setupTitle">Sign in to your stores</h2>
    <p>Each store opens in Hoard's own window. Sign in there as usual, then close the window, and Hoard reads what you own.</p>
    ${STORE_ORDER.filter(s => st.stores[s].enabled).map(s => `<div class="signrow"><span class="who"><span class="dot ${s}"></span>${esc(st.stores[s].label)}</span>
      <span class="state${st.stores[s].signed_in ? " ok" : ""}">${st.stores[s].signed_in ? "Signed in" : "Not signed in yet"}</span>
      <button class="ghost sm" data-signin="${s}">${s === "itch" ? (st.stores[s].signed_in ? "Change API key" : "Add API key") : st.stores[s].signed_in ? "Sign in again" : "Sign in"}</button></div>`).join("")
      || `<p class="muted">You haven't picked any stores. Go back a step to choose some.</p>`}
    <div class="progress" id="signinProgress" aria-live="polite"></div>
    <div id="linkBox" hidden><p class="muted">Did the store email you a link to sign in, or to confirm it's you? Paste it here instead of clicking it, and Hoard opens it in its window.</p>
      <div class="field"><input id="signinLink" placeholder="Paste the link from the email" aria-label="Link from the email"><button class="ghost" id="openLink">Open</button></div></div>
    ${PASSWORD_HELP}`,
  folder: st => `<h2 id="setupTitle">Where should downloads go?</h2>
    <p>Hoard keeps local copies of what you own, in folders by store, creator and product.</p>
    <div class="field"><input id="setupRoot" spellcheck="false" aria-label="Downloads folder" value="${esc(st.root)}"><button class="ghost sm" id="setupRootBrowse" data-browse ${canPick() ? "" : "hidden"}>Browse…</button><button class="ghost sm" id="setupRootDefault">Default</button></div>
    <p class="muted">Pick a drive with room to spare; VRChat assets add up. You can change this later in Settings.</p>`,
  // Issue #288: where Hoard can send its news, through Apprise (a service, its fields, a test); nothing until one's added.
  notifications: st => {
    const chosen = new Set(st.apprise.events.length ? st.apprise.events : ["new", "updates", "prices"]);
    // One of what can be sent, ticked as chosen (or, the first time, the routine check's finds and cheaper wishes).
    const event = (id, label) => `<label class="check"><input type="checkbox" data-setup-event="${id}"${chosen.has(id) ? " checked" : ""}> ${label}</label>`;
    return `<h2 id="setupTitle">Get Hoard's news where you are</h2>
    <p>Hoard can tell you what it finds on Discord, Telegram, ntfy, by email and more, through Apprise. Choose a
    service, fill in what it gives you, and add it. Hoard keeps the address as it keeps API keys, never in config.json.</p>
    <ul id="setupNotifyList" class="apprise-list" aria-label="Addresses kept"></ul>
    <div class="apprise-fields"><label class="field-row"><span>Service</span>
      <select id="setupNotifyService" aria-label="Service">${appriseServiceOptions()}</select></label></div>
    <div id="setupNotifyFields" class="apprise-fields"></div>
    <div class="row"><button class="ghost sm" id="setupNotifyAdd">Add it</button></div>
    <p class="progress" id="setupNotifyNote" aria-live="polite"></p>
    <div class="apprise-events" role="group" aria-label="What to send">
      ${event("new", "New products the routine check finds")}${event("updates", "Updates the routine check finds")}
      ${event("prices", "Products on my wishlists that got cheaper")}${event("tasks", "Tasks that finish or fail")}
    </div>
    <p class="muted">Not now? Choose Next: nothing is sent until you add an address. You can change this later in
    Settings, under Notifications through Apprise.</p>`;
  },
  closing: st => `<h2 id="setupTitle">When you close Hoard's window</h2>
    <div class="closepick" role="radiogroup" aria-labelledby="setupTitle">
      <label><input type="radio" name="setupClose" value="background"${st.close_to_taskbar !== false ? " checked" : ""}>
        <span><strong>Keep Hoard running</strong><span class="muted">The window minimizes to the taskbar (the Dock on a Mac).
        Downloads, syncs and the routine check carry on, and the routine check can tell you what it found. Quit with
        <strong>Quit Hoard</strong> in Settings.</span></span></label>
      <label><input type="radio" name="setupClose" value="quit"${st.close_to_taskbar === false ? " checked" : ""}>
        <span><strong>Quit Hoard</strong><span class="muted">Closing the window quits it. While something's running, Hoard
        asks first.</span></span></label>
    </div>
    <p class="muted">You can change this later in Settings, under Closing Hoard.</p>`,
  done: () => `<h2 id="setupTitle">Hoard's ready</h2>
    <p>When you choose Finish, Hoard reads what you own from your stores. After that, choose <strong>Download everything new</strong> in Stores, or <strong>Download new</strong> in Downloads, whenever you want local copies.</p>
    <p>Once Hoard has read your library, a short tour can show you what else it does.</p>
    <details class="setup-kono"${SETUP.kono ? " open" : ""}><summary>Coming from KonoAsset?</summary>
      <p>Hoard can bring in your KonoAsset library once it's read your stores: what's in your library is matched by its BOOTH item, and the rest come in as Local products, left where they are. Its tags and memos come too. Nothing in KonoAsset's folder is changed.</p>
      <div class="field"><input id="setupKono" spellcheck="false" aria-label="KonoAsset's data folder" placeholder="KonoAsset's data folder (its Settings say where)">
        <button class="ghost sm" id="setupKonoBrowse" data-browse ${canPick() ? "" : "hidden"}>Browse…</button><button class="ghost sm" id="setupKonoCheck">Check</button></div>
      <p class="progress" id="setupKonoResult" aria-live="polite"></p>
    </details>
    <p class="muted">Run this again any time from Settings.</p>`,
};

// Follow a sign-in or install the assistant started, drawing its step again as it goes, until onDone.
function pollSetup(onDone, show) {
  clearTimeout(SETUP.timer);
  SETUP.watching = true;
  SETUP.timer = setTimeout(async () => {
    let st;
    try { st = await setupStatus(); } catch (e) { return pollSetup(onDone, show); }
    // show() fills in this step's progress, which isn't on the page once you've moved to another step: what it
    // throws mustn't end the watch, or what comes after (reading the library again) never happens
    if (st.job && st.job.running) { try { show(st.job); } catch (e) {} pollSetup(onDone, show); }
    else { SETUP.watching = false; onDone(st); }
  }, 1000);
}
const SETUP_WIRES = {
  look: () => {
    viewListen("library", $("#setupBody .style-choices"), "change", async e => {
      const r = await apiPost("/api/settings", { display: { style: e.target.value } });
      if (!r.ok) { toast(r.data.error || "That wasn't saved."); return; }
      DATA.display = r.data.settings.display;
      applyDisplay(DATA.display);
    });
  },
  access: () => {
    // The display choices made in the assistant.
    const read = () => ({ text_size: Number($("#setupTextSize").value), font: $("#setupFont").value, mode: $("#setupMode").value,
                          colours: $("#setupColours").value, spacing: $("#setupSpacing").checked,
                          card_outlines: $("#setupCardOutlines").checked,
                          reduce_motion: $("#setupMotion").checked, pause_animations: $("#setupPause").checked });
    viewListen("library", $("#setupBody .access-pick"), "change", async () => {
      const display = read();
      if ((DATA.display || {}).colours === "custom" && display.colours === "standard") delete display.colours;   // your own stay
      const r = await apiPost("/api/settings", { display });
      if (!r.ok) { toast(r.data.error || "That wasn't saved."); return; }
      DATA.display = r.data.settings.display;
      applyDisplay(DATA.display);
      refitWindows();
    });
  },
  browser: () => {
    const b = $("#installBrowser");
    if (!b) return;
    viewListen("library", b, "click", async () => {
      const r = await apiPost("/api/setup/browser");
      if (!r.ok) { toast(r.data.error || "The browser didn't start installing."); return; }
      b.disabled = true;
      pollSetup(st => { if (st.browser.ready) toast("Hoard's browser is installed."); else toast((st.job && (st.job.error || st.job.message)) || "The browser didn't install."); renderSetup(); },
                job => { const p = $("#installProgress"); if (p) p.textContent = job.message || ""; });
    });
  },
  signin: () => {
    for (const b of document.querySelectorAll("#setupBody [data-signin]")) {
      viewListen("library", b, "click", async () => {
        if (b.dataset.signin === "itch") { openItchKey(async () => { await setupStatus(); renderSetup(); }); return; }
        const r = await apiPost("/api/login", { stores: [b.dataset.signin] });
        if (!r.ok) { toast(r.data.error || "Signing in didn't start."); return; }
        document.querySelectorAll("#setupBody [data-signin]").forEach(x => { x.disabled = true; });
        $("#signinProgress").textContent = `Opening ${SETUP.st.stores[b.dataset.signin].label}'s sign-in window...`;
        $("#linkBox").hidden = false;
        pollSetup(st => { if (st.job && st.job.error) toast(st.job.error); renderSetup(); load(); },
                  job => { const p = $("#signinProgress"), l = $("#linkBox");
                           if (p) p.textContent = job.message || ""; if (l) l.hidden = job.task !== "login"; });
      });
    }
    viewListen("library", $("#openLink"), "click", async () => {
      const r = await apiPost("/api/signin-link", { url: $("#signinLink").value.trim() });
      toast(r.ok ? "Opening that link in Hoard's window." : (r.data.error || "That link didn't open."));
      if (r.ok) $("#signinLink").value = "";
    });
  },
  notifications: st => {
    const pick = $("#setupNotifyService"), fields = $("#setupNotifyFields"), note = $("#setupNotifyNote");
    // The addresses kept, each with its own Send a test.
    const list = () => { $("#setupNotifyList").innerHTML = st.apprise.addresses.map(x => `<li data-apprise-id="${esc(x.id)}"><b>${esc(tr(x.service))}</b>` +
      (x.label ? ` <span class="muted" translate="no">${esc(x.label)}</span>` : "") +
      `<span class="row"><button class="ghost sm" data-setup-test="${esc(x.id)}">${esc(tr("Send a test"))}</button></span></li>`).join(""); };
    // The chosen service's fields.
    const fill = () => { fields.innerHTML = appriseFieldsHTML(pick.value); note.textContent = ""; };
    viewListen("library", pick, "change", fill);
    fill(); list();
    viewListen("library", $("#setupNotifyAdd"), "click", async () => {
      const made = appriseBuilt(pick.value, fields);
      if (!made) { note.textContent = tr("Fill in its fields as the service gives them: that isn't an address yet."); return; }
      const r = await apiPost("/api/apprise", { action: "add", urls: made });
      if (!r.ok) { note.textContent = r.data.error || tr("That can't be done."); return; }
      st.apprise.addresses = r.data.addresses;
      fill(); list();
      note.textContent = tr("Added. Send it a test to check it.");
    });
    viewListen("library", $("#setupNotifyList"), "click", async e => {
      const b = e.target.closest("[data-setup-test]");
      if (!b) return;
      b.disabled = true;
      note.textContent = tr("Sending a test...");
      const r = await apiPost("/api/apprise/test", { id: b.dataset.setupTest });
      b.disabled = false;
      note.textContent = r.ok && r.data.ok ? tr("Sent. Check that it came.") : (r.data.error || tr("That can't be done."));
    });
  },
  folder: st => {
    viewListen("library", $("#setupRootDefault"), "click", () => { $("#setupRoot").value = st.default_root; });
    viewListen("library", $("#setupRootBrowse"), "click", () => browseInto($("#setupRoot")));
  },
  done: () => {   // issue #305: a KonoAsset library, brought in after the stores are read (a task after theirs)
    syncBrowse();
    if (SETUP.kono) { $("#setupKono").value = SETUP.kono; $("#setupKonoResult").textContent = tr("It's brought in after Hoard reads your stores."); }
    viewListen("library", $("#setupKonoBrowse"), "click", async () => { if (await browseInto($("#setupKono"))) $("#setupKonoCheck").click(); });
    viewListen("library", $("#setupKono"), "input", () => { SETUP.kono = ""; $("#setupKonoResult").textContent = ""; });
    viewListen("library", $("#setupKonoCheck"), "click", async () => {
      const path = $("#setupKono").value.trim(), r = await apiPost("/api/konoasset/preview", { path });
      SETUP.kono = r.ok ? path : "";
      $("#setupKonoResult").textContent = r.ok
        ? tr("{0} in KonoAsset. They're brought in after Hoard reads your stores.", tr(r.data.total === 1 ? "1 product" : "{0} products", r.data.total))
        : (r.data.error || tr("That folder couldn't be read."));
    });
  },
};
// Draw the setup assistant's step.
function renderSetup() {
  const list = setupSteps(), name = list[Math.min(SETUP.step, list.length - 1)];
  $("#setupSteps").innerHTML = list.map((_, i) => `<span class="${i <= SETUP.step ? "done" : ""}"></span>`).join("");
  $("#setupBody").innerHTML = SETUP_VIEWS[name](SETUP.st);
  $("#setupBack").hidden = SETUP.step === 0;
  $("#setupSkip").hidden = name === "done" || SETUP.firstRun;
  $("#setupNext").textContent = name === "welcome" ? "Start" : name === "done" ? "Finish" : "Next";
  (SETUP_WIRES[name] || (() => {}))(SETUP.st);
  $("#setupNext").focus();
}
async function setupSave(name) {   // what leaving a step saves; false keeps you on the step
  let body = null;
  if (name === "language") {
    const chosen = ($('#setupBody input[name="setupLang"]:checked') || {}).value || "system";
    if (chosen === ((DATA.display || {}).language || "system")) return true;
    const r = await apiPost("/api/settings", { display: { language: chosen } });
    if (!r.ok) { toast(r.data.error || "That wasn't saved."); return false; }
    // the page comes again in the language chosen, and the assistant with it, one step on
    try { sessionStorage.setItem("hoard-setup-step", "access"); } catch (e) { /* it starts at the language again */ }
    history.replaceState(null, "", location.pathname + "#setup");
    location.reload();
    return false;
  }
  if (name === "stores") {
    body = { stores: {} };
    for (const c of document.querySelectorAll("#setupBody [data-pick]")) body.stores[c.dataset.pick] = { enabled: c.checked };
    SETUP.picked = true;
  } else if (name === "payhip") {
    body = { payhip_shops: $("#setupShops").value.split("\n").map(x => x.trim()).filter(Boolean) };
  } else if (name === "folder") {
    const root = $("#setupRoot").value.trim();
    body = { root: root === SETUP.st.default_root ? "" : root };
  } else if (name === "closing") {
    body = { close_to_taskbar: !!$('#setupBody input[name="setupClose"][value="background"]').checked };
  } else if (name === "notifications") {   // what's sent, once there's somewhere to send it (skipped: nothing changes)
    if (!SETUP.st.apprise.addresses.length) return true;
    const chosen = new Set([...document.querySelectorAll("#setupBody [data-setup-event]")].filter(c => c.checked).map(c => c.dataset.setupEvent));
    // (the ones it doesn't show, routine and other, stay as Settings has them)
    const kept = SETUP.st.apprise.events.filter(e => e === "routine" || e === "other");
    body = { apprise_events: [...new Set([...kept, ...chosen])] };
  }
  if (!body) return true;
  const r = await apiPost("/api/settings", body);
  if (!r.ok) { toast(r.data.error || "That wasn't saved."); return false; }
  await setupStatus();
  return true;
}
// The first time through, a step that isn't done yet holds you there (or, where going on without it can make sense,
// asks first), so nobody ends up in an empty Hoard without knowing why (issue #21).
function setupNotDone(name) {
  const st = SETUP.st;
  if (name === "browser" && !st.browser.ready && st.browser.can_install)
    return { stop: "Install Hoard's browser first: Hoard reads your stores with it." };
  if (name === "stores" && ![...document.querySelectorAll("#setupBody [data-pick]")].some(c => c.checked))
    return { stop: "Pick at least one store you've bought from." };
  if (name === "payhip" && !$("#setupShops").value.trim())
    return { ask: "You haven't added a Payhip shop, so Hoard won't find your Payhip purchases until you do (in Settings, or by importing a shop's page). Go on anyway?" };
  if (name === "signin" && !STORE_ORDER.some(s => st.stores[s].enabled && st.stores[s].signed_in))
    return { ask: "You haven't signed in to any store yet, so Hoard can't read your library until you do. Go on anyway?" };
  return null;
}
// The setup assistant's buttons: Next, Back and Skip.
function wireSetup() {
  viewListen("library", $("#setupNext"), "click", async () => {
    if (SETUP.busy) return;
    SETUP.busy = true;
    try {
      const list = setupSteps(), name = list[SETUP.step];
      const missing = SETUP.firstRun && setupNotDone(name);
      if (missing && missing.stop) { toast(missing.stop); return; }
      if (missing && missing.ask && !await ask(missing.ask, "Go on anyway")) return;
      if (!(await setupSave(name))) return;
      if (name === "done") {
        await apiPost("/api/setup/done", { done: true });
        closeSetup();
        await load();
        const on = STORE_ORDER.filter(s => SETUP.st.stores[s].enabled);
        if (on.length) await runJob("/api/refresh", on, true);
        if (SETUP.kono) {   // (queued after reading the stores, so what's in your library is matched)
          const r = await apiPost("/api/konoasset/bring-in", { path: SETUP.kono, confirm: true });
          if (!r.ok) toast(r.data.error || "Bringing in from KonoAsset didn't start.");
          SETUP.kono = "";
        }
        return;
      }
      SETUP.step += 1;
      renderSetup();
    } finally { SETUP.busy = false; }
  });
  viewListen("library", $("#setupBack"), "click", () => { SETUP.step = Math.max(0, SETUP.step - 1); renderSetup(); });
  viewListen("library", document, "keydown", e => { if (e.key === "Escape" && !$("#setup").hidden && !SETUP.firstRun && !document.querySelector("dialog[open]")) closeSetup(); });
  viewListen("library", $("#setupSkip"), "click", async () => {
    await apiPost("/api/setup/done", { done: true });
    closeSetup();
    toast("Setup skipped. Run it any time from Settings.");
  });
}

/* ---------- issue #217: why copies are shown together, and "Not a copy" for one that isn't */
const STACK_WHY = { picture: "the same picture", name: "the same name and creator", look: "the same name, and pictures that look alike",
                    alike: "names alike, by the same creator" };
// Why a product is shown with its copies (or isn't), with a button to change it.
function stackNote(a) {
  if (a.apart) return `<p class="note">${esc(tr("You said this isn't a copy of anything, so it's shown on its own."))} ` +
    `<button class="linkish" data-act="apart" data-on="false">${esc(tr("Show it with its copies again"))}</button></p>`;
  if (!a.stack_key || !(a.stack_why || []).length) return "";
  // (only when its tile stands for them: a copy archived, say, is on its own here, issue #247)
  if (!state.copies && ((stacksHere(DATA.items.filter(o => matches(o))).get(a.stack_key) || []).length < 2)) return "";
  return `<p class="note">${esc(tr("Shown with its copies, as they have {0}.", listed(a.stack_why.map(w => tr(STACK_WHY[w])))))} ` +
    `<button class="linkish" data-act="apart" data-on="true">${esc(tr("Not a copy"))}</button></p>`;
}

/* ---------- archive, hide and remove; the hidden library and its PIN */
const VIEWS = { library: "Library", archive: "Archive", removed: "Removed", hidden: "Hidden" };
// Whether a product belongs in the view shown (Library, Archive, Hidden or Removed).
const inView = a => state.view === "library" ? !a.mark : state.view === "archive" ? a.mark === "archived" : a.mark === state.view;
// The view a product is in.
const viewOf = a => !a.mark ? "library" : a.mark === "archived" ? "archive" : a.mark;
// The views to choose from, with their counts (Hidden only once there's a PIN, Removed only when it has some).
function renderViews() {
  const p = DATA.privacy || {}, count = {};
  for (const a of DATA.items) if (shown(a.store)) (count[viewOf(a)] ||= new Set()).add(a.key);   // as the grid counts
  // How many products a view has.
  const n = v => (count[v] || new Set()).size;
  $("#views").innerHTML = Object.keys(VIEWS).filter(v => v === "library" || v === "archive" || state.view === v
      || (v === "removed" && n(v)) || (v === "hidden" && p.pin_set)).map(v =>
    `<button role="radio" data-view="${v}" aria-checked="${state.view === v}">${VIEWS[v]}` +
    (v === "hidden" && !p.unlocked ? ` <span aria-label="locked">&#128274;</span>` : `<span class="n">${n(v)}</span>`) + `</button>`).join("");
  const bar = $("#viewBar");
  bar.hidden = state.view === "library";
  bar.innerHTML = state.view === "archive" ? `<p>Your archive: older products set aside, out of your main library but still yours. Gumroad's archived purchases start here too.</p>`
    : state.view === "removed" ? `<p>Removed items stay out of your library, even after a refresh. Restore them, or delete them from Hoard for good. Their downloaded files stay on disk unless you choose <b>Delete downloaded files</b>.</p>`
    : state.view === "hidden" ? `<p>Hidden items only show here, and only in this browser while it's unlocked. It's a privacy screen for Hoard, not encryption.</p>
        <button class="ghost sm" data-privacy="lock">Lock now</button><button class="ghost sm" data-privacy="change">Change PIN</button>
        <button class="ghost sm" data-privacy="phrase">${(DATA.privacy || {}).recovery_set ? "New recovery phrase" : "Create a recovery phrase"}</button>` : "";
  if (selecting()) markSelected();   // (the selection's actions follow the view)
}
// A product's buttons to archive, hide or remove it, or undo that.
function markButtons(a) {
  // One of those buttons.
  const b = (kind, on, text) => `<button class="ghost sm" data-act="mark" data-kind="${kind}" data-on="${on}">${text}</button>`;
  if (a.mark === "removed") return b("removed", false, "Restore") + `<button class="ghost sm" data-act="purge">Delete for good</button>` +
    (onDisk(a) ? `<button class="ghost sm" data-act="delete-files">Delete downloaded files</button>` : "");
  const del = onDisk(a) ? `<button class="ghost sm" data-act="delete-files">Delete downloaded files</button>` : "";
  if (a.mark === "hidden") return b("hidden", false, "Unhide") + b("removed", true, "Remove") + del;
  return (a.mark === "archived" ? b("unarchived", true, "Unarchive") : b("archived", true, "Archive")) +
    b("hidden", true, "Hide") + b("removed", true, "Remove") + del;
}
function markActions(v) {   // Archive, Hide and Remove, or their undoing, for the view you're in
  // One of those actions, for the selection.
  const m = (kind, on, label) => ({ label, run: list => markItems(list, kind, on) });
  if (v === "removed") return [m("removed", false, "Restore")];
  if (v === "hidden") return [m("hidden", false, "Unhide"), m("removed", true, "Remove")];
  return [v === "archive" ? m("unarchived", true, "Unarchive") : m("archived", true, "Archive"), m("hidden", true, "Hide"), m("removed", true, "Remove")];
}
const MARK_DONE = {   // [one, many]
  "archived true": ["Archived 1 item. It's in Archive.", "Archived {0} items. They're in Archive."],
  "unarchived true": ["Moved 1 item back to your library.", "Moved {0} items back to your library."],
  "removed true": ["Removed 1 item. Restore it from Removed if you change your mind.", "Removed {0} items. Restore them from Removed if you change your mind."],
  "removed false": ["Restored 1 item.", "Restored {0} items."],
  "hidden true": ["Hidden 1 item. It's in Hidden, behind your PIN.", "Hidden {0} items. They're in Hidden, behind your PIN."],
  "hidden false": ["1 item is no longer hidden.", "{0} items are no longer hidden."],
  "apart true": ["Shown on its own now: it isn't stacked with other products.", "{0} items are shown on their own now."],
  "apart false": ["It's stacked with its copies again.", "{0} items are stacked with their copies again."],
};
// Archive, hide or remove products, or undo that (a PIN is set first, the first time anything is hidden).
async function markItems(list, kind, on) {
  const keys = [...new Set(list.filter(Boolean).map(a => a.tag_key))];
  if (!keys.length) { toast("Select some items first."); return; }
  if (kind === "hidden" && on && !(DATA.privacy || {}).pin_set && !(await pinDialog("set"))) return;
  const r = await apiPost("/api/marks", { kind, keys, on });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  if (kind === "apart") state.copies = null;   // (its stack is changing: back to the library, where the change shows)
  sel.ids.clear(); T.closeDetail(); await load();
  toast(tr(MARK_DONE[`${kind} ${on}`][keys.length === 1 ? 0 : 1], keys.length));
  // issue #81: removing something you downloaded offers to delete its files too, so Downloads doesn't keep it
  if (kind === "removed" && on) {
    const downloaded = list.filter(a => a && onDisk(a));
    if (downloaded.length) await deleteFiles(downloaded, true);
  }
}
// Delete products' downloaded files, once you say so.
async function deleteFiles(list, justRemoved = false) {
  const keys = [...new Set(list.filter(a => a && onDisk(a)).map(a => a.tag_key))];
  if (!keys.length) { toast("None of those are downloaded."); return; }
  const kept = list.some(a => a && onDisk(a) && a.mark !== "removed");   // still in your library: downloadable again
  const one = keys.length === 1;
  const head = one ? tr(justRemoved ? "It's downloaded. Delete its downloaded files too?" : "This item is downloaded. Delete its downloaded files?")
                   : tr(justRemoved ? "{0} of them are downloaded. Delete their downloaded files too?" : "{0} of them are downloaded. Delete their downloaded files?", keys.length);
  const body = [tr("Only the files Hoard downloaded are deleted; anything of your own in the same folder stays."), tr("This can't be undone."),
                justRemoved ? tr("If you keep them, they stay under Removed in Downloads.")
                : kept ? tr(one ? "It stays in your library, so you can download it again." : "They stay in your library, so you can download them again.") : ""];
  if (!await ask(head + "\n\n" + body.filter(Boolean).join(" "), "Delete files", true, "Keep the files")) return;
  const r = await apiPost("/api/delete-files", { keys, confirm: true });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  if (r.data.job) { sel.ids.clear(); T.closeDetail(); return afterQueuedJob(r, "delete-files", load); }
  sel.ids.clear(); T.closeDetail(); await load();
  toast([tr(r.data.files === 1 ? "Deleted {0} file ({1})." : "Deleted {0} files ({1}).", r.data.files, sizeText(r.data.bytes)),
         r.data.kept.length && tr(r.data.kept.length === 1 ? "A folder still has other files, so it was kept." : "{0} folders still have other files, so they were kept.",
                                  r.data.kept.length)].filter(Boolean).join(" "));
}
// Delete products from Hoard for good, once you say so.
async function purgeItems(list) {
  const keys = [...new Set(list.filter(Boolean).map(a => a.tag_key))];
  if (!keys.length) return;
  if (!await ask(tr(keys.length === 1 ? "Delete this item from Hoard for good?" : "Delete {0} items from Hoard for good?", keys.length) + " " +
                 tr("They stay out of your library even if a store lists them again. Downloaded files stay on disk."), "Delete for good", true)) return;
  const r = await apiPost("/api/purge", { keys });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  sel.ids.clear(); T.closeDetail(); await load();
  toast(tr(r.data.deleted === 1 ? "Deleted {0} item from Hoard's library." : "Deleted {0} items from Hoard's library.", r.data.deleted));
}
// Show a view (Hidden only once it's unlocked with the PIN).
async function showView(v) {
  if (v === "hidden" && !(DATA.privacy || {}).unlocked) {
    if (!(await pinDialog("unlock"))) return;
    await load();
  }
  state.view = v; sel.ids.clear(); T.closeDetail(); render();
}

/* the PIN dialog: choose a PIN, unlock, or change it */
const PIN = { mode: null, resolve: null };
const PIN_TEXT = {
  set: ["Choose a PIN", "Hidden items stay out of view until you enter this PIN. It's a privacy screen for Hoard, not encryption: anyone who can open your files can still find them."],
  unlock: ["Unlock hidden items", "Enter your PIN to show hidden items in this browser for a while."],
  change: ["Change your PIN", "Enter your current PIN, then the new one twice."],
  recover: ["Reset your PIN", "Enter your 6 recovery words, then choose a new PIN. Your hidden items stay hidden."],
  phrase: ["Your recovery phrase", "Write these 6 words down, in order, and keep them somewhere safe away from this computer. They're the only way to reset your PIN, and Hoard won't show them again."],
};
// Set the PIN dialog out for what it's doing: setting, changing or checking the PIN, or the recovery phrase.
function pinLayout(mode) {
  PIN.mode = mode;
  $("#pinTitle").textContent = PIN_TEXT[mode][0];
  $("#pinText").textContent = PIN_TEXT[mode][1];
  $("#pinCurrent").hidden = mode !== "change";
  $("#pinInput").hidden = mode === "phrase";
  $("#pinAgain").hidden = mode === "unlock" || mode === "phrase";
  $("#recoverWords").hidden = mode !== "recover";
  $("#phraseBox").hidden = mode !== "phrase";
  $("#pinInput").placeholder = mode === "unlock" ? "PIN" : "New PIN";
  $("#pinForgot").hidden = mode !== "unlock" && mode !== "change";
  $("#pinLost").hidden = mode !== "recover";
  $("#pinCancel").hidden = mode === "phrase";
  $("#pinOk").textContent = mode === "phrase" ? "I've written them down" : "OK";
  $("#pinNote").textContent = "";
}
// Show the recovery phrase, asking for two of its words back.
function showPhrase(phrase) {
  const words = phrase.split(" ");
  PIN.words = words;
  $("#phraseWords").innerHTML = words.map(w => `<li>${esc(w)}</li>`).join("");
  const picks = [0, 1, 2, 3, 4, 5].sort(() => Math.random() - 0.5).slice(0, 2).sort((a, b) => a - b);
  PIN.checks = picks;
  $("#checkA").textContent = picks[0] + 1; $("#checkB").textContent = picks[1] + 1;
  $("#checkWordA").value = ""; $("#checkWordB").value = "";
  pinLayout("phrase");
  $("#checkWordA").focus();
}
// Make a new recovery phrase, and show it.
async function newPhrase() {
  const r = await apiPost("/api/pin/phrase");
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  PIN.resolve = null;
  $("#pinDialog").showModal();
  showPhrase(r.data.recovery);
}
// Open the PIN dialog, resolving with whether it was done.
function pinDialog(mode) {
  return new Promise(resolve => {
    PIN.resolve = resolve;
    for (const id of ["#pinCurrent", "#pinInput", "#pinAgain", "#recoverWords"]) $(id).value = "";
    pinLayout(mode);
    $("#pinDialog").showModal();
    (mode === "change" ? $("#pinCurrent") : $("#pinInput")).focus();
  });
}
// Close the PIN dialog, saying whether it was done.
function pinDone(ok) {
  if ($("#pinDialog").open) $("#pinDialog").close();
  const r = PIN.resolve; PIN.resolve = null;
  if (r) r(ok);
}
// Send what was typed in the PIN dialog.
async function pinSubmit() {
  const pin = $("#pinInput").value, note = $("#pinNote");
  if (PIN.mode === "phrase") {   // both check words must match (the first four letters are enough)
    // Whether a word typed is the phrase's (its first four letters are enough).
    const same = (typed, word) => { const t = typed.trim().toLowerCase(); return t === word || (t.length >= 4 && word.startsWith(t)); };
    if (!same($("#checkWordA").value, PIN.words[PIN.checks[0]]) || !same($("#checkWordB").value, PIN.words[PIN.checks[1]])) {
      note.textContent = "Those don't match the words above. Check them, and try again."; return;
    }
    PIN.words = null;
    toast("Recovery phrase saved. Keep those words safe.");
    pinDone(true); return;
  }
  if (PIN.mode === "recover") {
    if (pin.length < 4) { note.textContent = "Use at least 4 characters for the new PIN."; return; }
    if (pin !== $("#pinAgain").value) { note.textContent = "The two PINs don't match."; return; }
    const r = await apiPost("/api/pin/recover", { phrase: $("#recoverWords").value, pin });
    if (!r.ok) { note.textContent = r.data.error || "That didn't work."; return; }
    await apiPost("/api/unlock", { pin });
    toast("New PIN set. Your hidden items are still hidden, and unlocked in this browser.");
    pinDone(true); return;
  }
  if (PIN.mode !== "unlock") {
    if (pin.length < 4) { note.textContent = "Use at least 4 characters."; return; }
    if (pin !== $("#pinAgain").value) { note.textContent = "The two PINs don't match."; return; }
  }
  const r = PIN.mode === "unlock" ? await apiPost("/api/unlock", { pin })
    : await apiPost("/api/pin", { pin, current: $("#pinCurrent").value || null });
  if (!r.ok) { note.textContent = r.data.error || "That didn't work."; $("#pinInput").select(); return; }
  if (PIN.mode === "change") toast("PIN changed.");
  if (r.data.recovery) { showPhrase(r.data.recovery); return; }   // the first PIN: show its recovery phrase once
  pinDone(true);
}
// Hidden locked itself again, nobody having used it for a while (shared.js, issue #248): out of view, details and all.
async function hiddenLocked() {
  const open = openKey && byKey.get(openKey);
  if (open && open.mark === "hidden") forgetDetail();
  if (state.view === "hidden") state.view = "library";
  await load(); toast("Hidden items locked again: they hadn't been used for a while.");
}
// The views, and the PIN, lock and phrase buttons.
function wirePrivacy() {
  viewListen("library", $("#views"), "click", e => { const b = e.target.closest("[data-view]"); if (b) showView(b.dataset.view); });
  viewListen("library", $("#viewBar"), "click", async e => {
    const b = e.target.closest("[data-privacy]");
    if (!b) return;
    if (b.dataset.privacy === "lock") {
      const open = openKey && byKey.get(openKey);
      if (open && open.mark === "hidden") forgetDetail();   // straight away, before the server answers
      await apiPost("/api/lock"); state.view = "library"; await load(); toast("Hidden items locked.");
    }
    else if (b.dataset.privacy === "phrase") {
      if ((DATA.privacy || {}).recovery_set && !await ask("Make a new recovery phrase? The old words will stop working.", "Make a new phrase", true)) return;
      await newPhrase(); await load();
    }
    else pinDialog("change");
  });
  viewListen("library", $("#pinOk"), "click", pinSubmit);
  viewListen("library", $("#pinCancel"), "click", () => pinDone(false));
  viewListen("library", $("#pinDialog"), "cancel", e => { e.preventDefault(); if (PIN.mode !== "phrase") pinDone(false); });
  viewListen("library", $("#pinDialog"), "keydown", e => { if (e.key === "Enter" && e.target.id !== "recoverWords") { e.preventDefault(); pinSubmit(); } });
  viewListen("library", $("#pinForgot"), "click", () => {
    if (!(DATA.privacy || {}).recovery_set) { $("#pinLost").click(); return; }
    for (const id of ["#pinInput", "#pinAgain", "#recoverWords"]) $(id).value = "";
    pinLayout("recover");
    $("#recoverWords").focus();
  });
  viewListen("library", $("#pinLost"), "click", async () => {
    if (!await ask("Forgot your PIN? Hoard can't show hidden items without it. Instead, it will delete them from its library and remove the PIN, so you can start again. They won't be shown. Downloaded files stay on disk.", "Delete them and start again", true)) return;
    const r = await apiPost("/api/hidden/forget", { confirm: true });
    pinDone(false);
    state.view = "library"; await load();
    toast(r.ok ? tr(r.data.deleted === 1 ? "Deleted {0} hidden item and removed the PIN." : "Deleted {0} hidden items and removed the PIN.", r.data.deleted)
               : (r.data.error || "That didn't work."));
  });
  viewListen("library", $("#storeRows"), "click", async e => {
    if (!e.target.closest("[data-review-shops]")) return;
    const found = (DATA.stores.payhip || {}).found_shops || [];
    if (!found.length) return;
    const list = found.map(s => s.replace(/^https:\/\//, "")).join("\n");
    if (!await ask(`Your Payhip library has products from these shops, on their own addresses:\n\n${list}\n\nAdd them to your Payhip shops? Hoard will then read your purchases there. Only add shops you bought from.`, "Add them")) return;
    const r = await addPayhipShops(found);
    if (!r) { toast("Hoard didn't answer, so the shops weren't added. Try again."); return; }
    toast(r.ok ? "Added. Refresh Payhip to read them." : (r.data.error || "They weren't added."));
  });
}

/* ---------- offline notice: everything here works offline except the store links and refreshing */
const showConnection = () => { $("#offline").hidden = navigator.onLine; };
  return {
    get STORE_ORDER() { return STORE_ORDER; },
    get shown() { return shown; },
    get usedStores() { return usedStores; },
    get importable() { return importable; },
    get downloadable() { return downloadable; },
    get importStore() { return importStore; }, set importStore(value) { importStore = value; },
    get importing() { return importing; }, set importing(value) { importing = value; },
    get state() { return state; },
    get DISK() { return DISK; },
    get onDisk() { return onDisk; },
    get DATA() { return DATA; }, set DATA(value) { DATA = value; },
    get byKey() { return byKey; }, set byKey(value) { byKey = value; },
    get openKey() { return openKey; }, set openKey(value) { openKey = value; },
    get lastFocus() { return lastFocus; }, set lastFocus(value) { lastFocus = value; },
    get polling() { return polling; }, set polling(value) { polling = value; },
    get label() { return label; },
    get placeholder() { return placeholder; },
    get thumb() { return thumb; },
    get refreshView() { return refreshView; },
    get matches() { return matches; },
    get SORTS() { return SORTS; },
    get filtersActive() { return filtersActive; },
    get STACK() { return STACK; }, set STACK(value) { STACK = value; },
    get stackSize() { return stackSize; }, set stackSize(value) { stackSize = value; },
    get stackStores() { return stackStores; }, set stackStores(value) { stackStores = value; },
    get stackKey() { return stackKey; },
    get stacksHere() { return stacksHere; },
    get stacked() { return stacked; },
    get showCopies() { return showCopies; },
    get render() { return render; },
    get storeSegShown() { return storeSegShown; }, set storeSegShown(value) { storeSegShown = value; },
    get renderStoreSeg() { return renderStoreSeg; },
    get renderStores() { return renderStores; },
    get renderStoreHealth() { return renderStoreHealth; },
    get giftsOpened() { return giftsOpened; }, set giftsOpened(value) { giftsOpened = value; },
    get isWrapped() { return isWrapped; },
    get unwrap() { return unwrap; },
    get slotHTML() { return slotHTML; },
    get renderGrid() { return renderGrid; },
    get renderFacets() { return renderFacets; },
    get renderStatus() { return renderStatus; },
    get syncControls() { return syncControls; },
    get showJob() { return showJob; },
    get startPolling() { return startPolling; },
    get runJob() { return runJob; },
    get openStores() { return openStores; },
    get shopNote() { return shopNote; },
    get addPayhipShops() { return addPayhipShops; },
    get addShop() { return addShop; },
    get showDetail() { return showDetail; },
    get closeDetail() { return closeDetail; },
    get forgetDetail() { return forgetDetail; },
    get saveHash() { return saveHash; },
    get readHash() { return readHash; },
    get qTimer() { return qTimer; }, set qTimer(value) { qTimer = value; },
    get downloadNew() { return downloadNew; },
    get downloadSelected() { return downloadSelected; },
    get itchDone() { return itchDone; }, set itchDone(value) { itchDone = value; },
    get openItchKey() { return openItchKey; },
    get saveItchKey() { return saveItchKey; },
    get PAYHIP_SAVER() { return PAYHIP_SAVER; },
    get payhipSaverUrl() { return payhipSaverUrl; },
    get PAGE_FILE() { return PAGE_FILE; },
    get IMPORT_BATCH() { return IMPORT_BATCH; },
    get MOST_PAGES() { return MOST_PAGES; },
    get plural() { return plural; },
    get shopName() { return shopName; },
    get importPages() { return importPages; },
    get sendPages() { return sendPages; },
    get showImport() { return showImport; },
    get finishImport() { return finishImport; },
    get filesIn() { return filesIn; },
    get dragDepth() { return dragDepth; }, set dragDepth(value) { dragDepth = value; },
    get applyStack() { return applyStack; },
    get toggle() { return toggle; },
    get T() { return T; },
    get storeLabel() { return storeLabel; },
    get SETUP() { return SETUP; },
    get setupPicked() { return setupPicked; },
    get setupSteps() { return setupSteps; },
    get setupStatus() { return setupStatus; },
    get openSetup() { return openSetup; },
    get closeSetup() { return closeSetup; },
    get PASSWORD_HELP() { return PASSWORD_HELP; },
    get LANGUAGE_NAMES() { return LANGUAGE_NAMES; },
    get SETUP_VIEWS() { return SETUP_VIEWS; },
    get pollSetup() { return pollSetup; },
    get SETUP_WIRES() { return SETUP_WIRES; },
    get renderSetup() { return renderSetup; },
    get setupSave() { return setupSave; },
    get setupNotDone() { return setupNotDone; },
    get wireSetup() { return wireSetup; },
    get STACK_WHY() { return STACK_WHY; },
    get stackNote() { return stackNote; },
    get VIEWS() { return VIEWS; },
    get inView() { return inView; },
    get viewOf() { return viewOf; },
    get renderViews() { return renderViews; },
    get markButtons() { return markButtons; },
    get markActions() { return markActions; },
    get MARK_DONE() { return MARK_DONE; },
    get markItems() { return markItems; },
    get deleteFiles() { return deleteFiles; },
    get purgeItems() { return purgeItems; },
    get showView() { return showView; },
    get PIN() { return PIN; },
    get PIN_TEXT() { return PIN_TEXT; },
    get pinLayout() { return pinLayout; },
    get showPhrase() { return showPhrase; },
    get newPhrase() { return newPhrase; },
    get pinDialog() { return pinDialog; },
    get pinDone() { return pinDone; },
    get pinSubmit() { return pinSubmit; },
    get hiddenLocked() { return hiddenLocked; },
    get wirePrivacy() { return wirePrivacy; },
    get showConnection() { return showConnection; },
    // Install this view's handlers once; viewListen routes events without duplicating shell handlers.
    wire() {
viewListen("library", window, "hashchange", () => {   // the bar's Sets, from here
  if (/(^|[#&])setup\b/.test(location.hash)) { if (typeof openSetup === "function") openSetup(); return; }
  const was = openKey;
  readHash(); render();
  if (openKey && openKey !== was && byKey.has(openKey)) showDetail(byKey.get(openKey), true);
});
viewListen("library", $("#q"), "input", e => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value; render(); }, 90); });
viewListen("library", $("#storeSeg"), "click", e => { const b = e.target.closest("[data-store]"); if (b) { state.store = b.dataset.store; state.set = ""; render(); } });
viewListen("library", $("#sort"), "change", e => { state.sort = e.target.value; uiSave({ sort: state.sort }); render(); });
viewListen("library", $("#creatorFind"), "input", e => { state.creatorFind = e.target.value; render(); });
viewListen("library", $("#moreTags"), "click", () => { state.allTags = !state.allTags; render(); });
viewListen("library", $("#storesBtn"), "click", () => openStores());
viewListen("library", $("#refreshAll"), "click", () => runJob("/api/refresh", usedStores(), true));
viewListen("library", $("#quickRefresh"), "click", () => runJob("/api/refresh", usedStores(), true, { quick: true }));
viewListen("library", $("#downloadAll"), "click", () => downloadNew(usedStores().filter(downloadable)));
viewListen("library", $("#signOutAll"), "click", async () => {
  if (await ask("Sign out of every store? Hoard signs out on each store's side where it can, then deletes all its saved sign-ins. Your library list stays.", "Sign out of all", true)) runJob("/api/logout", ["all"]);
});
viewListen("library", $("#storeRows"), "click", e => {
  const l = e.target.closest("[data-login]"), r = e.target.closest("[data-refresh]"), i = e.target.closest("[data-import]");
  const o = e.target.closest("[data-logout]"), q = e.target.closest("[data-quick]");
  const d = e.target.closest("[data-download]");
  if (d) downloadNew([d.dataset.download]);
  else if (o) runJob("/api/logout", [o.dataset.logout]);
  else if (l && l.dataset.login === "itch") openItchKey();
  else if (l) runJob("/api/login", [l.dataset.login]);
  else if (r) runJob("/api/refresh", [r.dataset.refresh]);
  else if (q) runJob("/api/refresh", [q.dataset.quick], false, { quick: true });   // (one store's start: issue #331)
  else if (i) { importStore = i.dataset.import; $("#importFile").value = ""; $("#importFile").click(); }
});
viewListen("library", $("#itchSave"), "click", saveItchKey);
viewListen("library", $("#itchKey"), "keydown", e => { if (e.key === "Enter") saveItchKey(); });
viewListen("library", $("#itchCancel"), "click", () => { $("#itchKey").value = ""; $("#itchDialog").close(); });
viewListen("library", $("#itchDialog"), "close", () => { $("#itchKey").value = ""; });
viewListen("library", $("#payhipSaverCopy"), "click", async () => {
  try { await navigator.clipboard.writeText(payhipSaverUrl()); toast("Copied. Make a bookmark in your usual browser, and paste it as its address."); }
  catch (e) { toast("Couldn't copy it here. Get it from its page instead, and drag it to your bookmarks bar there."); }
});
viewListen("library", $("#impStop"), "click", () => {
  if (importing) { importing.stop = true; $("#impMessage").textContent = "Stopping after the pages being read now"; }
});
viewListen("library", $("#impClose"), "click", () => { $("#impPanel").hidden = true; });
viewListen("library", $("#importPages"), "click", () => { importStore = null; $("#importFile").click(); });
viewListen("library", $("#importFolder"), "click", () => $("#importDir").click());
viewListen("library", $("#importFile"), "change", e => {
  const files = [...e.target.files];
  e.target.value = "";   // so the same pages can be chosen again (say, after declining a shop)
  importPages(files, importStore);
});
viewListen("library", $("#importDir"), "change", e => {
  const files = [...e.target.files];
  e.target.value = "";
  importPages(files, null);
});
// Files brought in from outside the window (never a product or project dragged in Hoard: issue #313, shared.js's DRAG)
const fromOutside = e => !DRAG.what && e.dataTransfer.types.includes("Files");
viewListen("library", document, "dragenter", e => { if (fromOutside(e)) { dragDepth++; $("#drop").hidden = false; } });
viewListen("library", document, "dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("#drop").hidden = true; } });
viewListen("library", document, "dragover", e => { if (fromOutside(e)) e.preventDefault(); });
viewListen("library", document, "drop", e => {
  if (DRAG.what || !e.dataTransfer.files.length) return;
  e.preventDefault(); dragDepth = 0; $("#drop").hidden = true;
  // What was dropped can only be read while the drop is happening, so take it now; folders are read after
  const entries = [...e.dataTransfer.items].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  const files = [...e.dataTransfer.files];
  if (entries.some(x => x.isDirectory)) filesIn(entries).then(found => importPages(found, null));
  else importPages(files, null);
});
viewListen("library", $("#filtersToggle"), "click", e => {
  const open = $("#filters").classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(open));
});
viewListen("library", zoom, "input", () => { setZoom(zoom.value); try { localStorage.setItem("hoard-tile-size", zoom.value); } catch (e) {} });
viewListen("library", zoom, "change", () => uiSave({ tile_size: Number(zoom.value) }));
try { const z = localStorage.getItem("hoard-tile-size"); if (z) setZoom(z); } catch (e) {}
viewListen("library", $("#stackCopies"), "click", () => { applyStack(!STACK); uiSave({ stack: STACK }); render(); });
viewListen("library", $("#filters"), "click", e => {
  const t = e.target.closest("[data-tag]"), c = e.target.closest("[data-creator]"), d = e.target.closest("[data-disk]");
  if (e.target.closest(".sec-toggle, .side-fold, #manageTags")) return;
  if (e.target.closest("[data-fresh]")) state.fresh = !state.fresh;
  else if (t) toggle(state.tags, t.dataset.tag);
  else if (c) state.creator = state.creator === c.dataset.creator ? "" : c.dataset.creator;
  else if (d) state.disk = state.disk === d.dataset.disk ? "" : d.dataset.disk;
  else return;
  render();
});
viewListen("library", document, "click", e => {
  if (e.target.closest("#openStores")) { openStores(true); return; }
  const b = e.target.closest("[data-clear]"); if (!b) return;
  const k = b.dataset.clear, v = b.dataset.v;
  if (k === "all") { state.q = ""; state.store = ""; state.creator = ""; state.tags.clear(); state.copies = null; state.disk = ""; state.fresh = false; state.ptype = ""; }
  else if (k === "fresh") state.fresh = false;
  else if (k === "copies") state.copies = null;
  else if (k === "disk") state.disk = "";
  else if (k === "q") state.q = ""; else if (k === "store") state.store = ""; else if (k === "creator") state.creator = "";
  else if (k === "tag") state.tags.delete(v);
  else if (k === "ptype") state.ptype = "";
  render();
});
viewListen("library", $("#grid"), "click", e => {
  const s = e.target.closest(".slot"); if (!s) return;
  if (selectClick(e, s)) return;
  if ((stackSize.get(s.dataset.key) || 0) > 1) { showCopies(byKey.get(s.dataset.key), "stack_key"); return; }   // a stack: every copy
  lastFocus = s; showDetail(byKey.get(s.dataset.key));
});
viewListen("library", $("#grid"), "error", e => {
  if (e.target.tagName !== "IMG") return;
  e.target.outerHTML = placeholder(byKey.get(e.target.closest(".slot").dataset.key));
}, true);
viewListen("library", $("#detail"), "error", e => {
  if (e.target.tagName === "IMG" && openKey) e.target.outerHTML = placeholder(byKey.get(openKey));
}, true);
viewListen("library", $("#detail"), "click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const a = byKey.get(openKey);
  if (tagDetailAction(b.dataset.act, b, a)) return;
  if (b.dataset.act === "download") {   // which of its files, asked first (issue #225)
    askFiles({ key: a.tag_key, store: a.store, name: a.name, creator: a.creator, names: (a.files || []).map(f => f.name) },
             files => { DL_FILES = files; startDownload([a.store], a.name, a.key); });
    return;
  }
  if (b.dataset.act === "mark") { markItems([a], b.dataset.kind, b.dataset.on === "true"); return; }
  if (b.dataset.act === "purge") { purgeItems([a]); return; }
  if (b.dataset.act === "delete-files") { deleteFiles([a]); return; }
  if (b.dataset.act === "unset") { changeSets({ action: "remove", id: b.dataset.set, items: [a.tag_key] }); return; }
  if (b.dataset.act === "toset") { addToSet([a], $("#setPick").value); return; }
  if (b.dataset.act === "showset") { showSet(b.dataset.set); return; }
  if (b.dataset.act === "add-shop") { addShop(a.payhip_shop); return; }
  if (b.dataset.act === "close") closeDetail();
  else if (b.dataset.act === "tag") { toggle(state.tags, b.dataset.tag); b.setAttribute("aria-pressed", String(state.tags.has(b.dataset.tag))); render(); }
  else if (b.dataset.act === "others") showCopies(a);
  else if (b.dataset.act === "apart") markItems([a], "apart", b.dataset.on === "true");
});
viewListen("library", $("#scrim"), "click", closeDetail);
viewListen("library", document, "keydown", e => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); $("#q").focus(); $("#q").select(); }
  else if (e.key === "Escape") {
    if (document.querySelector("dialog[open]")) return;   // a dialog closes itself
    if (closeTopWindow()) return;
    else if (selecting()) clearSelection();
    else if (openKey) closeDetail();
    else if (document.activeElement === $("#q")) { state.q = ""; render(); }
  }
});
viewListen("library", window, "online", showConnection);
viewListen("library", window, "offline", showConnection);
wireSetup();
wirePrivacy();
    },
  };
}
