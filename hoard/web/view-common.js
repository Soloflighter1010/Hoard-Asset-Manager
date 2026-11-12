// Shell helpers formerly duplicated by the two pages; all product calls share this implementation.
// Shared ago: one implementation for both Library and Downloads.
function ago(iso) {
  if (!iso) return tr("never");
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 90) return tr("just now");
  const [n, u] = s < 3600 ? [s / 60, "minute"] : s < 86400 ? [s / 3600, "hour"] : [s / 86400, "day"];
  const r = Math.round(n); return tr(`{0} ${u}${r === 1 ? "" : "s"} ago`, r);
}

// Shared toast: one implementation for both Library and Downloads.
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer);   // long enough to read: a longer message stays longer
  toastTimer = setTimeout(() => t.classList.remove("show"), Math.min(10000, Math.max(2600, String(msg).length * 60)));
}

// Shared post: one implementation for both Library and Downloads.
async function post(url, body) {
  const r = await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `The library server answered ${r.status}.`);
  return j;
}

// Shared setZoom: one implementation for both Library and Downloads.
function setZoom(v) { document.documentElement.style.setProperty("--slot-size", v + "px"); zoom.value = v; }

// Shared tagPanelAction: one implementation for both Library and Downloads.
async function tagPanelAction(b) {
  const t = b.dataset.tag, act = b.dataset.tact;
  if (act === "keep") return changeTags({ action: "keep", name: t }, `#${t} is now yours, on every item whose name has “${t}”.`);
  if (act === "hide") return changeTags({ action: "hide", name: t }, `#${t} won't be suggested again.`);
  if (act === "unhide") return changeTags({ action: "unhide", name: t });
  if (act === "delete") {
    const n = +b.dataset.count;
    if (!await ask(tr("Delete #{0}?", t) + (n ? " " + tr(n === 1 ? "It comes off 1 item." : "It comes off {0} items.", n) : ""), "Delete", true)) return;
    const filtered = state.tags.delete(t);
    const ok = await changeTags({ action: "delete", name: t }, `Deleted #${t}.`);
    if (!ok && filtered) { state.tags.add(t); render(); }   // not deleted: still filtered by it
    return ok;
  }
  if (act === "rename") {
    const to = prompt(tr("Rename #{0} to (an existing tag's name merges the two):", t), t);
    if (!to || !to.trim() || to.trim().toLowerCase() === t) return;
    const filtered = state.tags.delete(t);
    const ok = await changeTags({ action: "rename", name: t, to }, `Renamed #${t}.`);
    if (filtered) { state.tags.add(ok ? to.trim().toLowerCase() : t); render(); }   // not renamed: still filtered by it
    return;
  }
  if (act === "match") {
    const word = prompt(tr("Also tag every item whose name contains this word, including ones you buy later. Leave it empty to stop."), b.dataset.match || t);
    if (word !== null) return changeTags({ action: "match", name: t, match: word });
  }
}

// Shared wireTags: one implementation for both Library and Downloads.
function wireTags() {
  $("#tagsBtn").addEventListener("click", () => openTagPanel());
  $("#manageTags").addEventListener("click", () => openTagPanel(true));
  $("#tagPanel").addEventListener("click", e => { const b = e.target.closest("[data-tact]"); if (b) tagPanelAction(b); });
  $("#tagPanel").addEventListener("change", e => {   // what a tag is about (issue #157)
    const s = e.target.closest("[data-ttype]");
    if (s) changeTags({ action: "type", name: s.dataset.ttype, type: s.value || null }, s.value ? tr("{0} is now about: {1}.", "#" + s.dataset.ttype, tr(TAG_TYPES[s.value])) : "");
  });
  $("#newTagBtn").addEventListener("click", createTag);
  $("#newTag").addEventListener("keydown", e => { if (e.key === "Enter") createTag(); });
  wireSelection();
  wireBar();
  wireSearch();
  wireTypes();
  wireFiles();
  document.addEventListener("keydown", e => {
    if (e.key === "Enter" && e.target && e.target.id === "tagInput") { const a = T.open(); if (a) addTyped(a); }
  });
}

// Shared apiPost: one implementation for both Library and Downloads.
async function apiPost(url, body) {
  try {
    const r = await api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
  } catch (e) {
    return { ok: false, status: 0, data: { error: "Hoard isn't running. Open it again." } };
  }
}

// Shared wireSupportReport: one implementation for both Library and Downloads.
function wireSupportReport() {
  for (const el of document.querySelectorAll("#reportProblem, [data-report-problem]"))   // (the bar's, or the Menu's)
    el.addEventListener("click", e => { e.preventDefault(); openSupportReport({ source: "bar" }); });
  const settings = $("#makeSupportReport");
  if (settings) settings.addEventListener("click", () => openSupportReport({ source: "settings" }));
  const storeRows = $("#storeRows");
  if (storeRows) storeRows.addEventListener("click", e => {
    const b = e.target.closest("[data-report-store]");
    if (!b) return;
    const store = b.dataset.reportStore || "";
    const info = DATA.stores && DATA.stores[store] || {};
    openSupportReport({ source: "store", store, error: info.error || "" });
  });
  const dlReport = $("#dlReport");
  if (dlReport) dlReport.addEventListener("click", () => openSupportReport({ source: "job", store: (DATA.job && DATA.job.store) || "" }));
  $("#supportCreate").addEventListener("click", createSupportReport);
  $("#supportClose").addEventListener("click", closeSupportReport);
  $("#supportOpenFolder").addEventListener("click", openSupportFolder);
  $("#supportCopyPath").addEventListener("click", copySupportPath);
  const d = $("#supportDialog");
  if (d) d.addEventListener("click", e => { if (e.target === d) closeSupportReport(); });
}

// Shared describeUpdate: one implementation for both Library and Downloads.
function describeUpdate(u) {
  if (u.error) return u.error;
  if (u.busy) return u.message || tr("Getting the update");
  if (u.available) return tr("Hoard {0} is available (you have {1}).", verText(u.latest.version), verText(u.current)) +
    (u.can_install ? "" : " " + (u.how ? tr(u.how) : tr("Download it from the releases page, and install it over this one.")));
  if (u.checked) return tr("Hoard {0} is the newest version.", verText(u.current)) + " " + tr("Last checked {0}.", ago(new Date(u.checked * 1000).toISOString()));
  return tr("You have Hoard {0}.", verText(u.current));
}

// Shared startDownload: one implementation for both Library and Downloads.
async function startDownload(stores, only, item, keys) {   // item: the library item, so the download goes straight to it
  const files = takeFiles();   // the files chosen of each product, if some were left out (taken first: never kept for later)
  if (!navigator.onLine) { toast("You're offline. Downloading needs a connection."); return; }
  const r = await apiPost("/api/download", { ...(keys ? { stores, keys } : item ? { stores, only, item } : { stores, only }),
                                             ...(files ? { files } : {}) });
  if (!r.ok) { toast(r.data.error || "Downloading didn't start."); return; }
  if (queuedToast(r)) return;
  dlActive = true;
  showDownload({ running: true, message: "Starting", log: [] });
  pollDownload();
}

// Shared pollDownload: one implementation for both Library and Downloads.
async function pollDownload() {
  clearTimeout(dlTimer);
  let job;
  try {
    job = (await (await api("/api/status", { cache: "no-store" })).json()).job || {};
  } catch (e) {
    if (dlActive) dlTimer = setTimeout(pollDownload, 2000);
    return;
  }
  const running = job.running && (job.task === "download" || job.task === "check-updates" || job.sync);   // a sync counts, refreshing included
  if (running || dlActive) showDownload({ ...job, running });
  if (running) { dlActive = true; dlTimer = setTimeout(pollDownload, 1000); }
  else if (dlActive) { dlActive = false; T.reload(); }
}

// Shared showDownload: one implementation for both Library and Downloads.
function showDownload(job) {
  $("#dlPanel").hidden = false;
  const stopped = /^Stopped/.test(job.message || "");
  $("#dlTitle").textContent = job.running ? (job.sync && job.task !== "download" ? "Syncing: reading your stores" : job.sync ? "Syncing: downloading" : "Downloading")
    : stopped ? "Stopped" : job.error ? "Couldn't finish" : job.partial ? "Finished, with problems" : "Finished";
  const xfer = job.running ? job.transfer : null;   // a file downloading: its bar says it all
  $("#dlMessage").textContent = xfer ? "" : job.message || "";
  $("#dlMessage").hidden = !!xfer;
  showTransfer($("#dlXfer"), xfer);
  $("#dlLog").textContent = (job.log || []).join("\n");
  $("#dlStop").hidden = !job.running;
  $("#dlClose").hidden = !!job.running;
  const problems = (!job.running && job.report && job.report.problems) || [];
  $("#dlProblems").hidden = !problems.length;
  $("#dlProblems").innerHTML = problems.map(p => `<li>${esc(p)}</li>`).join("");
  // Finished, and all went well: it steps out of the way after a moment (Tasks keeps it), unless you're using it
  clearTimeout(dlFade);
  if (!job.running && !stopped && !job.error && !job.partial && !problems.length)
    dlFade = setTimeout(function fade() {
      const p = $("#dlPanel");
      if (p.matches(":hover, :focus-within")) dlFade = setTimeout(fade, 2000); else p.hidden = true;
    }, 8000);
  if ($("#dlReport")) { $("#dlReport").hidden = !!job.running || !(job.error || problems.length); }
}

// Shared wireApp: one implementation for both Library and Downloads.
function wireApp() {
  $("#syncBtn").addEventListener("click", confirmSync);
  $("#settingsBtn").addEventListener("click", () => openSettings());
  wireSupportReport();
  wireBackup();
  wireLocal();
  wireInside();
  for (const id of ["tagPanel", "stores", "settingsPanel"]) makeWindow($("#" + id));
  wireAutosave();
  wireLibs();
  wireSidebar();
  wireDock();
  wireTasks();
  wireNews();
  wireProjects();
  wireSets();
  wireClose();
  $("#updCheck").addEventListener("click", checkUpdate);
  $("#updInstall").addEventListener("click", installUpdate);
  for (const b of document.querySelectorAll("#updateNote, [data-update-note]")) b.addEventListener("click", () => openSettings(true));
  $("#setupAgain").addEventListener("click", () => {
    if (typeof openSetup === "function") openSetup(); else location.href = "/#setup";
  });
  $("#dlStop").addEventListener("click", async () => {
    const r = await apiPost("/api/cancel");
    if (r.ok) $("#dlMessage").textContent = "Stopping";
  });
  $("#dlClose").addEventListener("click", () => { $("#dlPanel").hidden = true; });
  pollDownload();  // a download started from the other view, or before this page opened
  // Every open page checks in once a minute: when Hoard runs in the browser, it stops once none has for a while.
  // It also brings up a sync another page started.
  setInterval(async () => {
    try {
      const job = (await (await api("/api/status", { cache: "no-store" })).json()).job || {};
      if (job.running && job.sync && !dlActive) pollDownload();
    } catch (e) { /* not running: the next check-in says so */ }
  }, 60000);
  $("#quitHoard").addEventListener("click", async () => {
    const r = await apiPost("/api/quit");
    if (!r.ok && r.data.busy) { askClose(); return; }   // it's working: stop it first, or close now
    if (!r.ok) { toast(r.data.error || "Hoard didn't quit."); return; }
    document.body.innerHTML = '<p style="font: 600 18px sans-serif; color: #c9b9a4; text-align: center; margin-top: 30vh">Hoard has stopped. You can close this tab.</p>';
  });
}

// Shared applyUi: one implementation for both Library and Downloads.
function applyUi(ui) {   // once, when the page first has its data
  if (uiApplied || !ui) return;
  uiApplied = true;
  seasonLabel();   // (which season the Seasonal sort puts first: shared.js)
  UI = { windows: {}, sections: {}, ...ui };
  for (const [name, open] of Object.entries(UI.sections || {})) if (SECTIONS[name]) SECTIONS[name](open, false);
  if (setSideFold && typeof UI.side_folded === "boolean") setSideFold(UI.side_folded, false);
  const tile = UI[APP.active === "downloads" ? "dl_tile_size" : "tile_size"];   // each page has its own
  if (tile && typeof setZoom === "function") setZoom(tile);
  if (typeof applyStack === "function") applyStack(UI.stack);   // the Library draws itself next
  state.sort = sortFrom(new URLSearchParams(location.hash.slice(1)).get("sort"), SORTS);   // the sort last chosen
}

// Shared watchJobs: one implementation for both Library and Downloads.
async function watchJobs() {
  try {
    const r = await api("/api/status", { cache: "no-store" });
    if (r.ok) {
      const st = await r.json(), j = st.job || {};
      showRoutine(st.routine);
      if (["verify", "add-local", "move", "rescan-local", "remove-local", "delete-files"].includes(lastTask) && j.task !== lastTask && typeof renderIntegrity === "function") load(true);
      jobEnded(lastTask, j);
      lastTask = j.running ? j.task : null;
      taskCount(jobCount(st));
      const pill = $("#job");   // what's running, on the shelf
      if (pill) { pill.hidden = !(j.running && j.message); pill.textContent = j.message || ""; }
      if (j.running && (j.sync || j.task === "download" || j.task === "check-updates") && !dlActive) pollDownload();
    }
  } catch (e) { /* not running */ }
  setTimeout(watchJobs, 4000);
}

// Keep the shared bar measurements in sync with its window.
new ResizeObserver(([e]) => document.documentElement.style.setProperty("--bar-h", e.target.offsetHeight + "px")).observe($(".bar"));

// Keep the shared bar measurements in sync with its window.
new ResizeObserver(([e]) => document.documentElement.style.setProperty("--shelf-h", e.target.offsetHeight + "px")).observe($(".shelf"));

// Keep the shared bar measurements in sync with its window.
{   // tabs out of sight (a very narrow window) fade at the edge they're beyond, so it shows there are more
  const seg = $(".shelf .seg");
  // Fade the tabs' edges where there are more tabs beyond them.
  const edges = () => {
    seg.classList.toggle("more-left", seg.scrollLeft > 2);
    seg.classList.toggle("more-right", seg.scrollLeft + seg.clientWidth < seg.scrollWidth - 2);
  };
  shellListen(seg, "scroll", edges, { passive: true });
  new ResizeObserver(edges).observe(seg);
  new MutationObserver(edges).observe(seg, { childList: true });
  shellListen(seg, "focusin", e => e.target.scrollIntoView({ block: "nearest", inline: "nearest" }));
}
