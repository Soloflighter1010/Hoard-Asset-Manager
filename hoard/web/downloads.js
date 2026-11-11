// Downloaded files and local packages: a view over the app's cached data.
// The shell owns navigation, shared windows, requests and the product components.
function createDownloadsView() {
// first, or it applies to nothing
const grid = $("#grid"), detail = $("#detail");
const state = { view: "downloads", space: "", q: "", store: "", lib: "", tags: new Set(), types: new Set(), creator: "", sort: "name", allTags: false, creatorFind: "", set: "", ptype: "" };
let DATA = { assets: [] }, byId = new Map(), openId = null, lastFocus = null;

// A store's name, from its folder's.
const storeName = folder => folder === "Itch" ? "itch.io" : folder;
const isLocal = a => a.store === "Local";   // your own (issue #80)   // a store as people write it, from its folder's name
// The address of a downloaded file (v: its version, so a changed picture isn't cached).
const fileUrl = (p, v) => keyed("/files/" + p.split("/").map(encodeURIComponent).join("/") + (v ? `?v=${+v}` : ""));
// A size in B, KB, MB, GB or TB.
function fmtSize(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + " " + u[i];
}
// A tile's letters, colour and file type, for a download with no picture.
function placeholder(a) {
  return `<span class="ph" style="--h:${hue(a.creator)}"><b>${esc(initials(a.name))}</b>` +
         `<small>${a.types[0] ? "." + esc(a.types[0]) : ""}</small></span>`;
}
// A download's picture (or its letters).
const art = a => a.thumb ? `<img src="${fileUrl(a.thumb, a.thumb_v)}" alt="" loading="lazy" decoding="async">` : placeholder(a);

/* ---------- highlights and accessibility */


/* ---------- data */
async function refreshView(response) {
  DATA = response;
  for (const a of DATA.assets) {
    withStoreTags(a).hay = norm([a.name, a.creator, a.store, storeName(a.store), a.variants, ...a.tags, ...a.suggested, ...a.files.map(f => f.path), a.your_note].join(" "));
  }
  byId = new Map(DATA.assets.map(a => [a.id, a]));
  stackMembers = new Map();
  for (const a of DATA.assets) if (a.stack_key) stackMembers.set(a.stack_key, [...(stackMembers.get(a.stack_key) || []), a]);
  if (APP.active !== "downloads") return;
  if (SPACE) mapSpace(SPACE);
  render();
  if (state.view === "space" && !SPACE) loadSpace();   // (opened at Disk space)
  if (openId != null && byId.has(openId)) showDetail(byId.get(openId), false);
  if (!UPDATE) showUpdate();   // (for the logo: it glows while an update is waiting)
  // copies on two stores whose pictures may be one picture saved twice: how they look decides (then read again)
  const wanted = (DATA.looks_wanted || []).map(w => ({ look_for: w.look_for, src: keyed("/thumb/" + encodeURIComponent(w.key)) }));
  if (wanted.length) lookAtPictures(wanted).then(found => { if (found) load(); });
  return DATA.assets.length;
}

/* ---------- filtering */
function matches(a, skip) {
  // Downloads, Archive, Removed or Hidden, as in the Library; a set's folder: all of it, archived or not
  if (inSets() && !state.set) return false;   // (every set's tile: no product's)
  if (!(inSets() ? setHas(a) : inView(a))) return false;
  if (state.store && !inSets() && a.store !== state.store) return false;   // (Sets: every set's tile, or the one open)
  if (state.lib !== "" && String(a.library || 0) !== state.lib) return false;   // a library folder's tab
  if (skip !== "creator" && state.creator && a.creator !== state.creator) return false;
  if (skip !== "ptype" && state.ptype && a.type !== state.ptype) return false;   // what it is (issue #223)
  for (const t of state.tags) if (!a.tags.includes(t) && !a.suggested.includes(t)) return false;
  for (const t of state.types) if (!a.types.includes(t)) return false;
  if (state.q && !searchMatches(a, state.q)) return false;   // (words, and prefixes: creator:, tag:...)
  return true;
}
const storeRank = folder => { const i = Object.keys(STORE_NAMES).indexOf(String(folder).toLowerCase()); return i < 0 ? 99 : i; };   // Local last
const SORTS = {
  name: (a, b) => coll.compare(a.name, b.name),
  creator: (a, b) => coll.compare(a.creator, b.creator) || coll.compare(a.name, b.name),
  store: (a, b) => storeRank(a.store) - storeRank(b.store) || coll.compare(a.name, b.name),   // as the Library's Store
  added: (a, b) => (b.added || "").localeCompare(a.added || "") || (b.modified || 0) - (a.modified || 0),
  size: (a, b) => b.size - a.size,
};
SORTS.season = seasonSort(SORTS.added);   // the season's first (issue #261: shared.js)
// How many of a list have each value of a list-valued field (types, tags...).
const countBy = (list, key) => {
  const m = new Map();
  for (const a of list) for (const v of a[key]) m.set(v, (m.get(v) || 0) + 1);
  return m;
};
// Whether any search or filter is narrowing the downloads down.
const filtersActive = () => state.ptype || state.q || state.store || state.lib !== "" || state.creator || state.tags.size || state.types.size || state.set;

/* ---------- rendering */
function render() {
  if (APP.active !== "downloads") return;
  if (!VIEWS[state.view] || (state.view === "hidden" && !(DATA.privacy || {}).unlocked)) state.view = "downloads";
  if (!inSets()) state.set = "";
  wishScope();
  const list = DATA.assets.filter(a => matches(a)).sort(SORTS[state.sort]);
  renderViews(); renderGrid(stacked(list)); markSelected(); renderFacets(list); renderStatus(list); syncControls(); saveHash(); renderTagPanel();
  drawSets();
}

/* ---------- views: the Library's archive, removed and hidden, for what's downloaded (issue #29) */
const VIEWS = { downloads: "Downloads", updates: "Asset updates", problems: "Problems", archive: "Archive", removed: "Removed", hidden: "Hidden", space: "Disk space" };
// The view a download is in (Downloads, Archive, Hidden or Removed).
const viewOf = a => !a.mark ? "downloads" : a.mark === "archived" ? "archive" : a.mark;
// Updates: what the last check found, from the Downloads and the Archive (issue #26)
const hasUpdate = a => !!(a.update && a.update.length);
// Problems (issue #334): files missing or changed, a download that didn't finish, a Local folder that's gone.
const hasProblem = a => !!(a.problems && a.problems.length);
// Whether a download belongs in the view shown (Updates, Problems and Disk space are views of their own).
const inView = a => state.view === "updates" ? hasUpdate(a) && a.mark !== "removed"
  : state.view === "problems" ? hasProblem(a) && a.mark !== "removed"
  : state.view === "space" ? inSpace(a) : viewOf(a) === state.view;
// The views to choose from, with their counts (Disk space's: the size downloads take).
function renderViews() {
  const p = DATA.privacy || {}, count = {};
  for (const a of DATA.assets) count[viewOf(a)] = (count[viewOf(a)] || 0) + 1;
  count.updates = DATA.assets.filter(a => hasUpdate(a) && a.mark !== "removed").length;
  count.problems = DATA.assets.filter(a => hasProblem(a) && a.mark !== "removed").length;
  // How many downloads a view has.
  const n = v => count[v] || 0;
  const onDisk = DATA.assets.filter(takesSpace).reduce((t, a) => t + a.size, 0);   // Disk space: its count is the size
  $("#views").innerHTML = Object.keys(VIEWS).filter(v => v === "downloads" || v === "updates" || v === state.view || n(v)
      || (v === "hidden" && p.pin_set) || (v === "space" && onDisk)).map(v =>
    `<button role="radio" data-view="${v}" aria-checked="${state.view === v}">${VIEWS[v]}` +
    (v === "hidden" && !p.unlocked ? ` <span aria-label="locked">&#128274;</span>`
      : `<span class="n">${v === "space" ? sizeText(onDisk) : n(v)}</span>`) + `</button>`).join("");
  const bar = $("#viewBar");
  bar.hidden = state.view === "downloads";
  bar.innerHTML = state.view === "updates" ? updatesBar(n("updates")) : state.view === "space" ? spaceBar()
    : state.view === "problems" ? `<p>${esc(tr("Downloads with something wrong: files missing or changed on disk, a download that didn't finish, or a Local folder that's gone. Open one to see what to do."))}</p>`
    : state.view === "archive" ? `<p>Downloads of what you archived in the Library. Their files stay where they are.</p>`
    : state.view === "removed" ? `<p>Downloads of what you removed from the Library. The files stay on disk until you delete them: open one and choose <b>Delete downloaded files</b>.</p>`
    : state.view === "hidden" ? `<p>Downloads of your hidden items, shown while the hidden library is unlocked. Change your PIN in the Library.</p>
        <button class="ghost sm" data-privacy="lock">Lock now</button>` : "";
}
/* ---------- updates (issue #26): a check reads your stores without downloading anything, and lists what each
   download is missing that its store has now: files the creator added or changed. Update downloads just those. */
const STORE_IDS = { booth: "booth", gumroad: "gumroad", jinxxy: "jinxxy", itch: "itch", payhip: "payhip" };
// A download's store, as Hoard's settings name it.
const storeId = a => STORE_IDS[a.store.toLowerCase()] || a.store.toLowerCase();
// Whether Hoard can download a product again (not Payhip's or your own).
const canDownload = a => storeId(a) !== "payhip" && !isLocal(a);
// When updates were last checked, in words.
function whenChecked() {
  const times = Object.values(DATA.updates_checked || {}).filter(Boolean).sort();
  if (!times.length) return "";
  const d = new Date(times[times.length - 1]);   // the latest check
  return isNaN(d) ? "" : d.toLocaleString(document.documentElement.lang || undefined, { dateStyle: "medium", timeStyle: "short" });
}
// The Updates view's bar: how many have newer files, when they were checked, and its buttons.
function updatesBar(n) {
  const when = whenChecked();
  const say = [n ? tr(n === 1 ? "1 download has newer files on the store: files the creator added or changed since you downloaded them."
                               : "{0} downloads have newer files on the store: files the creator added or changed since you downloaded them.", n)
                 : tr("Nothing to update."), when ? tr("Last checked {0}.", when) : tr("Not checked yet.")];
  return `<p>${say.map(esc).join(" ")}</p>` +
    `<button class="ghost sm" data-upd="check">Check for updates</button>` +
    (n ? `<button class="primary sm" data-upd="all">Update all</button>` : "");
}
   // (shared.js: a set made from a project shows in Sets)
// Previous versions (hoard/previous.py): what updates replaced, kept in the product's folder, to put back
function previousSection(a) {
  const list = a.previous || [];
  if (!list.length) return "";
  // A previous version's time, as this computer writes one.
  const when = s => { const m = /^(\d{4})-(\d\d)-(\d\d) (\d\d)(\d\d)/.exec(s);
    return m ? new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5]).toLocaleString(document.documentElement.lang || undefined,
      { dateStyle: "medium", timeStyle: "short" }) : s; };
  return `<h3>Previous versions<span class="muted">${esc(sizeText(list.reduce((t, v) => t + v.size, 0)))}</span></h3>` +
    `<ul class="files">${list.map(v => `<li><span class="fn"><span translate="no">${esc(v.file)}</span>` +
      `<br><span class="muted">${esc(tr("Replaced {0}", when(v.stamp)))}</span></span><span class="fs">${fmtSize(v.size)}</span>` +
      `<button class="ghost sm" data-act="restore" data-stamp="${esc(v.stamp)}" data-file="${esc(v.file)}">Restore</button></li>`).join("")}</ul>` +
    `<p class="sub">Restore puts it back, and keeps the one it replaces here, so you can change your mind.</p>`;
}
// Put a previous version of a file back, once you say so (the current one is kept as a previous version).
async function restorePrevious(a, b) {
  if (!await ask(tr("Put back {0} from {1}? The current one is kept here as a previous version.", b.dataset.file, b.closest("li").querySelector(".muted").textContent),
                 "Restore")) return;
  const r = await apiPost("/api/previous/restore", { folder: a.folder, stamp: b.dataset.stamp, file: b.dataset.file });
  if (!r.ok) { toast(r.data.error || "That version couldn't be put back."); return; }
  toast(tr("Put back {0}.", b.dataset.file));
  await load(true);
}
// What it needs (hoard/needs.py): the tools and other products its packages use, from what Hoard has read of them
function needsSection(a) {
  const n = a.needs, R = DATA.needs_reading || {};
  if (!n) return "";
  const head = `<h3 id="needsHead">What it needs</h3>`;
  if (!n.read) return head + `<p class="sub">${esc(R.reading && R.total
    ? tr("Hoard is reading your packages to find out ({0} of {1}).", R.done.toLocaleString(), R.total.toLocaleString())
    : tr("Hoard reads your packages to find out, while nothing else is running."))}</p>`;
  const rows = [
    ...n.tools.map(t => `<li><span class="nm"><span translate="no">${esc(t.name)}${t.versions.length ? " " + esc(t.versions.join(", ")) : ""}</span>` +
      (t.common ? ` <span class="muted">${esc(tr("(every VRChat project has it)"))}</span>` : "") + `</span>` +
      (t.common || !safeUrl(t.url) ? "<span></span>" : `<a class="ghost sm" href="${esc(safeUrl(t.url))}" target="_blank" rel="noopener noreferrer">Get it</a>`) + `</li>`),
    ...n.products.map(o => `<li><span class="nm"><span translate="no">${esc(o.name)}</span> <span class="muted" translate="no">${esc(tr("by {0}", o.creator))}</span></span>` +
      `<button class="ghost sm" data-act="goto" data-id="${o.id}">View</button></li>`),
  ];
  const unknown = n.unknown ? `<p class="sub">${esc(tr("It also uses files from other products, such as a base avatar or a shader."))}</p>` : "";
  if (!rows.length && !unknown) return head + `<p class="sub">${esc(tr("Nothing from elsewhere: everything it uses is in it."))}</p>`;
  return head + (rows.length ? `<ul class="needs">${rows.join("")}</ul>` : "") + unknown;
}
// A download's details: its update (what's newer, to download), or a button to check for one.
function updateSection(a) {
  if (!canDownload(a)) return "";
  if (!hasUpdate(a)) return `<div class="update"><button class="ghost sm" data-act="check-one">Check for updates</button>` +
    `<span class="muted">Reads ${storeName(a.store)} for this one, without downloading anything.</span></div>` +
    `<div class="update"><button class="ghost sm" data-act="more">${esc(tr("Download more of it..."))}</button>` +
    `<span class="muted">${esc(tr("Its files you haven't downloaded, to choose from."))}</span></div>`;
  return `<div class="update"><strong>Update available</strong><ul>${a.update.map(f =>
      `<li>${esc(f.file)} <span class="muted-inline">(${f.kind === "changed" ? "changed" : "new"})</span></li>`).join("")}</ul>` +
    `<button class="primary sm" data-act="update-one">Update</button> <button class="ghost sm" data-act="check-one">Check again</button></div>`;
}
// Download the updates of some downloads.
function updateItems(list) {
  const chosen = list.filter(a => canDownload(a));
  if (!chosen.length) { takeFiles(); return; }
  startDownload([...new Set(chosen.map(storeId))], null, null, chosen.map(a => a.tag_key));
}
// Check the stores for updates (of some downloads, or all of them).
async function checkUpdates(list) {
  if (!navigator.onLine) { toast("You're offline. Checking for updates needs a connection."); return; }
  const body = list ? { stores: [...new Set(list.map(storeId))], keys: list.map(a => a.tag_key) } : {};
  const r = await apiPost("/api/check-updates", body);
  if (!r.ok) { toast(r.data.error || "Checking for updates didn't start."); return; }
  if (queuedToast(r)) return;
  dlActive = true;
  showDownload({ running: true, task: "check-updates", message: "Starting", log: [] });
  pollDownload();
}

/* ---------- disk space: the biggest downloads, the same file kept more than once (hoard/space.py, from the
   fingerprints the integrity check keeps), and what no Unity project uses. Each can be moved to another library
   folder, archived or deleted, a few at a time with Select. */
let SPACE = null;   // /api/space: {groups, unchecked, projects}, read when Disk space is opened
const takesSpace = a => !a.linked;   // (a folder of your own, listed where it is, isn't Hoard's to free)
// The files of a download that are kept elsewhere too, or null.
const copiesOf = a => (SPACE && SPACE.of.get(a.id)) || null;
// Whether a download is in Disk space's list, as its chips choose (all, copies, unused...).
function inSpace(a) {
  if (!takesSpace(a)) return false;
  if (state.space === "copies") return !!copiesOf(a);
  if (state.space === "unused") return !isLocal(a) && !(a.used_in || []).length;
  if (state.space === "dupes") return dupeIds().has(a.id);
  return true;
}
/* products you have from more than one store, each downloaded (the same product, as Hoard stacks copies): keep
   one store's copy and remove the others. A copy removed leaves your library (Library, Removed, where Restore
   brings it back), so syncing doesn't download it again, and its downloaded files are deleted. */
const dupeKeep = new Map();   // stack_key -> the id of the copy to keep; none chosen: all of them stay
// The products downloaded from more than one store, each as a group of its copies.
function dupeGroups() {
  const by = new Map();
  for (const a of DATA.assets) if (a.stack_key && takesSpace(a) && !isLocal(a) && !a.mark) by.set(a.stack_key, [...(by.get(a.stack_key) || []), a]);
  return [...by.values()].filter(g => new Set(g.map(a => a.store)).size > 1)
    .map(g => g.sort((x, y) => coll.compare(storeName(x.store), storeName(y.store)) || y.size - x.size))
    .sort((x, y) => coll.compare(x[0].name, y[0].name));
}
// Every download that's in such a group.
const dupeIds = () => new Set(dupeGroups().flat().map(a => a.id));
/* A copy is removed (marked Removed, its files deleted) by its product key, the key tags use: a store and a name
   without versions or (labels), so "Hair Pack 1" and "Hair Pack 2" from one store share one. So a copy goes only
   when its key is neither the kept copy's nor any download's outside this group: else the copy you keep, or
   another product, would go with it. */
function dupeRemovals(groups = dupeGroups()) {
  const count = new Map();
  for (const a of DATA.assets) count.set(a.tag_key, (count.get(a.tag_key) || 0) + 1);
  return groups.flatMap(g => {
    const keep = g.find(a => a.id === dupeKeep.get(g[0].stack_key));
    if (!keep) return [];
    const here = new Map();
    for (const a of g) here.set(a.tag_key, (here.get(a.tag_key) || 0) + 1);
    return g.filter(a => a.tag_key !== keep.tag_key && here.get(a.tag_key) === count.get(a.tag_key));
  });
}
// The products downloaded from more than one store: which copy of each to keep.
function dupesPanel() {
  const groups = dupeGroups();
  if (!groups.length) return `<p class="muted">${esc(tr("Nothing here is downloaded from more than one store."))}</p>`;
  const stores = [...new Set(groups.flat().map(a => a.store))].sort((x, y) => coll.compare(storeName(x), storeName(y)));
  const going = dupeRemovals(groups), bytes = going.reduce((t, a) => t + a.size, 0);
  return `<div class="dupes"><p>${esc(tr(groups.length === 1 ? "1 product is downloaded from more than one store." : "{0} products are downloaded from more than one store.", groups.length.toLocaleString()))} ` +
    `${esc(tr("Choose the copy to keep: the others are removed from your library, so a sync doesn't download them again, and their files are deleted. Restore, under Removed in the Library, brings one back."))}</p>` +
    `<div class="row"><label for="dupeStore">${esc(tr("Keep the copy from"))}</label> <select id="dupeStore">` +
    stores.map(st => `<option value="${esc(st)}">${esc(storeName(st))}</option>`).join("") + `</select>` +
    `<button class="ghost sm" data-dupe="apply">${esc(tr("In every one"))}</button>` +
    `<button class="linkish" data-dupe="none">${esc(tr("Keep them all"))}</button></div>` +
    `<ul class="dupelist">${groups.map(g => {
      const k = g[0].stack_key, keep = dupeKeep.get(k), name = `dk-${g[0].id}`;
      // Which copy to keep, as a radio button.
      const opt = (v, label, on) => `<label><input type="radio" name="${name}" data-stack="${esc(k)}" value="${v}"${on ? " checked" : ""}> ${label}</label>`;
      const twice = st => g.filter(a => a.store === st).length > 1;   // two from one store: which is which, by name
      return `<li><span class="nm"><b translate="no">${esc(g[0].name)}</b> <span class="muted" translate="no">${esc(tr("by {0}", g[0].creator))}</span></span><span class="opts">` +
        g.map(a => opt(a.id, esc(tr("Keep {0}", storeName(a.store))) + (twice(a.store) ? ` <span translate="no">${esc(a.name)}</span>` : "") +
                             ` <span class="muted">(${sizeText(a.size)})</span>`, keep === a.id)).join("") +
        opt("", esc(tr("Keep all")), keep == null || !g.some(a => a.id === keep)) + `</span></li>`;
    }).join("")}</ul>` +
    `<button class="primary sm danger" data-dupe="go"${going.length ? "" : " disabled"}>${dupeGoText(going, bytes)}</button></div>`;
}
// The button's words: how many copies go, and the room it frees.
function dupeGoText(going, bytes) {
  return esc(going.length ? tr(going.length === 1 ? "Remove 1 copy ({1})" : "Remove {0} copies ({1})", going.length.toLocaleString(), sizeText(bytes))
                          : tr("Choose the copies to keep"));
}
// Remove the copies not kept (their files deleted), once you say so.
async function removeDupes() {
  const going = dupeRemovals();
  if (!going.length) return;
  const bytes = going.reduce((t, a) => t + a.size, 0);
  if (!await ask(tr(going.length === 1 ? "Remove 1 copy, and delete its downloaded files ({1})?" : "Remove {0} copies, and delete their downloaded files ({1})?",
                    going.length.toLocaleString(), sizeText(bytes)) + "\n\n" +
                 going.map(a => `${a.name} (${storeName(a.store)})`).slice(0, 12).join("\n") + (going.length > 12 ? "\n..." : "") + "\n\n" +
                 tr("They leave your library, so syncing doesn't download them again; the copy you keep stays. Restore, under Removed in the Library, brings one back."),
                 "Remove them", true)) return;
  const keys = [...new Set(going.map(a => a.tag_key))];
  const marked = await apiPost("/api/marks", { kind: "removed", keys, on: true });   // first: a sync never brings them back
  if (!marked.ok) { toast(marked.data.error || "That didn't work."); return; }
  const r = await apiPost("/api/delete-files", { keys, confirm: true });
  dupeKeep.clear();
  if (!r.ok) { await load(); toast(r.data.error || "They were removed from your library, but their files couldn't be deleted just now."); return; }
  if (r.data.job) return afterQueuedJob(r, "delete-files", () => load(true).then(() => state.view === "space" && loadSpace()));
  await load();
  if (state.view === "space") loadSpace();
  toast(tr(going.length === 1 ? "Removed 1 copy and deleted {1}." : "Removed {0} copies and deleted {1}.", going.length.toLocaleString(), sizeText(r.data.bytes)));
}
// Read Disk space's findings: the same files kept twice, and how much room that takes.
async function loadSpace() {
  let j;
  try { const r = await api("/api/space", { cache: "no-store" }); if (!r.ok) throw new Error(); j = await r.json(); }
  catch (e) { j = { groups: [], unchecked: 0, projects: 0, failed: true }; }
  mapSpace(j);
  if (state.view === "space") render();
}
function mapSpace(j) {   // (again after each reload of the downloads, whose ids are new)
  // each copy, matched to the download it's in: the same library folder, the same product folder
  const where = new Map(DATA.assets.map(a => [`${a.library || 0}\n${a.catalog_folder}`, a]));
  const of = new Map();
  let saving = 0, files = 0;
  for (const g of j.groups || []) {
    const here = g.copies.map(c => where.get(`${c.library}\n${c.folder}`)).filter(Boolean);
    if (here.length < 2) continue;
    saving += g.size * (here.length - 1); files++;
    for (const a of here) {
      const e = of.get(a.id) || { files: 0, bytes: 0, others: new Set() };
      e.files++; e.bytes += g.size;
      for (const o of here) if (o !== a) e.others.add(o.id);
      of.set(a.id, e);
    }
  }
  SPACE = { ...j, of, saving, files };
}
// Disk space's bar: how much room downloads take, and its chips.
function spaceBar() {
  const here = DATA.assets.filter(takesSpace), total = here.reduce((t, a) => t + a.size, 0);
  const unused = here.filter(a => !isLocal(a) && !(a.used_in || []).length);
  // One of Disk space's chips, with its count.
  const chip = (v, label, n) => `<button class="chip" data-space="${v}" aria-pressed="${state.space === v}">${label}` +
    (n != null ? `<span class="n">${esc(String(n))}</span>` : "") + `</button>`;
  const copies = !SPACE ? `<span class="muted">Looking for copies…</span>`
    : chip("copies", "Same file kept twice", SPACE.files ? `${SPACE.of.size.toLocaleString()} · ${sizeText(SPACE.saving)} to free` : 0);
  const notes = [];
  if (SPACE && SPACE.failed) notes.push("Couldn't look for copies just now.");
  else if (SPACE && SPACE.unchecked) notes.push(esc(tr(SPACE.unchecked === 1 ? "1 file hasn't been checked yet, so copies of it aren't shown."
                                                                            : "{0} files haven't been checked yet, so copies of them aren't shown.",
                                                     SPACE.unchecked.toLocaleString())) + ` <button class="linkish" data-checknow>Check now</button>`);
  if (state.space === "unused" && SPACE && !SPACE.projects)
    notes.push("Hoard hasn't found any Unity projects yet: open a project with Hoard for Unity, or add one in Projects.");
  return `<p>${esc(tr(here.length === 1 ? "1 download takes {1}." : "{0} downloads take {1}, biggest first.", here.length.toLocaleString(), sizeText(total)))} ` +
    `<span>To free some, choose them (tick their boxes, or right-click): move them to another library folder, archive them, or delete their files.</span></p>` +
    `<div class="chips">${chip("", "Everything")}${copies}${chip("dupes", "From more than one store", dupeGroups().length.toLocaleString())}` +
    `${chip("unused", "Not in any Unity project", unused.length.toLocaleString())}</div>` +
    notes.map(t => `<p class="muted">${t}</p>`).join("") + (state.space === "dupes" ? dupesPanel() : "");
}
// A download's details: the files of it that are kept elsewhere too.
function spaceSection(a) {
  const e = copiesOf(a);
  if (!e) return "";
  return `<div class="update"><strong>${esc(tr(e.files === 1 ? "1 file is kept elsewhere too" : "{0} files are kept elsewhere too", e.files.toLocaleString()))}</strong>` +
    ` <span class="muted-inline">(${sizeText(e.bytes)})</span><ul>` +
    [...e.others].map(id => byId.get(id)).filter(Boolean).map(o => `<li>${esc(o.name)} <span class="muted-inline">(${esc(storeName(o.store))}` +
      `${(DATA.libraries || []).length > 1 ? `, ${esc(libName(o.library || 0))}` : ""})</span> ` +
      `<button class="linkish" data-act="goto" data-id="${o.id}">View</button></li>`).join("") + `</ul></div>`;
}


// Show a view (Hidden only once it's unlocked with the PIN).
async function showView(v) {
  if (v === "hidden" && !(DATA.privacy || {}).unlocked) {   // the same PIN as the Library's Hidden
    if (!(await unlockDialog())) return;
    await load();
    if (!(DATA.privacy || {}).unlocked) return;
  }
  if (v === "space" && state.view !== "space") { state.sort = "size"; state.space = ""; SPACE = null; loadSpace(); }
  else if (v !== "space" && state.view === "space" && state.sort === "size") state.sort = sortFrom("", SORTS);   // the one you chose
  state.view = v; sel.ids.clear(); closeDetail(); render();
}
// Hidden locked itself again, nobody having used it for a while (shared.js, issue #248): out of view, details and all.
async function hiddenLocked() {
  const open = openId != null && byId.get(openId);
  if (open && open.mark === "hidden") closeDetail();
  if (state.view === "hidden") { state.view = "downloads"; sel.ids.clear(); }
  await load(); toast("Hidden items locked again: they hadn't been used for a while.");
}

/* unlocking hidden items: setting, changing or resetting the PIN is the Library's */
let pinResolve = null;
// Ask for the PIN, resolving with whether it unlocked Hidden.
function unlockDialog() {
  return new Promise(resolve => {
    pinResolve = resolve;
    $("#pinInput").value = ""; $("#pinNote").textContent = "";
    $("#pinDialog").showModal();
    $("#pinInput").focus();
  });
}
// Close the PIN dialog, saying whether it unlocked.
function pinDone(ok) {
  if ($("#pinDialog").open) $("#pinDialog").close();
  const r = pinResolve; pinResolve = null;
  if (r) r(ok);
}
// Send the PIN typed.
async function pinSubmit() {
  const r = await apiPost("/api/unlock", { pin: $("#pinInput").value });
  if (!r.ok) { $("#pinNote").textContent = r.data.error || "That didn't work."; $("#pinInput").select(); return; }
  pinDone(true);
}







/* copies of one product (bought twice, in versions, or on two stores: hoard/library.py's stack_key) as one tile, as in
   the Library: its details list the others. Every copy shows while selecting, and in Disk space (each takes space). */
let stackSize = new Map();   // the first copy's id -> how many copies its tile stands for
// The downloads with each one's copies shown as one tile (counting them), unless copies aren't stacked.
function stacked(list) {
  stackSize = new Map();
  if (UI.stack === false || sel.on || state.view === "space") return list;
  const first = new Map(), out = [];
  for (const a of list) {
    const f = a.stack_key && first.get(a.stack_key);
    if (f) { stackSize.set(f.id, (stackSize.get(f.id) || 1) + 1); continue; }
    if (a.stack_key) first.set(a.stack_key, a);
    out.push(a);
  }
  return out;
}
// the other copies of a product: on another store by the same creator (also_in), or in its stack
let stackMembers = new Map();   // stack_key -> its copies (made with byId, in load)
// A download's copies: on other stores, and versions of it.
function otherCopies(a) {
  const ids = new Set(a.also_in.map(o => o.id));
  for (const o of (a.stack_key && stackMembers.get(a.stack_key)) || []) if (o.id !== a.id) ids.add(o.id);
  return [...ids].map(id => byId.get(id)).filter(Boolean);
}
// A download's tile: its picture, name, creator, store, size and marks.
// Downloads' file/status values for the same product tile used by the Library.
const slotHTML = a => {
  const n = stackSize.get(a.id) || 0, others = otherCopies(a), store = storeName(a.store);
  const also = [...new Set(others.filter(o => o.store !== a.store).map(o => storeName(o.store)))];
  const [status, statusKind] = a.folder_gone ? [tr("Folder gone"), "bad"] : a.missing ? [tr("Missing files"), "bad"] : hasUpdate(a) ? [tr("Update"), "upd"]
    : [tr(a.files.length === 1 ? "{0} file, {1}" : "{0} files, {1}", a.files.length, fmtSize(a.size)), ""];
  return productTile(a, { key: "id", id: a.id, current: a.id === openId, store: a.store.toLowerCase(), storeName: store,
    src: a.thumb ? fileUrl(a.thumb, a.thumb_v) : "", type: a.types[0], count: n, others: others.map(o => o.store.toLowerCase()),
    description: [tr("{0}, by {1}, from {2}", a.name, a.creator, store), n > 1 && tr("{0} copies", n),
      also.length && tr("also from {0}", listed(also)), a.your_note && tr("has a note")],
    badges: [n > 1 && { kind: "count", text: `×${n}`, hidden: true }, hasUpdate(a) && { kind: "upd", text: tr("Update") },
      state.view === "space" && copiesOf(a) && { kind: "upd", text: tr("Copies") }],
    size: state.view === "space" ? fmtSize(a.size) : "", status, statusKind,
    added: shortDay(a.added || (a.modified && new Date(a.modified * 1000).toISOString())),
  });
};
// Draw the tiles (or why there are none).
function renderGrid(list) {
  (cards = cards || lazyCards(grid)).show(list, slotHTML);

  const empty = $("#empty");
  if (DATA.error) {
    empty.innerHTML = `<h2>Can't reach your downloads</h2><p>${esc(DATA.error)}</p>`;
  } else if (!DATA.assets.length) {
    const st = DATA.status || { stores: {}, elsewhere: [] };
    const rows = Object.entries(st.stores).map(([s, i]) =>
      `<li>${storeName(s)}: ${i.found ? `manifest found, ${i.assets} assets with files` : `no <code>${esc(i.manifest)}</code>`}</li>`).join("");
    const other = st.elsewhere.map(p => `<li>Downloads found in <code>${esc(p)}</code>. To use them, choose that folder in Settings.</li>`).join("");
    empty.innerHTML = `<svg viewBox="0 0 64 64" aria-hidden="true"><g class="boxes heap">${heapMarkup(heapBoxes())}</g></svg><h2>Nothing downloaded yet</h2>` +
      (Object.values(st.stores).some(i => i.found)
        ? `<p>Looking in <code>${esc(DATA.root)}</code>.</p><ul>${rows}${other}</ul>`
        : `<p>Sign in to your stores (in the Library, choose <strong>Stores</strong>), then choose <strong>Download new</strong>. ` +
          `Files go to <code>${esc(DATA.root)}</code>; you can pick another folder in Settings.</p>` + (other ? `<ul>${other}</ul>` : "")) +
      (Object.values(st.stores).some(i => i.found) ? `<p>Choose <strong>Download new</strong> to download everything you own.</p>` : "");
  } else if (!list.length && !filtersActive() && state.view === "space") {
    empty.innerHTML = `<h2>${{ copies: "No file is kept twice", unused: "Every download is in a Unity project" }[state.space] || "Nothing here"}</h2>` +
      (state.space === "copies" && SPACE && SPACE.unchecked ? `<p>Some files haven't been checked yet: check now to look at those too.</p>` : "");
  } else if (!list.length && !filtersActive()) {
    empty.innerHTML = `<h2>${{ updates: "Nothing to update", archive: "Nothing archived is downloaded", removed: "Nothing removed is downloaded",
                               hidden: "Nothing hidden is downloaded" }[state.view] || "Nothing here"}</h2>` +
      (state.view === "downloads" ? `<p>Everything downloaded is archived, removed or hidden in the Library.</p>` : "");
  } else if (!list.length) {
    empty.innerHTML = `<h2>Nothing in your downloads matches that</h2><p><button class="linkish" data-clear="all">Clear filters</button></p>`;
  }
  empty.hidden = list.length > 0 || (inSets() && !DATA.error && DATA.assets.length > 0);   // (Sets says what it has)
}

// The filters for the downloads shown: tags, file types, library folders and creators.
function renderFacets(list) {
  renderTagFacets(list);

  const typeCounts = countBy(list, "types");
  for (const t of state.types) if (!typeCounts.has(t)) typeCounts.set(t, 0);
  $("#types").innerHTML = [...typeCounts].sort((x, y) => y[1] - x[1] || coll.compare(x[0], y[0])).map(([t, n]) =>
    `<button class="chip" data-type="${esc(t)}" aria-pressed="${state.types.has(t)}">.${esc(t)}<span class="n">${n}</span></button>`).join("");

  const wish = openWish(), creatorCounts = wish ? wishCreators(wish) : new Map();   // (a wishlist open: its products' creators)
  if (!wish) for (const a of DATA.assets) if (matches(a, "creator")) creatorCounts.set(a.creator, (creatorCounts.get(a.creator) || 0) + 1);
  if (state.creator && !creatorCounts.has(state.creator)) creatorCounts.set(state.creator, 0);
  const f = norm(state.creatorFind);
  $("#creators").innerHTML = [...creatorCounts].filter(([c]) => !f || norm(c).includes(f))
    .sort((x, y) => coll.compare(x[0], y[0])).map(([c, n]) =>
      `<li><button data-creator="${esc(c)}" aria-pressed="${state.creator === c}"><span>${esc(c)}</span><span class="n">${n}</span></button></li>`).join("");

  const total = DATA.assets.reduce((s, a) => s + a.size, 0);
  const missing = DATA.assets.reduce((s, a) => s + a.missing, 0);
  const gone = DATA.gone || 0;   // downloaded before, every file since deleted from disk (issue #24)
  renderIntegrity();
  $("#totals").textContent = [
    DATA.assets.length && tr(DATA.assets.length === 1 ? "1 thing, {1} on disk." : "{0} things, {1} on disk.", DATA.assets.length, fmtSize(total)),
    DATA.assets.length && missing && tr(missing === 1 ? "1 file missing." : "{0} files missing.", missing),
    gone && tr(gone === 1 ? "1 download was deleted from disk and isn't shown; the library offers it to download again."
                          : "{0} downloads were deleted from disk and aren't shown; the library offers them to download again.", gone),
  ].filter(Boolean).join(" ");
}

/* issue #83: when the downloads were last checked to be as Hoard downloaded them, and what that found */
function renderIntegrity() {
  const v = DATA.integrity || {}, el = $("#integrity");
  if (!el || !DATA.assets.length) { if (el) el.innerHTML = ""; return; }
  const every = { 6: "every 6 hours", 12: "every 12 hours", 24: "every day", 168: "every week", 720: "every month" }[v.every_hours];
  const when = !v.checked ? tr("Not checked yet.") : !v.complete ? tr("Checked {0} (stopped part way).", ago(v.checked))
    : tr("Checked {0}:", ago(v.checked));
  const found = !v.checked || !v.complete ? "" : (v.changed || v.missing || v.data_changed)
    ? ` <strong class="warn">${esc(v.summary)}</strong> ` + (v.listed ? `<button class="linkish" data-check-open>${esc(tr("See what it found"))}</button>`
      : esc(tr("Which files is in Tasks."))) : ` ${esc(v.summary)}`;
  el.innerHTML = `${esc(when)}${found} ${esc(every ? tr("Hoard checks {0}, in its routine check (Settings).", tr(every)) : tr("Hoard checks only when you ask (Settings)."))} ` +
    `<button class="linkish" id="checkNow">Check now</button>`;
}
// Issue #231: the files the last check found changed or missing, each with what can be done about it: a change kept as
// it is (it's fine from then on), a missing file forgotten (and left out of its product's downloads), either
// downloaded again (a changed one kept in _Previous versions first), or shown in its folder
const CHECK = { list: [], hidden: 0, more: 0 };
// Open what the last integrity check found, each file to deal with.
async function openCheck() {
  const r = await api("/api/integrity", { cache: "no-store" });
  if (!r.ok) { toast(tr("That can't be done.")); return; }
  const v = await r.json();
  Object.assign(CHECK, { list: v.problems || [], hidden: v.hidden_left_out || 0, more: v.more || 0 });
  $("#checkWhen").textContent = v.checked ? tr("Checked {0}.", ago(v.checked)) + (CHECK.hidden ? " " +
    tr("Hidden items are left out while your hidden library is locked.") : "") : "";
  drawCheck();
  if (!$("#checkDialog").open) $("#checkDialog").showModal();
}
// Draw what the check found, by product, each with Keep, Forget and Download again.
function drawCheck() {
  const by = new Map();
  CHECK.list.forEach((x, i) => { const k = `${x.store}:${x.name}`; if (!by.has(k)) by.set(k, []); by.get(k).push([x, i]); });
  $("#checkList").innerHTML = !CHECK.list.length ? `<p class="none">${esc(tr("Nothing left to deal with."))}</p>`
    : [...by.values()].map(xs => `<h3><span class="dot ${esc(xs[0][0].store)}"></span><span translate="no">${esc(xs[0][0].name)}</span></h3><ul>` +
      xs.map(([x, i]) => `<li><span class="cf"><b translate="no">${esc(x.path)}</b><span class="warn">${esc(x.kind === "changed"
          ? tr("Changed since Hoard downloaded it") : tr("Missing"))}</span></span><span class="acts">` +
        `<button class="ghost sm" data-check="again" data-i="${i}">${esc(tr("Download again"))}</button>` +
        (x.kind === "changed" ? `<button class="ghost sm" data-check="keep" data-i="${i}">${esc(tr("Keep it as it is"))}</button>`
          : `<button class="ghost sm" data-check="forget" data-i="${i}">${esc(tr("Forget it"))}</button>`) +
        (x.kind === "changed" ? `<button class="ghost sm" data-check="show" data-i="${i}">${esc(tr("Show in folder"))}</button>` : "") +
        `</span></li>`).join("") + `</ul>`).join("") +   // (a missing file: nothing there to show, issue #259)
    (CHECK.more ? `<p class="muted">${esc(tr("{0} more are named in the check's log, in Tasks.", CHECK.more))}</p>` : "");
  $("#checkKeepAll").hidden = !CHECK.list.some(x => x.kind === "changed");
  $("#checkAgainAll").hidden = CHECK.list.length < 2;
}
// Deal with files the check found (forgetting them once you say so).
async function resolveCheck(action, list) {
  if (action === "forget" && !await ask(tr(list.length === 1 ? "Forget {0}? Hoard stops expecting it, and leaves it out of that product's downloads from now on."
      : "Forget these {0} files? Hoard stops expecting them, and leaves them out of their products' downloads from now on.",
      list.length === 1 ? list[0].path : list.length), tr("Forget"))) return;
  const r = await apiPost("/api/integrity/resolve", { action, problems: list });
  if (!r.ok) { toast(r.data.error || tr("That can't be done.")); return; }
  if (action === "show") return;
  if (r.data.failed && r.data.failed.length) toast(r.data.failed[0].error);
  else if (action === "again") toast(r.data.started === "queued" ? tr("Downloading them again: it starts when what's running now is done.")
    : tr("Downloading them again. Follow it in Tasks."));
  await openCheck();
  load();
}

// Start an integrity check of the downloads.
async function checkDownloads() {
  const r = await apiPost("/api/verify");
  if (!r.ok) { toast(r.data.error || "The check didn't start."); return; }
  if (queuedToast(r)) return;
  toast("Checking your downloads. Follow it in Tasks.");
}


// The status line: what's searched and filtered (each to clear), and how many things are shown.
function renderStatus(list) {
  const total = DATA.assets.filter(inView).length;   // this view: Downloads, Archive, ...
  const pills = [];
  if (state.q) pills.push(["q", "", `Search`, state.q]);
  if (state.store && !inSets()) pills.push(["store", "", "Store", storeName(state.store)]);   // (Sets says where you are)
  if (state.lib !== "") pills.push(["lib", "", "Folder", libName(state.lib)]);
  if (state.creator) pills.push(["creator", "", "Creator", state.creator]);
  for (const t of state.tags) pills.push(["tag", t, "Tag", t]);
  for (const t of state.types) pills.push(["type", t, "Type", "." + t]);
  if (state.ptype) pills.push(["ptype", "", "Product type", tr(PRODUCT_TYPES[state.ptype] || state.ptype)]);
  // "1 thing" or "n things".
  const things = n => `${n} ${n === 1 ? "thing" : "things"}`;
  // Local, from the bar, is a place of its own: the bar says so, and so do the heading and the window's title
  const local = state.store === "Local";
  for (const [a, here] of [[$('.apptabs a[href="/downloads"]'), !local], [$('.apptabs a[href="/downloads#store=Local"]'), local]])
    if (a) { if (here) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); }
  document.title = local ? tr("Hoard: Local") : tr("Hoard: Downloads");
  $("#count").hidden = !total || (inSets() && !!state.set);   // (a set open has its own heading)
  $("#count").innerHTML = inSets() ? esc(setsCountText()) : local && pills.length === 1 && state.view === "downloads"
    ? esc(tr(list.length === 1 ? "1 package of your own" : "{0} packages of your own", list.length))
    : filtersActive() ? `${list.length} <span class="of">of ${things(total)}</span>`
    : `${things(total)} ${{ archive: "archived", removed: "removed", hidden: "hidden" }[state.view] || "on disk"}` +
      (state.view === "space" ? `, ${sizeText(list.reduce((t, a) => t + a.size, 0))}` : "");
  $("#status").innerHTML =
    pills.map(([k, v, label, text]) =>
      `<button class="pill" data-clear="${k}" data-v="${esc(v)}" aria-label="Remove ${label.toLowerCase()} filter ${esc(text)}">` +
      `<b>${label}</b> ${esc(text)}<span aria-hidden="true">×</span></button>`).join("") +
    (pills.length > 1 ? `<button class="linkish" data-clear="all">Clear all</button>` : "");
}

// Put the search box, store tabs, library folders and sort as the state says.
function syncControls() {
  const q = $("#q"); if (q.value !== state.q) q.value = state.q;
  renderDrives();
  // a store's tab only when there's something of it in this view (Downloads, Archive...), or it's the one you chose
  // (the Local link in the bar, with nothing in Local yet)
  const here = DATA.assets.filter(inView), have = {};
  for (const a of here) have[a.store] = (have[a.store] || 0) + 1;
  have.Sets = (DATA.sets || []).length || 0.5;   // (Sets is always there: its count is how many sets)
  for (const b of $("#storeSeg").querySelectorAll("[data-store]")) {   // Everything: every store, on every drive
    b.hidden = b.dataset.store !== "" && !have[b.dataset.store] && b.dataset.store !== state.store;
    const n = (b.dataset.store === "" ? here.length : Math.floor(have[b.dataset.store] || 0)).toLocaleString();   // as in the Library
    if (b.lastChild.textContent !== n) b.lastChild.textContent = n;
    b.setAttribute("aria-checked", String(b.dataset.store === state.store && (b.dataset.store !== "" || state.lib === "")));
  }
  for (const b of $("#drives").querySelectorAll("[data-lib]")) b.setAttribute("aria-checked", String(b.dataset.lib === state.lib));
  // the stores you have downloads from, for Everything's glow
  setGlow(inSets() ? "" : state.store.toLowerCase(), GLOW_COLORS.filter(s => DATA.assets.some(a => a.store.toLowerCase() === s)));
  $("#sort").value = state.sort;
}

/* ---------- detail */
function showDetail(a, focus = true) {
  openId = a.id;
  markCurrent(`.slot[data-id="${a.id}"]`);
  const sections =
    ((a.used_in || []).length ? `<p class="also"><span translate="no">${esc(tr("Used in {0}.", listed(a.used_in)))}</span> ` +
      `<button class="linkish" data-act="projects">See Projects</button></p>` : "") +
    otherCopies(a).map(o => `<p class="also"><span translate="no">${esc(tr(o.store === a.store ? (o.creator !== a.creator ? "You also have this again (by {1})." : "You also have this again.")
                                                                         : (o.creator !== a.creator ? "You also have this from {0} (by {1})." : "You also have this from {0}."),
                                                     storeName(o.store), o.creator))}</span> ` +
      `<button class="linkish" data-act="goto" data-id="${o.id}">View that copy</button></p>`).join("") +
    `<div class="actions"><button class="primary" data-act="open" data-path="${esc(a.folder)}">Open folder</button>` +
      `<button class="ghost" data-act="copy">Copy path</button>` +
      `<button class="ghost" data-act="edit-copy">Make an editable copy</button>` +
      (isLocal(a) ? "" : `<button class="ghost" data-act="delete-files">Delete downloaded files</button>`) + `</div>` +
      (isLocal(a) ? localSection(a)
        : `<p class="sub">Want to change a texture or a file? Make an editable copy and change that: Hoard checks the files
        here, and replaces one that was changed.</p>`) +
    `<h3>Files<span class="muted">${a.files.length} ${a.files.length === 1 ? "file" : "files"}, ${fmtSize(a.size)}</span></h3>` +
    `<ul class="files">${a.files.map(f => `<li class="${f.missing ? "miss" : ""}"><span class="fn">${esc(f.path)}${f.code ? ` <span class="codemark" ` +
      `title="${esc(codeWords(f.code, f.code.loose).join(" "))}">${esc(tr("Code"))}</span>` : ""}</span>` +
      `<span class="fs">${f.missing ? "Missing on disk" : fmtSize(f.size)}</span>` +
      (f.missing ? "<span></span>" : `<span class="fb">` + (canLookInside(f.path)
        ? `<button class="ghost sm" data-act="inside" data-path="${esc(a.folder + "/" + f.path)}">Look inside</button>` : "") +
        `<button class="ghost sm" data-act="open" data-path="${esc(a.folder + "/" + f.path)}">Show in folder</button></span>`) +
      `</li>`).join("")}</ul>` +
    spaceSection(a) +
    updateSection(a) +
    needsSection(a) +
    librarySection(a) +
    noteSection(a) +
    tagSection(a) +
    setsSection(a) +
    previousSection(a) +
    `<p class="path" id="absPath">${esc(a.abs_folder)}</p>`;
  saveHash();   // (first: the step left behind keeps the page's place as it was, for Back to return to, issue #329)
  renderProductDetail(a, { store: a.store.toLowerCase(), storeName: storeName(a.store), storeUrl: storeUrl(a.store, a.url),
    copyUrl: a.public,   // (its public page: never the purchase's own link Open on the store opens)
    extra: a.variants, src: a.thumb ? fileUrl(a.thumb, a.thumb_v) : "", type: a.types[0],
    facts: [["Files", a.files.length], ["Size", fmtSize(a.size)], ["Added", shortDay(a.added) || "—"], ["Projects", (a.used_in || []).length]],
  }, sections, focus);
}
// Close the details, focusing the tile they were for.
function closeDetail() {
  if (openId == null) return;
  const back = grid.querySelector(`[data-id="${openId}"]`) || lastFocus;
  keepTileInPlace(back && back.closest("#grid") ? back : null, () => {   // (its tile stays where it is on screen: #329)
    detail.classList.remove("open"); document.body.classList.remove("panel-open"); $("#scrim").hidden = true;
  });
  openId = null;
  markCurrent(null);
  if (back) back.focus({ preventScroll: true });
  saveHash();
}
// Show a downloaded file or folder in the system's file manager.
async function reveal(path) {
  try {
    const r = await api("/api/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) });
    const j = await r.json();
    toast(r.ok ? tr("Opened in {0}", tr(j.opened_in)) : j.error);
  } catch (e) { toast("Couldn't reach the library server."); }
}
// Copy the open download's folder's path.
async function copyPath() {
  const text = byId.get(openId).abs_folder;
  try { await navigator.clipboard.writeText(text); }
  catch (e) {
    const sel = getSelection(); const range = document.createRange();
    range.selectNodeContents($("#absPath")); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand("copy"); sel.removeAllRanges();
  }
  toast("Path copied");
}

/* ---------- Look inside: what a .unitypackage or .zip holds, read without extracting it (hoard/packages.py) */
const canLookInside = name => /\.(unitypackage|zip)$/i.test(name);
let INSIDE = null;   // what's shown: {id, kind, items | files + packages, nodes: folders drawn when opened}
// Open Look inside, or close it (open: which; else the other way).
function openInside(open) {
  const w = $("#insideWin"), show = open ?? w.hidden;
  w.hidden = !show;
  if (!show) { INSIDE = null; HoardInside.clear($("#insideBody")); }
}
// Look inside a package or .zip: read what's in it, and show it.
async function lookInside(path) {
  const body = $("#insideBody"), name = path.split("/").pop();
  INSIDE = null;
  HoardInside.clear(body);
  body.innerHTML = `<p class="file-name" translate="no">${esc(name)}</p><p class="sum">${esc(tr("Reading it. A large package takes a few seconds."))}</p>`;
  openInside(true);
  const r = await apiPost("/api/look-inside", { path });
  if (!$("#insideWin").hidden && body.querySelector(".file-name") && body.querySelector(".file-name").textContent === name) {
    if (!r.ok || r.data.error) {
      body.innerHTML = `<p class="file-name" translate="no">${esc(name)}</p><p class="note">${esc(tr((r.data && r.data.error) || "That file couldn't be read."))}</p>`;
      return;
    }
    INSIDE = { ...r.data, name, path, nodes: [], pick: new Map() };   // pick: what's chosen to take out, and how many files each is
    drawInside();
  }
}
// a package's assets as folders (each drawn when it's opened, so a package of thousands opens at once)
function insideTree(items) {
  const root = { dirs: new Map(), files: [], count: 0, size: 0, path: "" };
  for (const it of items) {
    const parts = it.path.split("/");
    let node = root;
    for (const part of parts.slice(0, it.size == null ? parts.length : -1)) {
      if (!node.dirs.has(part)) node.dirs.set(part, { dirs: new Map(), files: [], count: 0, size: 0, path: (node.path ? node.path + "/" : "") + part });
      node = node.dirs.get(part);
    }
    if (it.size != null) node.files.push({ ...it, name: parts[parts.length - 1] });
  }
  (function total(n) {
    for (const d of n.dirs.values()) { total(d); n.count += d.count; n.size += d.size; }
    n.count += n.files.length; n.size += n.files.reduce((t, f) => t + f.size, 0);
  })(root);
  return root;
}
// A file's preview in Look inside (its type, when it has no picture).
function previewImg(it, n) {
  const ext = (it.name || it.path).split(".").pop();
  return it.preview ? `<img class="pv" loading="lazy" alt="" src="${keyed(`/inside/${INSIDE.id}/${n}-${it.guid}.png`)}">`
    : `<span class="pv" aria-hidden="true">${esc(ext.length <= 6 ? ext : "")}</span>`;
}
function insideFolder(node, n) {   // one folder's contents: its folders (closed), then its files
  const dirs = [...node.dirs.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  return `<ul>` + dirs.map(([name, d]) => {
    INSIDE.nodes.push({ node: d, n });
    return `<li><details data-node="${INSIDE.nodes.length - 1}"><summary>${pickBox(`d:${n}:${d.path}`, d.count, name)}<span translate="no">${esc(name)}</span>` +
      `<span class="n">${esc(tr(d.count === 1 ? "{0} file, {1}" : "{0} files, {1}", d.count.toLocaleString(), sizeText(d.size)))}</span></summary></details></li>`;
  }).join("") + node.files.sort((a, b) => a.name.localeCompare(b.name)).map(f =>
    `<li class="f">${pickBox(`p:${n}:${f.path}`, 1, f.name)}${previewImg(f, n)}<span class="nm" translate="no">${esc(f.name)}${codeTag(f)}</span><span class="sz">${sizeText(f.size)}</span></li>`).join("") + `</ul>`;
}
// What's in a package, as a tree of folders, with how many files and their size.
function insidePackage(items, n, open) {
  const tree = insideTree(items);
  if (!tree.count) return `<p class="sum">${esc(tr("No files in it."))}</p>`;
  const sum = `<p class="sum">${esc(tr(tree.count === 1 ? "{0} file, {1}" : "{0} files, {1}", tree.count.toLocaleString(), sizeText(tree.size)))}</p>`;
  return sum + (open ? insideFolder(tree, n) : (INSIDE.nodes.push({ node: tree, n }), `<div data-pkg-node="${INSIDE.nodes.length - 1}"></div>`));
}
// searching: every file whose path has these words, wherever it is (with Only code, only scripts and plugins)
function insideFound(q, onlyCode = false) {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean), found = [];
  // Note the files in a package that have every word searched for.
  const look = (items, n, where) => {
    for (const it of items) if ((it.size != null || it.code) && (!onlyCode || it.code) && words.every(w => it.path.toLowerCase().includes(w))) found.push({ ...it, n, where });
  };
  if (INSIDE.kind === "zip") INSIDE.packages.forEach((p, n) => look(p.items, n, p.name));
  else look(INSIDE.items, 0, "");
  if (INSIDE.kind === "zip")
    for (const f of INSIDE.files) if ((!onlyCode || f.code) && words.every(w => f.name.toLowerCase().includes(w))) found.push({ path: f.name, size: f.size, zip: true, code: f.code, editor: f.editor });
  if (!found.length) return `<p class="sum">${esc(tr(onlyCode && !words.length ? "No scripts or DLLs." : "Nothing in it matches."))}</p>`;
  return `<p class="sum">${esc(tr(found.length === 1 ? "{0} file matches." : "{0} files match.", found.length.toLocaleString()))}</p>` +
    `<ul class="found">${found.slice(0, 500).map(f => `<li class="f">${pickBox(f.zip ? `z:${f.path}` : `${f.size == null ? "d" : "p"}:${f.n}:${f.path}`, 1, f.path)}` +
      `${f.zip ? `<span class="pv" aria-hidden="true">zip</span>` : previewImg(f, f.n)}` +
      `<span class="nm" translate="no">${esc(f.path)}${codeTag(f)}${f.where ? `<small>${esc(f.where)}</small>` : ""}</span><span class="sz">${f.size == null ? "" : sizeText(f.size)}</span></li>`).join("")}</ul>` +
    (found.length > 500 ? `<p class="more">${esc(tr("The first 500 are shown: search for more words to narrow it down."))}</p>` : "");
}
/* What code a package holds (issue #303): its scripts and plugins, which of them run in the editor, which are a tool's
   Hoard knows by their GUIDs (so the rest stands out), and where the rest goes. It's information, not a verdict. */
const CODE_KINDS = { script: "Script", plugin: "DLL" };
// What each kind is, said when you point at its mark.
const CODE_SAYS = { script: "A script: Unity compiles it when it's imported.", plugin: "A DLL or plugin: Unity loads it when it's imported." };
// A file's mark in Look inside, when it's a script or a plugin.
function codeTag(it) {
  if (!it.code) return "";
  const what = [tr(CODE_SAYS[it.code]),
                it.editor && tr("It runs in the editor."), it.tool && tr("It's {0}'s.", it.tool)].filter(Boolean).join(" ");
  return ` <span class="codetag${it.editor ? " ed" : ""}${it.tool ? " known" : ""}" title="${esc(what)}">${esc(tr(CODE_KINDS[it.code]))}` +
    `${it.editor ? ` · ${esc(tr("Editor"))}` : ""}${it.tool ? ` · <span translate="no">${esc(it.tool)}</span>` : ""}</span>`;
}
// The code in a package (or all of a .zip's), in words: one sentence each.
function codeWords(c, loose) {
  const n = c ? c.scripts + c.plugins : 0, l = loose ? (loose.scripts || 0) + (loose.plugins || 0) : 0;
  if (!n && !l) return [tr("No scripts or DLLs.")];
  // How many scripts and plugins, in words.
  const count = x => [x.scripts && tr(x.scripts === 1 ? "1 script" : "{0} scripts", x.scripts),
                      x.plugins && tr(x.plugins === 1 ? "1 DLL or plugin" : "{0} DLLs or plugins", x.plugins)].filter(Boolean);
  const out = [];
  if (n) {
    out.push(tr("Code that Unity runs once it's imported: {0}.", listed(count(c))));
    if (c.editor) out.push(tr(c.editor === 1 ? "1 of them runs in the editor." : "{0} of them run in the editor.", c.editor));
    const tools = Object.entries(c.tools || {}), theirs = tools.reduce((t, [, k]) => t + k, 0);
    if (tools.length) out.push(tr("{0} from tools Hoard knows: {1}.", theirs, listed(tools.map(([t]) => t))));
    if (n > theirs && (c.folders || []).length) out.push(tr("The rest goes in {0}.", listed(c.folders)));
  }
  if (l) out.push(tr("Loose in the zip, outside its packages: {0}.", listed(count(loose))));
  return out;
}
// Look inside's code: what a package holds, with Only code to list just that.
function insideCode(I) {
  const all = I.kind === "zip" ? I.packages.reduce((t, p) => {
    const c = p.code || {};
    for (const k of ["scripts", "plugins", "editor"]) t[k] += c[k] || 0;
    for (const [tool, k] of Object.entries(c.tools || {})) t.tools[tool] = (t.tools[tool] || 0) + k;
    for (const f of c.folders || []) if (!t.folders.includes(f) && t.folders.length < 8) t.folders.push(f);
    return t;
  }, { scripts: 0, plugins: 0, editor: 0, tools: {}, folders: [] }) : I.code;
  if (!all) return { code: "", hasCode: false };   // cached before code summaries: read again next time
  const any = all.scripts + all.plugins + ((I.loose || {}).scripts || 0) + ((I.loose || {}).plugins || 0);
  return { code: codeWords(all, I.loose).join(" "), hasCode: !!any };
}
// Draw Look inside: the package (or each in the .zip), or the files matching what's searched for.
function drawInside(q = "") {
  const I = INSIDE, body = $("#insideBody");
  I.nodes = [];
  let html;
  if (q.trim() || I.onlyCode) html = insideFound(q, !!I.onlyCode);
  else if (I.kind === "zip") {
    const total = I.files.reduce((t, f) => t + f.size, 0);
    html = `<p class="sum">${esc(tr(I.files.length === 1 ? "This zip holds {0} file, {1}." : "This zip holds {0} files, {1}.", I.files.length.toLocaleString(), sizeText(total)))} ` +
      esc(I.packages.length ? tr(I.packages.length === 1 ? "One of them is a Unity package: open it to see what's in it." : "{0} of them are Unity packages: open one to see what's in it.", I.packages.length) : "") + `</p>` +
      (I.files.some(f => f.locked) ? `<p class="note">${esc(tr("This zip is locked with a password. The store page usually says what it is."))}</p>` : "") +
      I.packages.map((p, n) => `<details class="pkg"${I.packages.length === 1 ? " open" : ""} data-pkg="${n}"><summary translate="no">${esc(p.name)}</summary>` +
        (p.error ? `<p class="note">${esc(tr(p.error))}</p>` : insidePackage(p.items, n, false)) + `</details>`).join("") +
      `<details><summary>${esc(tr("Every file in the zip"))}</summary><ul class="zipfiles">${I.files.map(f =>
        `<li>${pickBox(`z:${f.name}`, 1, f.name)}<span class="nm" translate="no">${esc(f.name)}${codeTag(f)}</span><span class="sz">${sizeText(f.size)}</span></li>`).join("")}</ul>` +
      (I.more ? `<p class="more">${esc(tr("And {0} more.", I.more.toLocaleString()))}</p>` : "") + `</details>`;
  } else html = insidePackage(I.items, 0, true);
  HoardInside.render(body, { name: I.name, query: q, onlyCode: !!I.onlyCode, ...insideCode(I), ...insideBar(),
    controls: I.kind !== "zip" || !!I.files.length, content: legacyFragment(html) }, tr);
  for (const d of body.querySelectorAll("details.pkg[open]")) fillPackage(d);
}
// Extract: what's chosen (a file "p:<package>:<path>", a folder and everything in it "d:...", a zip's file "z:<name>")
// taken out into a folder of its own in Hoard Edits (hoard/packages.py, extract), which opens when it's done
function pickedUnder(key) {   // in a folder that's chosen (so chosen with it)
  const [kind, n, ...rest] = key.split(":"), path = rest.join(":");
  return kind !== "z" && [...INSIDE.pick.keys()].some(k => k !== key && k.startsWith(`d:${n}:`) && path.startsWith(k.slice(`d:${n}:`.length) + "/"));
}
// A file's or folder's tick, to take it out (one in a folder ticked is ticked with it).
function pickBox(key, count, name) {
  const under = pickedUnder(key), on = under || INSIDE.pick.has(key);
  return `<input type="checkbox" class="pick" data-pick="${esc(key)}" data-count="${count}"${on ? " checked" : ""}${under ? " disabled" : ""}` +
    ` aria-label="${esc(tr("Choose {0}", name))}">`;
}
// Selection and extraction progress for Svelte; the lazy file tree stays mounted when only these change.
function insideBar() {
  return { chosen: [...INSIDE.pick.values()].reduce((total, count) => total + count, 0),
    packaged: INSIDE.kind !== "zip" || !!INSIDE.packages.length, busy: !!INSIDE.busy, metas: !!INSIDE.metas };
}
// Note a tick: a folder's brings everything in it, no longer chosen on its own.
function pickChanged(box) {
  const key = box.dataset.pick;
  if (box.checked) INSIDE.pick.set(key, Number(box.dataset.count)); else INSIDE.pick.delete(key);   // (an empty folder: 0)
  if (key.startsWith("d:")) {   // a folder: what's in it comes with it (and is no longer chosen on its own)
    const n = key.split(":")[1], under = key.slice(`d:${n}:`.length) + "/";
    for (const k of [...INSIDE.pick.keys()]) if (/^[pd]:/.test(k) && k.split(":")[1] === n && k.slice(`d:${n}:`.length).startsWith(under)) INSIDE.pick.delete(k);
    const d = box.closest("details");
    for (const b of d.querySelectorAll("input.pick")) {
      if (b === box) continue;
      INSIDE.pick.delete(b.dataset.pick);
      b.checked = box.checked; b.disabled = box.checked;
    }
  }
  HoardInside.bar($("#insideBody"), insideBar());
}
// Take what's ticked out of the package (or all of it) into a folder, then open it.
async function extractInside(what) {
  const I = INSIDE, picks = what === "all" ? ["all"] : [...I.pick.keys()];
  if (!picks.length || I.busy) return;
  // Draw Look inside's bar again.
  const redraw = () => { if (INSIDE === I) HoardInside.bar($("#insideBody"), insideBar()); };
  I.busy = true;
  redraw();
  const r = await apiPost("/api/look-inside/extract", { path: I.path, picks, metas: !!I.metas, open: true });
  I.busy = false;
  redraw();   // (only while it's still this file's window: closed, or another file opened, it just says how it went)
  if (!r.ok) {   // (with what was left out, and why, when nothing could be: issue #174)
    const why = (r.data.skipped || [])[0];
    toast(tr(r.data.error || "Those files couldn't be taken out.") + (why ? ` ${why.name} (${tr(why.why)})` : ""));
    return;
  }
  toast(tr(r.data.files === 1 ? "Took 1 file out, into {1}." : "Took {0} files out, into {1}.", r.data.files.toLocaleString(), r.data.folder) +
    (r.data.skipped.length ? " " + tr(r.data.skipped.length === 1 ? "1 file was left out: {0}." : "{0} files were left out.",
      r.data.skipped.length === 1 ? `${r.data.skipped[0].name} (${tr(r.data.skipped[0].why)})` : r.data.skipped.length) : ""));
}
// Fill a folder of the package's tree, the first time it's opened.
function fillPackage(d) {
  const slot = d.querySelector("[data-pkg-node]");
  if (slot && !slot.childElementCount) { const { node, n } = INSIDE.nodes[+slot.dataset.pkgNode]; slot.innerHTML = insideFolder(node, n); }
}
// Look inside's window, its search, ticks and buttons.
function wireInside() {
  makeWindow($("#insideWin"));
  WINDOWS.insideWin = () => openInside(false);
  const w = $("#insideWin");
  viewListen("downloads", w, "toggle", e => {   // a folder, or a package in a zip, is drawn as it's opened
    const d = e.target;
    if (!INSIDE || !d.open) return;
    if (d.dataset.node != null && d.childElementCount === 1) {
      const { node, n } = INSIDE.nodes[+d.dataset.node];
      d.insertAdjacentHTML("beforeend", insideFolder(node, n));
    } else if (d.classList.contains("pkg")) fillPackage(d);
  }, true);
  viewListen("downloads", w, "change", e => {
    if (!INSIDE) return;
    if (e.target.matches("input.pick")) pickChanged(e.target);
    else if (e.target.id === "insideMetas") INSIDE.metas = e.target.checked;
  });
  viewListen("downloads", w, "click", e => {
    const x = e.target.closest("[data-x=extract]");
    if (x && INSIDE && !x.disabled) extractInside(x.dataset.what);
    if (e.target.closest("[data-only-code]") && INSIDE) {   // just the scripts and plugins, or everything again
      INSIDE.onlyCode = !INSIDE.onlyCode;
      drawInside(($("#insideQ") || {}).value || "");
      const b = $("#insideBody [data-only-code]");
      if (b) b.focus();
    }
    if (e.target.matches("summary input.pick")) e.stopPropagation();   // (choosing a folder doesn't open or close it)
  });
  let t;
  viewListen("downloads", w, "input", e => {
    if (e.target.id !== "insideQ" || !INSIDE) return;
    clearTimeout(t);
    t = setTimeout(() => {
      const q = e.target.value, at = e.target.selectionStart;
      drawInside(q);
      const box = $("#insideQ"); box.focus(); box.setSelectionRange(at, at);
    }, 150);
  });
}

/* ---------- URL state */
function saveHash() {
  const p = new URLSearchParams();
  if (state.q) p.set("q", state.q);
  if (state.store) p.set("store", state.store);
  if (state.lib !== "") p.set("lib", state.lib);
  if (state.creator) p.set("creator", state.creator);
  if (state.tags.size) p.set("tags", [...state.tags].join(","));
  if (state.types.size) p.set("types", [...state.types].join(","));
  if (state.set) p.set("set", state.set);
  if (state.sort !== "name") p.set("sort", state.sort);
  if (state.ptype) p.set("type", state.ptype);
  if (state.view !== "downloads") p.set("view", state.view);
  if (state.view === "space" && state.space) p.set("space", state.space);
  if (openId != null) p.set("open", openId);   // (a product's details: a place, for Back and Forward)
  setAddress(p);
}
// Read the search, filters and place from the address.
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get("q") || ""; state.store = p.get("store") || ""; state.creator = p.get("creator") || "";
  state.lib = /^\d+$/.test(p.get("lib") || "") ? p.get("lib") : "";
  state.tags = new Set((p.get("tags") || "").split(",").filter(Boolean));
  state.types = new Set((p.get("types") || "").split(",").filter(Boolean));
  state.set = /^[0-9A-Za-z]{1,16}$/.test(p.get("set") || "") ? p.get("set") : "";
  if (state.set) state.store = "Sets";   // (a set's folder; and "Show in Downloads" from 4.1)
  state.sort = sortFrom(p.get("sort"), SORTS);
  state.ptype = PRODUCT_TYPES[p.get("type")] ? p.get("type") : "";
  state.view = VIEWS[p.get("view")] ? p.get("view") : "downloads";
  state.space = ["copies", "unused"].includes(p.get("space")) ? p.get("space") : "";
  if (/^\d+$/.test(p.get("open") || "")) openId = +p.get("open");  // "Show it in Downloads" from the Library
}

/* ---------- events */
let qTimer;


/* ---------- moving the selected downloads to another library folder, each as a job of its own (Tasks) */
async function bulkMove(to) {
  const lib = (DATA.libraries || []).find(l => l.n === to);
  const chosen = [...sel.ids].map(T.byId).filter(a => a && !isLocal(a) && !a.linked && (a.library || 0) !== to);
  if (!lib) return;
  if (!chosen.length) { toast(tr("Those are already in {0}, or are your own packages (which stay in Local).", libText(lib))); return; }
  if (!await ask(tr(chosen.length === 1 ? "Move {0} to {1} ({2})?" : "Move {0} products to {1} ({2})?",
                    chosen.length === 1 ? chosen[0].name : chosen.length, libText(lib), lib.path) + "\n\n" +
                 tr("Hoard copies the files there, checks every one, then deletes them where they were. Anything of your own " +
                    "in their folders stays. Each move is a task of its own: follow them in Tasks."), "Move them")) return;
  let started = 0, refused = 0;
  for (const a of chosen) {
    const r = await apiPost("/api/move", { key: a.tag_key, to });
    if (r.ok) started++; else refused++;
  }
  setSelecting(false);
  toast([tr(started === 1 ? "Moving 1 product to {1}. Follow it in Tasks." : "Moving {0} products to {1}. Follow them in Tasks.", started, libText(lib)),
         refused && tr("{0} couldn't start (the queue may be full): try those again when it's done.", refused)].filter(Boolean).join(" "));
  for (let n = 0; started && n < 4000; n++) {   // when they're done, show where they are now (quick ones too)
    await new Promise(ok => setTimeout(ok, n < 20 ? 300 : 1500));
    let t = {};
    try { t = await (await api("/api/tasks", { cache: "no-store" })).json(); } catch (e) { return; }
    if ((t.current && t.current.task === "move") || (t.queue || []).some(q => q.task === "move")) continue;
    await load(true);
    return;
  }
}
/* ---------- archiving the selected (in the Library too), and deleting their downloaded files */
async function bulkArchive() {
  const chosen = [...sel.ids].map(T.byId).filter(a => a && !isLocal(a) && !a.mark);
  if (!chosen.length) { toast("Those are archived, removed or hidden already, or are your own packages."); return; }
  const r = await apiPost("/api/marks", { kind: "archived", keys: [...new Set(chosen.map(a => a.tag_key))], on: true });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  setSelecting(false); await load();
  toast(tr(chosen.length === 1 ? "Archived {0}. Its files stay where they are: find it in Archive." : "Archived {0} products. Their files stay where they are: find them in Archive.",
           chosen.length === 1 ? chosen[0].name : chosen.length));
}
// Delete the selected downloads' files, once you say so.
async function bulkDelete() {
  const chosen = [...sel.ids].map(T.byId).filter(a => a && !isLocal(a) && !a.linked);
  if (!chosen.length) { toast("Your own packages leave Local from their own panel: Take out of Local."); return; }
  const bytes = chosen.reduce((t, a) => t + a.size, 0);
  if (!await ask(tr(chosen.length === 1 ? "Delete the files Hoard downloaded for {0} ({1})?" : "Delete the files Hoard downloaded for {0} products ({1})?",
                    chosen.length === 1 ? chosen[0].name : chosen.length, sizeText(bytes)) + "\n\n" +
                 tr("Anything of your own in the same folders stays. This can't be undone. What's still in your library stays " +
                    "there, so you can download it again."), "Delete files", true)) return;
  const r = await apiPost("/api/delete-files", { keys: [...new Set(chosen.map(a => a.tag_key))], confirm: true });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  setSelecting(false);
  if (r.data.job) return afterQueuedJob(r, "delete-files", () => load(true).then(() => state.view === "space" && loadSpace()));
  await load();
  if (state.view === "space") loadSpace();
  toast(tr(r.data.files === 1 ? "Deleted {0} file ({1})." : "Deleted {0} files ({1}).", r.data.files.toLocaleString(), sizeText(r.data.bytes)));
}
/* ---------- a tab for each library folder (hoard/libraries.py): shown once there's more than the downloads folder */
const libName = n => { const l = (DATA.libraries || []).find(l => String(l.n) === String(n)); return l ? libText(l) : tr("Another folder"); };
let drivesShown = "";
// The library folders, each with how many downloads it has, to show only one.
function renderDrives() {
  const libs = DATA.libraries || [];
  if (state.lib !== "" && !libs.some(l => String(l.n) === state.lib)) state.lib = "";   // a folder taken out
  const counts = {};
  for (const a of DATA.assets) if (inView(a)) counts[a.library || 0] = (counts[a.library || 0] || 0) + 1;
  const html = libs.length < 2 ? "" : '<span class="tabsep" aria-hidden="true"></span>' + libs.map(l =>
    `<button role="radio" data-lib="${l.n}" aria-checked="false" class="${l.available ? "" : "away"}" ` +
    `title="${esc(l.available ? l.path : tr("{0} (its drive isn't connected)", l.path))}">${DRIVE_ICON}${esc(libText(l))}` +
    `<span class="n">${(counts[l.n] || 0).toLocaleString()}</span></button>`).join("");
  if (html !== drivesShown) { $("#drives").innerHTML = html; drivesShown = html; }
  $("#drives").hidden = !html;
}



// Download what's new from some stores (choosing what, in the downloads dialog).
const downloadNew = stores => pickNew(stores, keys => keys ? startDownload(storesOf(keys), null, null, keys) : startDownload(stores));



// Set the tiles' size.


   // kept with the other layout choices
const TILE_KEY = "dl_tile_size";   // this page's own tile size (see applyUi)


// Add a value to a set, or take it out when it's there.
function toggle(set, v) { set.has(v) ? set.delete(v) : set.add(v); }




/* ---------- Local (issue #80): your own packages, copied into Hoard or listed where they are */
function localSection(a) {
  return `<p class="sub">${a.note ? `${esc(tr("For {0}.", a.note))} ` : ""}${a.linked
      ? "Listed where it is: Hoard never changes anything in this folder."
      : "A copy in Hoard, checked like your downloads."}</p>` +
    `<div class="actions">${a.linked ? `<button class="ghost" data-act="local-rescan">Rescan</button>` : ""}` +
    `<button class="ghost" data-act="local-picture">${esc(tr(a.own_picture ? "Change its picture..." : "Choose a picture..."))}</button>` +
    (a.own_picture ? `<button class="ghost" data-act="local-unpicture">${esc(tr(a.linked ? "Use one of its own pictures" : "Take the picture off"))}</button>` : "") +
    `<button class="ghost" data-act="local-remove">Remove from Local</button></div>`;
}
// Do what a button on one of your own packages says: its picture, details, or taking it out of Local.
async function localAction(act, a) {
  if (!a) return;
  if (act === "local-picture" || act === "local-unpicture") {   // (kept in Hoard's own folder for it: see local.py)
    const image = act === "local-picture" ? await choosePicture() : null;
    if (act === "local-picture" && !image) return;
    const r = await apiPost("/api/local/picture", { folder: a.folder, image });
    if (!r.ok) { toast(r.data.error || "That picture couldn't be kept."); return; }
    await load();
    const again = DATA.assets.find(x => x.folder === a.folder);
    if (again && openId === a.id) showDetail(again, false);
    toast(image ? "Its tile shows that picture now." : "Took the picture off.");
    return;
  }
  if (act === "local-remove" && !await ask(a.linked
      ? tr("Take {0} out of Local? Nothing in its folder is touched.", a.name)
      : tr("Take {0} out of Local, and delete Hoard's copy of it? Your original isn't touched.", a.name), "Take it out")) return;
  const r = await apiPost(act === "local-rescan" ? "/api/local/rescan" : "/api/local/remove",
                          { folder: a.folder, confirm: act === "local-remove" });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  if (act === "local-remove") closeDetail();
  if (r.data.job) return afterQueuedJob(r, act === "local-rescan" ? "rescan-local" : "remove-local", () => load(true));
  await load(true);
  if (act === "local-rescan") { const again = DATA.assets.find(x => x.folder === a.folder); if (again) showDetail(again, false); }
  toast(act === "local-rescan" ? tr(r.data.files === 1 ? "Rescanned: 1 file." : "Rescanned: {0} files.", r.data.files)
        : tr("Took {0} out of Local.", a.name));
}
// Open Add to Local, or close it (open: which; else the other way).
function openLocal(open) {
  const panel = $("#localPanel");
  const show = open ?? panel.hidden;
  if (show) {
    const copy = !SETTINGS || SETTINGS.local_copy !== false;
    $(copy ? "#localCopy" : "#localLink").checked = true;
    $("#localMsg").textContent = "";
    syncBrowse();
  }
  panel.hidden = !show;
  $("#localAdd").setAttribute("aria-expanded", String(show));
  if (show) $("#localPath").focus();
}
// issue #109: each folder some levels down as its own package: what that would add, before adding it
let previewFor = "";
// Show what adding a folder to Local would add: one product, or one for each folder in it.
async function previewLocal() {
  const depth = Number($("#localDepth").value), path = $("#localPath").value.trim(), list = $("#localPreview");
  $("#localNameRow").hidden = depth > 0;
  $("#localSplitHint").hidden = !depth;
  $("#localCreator").placeholder = depth >= 2 ? "The folder above each, or type one for all" : "You";
  const key = `${depth}|${path}|${$("#localCopy").checked}`;
  if (!depth || !path) { list.hidden = true; previewFor = ""; return; }
  if (key === previewFor) return;
  previewFor = key;
  const r = await apiPost("/api/local/preview", { path, depth, copy: $("#localCopy").checked });
  if (previewFor !== key) return;   // changed meanwhile
  list.hidden = false;
  if (!r.ok) { list.innerHTML = `<li class="muted">${esc(r.data.error || "That folder can't be split.")}</li>`; return; }
  const n = r.data.packages.length;
  list.innerHTML = `<li class="muted">${esc(r.data.loose ? tr(r.data.loose === 1 ? "{0} packages; 1 file in the folders above is left out:" : "{0} packages; {1} files in the folders above are left out:", n, r.data.loose)
                                                        : tr(n === 1 ? "1 package:" : "{0} packages:", n))}</li>` +
    r.data.packages.slice(0, 200).map(p => `<li${p.added ? ' class="muted"' : ""}><strong>${esc(p.name)}</strong>` +
      `${p.creator ? ` <span class="muted" translate="no">${esc(tr("by {0}", p.creator))}</span>` : ""}${p.added ? ` <span>${esc(tr("(already in Local: left as it is)"))}</span>` : ""}</li>`).join("") +
    (n > 200 ? `<li class="muted">${esc(tr("and {0} more", n - 200))}</li>` : "");
}
// Add a folder (or each of its folders) to Local.
async function addLocal() {
  const depth = Number($("#localDepth").value);
  const body = { path: $("#localPath").value, name: depth ? "" : $("#localName").value, creator: $("#localCreator").value,
                 note: $("#localNote").value, copy: $("#localCopy").checked, depth };
  $("#localGo").disabled = true;
  const r = await apiPost("/api/local/add", body);
  $("#localGo").disabled = false;
  if (!r.ok) { $("#localMsg").textContent = r.data.error || "That didn't work."; return; }
  if (SETTINGS) SETTINGS.local_copy = body.copy;
  for (const id of ["#localPath", "#localName", "#localNote"]) $(id).value = "";
  $("#localDepth").value = "0"; previewLocal();
  openLocal(false);
  if (queuedToast(r)) return;
  toast(depth ? "Adding each folder to Local. Follow it in Tasks." : body.copy ? "Copying it into Hoard. Follow it in Tasks." : "Adding it to Local.");
  // when it's done, show it (a quick one can finish before the tasks poll sees it)
  for (let n = 0; n < 2000; n++) {
    await new Promise(ok => setTimeout(ok, n < 20 ? 300 : 1500));
    let j = {};
    try { j = (await (await api("/api/status", { cache: "no-store" })).json()).job || {}; } catch (e) { return; }
    if (j.running && j.task === "add-local") continue;
    await load(true);
    if (j.error) toast(j.error);
    return;
  }
}
// Add to Local's window, its fields and buttons.
function wireLocal() {
  makeWindow($("#localPanel"));
  WINDOWS.localPanel = () => openLocal(false);
  viewListen("downloads", $("#localAdd"), "click", () => openLocal());
  viewListen("downloads", $("#localBrowseFolder"), "click", async () => { if (await browseInto($("#localPath"), "folder")) previewLocal(); });
  viewListen("downloads", $("#localBrowseFile"), "click", async () => {
    if (await browseInto($("#localPath"), "file")) $("#localCopy").checked = true;   // a single file can only be copied in
  });
  viewListen("downloads", $("#localGo"), "click", addLocal);
  viewListen("downloads", $("#localDepth"), "change", previewLocal);
  viewListen("downloads", $("#localPath"), "change", previewLocal);
  for (const r of document.querySelectorAll("input[name=localKeep]")) viewListen("downloads", r, "change", previewLocal);
  viewListen("downloads", $("#localPath"), "keydown", e => { if (e.key === "Enter") addLocal(); });
}


// issue #82: a copy of a download for you to change, in a folder of its own that Hoard never checks or replaces
async function editableCopy(a, button) {
  if (!a) return;
  if (!await ask(tr("Copy {0} into a folder of its own for you to change?", a.name) + "\n\n" +
               tr("Hoard never checks, updates or replaces that copy. Only files that still match what Hoard downloaded " +
                  "are copied. Anything you add to the copy later hasn't been checked by Hoard, so be as careful with it as " +
                  "with any download.") + "\n\n" + tr("The copy is listed in Local, where it is, and opened there."), "Make the copy")) return;
  button.disabled = true;
  const r = await apiPost("/api/edit-copy", { key: a.tag_key, open: false });
  button.disabled = false;
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  const left = r.data.skipped.length;
  const said = [tr(r.data.files === 1 ? "Copied 1 file to {1}." : "Copied {0} files to {1}.", r.data.files, r.data.folder),
         left && tr(left === 1 ? "Left out 1 that has changed or gone since Hoard downloaded it (listed in the read-me there)."
                               : "Left out {0} that have changed or gone since Hoard downloaded them (listed in the read-me there).", left)].filter(Boolean).join(" ");
  if (!r.data.local) { toast(said); return; }
  // issue #328: the copy is in Local once its task is done: its tile is opened there, with what was copied said
  await afterQueuedJob(r, "add-local", async () => {
    await load(true);
    const copy = DATA.assets.find(x => isLocal(x) && x.abs_folder === r.data.folder);
    if (!copy) return;
    closeDetail();
    Object.assign(state, { view: "downloads", store: "Local", lib: "", q: "", creator: "", ptype: "", set: "" });
    state.tags.clear(); state.types.clear();
    render();
    showDetail(copy);
  });
  toast(said);
}
// Library folders (Settings): a product kept in one of them can be moved to another
const libLabel = l => `${libText(l)} (${l.path})`;
// A download's details: the library folder it's in, and moving it to another.
function librarySection(a) {
  const libs = DATA.libraries || [];
  if (isLocal(a) || a.linked || libs.length < 2) return "";
  const here = libs.find(l => l.n === a.library), others = libs.filter(l => l.n !== a.library && l.available);
  return `<h3>Library folder</h3><p class="sub">${esc(here ? tr("Kept in {0}.", libLabel(here)) : tr("Kept in another folder."))}</p>` +
    (others.length ? `<div class="field movefield"><select id="moveTo" aria-label="Move it to">` +
      others.map(l => `<option value="${l.n}">${esc(l.free != null ? tr("{0}, {1} free", libLabel(l), sizeText(l.free)) : libLabel(l))}</option>`).join("") +
      `</select><button class="ghost sm" data-act="move">Move here</button></div>`
      : `<p class="sub">Your other library folders' drives aren't connected.</p>`);
}
// Move a download to another library folder, once you say so (copied, checked, then deleted here).
async function moveProduct(a, button) {
  const to = +$("#moveTo").value, lib = (DATA.libraries || []).find(l => l.n === to);
  if (!a || !lib) return;
  if (!await ask(tr("Move {0} to {1}?", a.name, lib.path) + "\n\n" + tr("Hoard copies its files there, checks every one, then deletes them " +
                 "here. Anything of your own in its folder stays where it is."), "Move it")) return;
  button.disabled = true;
  const r = await apiPost("/api/move", { key: a.tag_key, to });
  button.disabled = false;
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  closeDetail();
  if (queuedToast(r)) return;
  toast(tr("Moving {0}. Follow it in Tasks.", a.name));
  for (let n = 0; n < 4000; n++) {   // when it's done, show where it is now
    await new Promise(ok => setTimeout(ok, n < 20 ? 300 : 1500));
    let j = {};
    try { j = (await (await api("/api/status", { cache: "no-store" })).json()).job || {}; } catch (e) { return; }
    if (j.running && j.task === "move") continue;
    await load(true);
    if (j.error) toast(j.error);
    return;
  }
}
// issue #81: a download can be deleted from disk, after you confirm
async function deleteFiles(a) {   // issue #81; and since 3.0, for anything downloaded, whether or not it's removed
  if (!a || isLocal(a)) return;   // (your own packages: Take out of Local)
  if (!await ask(tr("Delete the files Hoard downloaded for {0}?", a.name) + "\n\n" +
               [tr("Anything of your own in the same folder stays."), tr("This can't be undone."),
                a.mark !== "removed" && tr("It stays in your library, so you can download it again.")].filter(Boolean).join(" "),
               "Delete files", true)) return;
  const r = await apiPost("/api/delete-files", { keys: [a.tag_key], confirm: true });
  if (!r.ok) { toast(r.data.error || "That didn't work."); return; }
  if (r.data.job) { closeDetail(); return afterQueuedJob(r, "delete-files", () => load(true)); }
  closeDetail(); await load();
  toast([tr(r.data.files === 1 ? "Deleted {0} file ({1})." : "Deleted {0} files ({1}).", r.data.files, sizeText(r.data.bytes)),
         r.data.kept.length && tr("Its folder still has other files, so it was kept.")].filter(Boolean).join(" "));
}







/* ---------- how the tag code below finds its way around this page */
const T = {
  slotKey: "id",
  id: a => String(a.id),
  art: a => art(a),   // its picture (from its folder) or its initials
  byId: id => byId.get(+id),
  open: () => (openId != null ? byId.get(openId) : null),
  shown: () => DATA.assets.filter(a => matches(a)),
  facets: () => renderFacets(DATA.assets.filter(a => matches(a))),   // the filters drawn again, and nothing else
  reload: () => load(),
  closeDetail: () => closeDetail(),
  closeOtherPanels: () => {},   // windows stay open side by side
  render: () => render(),
  goTo: () => {   // Back or Forward (shared.js): the tab, view, filters and details the address names
    const want = new URLSearchParams(location.hash.slice(1)).get("open"), was = openId;
    readHash();
    if (!want) { openId = was; closeDetail(); }
    render();
    if (want && byId.has(+want) && (+want !== was || !detail.classList.contains("open"))) showDetail(byId.get(+want), false);
  },
  pickHere: () => {   // Projects' Add Assets: what's downloaded, to choose from (pickStart)
    if (state.store === "Sets") { state.store = ""; state.set = ""; }
    state.view = "downloads";
    closeDetail();
  },
  all: () => DATA.assets,
  download: keys => startDownload(storesOf(keys), null, null, keys),   // (the Sets tab)
  membersOf: id => {   // a stack's copies, all chosen together
    const a = byId.get(+id);
    return a && (stackSize.get(a.id) || 0) > 1 ? (stackMembers.get(a.stack_key) || [a]).map(o => String(o.id)) : null;
  },
  actions: () => {   // what the selection bar and right-click offer here
    const groups = [TAG_ACTIONS, SET_ACTIONS(), PROJECT_ACTIONS()];
    const libs = (DATA.libraries || []).filter(l => l.available);
    if ((DATA.libraries || []).length > 1 && libs.length)
      groups.push({ name: "Move", items: libs.map(l => ({ label: tr("Move to {0}", libText(l)), raw: true, run: () => bulkMove(l.n) })) });
    groups.push({ name: "More", items: [{ label: "Archive", run: bulkArchive },
                                        { label: "Delete downloaded files", run: bulkDelete, danger: true }] });
    return { main: [], groups };
  },
};
// Do what a button in the tag manager says: keep a suggestion, hide it, rename a tag or delete one.

// The tag manager's buttons and fields.


/* ---------- settings and downloading, the same in both views. T (above) connects this to the page. */
/* ---------- issue #113: what the routine check found. It downloads nothing itself: you choose, from the same list
   Download new shows, or put it off (Not now) until the next check finds something. */


/* ---------- local support reports: everything stays on this computer until the user chooses to share the ZIP. */


/* ---------- Browse: the system's own folder (or file) picker, in Hoard's window (not in a web browser, where
   there's no way to ask for one; the path is typed there) */
/* ---------- updates: checked with GitHub when you ask (or daily, if you turned that on); installed by Hoard itself
   only in the app Hoard-Setup installed on Windows */

// Whether a new version of Hoard is out, in words.

// Start a download (of some stores, only some kinds, or some products), with the files chosen.

// Follow the download running, showing its progress, until it's done.

// Show a download's progress: what it's doing, each file's transfer, and what it found when it's done.


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
const storeLabel = s => STORE_NAMES[s] || storeName(s);   // a store's id ("booth") or its folder ("Itch"), as people know it
/* ---------- What's new: Hoard's changelog, in the app. Betas are left out unless you tick them (ticked to begin
   with when you get beta updates). The changelog's HTML is made from CHANGELOG.md with everything escaped first. */

/* ---------- closing Hoard while it's working: stop it first, carry on in the background, or close at once */
/* ---------- the download panels beside the details (issue #85): the page's styles place them by these */


/* ---------- offline notice: everything here works offline except the store links and refreshing */
const showConnection = () => { $("#offline").hidden = navigator.onLine; };







   // the tour, carried on from the Library,
// or choosing products for a project there (Projects' Add Assets)
  return {
    get grid() { return grid; },
    get detail() { return detail; },
    get state() { return state; },
    get DATA() { return DATA; }, set DATA(value) { DATA = value; },
    get byId() { return byId; }, set byId(value) { byId = value; },
    get openId() { return openId; }, set openId(value) { openId = value; },
    get lastFocus() { return lastFocus; }, set lastFocus(value) { lastFocus = value; },
    get storeName() { return storeName; },
    get isLocal() { return isLocal; },
    get fileUrl() { return fileUrl; },
    get fmtSize() { return fmtSize; },
    get placeholder() { return placeholder; },
    get art() { return art; },
    get refreshView() { return refreshView; },
    get matches() { return matches; },
    get storeRank() { return storeRank; },
    get SORTS() { return SORTS; },
    get countBy() { return countBy; },
    get filtersActive() { return filtersActive; },
    get render() { return render; },
    get VIEWS() { return VIEWS; },
    get viewOf() { return viewOf; },
    get hasUpdate() { return hasUpdate; },
    get inView() { return inView; },
    get renderViews() { return renderViews; },
    get STORE_IDS() { return STORE_IDS; },
    get storeId() { return storeId; },
    get canDownload() { return canDownload; },
    get whenChecked() { return whenChecked; },
    get updatesBar() { return updatesBar; },
    get previousSection() { return previousSection; },
    get restorePrevious() { return restorePrevious; },
    get needsSection() { return needsSection; },
    get updateSection() { return updateSection; },
    get updateItems() { return updateItems; },
    get checkUpdates() { return checkUpdates; },
    get SPACE() { return SPACE; }, set SPACE(value) { SPACE = value; },
    get takesSpace() { return takesSpace; },
    get copiesOf() { return copiesOf; },
    get inSpace() { return inSpace; },
    get dupeKeep() { return dupeKeep; },
    get dupeGroups() { return dupeGroups; },
    get dupeIds() { return dupeIds; },
    get dupeRemovals() { return dupeRemovals; },
    get dupesPanel() { return dupesPanel; },
    get dupeGoText() { return dupeGoText; },
    get removeDupes() { return removeDupes; },
    get loadSpace() { return loadSpace; },
    get mapSpace() { return mapSpace; },
    get spaceBar() { return spaceBar; },
    get spaceSection() { return spaceSection; },
    get showView() { return showView; },
    get hiddenLocked() { return hiddenLocked; },
    get pinResolve() { return pinResolve; }, set pinResolve(value) { pinResolve = value; },
    get unlockDialog() { return unlockDialog; },
    get pinDone() { return pinDone; },
    get pinSubmit() { return pinSubmit; },
    get stackSize() { return stackSize; }, set stackSize(value) { stackSize = value; },
    get stacked() { return stacked; },
    get stackMembers() { return stackMembers; }, set stackMembers(value) { stackMembers = value; },
    get otherCopies() { return otherCopies; },
    get slotHTML() { return slotHTML; },
    get renderGrid() { return renderGrid; },
    get renderFacets() { return renderFacets; },
    get renderIntegrity() { return renderIntegrity; },
    get CHECK() { return CHECK; },
    get openCheck() { return openCheck; },
    get drawCheck() { return drawCheck; },
    get resolveCheck() { return resolveCheck; },
    get checkDownloads() { return checkDownloads; },
    get renderStatus() { return renderStatus; },
    get syncControls() { return syncControls; },
    get showDetail() { return showDetail; },
    get closeDetail() { return closeDetail; },
    get reveal() { return reveal; },
    get copyPath() { return copyPath; },
    get canLookInside() { return canLookInside; },
    get INSIDE() { return INSIDE; }, set INSIDE(value) { INSIDE = value; },
    get openInside() { return openInside; },
    get lookInside() { return lookInside; },
    get insideTree() { return insideTree; },
    get previewImg() { return previewImg; },
    get insideFolder() { return insideFolder; },
    get insidePackage() { return insidePackage; },
    get insideFound() { return insideFound; },
    get CODE_KINDS() { return CODE_KINDS; },
    get CODE_SAYS() { return CODE_SAYS; },
    get codeTag() { return codeTag; },
    get codeWords() { return codeWords; },
    get insideCode() { return insideCode; },
    get drawInside() { return drawInside; },
    get pickedUnder() { return pickedUnder; },
    get pickBox() { return pickBox; },
    get insideBar() { return insideBar; },
    get pickChanged() { return pickChanged; },
    get extractInside() { return extractInside; },
    get fillPackage() { return fillPackage; },
    get wireInside() { return wireInside; },
    get saveHash() { return saveHash; },
    get readHash() { return readHash; },
    get qTimer() { return qTimer; }, set qTimer(value) { qTimer = value; },
    get bulkMove() { return bulkMove; },
    get bulkArchive() { return bulkArchive; },
    get bulkDelete() { return bulkDelete; },
    get libName() { return libName; },
    get drivesShown() { return drivesShown; }, set drivesShown(value) { drivesShown = value; },
    get renderDrives() { return renderDrives; },
    get downloadNew() { return downloadNew; },
    get TILE_KEY() { return TILE_KEY; },
    get toggle() { return toggle; },
    get localSection() { return localSection; },
    get localAction() { return localAction; },
    get openLocal() { return openLocal; },
    get previewFor() { return previewFor; }, set previewFor(value) { previewFor = value; },
    get previewLocal() { return previewLocal; },
    get addLocal() { return addLocal; },
    get wireLocal() { return wireLocal; },
    get editableCopy() { return editableCopy; },
    get libLabel() { return libLabel; },
    get librarySection() { return librarySection; },
    get moveProduct() { return moveProduct; },
    get deleteFiles() { return deleteFiles; },
    get T() { return T; },
    get storeLabel() { return storeLabel; },
    get showConnection() { return showConnection; },
    // Install this view's handlers once; viewListen routes events without duplicating shell handlers.
    wire() {
viewListen("downloads", $("#viewBar"), "click", e => {
  const b = e.target.closest("[data-upd]"); if (!b) return;
  if (b.dataset.upd === "check") { checkUpdates(null); return; }
  const list = DATA.assets.filter(inView).filter(a => canDownload(a));   // issue #107: to untick, first
  pickDownloads("Update", "Update", list.map(a => ({ key: a.tag_key, store: storeId(a), name: a.name, creator: a.creator,
                                                     files: (a.update || []).length, names: (a.update || []).map(f => f.file) })),
                keys => updateItems(keys ? list.filter(a => keys.includes(a.tag_key)) : list));
});
viewListen("downloads", $("#viewBar"), "change", e => {   // Duplicates: which copy each keeps
  const r = e.target.closest("input[data-stack]"); if (!r) return;
  if (r.value === "") dupeKeep.delete(r.dataset.stack); else dupeKeep.set(r.dataset.stack, +r.value);
  const going = dupeRemovals(), go = $("[data-dupe='go']");   // (just the button: the list keeps its place)
  go.innerHTML = dupeGoText(going, going.reduce((t, a) => t + a.size, 0));
  go.disabled = !going.length;
});
viewListen("downloads", $("#viewBar"), "click", e => {
  const d = e.target.closest("[data-dupe]");
  if (d && d.dataset.dupe === "apply") {   // the chosen store's copy, in every one that has one
    const st = $("#dupeStore").value;
    for (const g of dupeGroups()) { const a = g.find(x => x.store === st); if (a) dupeKeep.set(g[0].stack_key, a.id); }
    render();
  } else if (d && d.dataset.dupe === "none") { dupeKeep.clear(); render(); }
  else if (d && d.dataset.dupe === "go") removeDupes();
  const b = e.target.closest("[data-space]"); if (!b) return;
  state.space = state.space === b.dataset.space ? "" : b.dataset.space; sel.ids.clear(); render();
});
viewListen("downloads", $("#viewBar"), "click", async e => {
  if (!e.target.closest('[data-privacy="lock"]')) return;
  const open = openId != null && byId.get(openId);
  if (open && open.mark === "hidden") closeDetail();   // straight away, before the server answers
  await apiPost("/api/lock"); state.view = "downloads"; sel.ids.clear(); await load(); toast("Hidden items locked.");
});
viewListen("downloads", $("#pinOk"), "click", pinSubmit);
viewListen("downloads", $("#pinCancel"), "click", () => pinDone(false));
viewListen("downloads", $("#pinDialog"), "cancel", e => { e.preventDefault(); pinDone(false); });
viewListen("downloads", $("#pinDialog"), "keydown", e => { if (e.key === "Enter") { e.preventDefault(); pinSubmit(); } });
viewListen("downloads", $("#pinForgot"), "click", () => {
  $("#pinNote").textContent = "Reset it in the Library: choose Hidden there, then Forgot your PIN?";
});
viewListen("downloads", $("#views"), "click", e => { const b = e.target.closest("[data-view]"); if (b) showView(b.dataset.view); });
viewListen("downloads", document, "click", e => {
  if (e.target.closest("[data-check-open]")) { openCheck(); return; }
  if (e.target.closest("[data-check-close]")) { $("#checkDialog").close(); return; }
  const one = e.target.closest("[data-check]"), all = e.target.closest("[data-check-all]");
  if (one) resolveCheck(one.dataset.check, [CHECK.list[+one.dataset.i]]);
  else if (all) resolveCheck(all.dataset.checkAll, all.dataset.checkAll === "keep" ? CHECK.list.filter(x => x.kind === "changed") : CHECK.list);
});
viewListen("downloads", document, "click", e => { if (e.target.closest("#checkNow, [data-checknow]")) checkDownloads(); });
viewListen("downloads", $("#q"), "input", e => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value; render(); }, 90); });
viewListen("downloads", $("#storeSeg"), "click", e => {
  const d = e.target.closest("[data-lib]");   // a library folder's tab: chosen again, it goes back to every folder
  if (d) { state.lib = state.lib === d.dataset.lib ? "" : d.dataset.lib; render(); return; }
  const b = e.target.closest("[data-store]");
  if (b) { state.store = b.dataset.store; state.set = ""; if (!b.dataset.store) state.lib = ""; render(); }   // (Sets: every set)
});
viewListen("downloads", $("#sort"), "change", e => { state.sort = e.target.value; if (state.view !== "space") uiSave({ sort: state.sort }); render(); });
viewListen("downloads", $("#creatorFind"), "input", e => { state.creatorFind = e.target.value; render(); });
viewListen("downloads", $("#moreTags"), "click", () => { state.allTags = !state.allTags; render(); });
viewListen("downloads", $("#downloadNew"), "click", () => downloadNew(Object.keys(STORE_NAMES)));
viewListen("downloads", $("#rescan"), "click", async () => {
  const n = await load(true);
  toast(DATA.error ? DATA.error : tr(n === 1 ? "Rescanned 1 asset" : "Rescanned {0} assets", n));   // not "Rescanned 0" when it couldn't be
});
viewListen("downloads", $("#filtersToggle"), "click", e => {
  const open = $("#filters").classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(open));
});
viewListen("downloads", zoom, "input", () => { setZoom(zoom.value); try { localStorage.setItem("hoard-dl-tile-size", zoom.value); } catch (e) {} });
viewListen("downloads", zoom, "change", () => uiSave({ dl_tile_size: Number(zoom.value) }));
try { const z = localStorage.getItem("hoard-dl-tile-size"); if (z) setZoom(z); } catch (e) {}
viewListen("downloads", $("#filters"), "click", e => {
  const t = e.target.closest("[data-tag]"), ty = e.target.closest("[data-type]"), c = e.target.closest("[data-creator]");
  if (t) toggle(state.tags, t.dataset.tag);
  else if (ty) toggle(state.types, ty.dataset.type);
  else if (c) state.creator = state.creator === c.dataset.creator ? "" : c.dataset.creator;
  else return;
  render();
});
viewListen("downloads", document, "click", e => {
  const b = e.target.closest("[data-clear]"); if (!b) return;
  const k = b.dataset.clear, v = b.dataset.v;
  if (k === "all") { state.q = ""; state.store = ""; state.lib = ""; state.creator = ""; state.tags.clear(); state.types.clear(); state.set = ""; state.ptype = ""; }
  else if (k === "q") state.q = ""; else if (k === "lib") state.lib = ""; else if (k === "store") state.store = ""; else if (k === "creator") state.creator = "";
  else if (k === "tag") state.tags.delete(v); else if (k === "type") state.types.delete(v);
  else if (k === "ptype") state.ptype = "";
  render();
});
viewListen("downloads", grid, "click", e => {
  const s = e.target.closest(".slot"); if (!s) return;
  if (selectClick(e, s)) return;
  lastFocus = s; showDetail(byId.get(+s.dataset.id));
});
viewListen("downloads", grid, "error", e => {  // thumbnail missing or unreadable: fall back to the placeholder
  if (e.target.tagName !== "IMG") return;
  const a = byId.get(+e.target.closest(".slot").dataset.id);
  e.target.outerHTML = placeholder(a);
}, true);
viewListen("downloads", window, "hashchange", () => {   // the Local tab, from the bar or the Library; a download, from Projects
  const was = openId;
  readHash(); render();
  if (openId != null && openId !== was && byId.has(openId)) showDetail(byId.get(openId), true);
});
viewListen("downloads", detail, "click", e => {
  const b = e.target.closest("[data-act]"); if (!b) return;
  const act = b.dataset.act;
  if (tagDetailAction(act, b, byId.get(openId))) return;
  if (act === "close") closeDetail();
  else if (act === "open") reveal(b.dataset.path);
  else if (act === "inside") lookInside(b.dataset.path);
  else if (act === "restore") restorePrevious(byId.get(openId), b);
  else if (act === "unset") changeSets({ action: "remove", id: b.dataset.set, items: [byId.get(openId).tag_key] });
  else if (act === "toset") addToSet([byId.get(openId)], $("#setPick").value);
  else if (act === "showset") showSet(b.dataset.set);
  else if (act === "copy") copyPath();
  else if (act === "goto") showDetail(byId.get(+b.dataset.id));
  else if (act === "update-one" || act === "more") {   // which of its files, asked first (issue #225)
    const a = byId.get(openId), more = act === "more";
    askFiles({ key: a.tag_key, store: storeId(a), name: a.name, creator: a.creator, more,
               names: more ? null : (a.update || []).map(f => f.file) },
             files => { DL_FILES = files; updateItems([a]); });
  }
  else if (act === "check-one") checkUpdates([byId.get(openId)]);
  else if (act === "delete-files") deleteFiles(byId.get(openId));
  else if (act === "edit-copy") editableCopy(byId.get(openId), b);
  else if (act === "move") moveProduct(byId.get(openId), b);
  else if (act === "projects") openProjects(true);
  else if (act.startsWith("local-")) localAction(act, byId.get(openId));
  else if (act === "tag") { toggle(state.tags, b.dataset.tag); b.setAttribute("aria-pressed", String(state.tags.has(b.dataset.tag))); render(); }
});
viewListen("downloads", $("#scrim"), "click", closeDetail);
viewListen("downloads", document, "keydown", e => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); $("#q").focus(); $("#q").select(); }
  else if (e.key === "Escape") {
    if (document.querySelector("dialog[open]")) return;   // a dialog closes itself
    if (closeTopWindow()) return;
    else if (selecting()) clearSelection();
    else if (openId != null) closeDetail();
    else if (document.activeElement === $("#q")) { state.q = ""; render(); }
  }
});
viewListen("downloads", $("#stackCopies"), "click", e => {
  const on = e.currentTarget.getAttribute("aria-pressed") !== "true";
  e.currentTarget.setAttribute("aria-pressed", String(on));
  uiSave({ stack: on }); render();
});
viewListen("downloads", window, "online", showConnection);
viewListen("downloads", window, "offline", showConnection);
    },
  };
}
