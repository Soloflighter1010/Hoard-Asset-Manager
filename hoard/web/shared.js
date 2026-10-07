// What both of Hoard's pages share, served inside each page's own script (server.page_source): each page
// is still one script, which the Content-Security-Policy allows by its hash. Changed here, it changes on both.
/* ---------- splash (issue #50): the logo while the page first reads your library. It's in the markup, so it shows
   from the first paint; on the window's first page it stays at least a moment, and on later pages (Library to
   Downloads and back) the stylesheet only fades it in if reading takes more than a moment. */
const hideSplash = (() => {
  const el = document.getElementById("splash");
  let first = true;
  try { first = !sessionStorage.getItem("hoard-opened"); sessionStorage.setItem("hoard-opened", "1"); } catch (e) {}
  if (first) el.classList.add("first");
  const since = performance.now(), MIN = first ? 1200 : 0;
  let done = false;
  const hide = () => {
    if (done) return;
    done = true;
    setTimeout(() => {
      el.classList.add("gone");
      setTimeout(() => el.remove(), 400);
    }, Math.max(0, MIN - (performance.now() - since)));
  };
  setTimeout(hide, 20000);   // never in the way for good, whatever happens
  return hide;
})();
const $ = s => document.querySelector(s);
/* ---------- the access key. Hoard's server only answers requests that carry this run's key (see server.py).
   Hoard opens this page with a one-time link (#enter=...) that's traded for it; the address `hoard serve`
   prints carries the key itself (#key=...). It's kept for this address only: each start brings a new one. */
const ACCESS = { key: "" };
const entered = (async () => {
  const h = new URLSearchParams(location.hash.slice(1)), once = h.get("enter"), given = h.get("key");
  if (once !== null || given !== null) {   // out of the address before anything else reads or shows it
    h.delete("enter"); h.delete("key");
    history.replaceState(null, "", h.toString() ? "#" + h : location.pathname);
  }
  try { ACCESS.key = given || localStorage.getItem("hoard-key") || ""; } catch (e) { ACCESS.key = given || ""; }
  if (once) {
    try {
      const r = await fetch("/api/enter", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: once }) });
      if (r.ok) ACCESS.key = (await r.json()).key || "";
    } catch (e) { /* Hoard isn't running: the first request says so */ }
  }
  try { if (ACCESS.key) localStorage.setItem("hoard-key", ACCESS.key); } catch (e) { /* no storage: this page still works */ }
})();
// Every request to Hoard's server goes through api(), with the key. Images, which the browser loads by itself,
// carry it in their address instead (keyed()).
async function api(url, opts = {}) {
  await entered;
  return fetch(url, { ...opts, headers: { ...(opts.headers || {}), "X-Hoard-Key": ACCESS.key } });
}
const keyed = url => `${url}${url.includes("?") ? "&" : "?"}k=${encodeURIComponent(ACCESS.key)}`;
const NEEDS_KEY = "Hoard didn't recognise this page. Open Hoard again (or the address it printed, which includes its key).";
// Only plain web addresses become links; anything else from a store page (javascript:, file:, ...) is dropped.
const safeUrl = u => { try { const x = new URL(u); return x.protocol === "https:" || x.protocol === "http:" ? x.href : ""; } catch (e) { return ""; } };
// Links to a store only open when they lead to that store's own website (the same rule the tool applies).
const STORE_SITES = { booth: ["booth.pm"], gumroad: ["gumroad.com"], jinxxy: ["jinxxy.com"], payhip: ["payhip.com"], itch: ["itch.io"] };
const storeUrl = (store, u) => {
  const s = safeUrl(u); if (!s) return "";
  const x = new URL(s), host = x.hostname.replace(/\.$/, "");
  const sites = STORE_SITES[String(store).toLowerCase()] || [];
  return x.protocol === "https:" && !x.username && !x.password && (!x.port || x.port === "443") &&
    sites.some(d => host === d || host.endsWith("." + d)) ? s : "";
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = s => String(s || "").normalize("NFKC").toLowerCase();
const coll = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
const hue = s => { let h = 7; for (const c of s) h = (h * 31 + c.codePointAt(0)) % 360; return h; };
const initials = s => (s.match(/[\p{L}\p{N}]+/gu) || ["?"]).slice(0, 2).map(w => [...w][0]).join("").toUpperCase();
const STRIPE_STORES = ["booth", "gumroad", "jinxxy", "payhip", "itch"];
// A tile's store spine; for something you own on more than one store, striped with the other store's colour.
function notch(store, others) {
  const other = (others || []).find(o => STRIPE_STORES.includes(o) && o !== store);
  return other ? `<i class="notch ${store} dup" style="--c2: var(--${other})"></i>` : `<i class="notch ${store}"></i>`;
}
// The item whose details are open stays marked in the grid.
function markCurrent(selector) {
  for (const s of document.querySelectorAll('.slot[aria-current="true"]')) s.removeAttribute("aria-current");
  const slot = selector && document.querySelector(selector);
  if (slot) slot.setAttribute("aria-current", "true");
}
// Text size, Reduce motion and Pause animated pictures, from Settings.
let PAUSE = false;
const COLOURED = ["booth", "gumroad", "jinxxy", "payhip", "itch", "local"];
const COLOUR_NAMES = { booth: "Booth", gumroad: "Gumroad", jinxxy: "Jinxxy", payhip: "Payhip", itch: "itch.io", local: "Local" };
// Your own colours: one picker a store, starting from the colour it shows now
function fillColours() {
  const d = SETTINGS.display, box = $("#customColours");
  box.hidden = d.colours !== "custom";
  if (box.hidden) return;
  const now = getComputedStyle(document.documentElement);
  box.innerHTML = COLOURED.map(c => {
    const v = (d.custom_colours || {})[c] || now.getPropertyValue("--" + c).trim() || "#888888";
    return `<label class="check"><input type="color" data-colour="${c}" value="${/^#[0-9a-f]{6}$/i.test(v) ? v : "#888888"}"> ${COLOUR_NAMES[c]}</label>`;
  }).join("");
}
function applyDisplay(d) {
  if (!d) return;
  document.documentElement.style.zoom = d.text_size && d.text_size !== 100 ? String(d.text_size / 100) : "";
  // Zoom scales every length, the window's own size (vh, vw) included: --zoom undoes that for --vh and --vw, so
  // what's sized to the window still fits it at a larger text size (issue #48)
  document.documentElement.style.setProperty("--zoom", String((d.text_size || 100) / 100));
  document.body.classList.toggle("less-motion", !!d.reduce_motion);
  document.body.classList.toggle("no-glow", d.glow === false);
  const root = document.documentElement;
  if (d.colours === "standard" || !d.colours) delete root.dataset.colours; else root.dataset.colours = d.colours;
  for (const c of COLOURED) {   // your own colours (issue #112), only while you've chosen them
    const mine = d.colours === "custom" && (d.custom_colours || {})[c];
    if (mine) root.style.setProperty("--" + c, mine); else root.style.removeProperty("--" + c);
  }
  if (!!d.pause_animations === PAUSE) return;
  PAUSE = !!d.pause_animations;
  if (PAUSE) document.querySelectorAll(".art img, .d-art img").forEach(freeze);
  else for (const c of document.querySelectorAll("canvas.still")) c.replaceWith(c.moving);
}
// Swap a picture for a still of the frame it's showing (the first, when it's just loaded), drawn the way the
// picture is: filling a tile, or whole in the details.
function freeze(img) {
  if (!PAUSE || !img.complete || !img.naturalWidth || !img.closest(".art, .d-art")) return;
  const w = img.clientWidth, h = img.clientHeight;
  if (!w || !h) return;
  const dpr = window.devicePixelRatio || 1, c = document.createElement("canvas");
  c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
  const scale = (img.closest(".art") ? Math.max : Math.min)(c.width / img.naturalWidth, c.height / img.naturalHeight);
  const dw = img.naturalWidth * scale, dh = img.naturalHeight * scale;
  c.getContext("2d").drawImage(img, (c.width - dw) / 2, (c.height - dh) / 2, dw, dh);
  c.className = "still"; c.moving = img; c.setAttribute("aria-hidden", "true");
  img.replaceWith(c);
}
document.addEventListener("load", e => { if (e.target.tagName === "IMG") freeze(e.target); }, true);

let toastTimer;
/* A question before something that can't be undone, in Hoard's own dialog (the browser's plain confirm box looked
   out of place). Resolves true for the main button, false for Cancel, Escape or a click outside it. */
function ask(text, ok = "OK", danger = false, cancel = "Cancel") {
  return new Promise(resolve => {
    let d = document.getElementById("askDialog");
    if (!d) {
      d = document.createElement("dialog");
      d.id = "askDialog"; d.className = "ask";
      d.setAttribute("aria-labelledby", "askText");
      d.innerHTML = '<div id="askText"></div><div class="ask-row"><button class="ghost" value="no"></button>' +
                    '<button class="primary" value="yes"></button></div>';
      d.addEventListener("click", e => {
        const b = e.target.closest("button");
        if (b) d.close(b.value);
        else if (e.target === d) d.close("no");   // the dimmed page around it
      });
      document.body.appendChild(d);
    }
    const body = d.querySelector("#askText");
    body.replaceChildren(...String(text).split(/\n\n+/).map(par => {
      const p = document.createElement("p");
      p.append(...par.split("\n").flatMap((line, i) => i ? [document.createElement("br"), line] : [line]));
      return p;
    }));
    const [no, yes] = d.querySelectorAll("button");
    no.textContent = cancel; yes.textContent = ok;
    yes.classList.toggle("danger", !!danger);
    d.returnValue = "no";
    d.addEventListener("close", () => resolve(d.returnValue === "yes"), { once: true });
    d.showModal();
    (danger ? no : yes).focus();   // Enter doesn't delete anything by accident
  });
}

// Only the cards near the screen are drawn (review finding P-02): a batch now, and the next whenever the last one
// drawn comes within about two screens of view. A redraw keeps at least as many as were showing, so the page
// doesn't jump. Clicks, pictures, "Select all shown" and the marks work from the list, not from what's drawn.
function lazyCards(box, batch = 120) {
  let list = [], shown = 0, card = null;
  const near = new IntersectionObserver(seen => { if (seen.some(e => e.isIntersecting)) more(); },
                                        { rootMargin: "0px 0px 200% 0px" });
  function more(count = batch) {
    near.disconnect();
    const next = list.slice(shown, shown + count);
    if (next.length) {
      box.insertAdjacentHTML("beforeend", next.map(card).join(""));
      shown += next.length;
      markSelected();   // cards drawn now get the marks the others have
    }
    if (shown < list.length && box.lastElementChild) near.observe(box.lastElementChild);
  }
  return {
    show(items, cardFor) {
      const keep = Math.max(batch, shown);
      list = items; card = cardFor; shown = 0; box.innerHTML = "";
      more(keep);
    },
    get drawn() { return shown; },
  };
}
let cards = null;
const storesOf = keys => [...new Set(keys.map(k => k.split(":")[0]))];
const zoom = $("#zoom");
/* ---------- tags: your own tags, suggestions you can keep or hide, and tagging many items at once.
   Tags are saved by the tool (POST /api/tags) in a file both Hoard tools share. T (defined above)
   connects this code to the page it's in. */
const sel = { on: false, ids: new Set() };
const keysOf = list => [...new Set(list.flatMap(a => [a.tag_key, ...(a.copy_keys || [])]))];

async function changeTags(body, done) {
  try {
    const r = await api("/api/tags", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) { toast(j.error || "That tag change wasn't saved."); return false; }
  } catch (e) { toast("That tag change wasn't saved, because the tool isn't running."); return false; }
  await T.reload();
  if (done) toast(done);
  return true;
}
const tagChip = ([t, n], kind) =>
  `<button class="chip ${kind}" data-tag="${esc(t)}" aria-pressed="${state.tags.has(t)}">${esc(t)}<span class="n">${n}</span></button>`;

function renderTagFacets(list) {
  const mine = new Map(), sugg = new Map();
  for (const a of list) {
    for (const t of a.tags) mine.set(t, (mine.get(t) || 0) + 1);
    for (const t of a.suggested) sugg.set(t, (sugg.get(t) || 0) + 1);
  }
  const yours = new Set(((DATA.tagset || {}).tags || []).map(x => x.name));
  for (const t of state.tags) if (!mine.has(t) && !sugg.has(t)) (yours.has(t) ? mine : sugg).set(t, 0);
  const order = (x, y) => state.tags.has(y[0]) - state.tags.has(x[0]) || y[1] - x[1] || coll.compare(x[0], y[0]);
  const m = [...mine].sort(order), s = [...sugg].sort(order);
  $("#myTags").innerHTML = m.map(x => tagChip(x, "mine")).join("") ||
    `<span class="none">${yours.size ? "None on these items" : "Add tags from an item's details, or select several items at once."}</span>`;
  $("#tags").innerHTML = (state.allTags ? s : s.slice(0, 36)).map(x => tagChip(x, "sugg")).join("") ||
    `<span class="none">No suggestions here</span>`;
  const more = $("#moreTags"); more.hidden = s.length <= 36;
  more.textContent = state.allTags ? "Show fewer" : `Show all ${s.length}`;
  $("#tagList").innerHTML = [...yours].sort(coll.compare).map(t => `<option value="${esc(t)}">`).join("");
}

function tagSection(a) {
  const mine = a.tags.map(t => `<span class="tagpill"><button class="chip" data-act="tag" data-tag="${esc(t)}" aria-pressed="${state.tags.has(t)}">${esc(t)}</button>` +
    `<button class="untag" data-act="untag" data-tag="${esc(t)}" aria-label="Remove the tag ${esc(t)}">×</button></span>`).join("");
  const sugg = a.suggested.map(t => `<button class="chip add" data-act="addtag" data-tag="${esc(t)}" aria-label="Add the tag ${esc(t)}">${esc(t)}</button>`).join("");
  return `<h3>Tags</h3><div class="chips">${mine || '<span class="none">No tags yet</span>'}</div>` +
    (sugg ? `<p class="sub">Suggested for this item</p><div class="chips">${sugg}</div>` : "") +
    `<div class="tagadd"><input id="tagInput" list="tagList" maxlength="40" placeholder="Add a tag" aria-label="Add a tag">` +
    `<button class="ghost sm" data-act="addtyped">Add</button></div>` +
    ((a.copy_keys || []).length ? `<p class="sub">Tags apply to every copy of this product you own.</p>` : "");
}
function addTyped(a) {
  const input = $("#tagInput"), t = input ? input.value.trim() : "";
  if (!t) { if (input) input.focus(); return; }
  changeTags({ action: "assign", keys: keysOf([a]), add: [t] });
}
function tagDetailAction(act, b, a) {  // true when the click was a tag action
  if (act === "untag") changeTags({ action: "assign", keys: keysOf([a]), remove: [b.dataset.tag] });
  else if (act === "addtag") changeTags({ action: "assign", keys: keysOf([a]), add: [b.dataset.tag] });
  else if (act === "addtyped") addTyped(a);
  else return false;
  return true;
}

function markSelected() {
  for (const s of document.querySelectorAll(".slot")) {
    if (sel.on) s.setAttribute("aria-pressed", String(sel.ids.has(s.dataset[T.slotKey])));
    else s.removeAttribute("aria-pressed");
  }
  if (!sel.on) return;
  $("#bulkCount").textContent = `${sel.ids.size} selected`;
  for (const b of $("#bulk").querySelectorAll("[data-needs]")) b.disabled = !sel.ids.size;
}
function toggleSelected(id) { sel.ids.has(id) ? sel.ids.delete(id) : sel.ids.add(id); markSelected(); }
async function bulkTag(mode) {
  const t = $("#bulkTag").value.trim();
  if (!t) { $("#bulkTag").focus(); toast("Type a tag first."); return; }
  const chosen = [...sel.ids].map(T.byId).filter(Boolean);
  if (!chosen.length) { toast("Select some items first."); return; }
  const n = chosen.length, what = `${n} ${n === 1 ? "item" : "items"}`, tag = "#" + t.toLowerCase();
  if (await changeTags({ action: "assign", keys: keysOf(chosen), [mode]: [t] },
      mode === "add" ? `Added ${tag} to ${what}.` : `Removed ${tag} from ${what}.`)) $("#bulkTag").value = "";
}

/* the tag manager */
function openTagPanel(open) {
  const p = $("#tagPanel"), show = open ?? p.hidden;
  p.hidden = !show;
  $("#tagsBtn").setAttribute("aria-expanded", String(show));
  if (show) { T.closeOtherPanels(); renderTagPanel(); }
}
function renderTagPanel() {
  if ($("#tagPanel").hidden) return;
  const ts = DATA.tagset || { tags: [], suggestions: [], hidden: [] };
  const btn = (act, t, text, extra = "") => `<button class="ghost sm" data-tact="${act}" data-tag="${esc(t)}" ${extra}>${text}</button>`;
  const items = n => `${n} ${n === 1 ? "item" : "items"}`;
  $("#tagRows").innerHTML = ts.tags.map(x => `<li><span class="tname">${esc(x.name)}</span>` +
    `<span class="tmeta">${items(x.count)}${x.match ? `, including every name with “${esc(x.match)}”` : ""}</span>` +
    `<span class="tbtns">${btn("rename", x.name, "Rename")}` +
    `${btn("match", x.name, x.match ? "Change match" : "Match names", `data-match="${esc(x.match || "")}"`)}` +
    `${btn("delete", x.name, "Delete", `data-count="${x.count}"`)}</span></li>`).join("") ||
    `<li class="none">No tags yet. Create one above, keep a suggestion below, or add one from an item's details.</li>`;
  $("#suggRows").innerHTML = ts.suggestions.slice(0, 60).map(x => `<li><span class="tname">${esc(x.name)}</span>` +
    `<span class="tmeta">in ${x.count} ${x.count === 1 ? "name" : "names"}</span>` +
    `<span class="tbtns">${btn("keep", x.name, "Keep")}${btn("hide", x.name, "Hide")}</span></li>`).join("") ||
    `<li class="none">No suggestions right now.</li>`;
  $("#hiddenCount").textContent = ts.hidden.length;
  $("#hiddenRows").innerHTML = ts.hidden.map(w => `<li><span class="tname">${esc(w)}</span>` +
    `<span class="tbtns">${btn("unhide", w, "Suggest again")}</span></li>`).join("") || `<li class="none">Nothing hidden.</li>`;
  $("#tagFile").textContent = ts.file ? `Saved in ${ts.file}.` : "";
}
async function createTag() {
  const v = $("#newTag").value.trim();
  if (!v) { $("#newTag").focus(); return; }
  if (await changeTags({ action: "create", name: v }, `Created #${v.toLowerCase()}.`)) $("#newTag").value = "";
}
const STORE_NAMES = { booth: "Booth", gumroad: "Gumroad", jinxxy: "Jinxxy", payhip: "Payhip", itch: "itch.io" };
let SETTINGS = null, dlActive = false, dlTimer = null;

const DRIVE_ICON = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="2.5" y="5" width="15" height="10" rx="2.5"/><circle cx="14" cy="10" r="1" fill="currentColor"/><path d="M5.5 10h5"/></svg>';
const libCount = n => `${n.toLocaleString()} ${n === 1 ? "product" : "products"}`;
function renderLibs(list) {   // every library folder, the downloads folder first (hoard/libraries.py)
  $("#setLibs").innerHTML = (list || []).map(l => `<div class="librow${l.available ? "" : " away"}">${DRIVE_ICON}` +
    `<span class="lp"><b>${esc(l.label || l.path)}</b><small>${esc(l.path)}${l.main ? " · new downloads go here" : ""}</small></span>` +
    `<span class="muted">${l.available ? `${libCount(l.products || 0)}${l.free != null ? ` · ${sizeText(l.free)} free` : ""}`
      : "Drive not connected"}</span>` +
    (l.available ? `<button class="ghost sm" data-lib-open="${l.n}">Open</button>` : "") +
    (l.main ? "" : `<button class="ghost sm" data-lib-remove="${l.n}">Remove</button>`) + `</div>`).join("");
}
async function libraryChange(path, body) {
  $("#libMsg").textContent = "";
  const r = await apiPost(path, body);
  if (!r.ok) { $("#libMsg").textContent = r.data.error || "That didn't work."; return null; }
  SETTINGS.libraries = r.data.libraries;
  if (typeof DATA === "object" && DATA) DATA.libraries = r.data.libraries;
  renderLibs(r.data.libraries);
  await T.reload();
  return r.data.libraries;
}
async function addLibrary(path) {
  const before = new Set((SETTINGS.libraries || []).map(l => l.path));
  const libs = await libraryChange("/api/libraries/add", { path });
  if (!libs) return false;
  const added = libs.find(l => !before.has(l.path));
  if (added) toast(`Added ${added.label}: ${added.products ? `${libCount(added.products)} found there` : "nothing downloaded there yet"}. ` +
                   "It has a tab in Downloads.");
  return true;
}
function wireLibs() {
  $("#libPick").addEventListener("click", async () => {   // in Hoard's window: choose it, and it's added
    const r = await apiPost("/api/pick", { kind: "folder" });
    if (!r.ok) { $("#libMsg").textContent = r.data.error || "The picker didn't open. Type the path instead."; return; }
    if (r.data.path) await addLibrary(r.data.path);
  });
  const add = async () => {
    const path = $("#libPath").value.trim();
    if (path && await addLibrary(path)) $("#libPath").value = "";
  };
  $("#libAdd").addEventListener("click", add);
  $("#libPath").addEventListener("keydown", e => { if (e.key === "Enter") add(); });
  $("#setLibs").addEventListener("click", async e => {
    const open = e.target.closest("[data-lib-open]");
    if (open) {
      const lib = (SETTINGS.libraries || []).find(l => l.n === +open.dataset.libOpen);
      if (lib) { const r = await apiPost("/api/open", { path: lib.main ? "" : `@${lib.n}/` }); toast(r.ok ? `Opened in ${r.data.opened_in}` : r.data.error); }
      return;
    }
    const b = e.target.closest("[data-lib-remove]"); if (!b) return;
    const lib = (SETTINGS.libraries || []).find(l => l.n === +b.dataset.libRemove);
    if (!lib || !await ask(`Stop reading ${lib.label} (${lib.path}) as part of your library?\n\nIts files stay where they are, ` +
                           "and come back to your library if you add the folder again.", "Remove")) return;
    if (await libraryChange("/api/libraries/remove", { n: lib.n })) toast(`${lib.label} is no longer part of your library.`);
  });
}
/* ---------- issue #107: before downloading new things, or updating, the list of what that gets: untick what you
   don't want this time, or Always skip it (left out of every download and sync until you stop skipping it). Left
   all ticked, the download runs as it always has; otherwise it gets just what's ticked. */
const PICK = { items: [], skipped: [], off: new Set(), go: null, verb: "Download" };
async function downloadChoices() {
  try { const r = await api("/api/download-choices", { cache: "no-store" }); if (r.ok) return await r.json(); } catch (e) {}
  return { new: [], updates: [], skipped: [] };
}
// Download new (or everything new on some stores): what's in your library with nothing on disk, and the updates the
// last check found. start(keys): null when everything's left ticked.
async function pickNew(stores, start) {
  const c = await downloadChoices(), want = new Set(stores), seen = new Set();
  const items = [...c.new, ...c.updates].filter(e => want.has(e.store) && !seen.has(e.key) && seen.add(e.key));
  pickDownloads("Download new", "Download", items, start, c);
}
async function pickDownloads(title, verb, items, go, choices) {
  choices = choices || await downloadChoices();
  const skip = new Set((choices.skipped || []).map(e => e.key));
  Object.assign(PICK, { items: items.filter(e => !skip.has(e.key)), skipped: choices.skipped || [], off: new Set(), go, verb,
                        offFiles: new Map(), openFiles: new Set() });
  if (!PICK.items.length && !PICK.skipped.length) { go(null); return; }   // nothing to choose from: as before
  $("#pickTitle").textContent = title;
  drawPick();
  $("#pickDialog").showModal();
}
// Each of a product's files, to untick one by one, when Hoard knows them before downloading: an update's changed
// and added files, and a new product's files where its store lists them (Booth's library does).
const fileNames = e => [...new Set(e.names || [])];   // a name two files share is one choice: both, or neither
function fileChoice(e) {
  const names = fileNames(e), count = {};
  for (const n of e.names || []) count[n] = (count[n] || 0) + 1;
  if (names.length < 2 || PICK.off.has(e.key)) return "";
  const off = PICK.offFiles.get(e.key) || new Set();
  return `<details class="pk-files" data-files-of="${esc(e.key)}"${PICK.openFiles.has(e.key) ? " open" : ""}>` +
    `<summary>Choose files (${names.length - off.size} of ${names.length})</summary>` +
    names.map(n => `<label><input type="checkbox" data-file-of="${esc(e.key)}" data-file="${esc(n)}"${off.has(n) ? "" : " checked"}>` +
      ` <span>${esc(n)}${count[n] > 1 ? ` <span class="muted">(${count[n]} files)</span>` : ""}</span></label>`).join("") + `</details>`;
}
let DL_FILES = null;   // the files chosen of each product, for the download about to start
function takeFiles() { const f = DL_FILES; DL_FILES = null; return f; }
function drawPick() {
  const files = n => n ? `, ${n} ${n === 1 ? "file" : "files"}` : "";
  const row = (e, skipped) => `<li>` + (skipped
    ? `<span class="dot ${esc(e.store)}"></span><span class="pk-nm">${esc(e.name)}</span><span class="muted">${esc(e.creator)}</span>` +
      `<button class="linkish" data-unskip="${esc(e.key)}">Stop skipping</button>`
    : `<label><input type="checkbox" data-pick="${esc(e.key)}"${PICK.off.has(e.key) ? "" : " checked"}> <span class="dot ${esc(e.store)}"></span>` +
      `<span class="pk-nm">${esc(e.name)}</span><span class="muted">${esc(e.creator)}${files(e.files)}</span></label>` +
      `<button class="linkish" data-skip="${esc(e.key)}">Always skip</button>` + fileChoice(e)) + `</li>`;
  $("#pickList").innerHTML = PICK.items.map(e => row(e, false)).join("") ||
    `<li class="muted">Nothing here to download, apart from what you always skip.</li>`;
  $("#pickSkipped").hidden = !PICK.skipped.length;
  $("#pickSkipN").textContent = PICK.skipped.length;
  $("#pickSkipped ul").innerHTML = PICK.skipped.map(e => row(e, true)).join("");
  const n = PICK.items.length - PICK.off.size;
  $("#pickGo").textContent = !PICK.off.size ? `${PICK.verb} all` : `${PICK.verb} ${n}`;
  $("#pickGo").disabled = PICK.items.length > 0 && n === 0;
}
async function pickSkip(key, on) {
  const r = await apiPost("/api/download-skip", { keys: [key], skip: on });
  if (!r.ok) { toast(r.data.error || "That wasn't saved."); return; }
  if (on) {
    const e = PICK.items.find(x => x.key === key);
    PICK.items = PICK.items.filter(x => x.key !== key); PICK.off.delete(key);
    if (e) PICK.skipped.push(e);
  } else {
    const e = PICK.skipped.find(x => x.key === key);
    PICK.skipped = PICK.skipped.filter(x => x.key !== key);
    if (e) PICK.items.push(e);
  }
  drawPick();
}
$("#pickDialog").addEventListener("change", e => {
  const of = e.target.dataset.fileOf;
  if (of != null) {   // one file of a product
    const off = PICK.offFiles.get(of) || new Set(), item = PICK.items.find(x => x.key === of);
    if (e.target.checked) off.delete(e.target.dataset.file); else off.add(e.target.dataset.file);
    PICK.offFiles.set(of, off);
    if (item && off.size >= fileNames(item).length) { PICK.off.add(of); PICK.offFiles.delete(of); }   // none: the product's unticked
    drawPick();
    return;
  }
  const k = e.target.dataset.pick; if (k == null) return;
  if (e.target.checked) PICK.off.delete(k); else PICK.off.add(k);
  drawPick();
});
$("#pickDialog").addEventListener("toggle", e => {   // a product's files stay open as the list is drawn again
  const k = e.target.dataset && e.target.dataset.filesOf; if (k == null) return;
  if (e.target.open) PICK.openFiles.add(k); else PICK.openFiles.delete(k);
}, true);
$("#pickDialog").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.skip != null) pickSkip(b.dataset.skip, true);
  else if (b.dataset.unskip != null) pickSkip(b.dataset.unskip, false);
  else if (b.dataset.pickAll) { PICK.off = b.dataset.pickAll === "on" ? new Set() : new Set(PICK.items.map(x => x.key)); drawPick(); }
  else if (b.dataset.pickGo) {
    $("#pickDialog").close();
    DL_FILES = null;   // (whatever was chosen before, and not used, is forgotten)
    if (b.dataset.pickGo !== "go") return;
    const files = {};
    for (const [k, off] of PICK.offFiles) {
      const item = PICK.items.find(x => x.key === k);
      if (item && off.size && !PICK.off.has(k)) files[k] = { shown: fileNames(item), chosen: fileNames(item).filter(n => !off.has(n)) };
    }
    DL_FILES = Object.keys(files).length ? files : null;
    PICK.go(PICK.off.size ? PICK.items.filter(x => !PICK.off.has(x.key)).map(x => x.key) : null);
  }
});

let routineShown = null;
function showRoutine(found) {
  const note = $("#routineNote");
  if (!note) return;
  const key = found ? `${found.at}|${found.new}|${found.updates}` : null;
  if (key === routineShown) return;
  routineShown = key;
  note.hidden = !found;
  if (!found) return;
  const n = (k, one, many) => `${found[k]} ${found[k] === 1 ? one : many}`;
  $("#routineText").textContent = "The routine check found " + [found.new && n("new", "new product", "new products"),
    found.updates && n("updates", "update", "updates")].filter(Boolean).join(" and ") + " to download.";
}
async function routineSeen() {
  $("#routineNote").hidden = true;
  await apiPost("/api/routine/seen", {});
}
$("#routineLater").addEventListener("click", routineSeen);
$("#routineChoose").addEventListener("click", () => {
  const stores = (DATA.downloadable || ["booth", "gumroad", "jinxxy", "itch"]).slice();
  routineSeen();
  downloadNew(stores);
});

let SUPPORT_CONTEXT = {};
function closeSupportReport() {
  const d = $("#supportDialog");
  if (d && d.open) d.close();
}
function openSupportReport(context = {}) {
  const d = $("#supportDialog");
  if (!d) return;
  SUPPORT_CONTEXT = context || {};
  $("#supportResult").hidden = true;
  $("#supportStatus").textContent = "The report is built locally and sanitized before it is saved.";
  $("#supportCreate").disabled = false;
  $("#supportNotes").value = "";
  if (d.showModal) d.showModal();
  else d.hidden = false;
}
async function createSupportReport() {
  const button = $("#supportCreate"), status = $("#supportStatus"), result = $("#supportResult");
  button.disabled = true;
  result.hidden = true;
  status.textContent = "Building the sanitized report…";
  const r = await apiPost("/api/diagnostics/report", { notes: $("#supportNotes").value, context: SUPPORT_CONTEXT });
  if (!r.ok) {
    status.textContent = r.data.error || "Hoard couldn't create the report.";
    button.disabled = false;
    return;
  }
  status.textContent = "Saved locally. Hoard did not upload anything. The report folder has been opened.";
  $("#supportFile").textContent = r.data.filename || "Support report";
  $("#supportPath").textContent = r.data.path || "";
  $("#supportPreview").textContent = r.data.preview || "";
  $("#supportIncident").textContent = r.data.id ? `Incident ID: ${r.data.id}` : "";
  result.hidden = false;
  button.disabled = false;
}
async function openSupportFolder() {
  const r = await apiPost("/api/diagnostics/open-folder");
  if (!r.ok) { toast(r.data.error || "Couldn't open the report folder."); return; }
  closeSupportReport();
}
async function copySupportPath() {
  const path = $("#supportPath").textContent;
  if (!path) return;
  try { await navigator.clipboard.writeText(path); toast("Report path copied."); }
  catch (e) { toast("Couldn't copy the report path."); }
}
function closeSettings() {
  $("#settingsPanel").hidden = true;
  $("#settingsBtn").setAttribute("aria-expanded", "false");
}
const BROWSER_NAMES = { msedge: "Microsoft Edge", chrome: "Google Chrome", chromium: "Hoard's own browser" };
function showBrowserInUse() {   // what the chosen browser really is on this computer (issue #20)
  const chosen = $("#setBrowser").value, used = ((SETTINGS && SETTINGS.browsers) || {})[chosen];
  $("#browserInUse").textContent = !used ? ""
    : chosen && used !== chosen ? `${BROWSER_NAMES[chosen]} isn't installed on this computer, so Hoard signs in with its own browser.`
    : `Hoard signs in with ${BROWSER_NAMES[used]}.`;
}
async function openSettings(open) {
  if (!(open ?? $("#settingsPanel").hidden)) return closeSettings();
  try {
    SETTINGS = await (await api("/api/settings", { cache: "no-store" })).json();
  } catch (e) {
    toast("Hoard isn't running. Open it again."); return;
  }
  $("#settingsPanel").hidden = false;
  $("#settingsBtn").setAttribute("aria-expanded", "true");
  winNote("settingsPanel", "");
  fillSettings();
}
const canPick = () => !!(typeof DATA === "object" && DATA && DATA.can_pick);
function syncBrowse() { for (const b of document.querySelectorAll("[data-browse]")) b.hidden = !canPick(); }
async function browseInto(input, kind = "folder") {
  const r = await apiPost("/api/pick", { kind });
  if (!r.ok) { toast(r.data.error || "The picker didn't open. Type the path instead."); return false; }
  if (!r.data.path) return false;   // cancelled
  input.value = r.data.path;
  return true;
}
function fillSettings() {   // the controls, as the settings are now
  syncBrowse();
  $("#setRoot").value = SETTINGS.root;
  renderLibs(SETTINGS.libraries);
  $("#setNewDays").value = String(SETTINGS.new_days ?? 7);
  $("#setRetries").value = String(SETTINGS.download_retries ?? 2);
  $("#setOffline").checked = SETTINGS.offline_images;
  $("#setUpdates").checked = SETTINGS.check_for_updates;
  $("#setBetas").checked = !!SETTINGS.beta_updates;
  $("#setBackground").checked = !!SETTINGS.close_to_taskbar;
  $("#backgroundRow").hidden = !DATA.can_background;
  showUpdate();
  $("#setBrowser").value = SETTINGS.browser_channel;
  showBrowserInUse();
  $("#setRoutine").value = String(SETTINGS.routine_hours ?? 0);
  $("#setTextSize").value = String(SETTINGS.display.text_size);
  $("#setPause").checked = SETTINGS.display.pause_animations;
  $("#setMotion").checked = SETTINGS.display.reduce_motion;
  $("#setGlowOn").checked = SETTINGS.display.glow;
  $("#setColours").value = SETTINGS.display.colours;
  fillColours();
  $("#setShops").value = (SETTINGS.payhip_shops || []).map(s => s.replace(/^https:\/\//, "")).join("\n");
  const box = (store, opt, on, label, sub) =>
    `<label class="check${sub ? " sub" : ""}"><input type="checkbox" data-set-store="${store}" data-opt="${opt}"${on ? " checked" : ""}> ${label}</label>`;
  $("#setStores").innerHTML = Object.entries(SETTINGS.stores).map(([s, o]) => box(s, "enabled", o.enabled, STORE_NAMES[s]) +
    (s === "booth" ? box(s, "include_gifts", o.include_gifts, "Include gifts", true) +
                     box(s, "include_free", o.include_free, "Include free downloads", true) : "") +
    (s === "gumroad" ? box(s, "include_archived", o.include_archived, "Include archived purchases", true) : "") +
    (s === "itch" ? box(s, "skip_game_builds", o.skip_game_builds, "Skip game builds (files marked for Windows, macOS, Linux or Android)", true) : "")).join("");
}
let UPDATE = null, updTimer = null;
const verText = v => String(v || "").replace(/-beta\.(\d+)$/, " beta $1");   // "3.1.0-beta.2" as "3.1.0 beta 2"
async function showUpdate(u) {
  if (!u) {
    try {
      const r = await api("/api/update", { cache: "no-store" });
      if (!r.ok) return;   // not this page's key (yet), or Hoard has stopped to update
      u = await r.json();
    } catch (e) { return; }
  }
  UPDATE = u;
  $("#updStatus").textContent = describeUpdate(u);
  $("#updInstall").hidden = !u.can_install || u.busy;
  $("#updInstall").textContent = u.available ? `Update to ${verText(u.latest.version)}` : "";
  $("#updCheck").disabled = !!u.busy;
  $("#updLink").hidden = !u.available;
  $("#updLink").href = u.available ? u.latest.url : u.releases_page;
  const note = $("#updateNote");   // the header's "Update to ..." link, on the Library page
  if (note) { note.hidden = !u.available; note.textContent = u.available ? `Update to ${verText(u.latest.version)}` : ""; }
  clearTimeout(updTimer);
  if (u.busy) updTimer = setTimeout(() => showUpdate(), 1000);
}
async function checkUpdate() {
  if (!navigator.onLine) { toast("You're offline. Checking for updates needs a connection."); return; }
  $("#updCheck").disabled = true;
  $("#updStatus").textContent = "Checking";
  const r = await apiPost("/api/update/check");
  if (!r.ok) { $("#updCheck").disabled = false; $("#updStatus").textContent = r.data.error || "Couldn't check for updates."; return; }
  showUpdate(r.data);
}
async function installUpdate() {
  if (!UPDATE || !UPDATE.available) return;
  if (!await ask(`Update to Hoard ${verText(UPDATE.latest.version)}? Hoard downloads it, closes, installs it and opens again. ` +
               "Your library, settings, sign-ins and downloads stay as they are.", "Update")) return;
  const r = await apiPost("/api/update/install");
  if (!r.ok) { toast(r.data.error || "The update didn't start."); return; }
  showUpdate({ ...UPDATE, busy: true, message: "Starting", error: "" });
}

let dlFade;
async function startSync() {
  if (!navigator.onLine) { toast("You're offline. Syncing needs a connection."); return; }
  const r = await apiPost("/api/sync", {});
  if (!r.ok) { toast(r.data.error || "Syncing didn't start."); return; }
  if (queuedToast(r)) return;
  dlActive = true;
  showDownload({ running: true, sync: true, task: "sync", message: "Starting", log: [] });
  pollDownload();
}

function dockPanels() {
  const shown = [...document.querySelectorAll(".dlpanel")].filter(p => !p.hidden);
  const dl = shown.find(p => !p.classList.contains("imppanel")), imp = shown.find(p => p.classList.contains("imppanel"));
  const s = document.body.style;
  s.setProperty("--dl-h", (dl ? dl.offsetHeight : 0) + "px");
  s.setProperty("--dl-all", shown.reduce((n, p) => n + p.offsetHeight + 12, 0) + "px");
  document.body.classList.toggle("dl-showing", shown.length > 0);
  document.body.classList.toggle("dl-both", !!(dl && imp));
}
function wireDock() {
  const sizes = typeof ResizeObserver === "function" ? new ResizeObserver(dockPanels) : null;
  for (const p of document.querySelectorAll(".dlpanel")) {
    new MutationObserver(dockPanels).observe(p, { attributes: true, attributeFilter: ["hidden"] });
    if (sizes) sizes.observe(p);
  }
  dockPanels();
}
const GLOW_COLORS = ["booth", "gumroad", "jinxxy", "payhip", "itch"];
let glowShown = null;
function setGlow(store, stores) {
  const el = $("#glow");
  if (!el) return;
  const list = store ? [store] : (stores || []).filter(s => GLOW_COLORS.includes(s));
  const key = (store ? "one:" : "all:") + list.join(",");
  if (key === glowShown) return;
  glowShown = key;
  const light = matchMedia("(prefers-color-scheme: light)").matches;
  const strength = light ? 32 : 48;
  const tint = c => `color-mix(in srgb, var(--${c}) ${strength}%, transparent)`;
  const inner = el.firstElementChild;
  if (list.length <= 1) {   // one colour, the width of the window
    const c = list[0];
    el.classList.remove("flow");
    inner.style.backgroundImage = c
      ? `radial-gradient(ellipse 120% 95% at 50% 115%, ${tint(c)} 0%, transparent 75%)`
      : `radial-gradient(ellipse 120% 95% at 50% 115%, color-mix(in srgb, var(--gold) ${strength - 16}%, transparent) 0%, transparent 75%)`;
  } else {   // each colour in turn along twice the window's width, drifting left and around again
    el.classList.add("flow");
    const spots = [...list, ...list], step = 100 / spots.length;
    inner.style.backgroundImage = spots.map((c, i) =>
      `radial-gradient(ellipse ${Math.max(step * 1.9, 22)}% 95% at ${(i + 0.5) * step}% 115%, ${tint(c)} 0%, transparent 75%)`).join(", ");
  }
  if (!document.body.classList.contains("less-motion") && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 450, easing: "ease-out" });
  }
}
const WINDOWS = { tagPanel: () => openTagPanel(false), stores: () => { if (typeof openStores === "function") openStores(false); },
                  settingsPanel: () => closeSettings(), tasksWin: () => openTasks(false),
                  newsWin: () => { $("#newsWin").hidden = true; } };
/* How you left the pages: windows' places, the sidebar, the tile size. Kept in Hoard's settings (config.json),
   not the page's own storage, which goes with the server's address, and that's new each time Hoard starts. */
let UI = { windows: {}, sections: {} }, uiPending = null, uiTimer = null, uiApplied = false;
const SECTIONS = {};   // each sidebar section's fold, by name
let setSideFold = null;
function uiSave(part) {
  uiPending = uiPending || {};
  for (const [k, v] of Object.entries(part)) {
    const obj = v && typeof v === "object";
    UI[k] = obj ? { ...(UI[k] || {}), ...v } : v;
    uiPending[k] = obj ? { ...(uiPending[k] || {}), ...v } : v;
  }
  clearTimeout(uiTimer);
  uiTimer = setTimeout(uiFlush, 300);
}
function uiFlush() {   // also as the page is left (to the other view, or closing), so nothing just changed is lost
  clearTimeout(uiTimer);
  if (!uiPending || !ACCESS.key) return;
  const ui = uiPending; uiPending = null;
  api("/api/settings", { method: "POST", keepalive: true, body: JSON.stringify({ ui }),   // keepalive: sent even as the page goes
                         headers: { "Content-Type": "application/json" } }).catch(() => {});
}
addEventListener("pagehide", uiFlush);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") uiFlush(); });
function winOpened(el) {   // one panel at a time: the others close as this one opens
  const from = document.activeElement;
  for (const other of document.querySelectorAll(".win:not([hidden])")) if (other !== el) WINDOWS[other.id]();
  winShade();
  el.scrollTop = 0;
  // The keyboard goes with it: into the panel now, and back to what opened it when it closes
  if (from && from !== document.body && !el.contains(from)) el._opener = from.closest(".win") ? from.closest(".win")._opener : from;
  requestAnimationFrame(() => {
    if (el.hidden || el.contains(document.activeElement) || document.querySelector("dialog[open]")) return;
    const first = winFocusables(el).find(n => !n.classList.contains("win-x")) || el.querySelector(".win-x");
    if (first) first.focus({ preventScroll: true });
  });
}
function winClosed(el) {
  winShade();
  const back = el._opener;
  el._opener = null;
  const lost = !document.activeElement || document.activeElement === document.body || el.contains(document.activeElement);
  if (lost && back && back.isConnected && !back.closest(".win[hidden]") && !document.querySelector(".win:not([hidden])"))
    back.focus({ preventScroll: true });
}
const FOCUSABLE = "a[href], button:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), " +
                  "textarea:not([disabled]), summary, [tabindex]:not([tabindex='-1'])";
function winFocusables(el) {
  return [...el.querySelectorAll(FOCUSABLE)].filter(n => n.getClientRects().length && !n.closest("[hidden], [inert]"));
}
// Tab stays in the open panel, as it would in a window of its own (the page behind is dimmed, not in use)
document.addEventListener("keydown", e => {
  if (e.key !== "Tab" || document.querySelector("dialog[open]")) return;
  const el = document.querySelector(".win:not([hidden])");
  if (!el) return;
  const all = winFocusables(el);
  if (!all.length) return;
  const at = all.indexOf(document.activeElement);
  if (at === -1 || (e.shiftKey && at === 0) || (!e.shiftKey && at === all.length - 1)) {
    e.preventDefault();
    (e.shiftKey ? all[all.length - 1] : all[0]).focus();
  }
});
function winShade() {   // the page behind an open panel is dimmed, and a click on it closes the panel
  let shade = document.getElementById("winShade");
  const open = !!document.querySelector(".win:not([hidden])");
  if (!shade) {
    if (!open) return;
    shade = document.createElement("div");
    shade.id = "winShade"; shade.className = "win-shade";
    shade.addEventListener("click", closeTopWindow);
    document.body.appendChild(shade);
  }
  shade.hidden = !open;
  document.body.classList.toggle("win-open", open);
}
function makeWindow(el) {
  if (!el || el.classList.contains("win")) return;
  el.classList.add("win");
  const bar = document.createElement("div"), body = document.createElement("div");
  bar.className = "win-bar"; body.className = "win-body";
  const title = el.querySelector(":scope > h2");
  while (el.firstChild) body.appendChild(el.firstChild);
  if (title) bar.appendChild(title);
  const extra = document.createElement("span"); extra.className = "win-extra"; extra.setAttribute("aria-live", "polite");
  const x = document.createElement("button"); x.className = "win-x"; x.textContent = "×";
  x.setAttribute("aria-label", "Close " + (title ? title.textContent.trim() : "panel"));
  bar.append(extra, x);
  el.append(bar, body);
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "true");
  if (title) { title.id = title.id || el.id + "Title"; el.setAttribute("aria-labelledby", title.id); }
  x.addEventListener("click", () => WINDOWS[el.id]());
  new MutationObserver(() => { if (!el.hidden) winOpened(el); else winClosed(el); })
    .observe(el, { attributes: true, attributeFilter: ["hidden"] });
  if (!el.hidden) winOpened(el);
}
// Escape closes the open panel
function closeTopWindow() {
  const open = document.querySelector(".win:not([hidden])");
  if (!open) return false;
  WINDOWS[open.id]();
  return true;
}
function winNote(id, text, ok = false) {   // a word in a panel's title bar: "Saved", "Saving..."
  const n = document.querySelector(`#${id} .win-extra`);
  if (n) { n.textContent = text; n.classList.toggle("ok", ok); }
}
function refitWindows() {}   // the panel is sized by the page's own styles, at any text size

function wireSidebar() {
  const side = $("#filters");
  if (!side || side.dataset.wired) return;
  side.dataset.wired = "1";
  for (const h of [...side.children].filter(n => n.tagName === "H2")) {
    const sec = document.createElement("section"), body = document.createElement("div");
    sec.className = "sec"; body.className = "sec-body";
    const rest = [];
    for (let n = h.nextSibling; n && !(n.nodeType === 1 && n.tagName === "H2"); n = n.nextSibling) rest.push(n);
    h.before(sec); sec.append(h, body); body.append(...rest);
    const text = h.firstChild && h.firstChild.nodeType === 3 ? h.firstChild : null;
    const name = (text ? text.textContent : h.textContent).trim();
    const key = name.toLowerCase().replace(/\W+/g, "-").slice(0, 40);
    const btn = document.createElement("button");
    btn.className = "sec-toggle"; btn.innerHTML = `<span class="chev" aria-hidden="true"></span>`;
    btn.append(document.createTextNode(name));
    if (text) text.remove(); else h.textContent = "";
    h.prepend(btn);
    const set = (open, keep = true) => {
      sec.classList.toggle("closed", !open); btn.setAttribute("aria-expanded", String(open));
      if (keep) uiSave({ sections: { [key]: open } });
    };
    btn.addEventListener("click", () => set(sec.classList.contains("closed")));
    SECTIONS[key] = set;
    set((UI.sections || {})[key] !== false, false);
  }
  const fold = document.createElement("button");
  fold.className = "side-fold"; fold.id = "sideFold";
  fold.innerHTML = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3 5 8l5 5"/></svg><span>Hide filters</span>`;
  side.prepend(fold);
  const setFold = (folded, keep = true) => {
    document.body.classList.toggle("side-folded", folded);
    fold.setAttribute("aria-expanded", String(!folded));
    fold.title = folded ? "Show filters" : "Hide filters";
    fold.setAttribute("aria-label", fold.title);
    if (keep) uiSave({ side_folded: folded });
  };
  fold.addEventListener("click", () => setFold(!document.body.classList.contains("side-folded")));
  setSideFold = setFold;
  setFold(!!UI.side_folded, false);
}

function settingsPart(el) {
  if (el.dataset.colour) {   // all of them, so what's saved is what you see
    const mine = {};
    for (const i of document.querySelectorAll("#customColours input[data-colour]")) mine[i.dataset.colour] = i.value;
    return { display: { colours: "custom", custom_colours: mine } };
  }
  if (el.dataset.setStore) return { stores: { [el.dataset.setStore]: { [el.dataset.opt]: el.checked } } };
  switch (el.id) {
    case "setRoot": { const root = el.value.trim(); return { root: root === SETTINGS.default_root ? "" : root }; }
    case "setOffline": return { offline_images: el.checked };
    case "setUpdates": return { check_for_updates: el.checked };
    case "setBetas": return { beta_updates: el.checked };
    case "setBackground": return { close_to_taskbar: el.checked };
    case "setBrowser": return { browser_channel: el.value };
    case "setRoutine": return { routine_hours: Number(el.value) };
    case "setNewDays": return { new_days: Number(el.value) };
    case "setRetries": return { download_retries: Number(el.value) };
    case "setGlowOn": return { display: { glow: el.checked } };
    case "setColours": return { display: { colours: el.value } };
    case "setTextSize": case "setPause": case "setMotion":
      return { display: { text_size: Number($("#setTextSize").value), pause_animations: $("#setPause").checked,
                          reduce_motion: $("#setMotion").checked } };
    case "setShops": return { payhip_shops: el.value.split("\n").map(x => x.trim()).filter(Boolean) };
  }
  return null;
}
const RELOAD_AFTER = ["root", "stores", "payhip_shops", "new_days", "offline_images"];
let saving = Promise.resolve();
function autosave(el) {
  const part = SETTINGS && settingsPart(el);
  if (!part) return;
  saving = saving.then(async () => {   // one at a time, in the order they were made
    winNote("settingsPanel", "Saving…");
    const r = await apiPost("/api/settings", part);
    if (!r.ok) {
      toast(r.data.error || "That setting wasn't saved.");
      winNote("settingsPanel", "Not saved");
      if (r.data.settings) { SETTINGS = r.data.settings; fillSettings(); }   // put back as it is
      return;
    }
    SETTINGS = r.data.settings;
    applyDisplay(SETTINGS.display);
    if ("display" in part) refitWindows();
    if (part.display && "colours" in part.display) fillColours();
    if ("browser_channel" in part) showBrowserInUse();
    if ("beta_updates" in part) showUpdate();   // a beta found earlier shows, or stops showing, as an update
    winNote("settingsPanel", "Saved", true);
    if (Object.keys(part).some(k => RELOAD_AFTER.includes(k))) T.reload();
  });
}
function wireAutosave() {
  $("#setBrowser").addEventListener("change", showBrowserInUse);   // at once, before it's saved
  $("#settingsPanel").addEventListener("change", e => { if (e.target.matches("input, select, textarea")) autosave(e.target); });
  $("#setRootBrowse").addEventListener("click", async () => {
    if (SETTINGS && await browseInto($("#setRoot"))) autosave($("#setRoot"));
  });
  $("#setRootDefault").addEventListener("click", () => {
    if (!SETTINGS) return;
    $("#setRoot").value = SETTINGS.default_root;
    autosave($("#setRoot"));
  });
}

function sizeText(n) {
  const units = ["bytes", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return i ? `${n.toFixed(1)} ${units[i]}` : `${Math.round(n)} bytes`;
}
function timeLeft(s) {
  s = Math.max(0, Math.round(s));
  return s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min`;
}
function transferHtml(t) {
  if (!t || !t.file) return "";
  const pct = t.total ? Math.min(100, (t.got || 0) * 100 / t.total) : null;
  const stats = [t.total ? `${sizeText(t.got || 0)} of ${sizeText(t.total)}` : `${sizeText(t.got || 0)} so far`];
  if (t.speed != null) stats.push(`${sizeText(t.speed)}/s`);
  if (t.eta != null) stats.push(`${timeLeft(t.eta)} left`);
  const bar = pct == null
    ? `<div class="xfer-bar unknown" role="progressbar" aria-label="${esc(t.file)}"><span></span></div>`
    : `<div class="xfer-bar" role="progressbar" aria-label="${esc(t.file)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.floor(pct)}"><span style="width: ${pct.toFixed(1)}%"></span></div>`;
  return `<div class="xfer"><div class="xfer-file" title="${esc(t.file)}">${esc(t.file)}</div>${bar}` +
    `<div class="xfer-stats"><span>${pct == null ? "" : Math.floor(pct) + "%"}</span><span>${esc(stats.join(" · "))}</span></div></div>`;
}
function showTransfer(box, t) {   // updates the bar in place, so it slides rather than jumps
  if (!t || !t.file) { box.hidden = true; box.innerHTML = ""; box.dataset.file = ""; return; }
  box.hidden = false;
  const fresh = document.createElement("div");
  fresh.innerHTML = transferHtml(t);
  const bar = box.querySelector(".xfer-bar"), next = fresh.querySelector(".xfer-bar");
  if (box.dataset.file !== t.file || !bar || bar.className !== next.className) {
    box.dataset.file = t.file;
    box.replaceChildren(...fresh.childNodes);
    return;
  }
  bar.firstElementChild.style.width = next.firstElementChild.style.width;
  if (next.hasAttribute("aria-valuenow")) bar.setAttribute("aria-valuenow", next.getAttribute("aria-valuenow"));
  box.querySelector(".xfer-stats").replaceWith(fresh.querySelector(".xfer-stats"));
}

let tasksTimer = null, tasksShown = "";
function openTasks(open) {
  const w = $("#tasksWin"), show = open ?? w.hidden;
  w.hidden = !show;
  $("#tasksTab").setAttribute("aria-expanded", String(show));
  clearTimeout(tasksTimer);
  if (show) { tasksShown = ""; loadTasks(); }
}
async function loadTasks() {
  clearTimeout(tasksTimer);
  if ($("#tasksWin").hidden) return;
  try {
    const r = await api("/api/tasks", { cache: "no-store" });
    if (r.ok) renderTasks(await r.json());
  } catch (e) { /* Hoard stopped: the page says so elsewhere */ }
  tasksTimer = setTimeout(loadTasks, 1500);
}
const OUTCOMES = { done: "Done", partial: "Partly done", failed: "Failed", stopped: "Stopped" };
const STOPPABLE = ["download", "check-updates", "sync"];
function whenDone(iso) { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); }
function tookTime(a, b) {
  const s = (Date.parse(b) - Date.parse(a)) / 1000;
  return isNaN(s) ? "" : s < 60 ? `${Math.max(0, Math.round(s))} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
}
function renderTasks(t) {
  const json = JSON.stringify(t);
  if (json === tasksShown) return;
  tasksShown = json;
  const open = new Set([...document.querySelectorAll("#tasksBody details[open]")].map(d => d.dataset.id));
  const cur = t.current;
  const problems = h => ((h.report && h.report.problems) || []);
  $("#tasksBody").innerHTML =
    `<h3>Running</h3>` + (cur
      ? `<div class="task run"><div class="task-top"><span class="spin" aria-hidden="true"></span><b>${esc(cur.label)}</b>` +
        (STOPPABLE.includes(cur.task) ? `<button class="ghost sm" data-task="stop">Stop</button>` : "") +
        `<button class="ghost sm" data-task="force" title="End it now, whatever it's doing">Force stop</button></div>` +
        (cur.transfer ? transferHtml(cur.transfer) : `<p class="task-msg">${esc(cur.message || "Starting")}</p>`) +
        `<details data-id="${esc(cur.id)}"${open.has(cur.id) ? " open" : ""}><summary>Progress</summary><pre>${esc((cur.log || []).join("\n"))}</pre></details></div>`
      : `<p class="none">Nothing is running.</p>`) +
    `<h3>Waiting <span class="n">${t.queue.length || ""}</span>${t.queue.length > 1 ? `<button class="linkish" data-task="clear-queue">Clear</button>` : ""}</h3>` +
    (t.queue.length
      ? `<ol class="tasklist">${t.queue.map(q => `<li class="task"><span>${esc(q.label)}</span>` +
          `<button class="untag" data-task="remove" data-id="${esc(q.id)}" aria-label="Take ${esc(q.label)} off the queue">×</button></li>`).join("")}</ol>`
      : `<p class="none">Nothing is waiting. What you start while something runs waits here for its turn.</p>`) +
    `<h3>Finished${t.history.length ? `<button class="linkish" data-task="clear-history">Clear</button>` : ""}</h3>` +
    (t.history.length ? t.history.map(h =>
      `<details class="task done-${esc(h.outcome)}" data-id="${esc(h.id)}"${open.has(h.id) ? " open" : ""}>` +
      `<summary><span class="outcome">${OUTCOMES[h.outcome] || "Done"}</span><b>${esc(h.label)}</b>` +
      `<span class="when">${esc(whenDone(h.ended))}${h.started ? ` · took ${esc(tookTime(h.started, h.ended))}` : ""}</span></summary>` +
      (h.message ? `<p class="task-msg">${esc(h.message)}</p>` : "") +
      (problems(h).length ? `<ul class="problems">${problems(h).map(p => `<li>${esc(p)}</li>`).join("")}</ul>` : "") +
      ((h.log || []).length ? `<pre>${esc(h.log.join("\n"))}</pre>` : "") + `</details>`).join("")
      : `<p class="none">Nothing yet. Each refresh, sync and download is listed here when it's done.</p>`);
  taskCount((cur ? 1 : 0) + t.queue.length);
}
function taskCount(n) {
  const b = $("#tasksCount");
  if (b) { b.hidden = !n; b.textContent = n || ""; }
}
let PROJECTS = [];
const PROJECT_STATUS = { yes: "In the project", partly: "Partly in the project", imported: "Imported, not found now" };
const CREDIT_STYLES = { List: "List", Markdown: "Markdown", ByCreator: "By creator" };
function openProjects(open) {
  const w = $("#projectsWin"), show = open ?? w.hidden;
  w.hidden = !show;
  $("#projectsTab").setAttribute("aria-expanded", String(show));
  if (show) loadProjects();
}
async function loadProjects() {
  const body = $("#projectsBody");
  try {
    const r = await api("/api/projects", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    const data = await r.json();
    PROJECTS = data.projects || [];
    body.innerHTML = renderProjects(PROJECTS, data.hidden_left_out);
  } catch (e) { body.innerHTML = `<p class="none">Projects couldn't be read just now.</p>`; }
}
function renderProjects(list, hiddenLeftOut) {
  if (!list.length) return `<p class="none">No projects yet. Open <strong>Window &gt; Hoard</strong> in a Unity project
    (Hoard for Unity 0.4.0 or newer) and it appears here, with every asset it uses and its credits list.</p>`;
  return (hiddenLeftOut ? `<p class="hint">Hidden items are left out while your hidden library is locked.</p>` : "") +
    list.map((p, i) => {
      const used = p.assets.length, updates = p.assets.filter(a => a.update).length;
      const style = p.credits.style;
      return `<details class="proj" data-project="${i}"${list.length === 1 ? " open" : ""}><summary><b>${esc(p.name)}</b>` +
        `<span class="n">${used} ${used === 1 ? "asset" : "assets"}${updates ? `, ${updates} with updates` : ""}</span>` +
        `<span class="meta">${esc(p.path)}${p.updated ? ` · opened in Unity ${esc(ago(p.updated))}` : ""}${p.unity ? ` · Unity ${esc(p.unity)}` : ""}</span></summary>` +
        (used ? `<table>${p.assets.map(a => `<tr><td>${a.download != null
            ? `<a href="/downloads#open=${a.download}">${esc(a.name)}</a>` : esc(a.name)}<br><span class="muted">${esc(a.creator)} · ${esc(storeLabel(a.store))}</span></td>` +
          `<td class="st ${a.status}">${PROJECT_STATUS[a.status]}${a.update ? ` <span class="upd">Update</span>` : ""}</td></tr>`).join("")}</table>`
          : `<p class="none">Nothing from Hoard is in it yet.</p>`) +
        `<h4>Credits</h4><div class="row"><select data-proj-style aria-label="Credits style">${Object.entries(CREDIT_STYLES).map(([k, v]) =>
          `<option value="${k}"${k === style ? " selected" : ""}>${v}</option>`).join("")}</select>` +
        `<button class="ghost sm" data-proj="copy">Copy</button></div>` +
        `<textarea readonly aria-label="Credits for ${esc(p.name)}">${esc(p.credits_text[style])}</textarea>` +
        `<p class="hint">The same list as <strong>Create Credits List</strong> in Unity, with what you changed there.</p>` +
        `<div class="row"><button class="ghost sm" data-proj="forget">Forget this project</button></div></details>`;
    }).join("");
}
function wireProjects() {
  makeWindow($("#projectsWin"));
  WINDOWS.projectsWin = () => openProjects(false);
  $("#projectsTab").addEventListener("click", () => openProjects());
  $("#projectsWin").addEventListener("change", e => {
    const sel = e.target.closest("[data-proj-style]"); if (!sel) return;
    const box = sel.closest(".proj"), p = PROJECTS[+box.dataset.project];
    box.querySelector("textarea").value = p.credits_text[sel.value];
  });
  $("#projectsWin").addEventListener("click", async e => {
    const b = e.target.closest("[data-proj]"); if (!b) return;
    const box = b.closest(".proj"), p = PROJECTS[+box.dataset.project];
    if (b.dataset.proj === "copy") {
      const text = box.querySelector("textarea").value;
      try { await navigator.clipboard.writeText(text); }
      catch (err) { box.querySelector("textarea").select(); document.execCommand("copy"); }
      toast("Copied the credits.");
    } else if (b.dataset.proj === "forget") {
      if (!await ask(`Forget ${p.name}? It comes back next time you open it in Unity with Hoard's window.`, "Forget")) return;
      await apiPost("/api/projects/forget", { id: p.id });
      loadProjects();
    }
  });
}
function openNews() {
  const w = $("#newsWin");
  makeWindow(w);
  $("#newsBetas").checked = !!(typeof SETTINGS === "object" && SETTINGS && SETTINGS.beta_updates);
  w.hidden = false;
  loadNews();
}
async function loadNews() {
  const body = $("#newsBody");
  try {
    const d = await (await api(`/api/changelog?betas=${$("#newsBetas").checked ? 1 : 0}`, { cache: "no-store" })).json();
    body.innerHTML = d.releases.length ? d.releases.map(r =>
      `<article class="news-release"><h3>${esc(r.version)}${r.beta ? ' <span class="n">Beta</span>' : ""}` +
      `${r.version === d.version ? ' <span class="n">This version</span>' : ""}</h3>${r.html}</article>`).join("")
      : `<p class="none">This copy of Hoard doesn't include its changelog.</p>`;
    for (const a of body.querySelectorAll("a[href]")) { a.target = "_blank"; a.rel = "noopener noreferrer"; }
  } catch (e) { body.innerHTML = `<p class="none">Couldn't load the changelog.</p>`; }
}
function wireNews() {
  $("#newsOpen").addEventListener("click", () => { if (typeof closeSettings === "function") closeSettings(); openNews(); });
  $("#newsBetas").addEventListener("change", loadNews);
}
function wireTasks() {
  makeWindow($("#tasksWin"));
  $("#tasksTab").addEventListener("click", () => openTasks());
  $("#tasksWin").addEventListener("click", async e => {
    const b = e.target.closest("[data-task]"); if (!b) return;
    const act = b.dataset.task;
    if (act === "stop") {   // (Hoard not answering isn't the job refusing to stop)
      const r = await apiPost("/api/cancel");
      if (!r.ok) toast(r.data.error || "Hoard didn't answer. Try again."); else if (!r.data.ok) toast("That job can't be stopped part-way.");
    }
    else if (act === "force") {   // any task, now: its store browser or sign-in window is closed at once
      if (!await ask("Force stop this task now? Hoard closes its store browser or sign-in window straight away. What " +
                     "finished is kept, and a file part way through resumes next time where it can.", "Force stop", true)) return;
      const r = await apiPost("/api/force-stop");
      if (!r.ok) toast(r.data.error || "Hoard didn't answer. Try again."); else if (!r.data.ok) toast("Nothing is running.");
    }
    else if (act === "remove") await apiPost("/api/queue/remove", { id: b.dataset.id });
    else if (act === "clear-queue") await apiPost("/api/queue/clear");
    else if (act === "clear-history") { if (!await ask("Clear the list of finished tasks?", "Clear")) return; await apiPost("/api/tasks/clear"); }
    tasksShown = ""; loadTasks();
  });
  const pill = $("#job");
  if (pill) pill.addEventListener("click", () => openTasks(true));
  watchJobs();
}
// Keeps the Tasks count up to date, and brings up a download or sync that was waiting its turn when it starts.
let lastTask = null;   // a check of the downloads that just ended: the Downloads page shows what it found
async function askClose() {
  const d = $("#closeDialog");
  if (!d || d.open) return;
  let j = {};
  try { j = (await (await api("/api/status", { cache: "no-store" })).json()).job || {}; } catch (e) { /* stopped */ }
  const waiting = (j.queue || []).length;
  $("#closeWhat").textContent = (j.running ? `${j.job_label || "A job"} is running` : "Nothing is running")
    + (waiting ? `, and ${waiting} more ${waiting === 1 ? "is" : "are"} waiting their turn.` : ".");
  $("#closeChoices").hidden = false;
  d.querySelector('[data-close="wait"]').hidden = false;
  d.querySelector('[data-close="background"]').hidden = !DATA.can_background;
  d.showModal();
}
function wireLogs() {
  const b = $("#openLogs");
  if (b) b.addEventListener("click", async () => {
    const r = await apiPost("/api/open-logs");
    toast(r.ok ? "Opened the logs folder." : (r.data.error || "The logs folder didn't open."));
  });
}
function wireClose() {
  wireLogs();
  const d = $("#closeDialog");
  if (!d) return;
  window.addEventListener("hoard-close", askClose);   // Hoard's window, asked to close while something runs
  d.addEventListener("click", async e => {
    const b = e.target.closest("[data-close]");
    if (!b) return;
    const how = b.dataset.close;
    if (how === "cancel") { d.close(); return; }
    const r = await apiPost("/api/app/close", { how });
    if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
    if (how === "background") { d.close(); return; }
    if (how === "wait") {   // only Close now is left, for when stopping takes too long
      $("#closeWhat").textContent = "Stopping what's running. Hoard closes as soon as it has.";
      d.querySelector('[data-close="wait"]').hidden = d.querySelector('[data-close="background"]').hidden = true;
      return;
    }
    $("#closeWhat").textContent = "Closing Hoard.";
    $("#closeChoices").hidden = true;
  });
}
// Something asked for while a job ran (taking an item out of Local, deleting downloaded files...) waits its turn as a
// job of its own: say so, and when it's done, show the page as it is then and say how it went.
async function afterQueuedJob(r, task, reload) {
  if (!queuedToast(r)) toast("Doing it now. Follow it in Tasks.");
  for (let n = 0; n < 2400; n++) {
    await new Promise(ok => setTimeout(ok, 1500));
    let t = {};
    try { t = await (await api("/api/tasks", { cache: "no-store" })).json(); } catch (e) { return; }
    if ((t.current && t.current.task === task) || (t.queue || []).some(q => q.task === task)) continue;
    await reload();
    const done = (t.history || []).find(h => h.task === task);   // how it went (newest first)
    if (done && done.message) toast(done.message);
    return;
  }
}
function queuedToast(r) {   // a job started while another runs waits its turn
  if (r && r.data && r.data.queued) { toast("Queued: it starts when what's running now is done. See Tasks."); return true; }
  return false;
}

