// Shared product components. Names, notes and paths enter the DOM as text; only the older sections still
// cross legacyFragment while they are migrated. Both views supply data, never a second tile/detail template.

// Create an element with text or node children. Attribute names are literals supplied by Hoard, never user data.
function productElement(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) if (value != null && value !== false) node.setAttribute(name, String(value));
  node.append(...children.filter(child => child != null && child !== false));
  return node;
}
// Fixed line icons used by the note and downloaded indicators.
function productIcon(path) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [name, value] of Object.entries({ viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", "stroke-width": "1.7", "stroke-linecap": "round", "stroke-linejoin": "round" })) svg.setAttribute(name, value);
  const line = document.createElementNS(svg.namespaceURI, "path");
  line.setAttribute("d", path); svg.append(line);
  return svg;
}
// The 18+ mark on an adult product's or set's picture (issue #338).
function adultMark() {
  return productElement("span", { class: "adult-mark", title: tr("For adults (18+)"), "aria-hidden": "true", translate: "no" }, "18+");
}
// What's wrong with a product (issue #334: the server's "problems"), in a few words each: for its tile's error mark,
// what it says on hover, and its spoken label.
function problemWords(list) {
  return (list || []).map(p => p.kind === "folder" ? tr("Its folder isn't there any more")
    : p.kind === "away" ? tr("Its drive isn't connected")
    : p.kind === "missing" ? tr(p.n === 1 ? "1 file is missing on disk" : "{0} files are missing on disk", p.n)
    : p.kind === "changed" ? tr(p.n === 1 ? "1 file was changed after it was downloaded" : "{0} files were changed after they were downloaded", p.n)
    : p.kind === "failed" ? tr("Its last download didn't finish") : "").filter(Boolean);
}
// ...and in its details, with what to do about it.
function problemAdvice(p) {
  return p.kind === "folder" ? tr("Its folder isn't there any more. If you moved it, take it out of Local and add it again from where it is now.")
    : p.kind === "away" ? tr("Its folder is on a drive or network share that isn't connected now, so Hoard isn't reading it. Connect it, and it's shown as before.")
    : p.kind === "missing" ? tr(p.n === 1 ? "1 file is missing on disk. Download it again, or deal with it in Check downloads."
                                          : "{0} files are missing on disk. Download it again, or deal with them in Check downloads.", p.n)
    : p.kind === "changed" ? tr(p.n === 1 ? "1 file was changed after it was downloaded, by you or by another program. In Check downloads, choose Keep it as it is, or Download again for the original."
                                          : "{0} files were changed after they were downloaded, by you or by another program. In Check downloads, choose Keep it as it is, or Download again for the originals.", p.n)
    : tr("Its last download didn't finish ({0}). Download it again.", p.why || tr("no reason given"));
}
// The mark on a product's tile for what's wrong with it: a red one for an error, and a blue one with a pencil when all
// that's different is a file changed after it was downloaded, which is often your own edit (issue #400).
function problemMark(words, changed = false) {
  return productElement("span", { class: `problem-mark${changed ? " change-mark" : ""}`, title: words.join(". ") + ".", "aria-hidden": "true" },
    productIcon(changed ? "M10.6 2.8 13.2 5.4 6 12.6 2.8 13.2 3.4 10zM9.2 4.2 11.8 6.8" : "M8 2.2 14.3 13.3H1.7zM8 6.4v3.4M8 11.6v.1"));
}
// Whether everything wrong with a product is a changed file (its mark is the change mark, not the error's).
const onlyChanged = list => !!(list && list.length) && list.every(p => p.kind === "changed");
// Who says a product is for adults, in words: you, its store, or its tags and name.
const ADULT_SAYS = { you: "For adults: you marked it.", store: "For adults: its store says so.", tags: "For adults: its tags or name say so." };
// The only bridge for existing escaped HTML sections. Do not pass raw product data or new templates here.
function legacyFragment(html) {
  const template = document.createElement("template");
  template.innerHTML = html;
  return template.content;
}
// A product's safe local picture, falling back to its initials without interpreting its name as markup.
// Pictures that have loaded, by address, kept to be put back when the grid is drawn again (issue #406): a new <img>
// for each redraw went blank until it was decoded again, so every refresh flickered. At most PICS_KEPT of them.
const PICS = new Map(), PICS_KEPT = 300;   // (a store's picture can be large: about two batches of tiles)
// The waits before a picture that didn't load is asked for again (Hoard fetches each from its store the first time,
// and a store can be slow or say no for a moment): its placeholder shows meanwhile, and the picture once it comes.
const PIC_RETRIES = [1500, 6000];
// A picture that has loaded, kept by its address (the newest last; the oldest let go past PICS_KEPT).
function keepPicture(src, img) {
  PICS.delete(src); PICS.set(src, img);
  if (PICS.size > PICS_KEPT) PICS.delete(PICS.keys().next().value);
}
// A product's picture: the one already drawn when it has loaded before (kept, so nothing flickers), else a new one
// that asks again if it doesn't load (retryPicture); its placeholder (its initials, in its creator's colour) without one.
function productPicture(a, src, type = "", lazy = true) {
  if (src) {
    const kept = PICS.get(src);
    if (kept && !kept.isConnected && kept.complete && kept.naturalWidth && !PAUSE) { keepPicture(src, kept); return kept; }
    const img = productElement("img", { src, alt: "", class: "loading", "data-pic": "", decoding: kept ? "sync" : "async", loading: lazy && !kept ? "lazy" : null });
    img.style.setProperty("--h", hue(a.creator));
    img.addEventListener("load", () => { img.classList.remove("loading"); keepPicture(src, img); }, { once: true });
    img.addEventListener("error", () => retryPicture(a, src, type, img, 0), { once: true });
    return img;
  }
  const node = productElement("span", { class: "ph" }, productElement("b", {}, initials(a.name)));
  node.style.setProperty("--h", hue(a.creator));
  if (type) node.append(productElement("small", {}, "." + type));
  return node;
}
// A picture that didn't load: its placeholder in its place, and the picture asked for again a little later, put in
// when it comes (while the placeholder is still showing). After the last try, the placeholder stays.
function retryPicture(a, src, type, img, n) {
  const ph = img.classList.contains("ph") ? img : productPicture(a, "", type);
  if (ph !== img && img.isConnected) img.replaceWith(ph);
  if (n >= PIC_RETRIES.length) return;
  setTimeout(() => {
    if (!ph.isConnected) return;   // (drawn again since: the new tile asks for it itself)
    const again = productElement("img", { src: src + (src.includes("?") ? "&" : "?") + "again=" + (n + 1), alt: "", "data-pic": "", decoding: "async" });
    again.addEventListener("load", () => { keepPicture(src, again); if (ph.isConnected) ph.replaceWith(again); }, { once: true });
    again.addEventListener("error", () => retryPicture(a, src, type, ph, n + 1), { once: true });
  }, PIC_RETRIES[n]);
}
// Store colours and accessible names on the spine of a tile, including copies bought elsewhere.
function productNotch(store, others = []) {
  const other = others.find(key => STRIPE_STORES.includes(key) && key !== store);
  const node = productElement("i", { class: `notch ${store}${other ? " dup" : ""}` });
  if (COLOUR_NAMES[store]) node.dataset.s = tr(COLOUR_NAMES[store]);
  node.dataset.all = [...new Set([store, ...others])].filter(key => COLOUR_NAMES[key]).map(key => tr(COLOUR_NAMES[key])).join(" · ");
  if (other) node.style.setProperty("--c2", `var(--${other})`);
  return node;
}
// One tile for both views. The view model owns the differences in badges, file sizes and available actions.
function productTile(a, model) {
  // (for adults, issues #311 and #338: said in its label, marked 18+, and its picture blurred unless you chose to see them)
  const wrong = problemWords(a.problems);   // (issue #334: an error mark, and said in its label)
  const button = productElement("button", { draggable: "true", class: `slot ${model.store}${model.count > 1 ? " stacked" : ""}${model.wrapped ? " wrapped" : ""}${a.adult ? " adult" : ""}${wrong.length ? " has-problem" : ""}`,
    "aria-label": [...model.description, a.adult && tr("for adults (18+)"), ...wrong].filter(Boolean).join(", "), "aria-current": model.current ? "true" : null });
  button.dataset[model.key] = model.id;
  const art = productElement("span", { class: "art" }, productPicture(a, model.src, model.type),
    productNotch(model.store, model.others), productElement("i", { class: "tick", "aria-hidden": "true" }));
  if (a.adult) art.append(adultMark());
  if (wrong.length) art.append(problemMark(wrong, onlyChanged(a.problems)));
  if (a.your_note) art.append(productElement("span", { class: "note-mark", title: tr("Has a note"), "aria-hidden": "true" },
    productIcon("M3.5 2.5h6.2l2.8 2.8v8.2h-9zM6 7.5h4M6 10h4")));
  if (model.downloaded) art.append(productElement("span", { class: "ondisk-mark", title: tr("Downloaded"), "aria-hidden": "true" },
    productIcon("M8 2v7.5M4.8 6.5 8 9.7l3.2-3.2M2.5 11v2.5h11V11")));
  // its marks (New, Update, ×2...) in one column, the same in both views (issue #418: Downloads' were in the corner the
  // selection box takes)
  const badges = productElement("span", { class: "badges" });
  for (const badge of model.badges) if (badge) badges.append(productElement("span", {
    class: `badge ${badge.kind || ""}`, "aria-hidden": badge.hidden ? "true" : null,
  }, badge.text));
  art.append(badges);
  button.append(art, productElement("span", { class: model.key === "key" ? "nm-t" : "nm", translate: "no" }, a.name),
    productElement("span", { class: "cr" }, model.size ? model.size + " · " : "", productElement("span", { translate: "no" }, a.creator)),
    productElement("span", { class: "row-meta", "aria-hidden": "true" },
      productElement("span", { class: "rm-store" }, productElement("span", { class: `dot ${model.store}` }), model.storeName),
      productElement("span", { class: `rm-state ${model.statusKind || ""}` }, model.status),
      productElement("span", { class: "rm-when" }, model.added)));
  return button;
}
// Make a change that lays the grid out again (the details opening or closing changes how many tiles fit a row), then
// scroll so this tile is where it was on screen. Before, a product's tile could end up rows away from where it was
// clicked, out of sight (issue #329).
function keepTileInPlace(tile, change) {
  const before = tile && tile.isConnected ? tile.getBoundingClientRect().top : null;
  const root = document.documentElement, anchoring = root.style.overflowAnchor;
  root.style.overflowAnchor = "none";   // (the browser's own guess at keeping the page still would be added to this)
  try {
    change();
    if (before == null || !tile.isConnected) return;
    const moved = tile.getBoundingClientRect().top - before;
    if (Math.abs(moved) > 1) window.scrollTo({ top: window.scrollY + moved, behavior: "instant" });
  } finally { requestAnimationFrame(() => { root.style.overflowAnchor = anchoring; }); }
}
// One details frame and common product fields. Older view-specific actions/files are supplied as escaped sections.
function renderProductDetail(a, model, sections, focus = true) {
  const detail = $("#detail"), by = productElement("p", { class: "d-by", translate: "no" });
  const creator = model.creatorUrl ? productElement("a", { href: model.creatorUrl, target: "_blank", rel: "noopener noreferrer" }, a.creator) : document.createTextNode(a.creator);
  // Preserve translated word order while keeping creator links as nodes.
  const sentence = tr("by {0}", "\u0001").split("\u0001");
  by.append(sentence[0], creator, sentence.slice(1).join("\u0001"), model.extra ? tr(", {0}", model.extra) : "");
  const store = productElement("p", { class: "d-store" }, productElement("span", { class: `dot ${model.store}` }), model.storeName);
  if (model.storeUrl) store.append(" ", productElement("a", { href: model.storeUrl, target: "_blank", rel: "noopener noreferrer", title: model.storeUrl }, tr("Open on {0}", model.pageName || model.storeName)));
  // Copy store link: its public page, as Hoard checked it, never the link Open on the store opens (a Gumroad purchase's is
  // its download page, which opens its files for whoever has it); none when there's no public page to copy
  const page = model.copyUrl;
  if (page) store.append(" ", productElement("button", { class: "linkish", type: "button", "data-store-link": page }, tr("Copy store link")));
  const facts = productElement("div", { class: "d-stats" });
  for (const [name, value] of model.facts) facts.append(productElement("span", {}, productElement("small", {}, tr(name)), productElement("b", {}, value)));
  // For adults (issues #311, #338): its 18+ mark and who says so; and your own word for it, which wins, and is how a
  // product of your own in Local gets the mark.
  const grown = productElement("p", { class: "d-adult" });
  if (a.adult) grown.append(productElement("span", { class: "adult-chip", translate: "no" }, "18+"), " ", tr(ADULT_SAYS[a.adult_from] || ADULT_SAYS.tags), " ");
  if (a.tag_key) grown.append(productElement("button", { class: "linkish", type: "button", "data-adult-mark": a.adult ? "not_adult" : "adult", "data-key": a.tag_key },
    tr(a.adult ? "It isn't for adults" : "Mark as 18+")));
  // what's wrong with it, and what to do (issue #334), each with its own mark (#400)
  const wrong = productElement("ul", { class: `d-problems${onlyChanged(a.problems) ? " changed-only" : ""}` });
  for (const p of a.problems || []) wrong.append(productElement("li", {}, problemMark([], p.kind === "changed"), problemAdvice(p)));
  keepTileInPlace(document.querySelector('#grid .slot[aria-current="true"]'), () => {
    detail.replaceChildren(productElement("button", { class: "x", "data-act": "close", "aria-label": tr("Close details") }, "×"),
      productElement("div", { class: `d-art ${model.store}${a.adult ? " adult" : ""}`, title: a.adult && blursAdult() ? tr("Blurred: for adults. Click to show it.") : null },
        productPicture(a, model.src, model.type, false)),
      productElement("h2", { class: "d-name", translate: "no" }, a.name), by, store, ...(wrong.children.length ? [wrong] : []), facts, grown, legacyFragment(sections));
    detail.classList.add("open"); document.body.classList.add("panel-open");
    $("#scrim").hidden = !matchMedia("(max-width: 860px)").matches;
    if (focus) detail.querySelector(".x").focus({ preventScroll: true });
  });
  showSpots();   // (what's new in a product's details, after an update: issue #244)
}
// Whether adult products' pictures are blurred (Settings, Appearance: on unless you turn it off).
const blursAdult = () => document.documentElement.dataset.adult !== "show";
// Mark as 18+, or It isn't for adults, in a product's details: your word, kept with your other choices (marks.json).
document.addEventListener("click", async e => {
  const b = e.target.closest ? e.target.closest("[data-adult-mark]") : null;
  if (b) {
    b.disabled = true;
    const kind = b.dataset.adultMark;   // (shown at once, the details drawn again: shared.js's adultMarked, issue #443)
    if (!(await adultMarked([b.dataset.key], kind))) { b.disabled = false; return; }
    toast(kind === "adult" ? "Marked as 18+." : "Marked as not for adults.");
    return;
  }
  const art = e.target.closest ? e.target.closest("#detail .d-art.adult") : null;   // a blurred picture, shown or blurred again
  if (art && blursAdult()) art.classList.toggle("seen");
});
// Copy store link, in a product's details on either page (issue #345).
document.addEventListener("click", async e => {
  const b = e.target.closest ? e.target.closest("[data-store-link]") : null;
  if (!b) return;
  try { await navigator.clipboard.writeText(b.dataset.storeLink); toast("Copied the store link."); }
  catch (x) { toast("That couldn't be copied here: choose Open on the store, and copy its address there."); }
});
