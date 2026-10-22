// What both of Hoard's pages share, served inside each page's own script (server.page_source): each page
// is still one script, which the Content-Security-Policy allows by its hash. Changed here, it changes on both.
/* ---------- languages (Settings, Appearance). The pages are written in English and translated as they're drawn,
   from the catalog the server puts in the page for your language (hoard/web/i18n/<language>.json): one dictionary
   for the markup, what the script builds and Hoard's own messages alike. A key is the English as it shows, with
   spaces run together; {0}, {1} stand for words that change (a count, a name), and <0>…</0> for an element inside a
   sentence (a link, a bold word), so a translation can put it where its own word order needs it; the element itself
   is kept, with what it does. Your own things (product names, creators, tags, files) are marked translate="no" and
   left as they are. English has no catalog, and nothing is done. */
const I18N = (() => {
  const data = document.getElementById("i18n");
  let catalog = {};
  try { catalog = data ? JSON.parse(data.textContent) : {}; } catch (e) { catalog = {}; }
  const exact = new Map(), patterns = [];
  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  for (const [key, value] of Object.entries(catalog)) {
    if (typeof value !== "string" || !value) continue;
    if (!/\{\d+\}/.test(key)) { exact.set(key, value); continue; }
    const order = [], parts = key.split(/(\{\d+\})/);
    const rx = new RegExp("^" + parts.map(part => {
      const m = /^\{(\d+)\}$/.exec(part);
      if (!m) return escape(part);
      order.push(+m[1]);
      return "(.+?)";
    }).join("") + "$", "s");
    // the longest fixed part, to skip a pattern quickly when the text doesn't have it
    const fixed = parts.filter(x => !/^\{\d+\}$/.test(x)).sort((a, b) => b.length - a.length)[0] || "";
    patterns.push({ rx, order, value, fixed });
  }
  patterns.sort((a, b) => b.fixed.length - a.fixed.length);   // the most specific first
  const on = exact.size + patterns.length > 0;
  const norm = s => String(s).replace(/\s+/g, " ").trim();
  // What fills a pattern's {0} is a name, a number, a path or a message of its own, never a run of English words
  // with no translation: "All 12 files of 3 downloads are as Hoard downloaded them." isn't "{0} of {1}", and a
  // message Hoard has no translation for stays whole, in English, rather than half translated.
  const SENTENCE = /\b[a-z]{2,}(?:[\s,]+[a-z]{2,}){2,}\b/;
  function lookup(key, depth = 0) {
    if (!key || /^[\d\s.,:;%+\-–—/()×#·…]*$/.test(key)) return null;   // numbers and marks need nothing
    const hit = exact.get(key);
    if (hit !== undefined) return hit;
    for (const p of patterns) {
      if (p.fixed && !key.includes(p.fixed)) continue;
      const m = p.rx.exec(key);
      if (!m) continue;
      const values = {};
      let fits = true;
      // a word that changes may be a message of its own ("Failed: {0}"): translated too, two levels down at most
      p.order.forEach((n, i) => {
        const part = m[i + 1], to = depth < 2 ? lookup(part, depth + 1) : null;
        if (to === null && SENTENCE.test(part)) fits = false;
        values[n] = to ?? part;
      });
      if (!fits) continue;
      return p.value.replace(/\{(\d+)\}/g, (_, n) => values[n] ?? "");
    }
    return null;
  }
  const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "PRE", "CODE", "svg", "SVG", "CANVAS", "IMG", "VIDEO"]);
  const INLINE = new Set(["STRONG", "B", "EM", "I", "CODE", "KBD", "A", "SPAN", "SMALL", "BR", "ABBR", "MARK", "SUP", "SUB", "U", "S", "Q", "TIME", "BUTTON"]);
  const ATTRS = ["title", "placeholder", "aria-label", "alt"];
  const kept = el => el.closest && el.closest('[translate="no"]');
  // an element whose children are words and simple inline elements (each only words): a sentence to translate whole.
  // A label beside a count or a mark ("Tasks <span>3</span>", "<span class=chev></span>Your tags") isn't one: its
  // words are translated on their own, and the count left as it is. Words on both sides of a number are a sentence.
  const bare = n => !/[A-Za-z]/.test(n.textContent);
  function sentence(el) {
    let texts = 0, elements = 0, worded = 0;
    for (const n of el.childNodes) {
      if (n.nodeType === 3) { if (n.data.trim()) texts++; continue; }
      if (n.nodeType !== 1) continue;
      if (!INLINE.has(n.tagName) || n.getAttribute("translate") === "no") return false;
      if (n.tagName !== "BR" && [...n.childNodes].some(c => c.nodeType === 1 && c.tagName !== "BR")) return false;
      elements++;
      if (n.tagName !== "BR" && !bare(n)) worded++;
    }
    if (!texts || !elements) return false;
    return worded > 0 || texts > 1;
  }
  function sentenceKey(el) {
    let i = 0, key = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) key += n.data;
      else if (n.nodeType === 1) key += n.tagName === "BR" ? `<${i++}/>` : `<${i}>${n.textContent}</${i++}>`;
    }
    return norm(key);
  }
  function applySentence(el, text) {
    const kids = [...el.childNodes].filter(n => n.nodeType === 1), out = document.createDocumentFragment();
    let last = 0;
    const rx = /<(\d+)>([\s\S]*?)<\/\1>|<(\d+)\/>/g;
    let m;
    while ((m = rx.exec(text))) {
      if (m.index > last) out.append(text.slice(last, m.index));
      const kid = kids[+(m[1] ?? m[3])];
      if (kid) {
        if (m[1] !== undefined && ![...kid.childNodes].some(c => c.nodeType === 1)) kid.textContent = m[2];
        out.append(kid);
      }
      last = rx.lastIndex;
    }
    if (last < text.length) out.append(text.slice(last));
    el.replaceChildren(out);
  }
  // missing: when given (a Set), nothing is changed, and the English that has no translation is added to it
  // (tests/test_i18n.py, and scripts/i18n_strings.py to find what's still to translate)
  let missing = null;
  const find = key => {
    const to = lookup(key);
    // (words already translated, with a name or two in them, aren't missing)
    if (to === null && missing && /[A-Za-z]{2}/.test(key) && !/[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af]/.test(key)) missing.add(key);
    return missing ? null : to;
  };
  function translateText(node) {
    const m = /^(\s*)([\s\S]*?)(\s*)$/.exec(node.data), to = find(norm(m[2]));
    if (to !== null && to !== m[2]) node.data = m[1] + to + m[3];
  }
  function translateAttrs(el) {
    for (const a of ATTRS) {
      const v = el.getAttribute(a);
      if (!v) continue;
      const to = find(norm(v));
      if (to !== null && to !== v) el.setAttribute(a, to);
    }
  }
  function walk(el) {
    if (el.nodeType === 3) { if (!kept(el.parentElement || document.body)) translateText(el); return; }
    if (el.nodeType !== 1 || SKIP.has(el.tagName) || el.getAttribute("translate") === "no") return;
    translateAttrs(el);
    if (el.tagName === "INPUT") return;
    if (sentence(el)) {
      const key = sentenceKey(el), to = lookup(key);
      if (to !== null && !missing) { applySentence(el, to); for (const k of el.children) translateAttrs(k); return; }
      if (to !== null) return;
      if (missing) { find(key); return; }
    }
    for (const n of [...el.childNodes]) {
      if (n.nodeType === 3) translateText(n);
      else walk(n);
    }
  }
  let observer = null;
  const watch = { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS };
  function translateAll(root) {
    if (!on) return;
    if (observer) observer.disconnect();
    walk(root);
    if (observer) observer.observe(document.body, watch);
  }
  function start() {
    if (!on) return;
    translateAll(document.body);
    document.title = lookup(norm(document.title)) ?? document.title;
    // what the script draws later (and Hoard's messages in it), as it's drawn
    observer = new MutationObserver(records => {
      observer.disconnect();
      const seen = new Set();
      for (const r of records) {
        if (r.type === "attributes") { if (!kept(r.target)) translateAttrs(r.target); continue; }
        const el = r.type === "characterData" ? r.target.parentElement : r.target;
        if (!el || seen.has(el) || kept(el)) continue;
        seen.add(el);
        walk(el);
      }
      observer.observe(document.body, watch);
    });
    observer.observe(document.body, watch);
  }
  function untranslated(root = document.body) {
    missing = new Set();
    try { walk(root); return [...missing]; } finally { missing = null; }
  }
  return { on, lookup, start, untranslated, t: (s, ...values) => {
    // for the script's own use (a dialog's words, a title set in code): {0}, {1} filled in after translating
    const key = norm(s), text = (typeof catalog[key] === "string" && catalog[key]) || lookup(key) || s;   // (its own words, as they're written)
    return text.replace(/\{(\d+)\}/g, (_, n) => values[n] ?? "");
  } };
})();
const tr = I18N.t;   // the script's own words: tr("Copied"), tr("{0} files", n)
// tr() for HTML: the words escaped, and each value (already HTML: a link, a name in <strong>) put in as it is
const trHTML = (s, ...html) => esc(tr(s, ...html.map((_, i) => `\u0001${i}\u0002`))).replace(/\u0001(\d+)\u0002/g, (_, n) => html[n]);
const listed = list => new Intl.ListFormat(document.documentElement.lang || "en", { type: "conjunction" }).format(list);   // "A, B and C"
I18N.start();
delete document.documentElement.dataset.i18n;   // shown now: translated (or English, if there's no catalog)

/* ---------- splash (issue #50): the logo while the page first reads your library. It's in the markup, so it shows
   from the first paint; on the window's first page it stays at least a moment, and on later pages (Library to
   Downloads and back) the stylesheet only fades it in if reading takes more than a moment. Projects has one of its
   own, shown the same way while it first reads your projects (loadProjects). */
function splash(el, seen) {   // el shown; what's returned takes it away, for good ("seen": whether it's been shown in this window)
  let first = true;
  try { first = !sessionStorage.getItem(seen); sessionStorage.setItem(seen, "1"); } catch (e) {}
  el.classList.toggle("first", first);
  el.hidden = false;
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
}
const hideSplash = splash(document.getElementById("splash"), "hoard-opened");
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
    for (const wait of [300, 0]) {   // (once more if it couldn't be sent at all: the link isn't used until it arrives)
      try {
        const r = await fetch("/api/enter", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token: once }) });
        if (r.ok) ACCESS.key = (await r.json()).key || "";
        break;
      } catch (e) { if (wait) await new Promise(res => setTimeout(res, wait)); }   // (Hoard isn't running: the first request says so)
    }
  }
  try { if (ACCESS.key) localStorage.setItem("hoard-key", ACCESS.key); } catch (e) { /* no storage: this page still works */ }
})();
// Every request to Hoard's server goes through api(), with the key. Images, which the browser loads by itself,
// carry it in their address instead (keyed()). One that only reads, and couldn't be sent at all (the connection
// refused or dropped for a moment, as on a computer short of network buffers), is sent again, twice at most: a page
// isn't left saying Hoard isn't running over a moment's hiccup. A change is never sent twice.
async function api(url, opts = {}) {
  await entered;
  const send = () => fetch(url, { ...opts, headers: { ...(opts.headers || {}), "X-Hoard-Key": ACCESS.key } });
  if ((opts.method || "GET").toUpperCase() !== "GET") return send();
  for (const wait of [300, 1000]) {
    try { return await send(); } catch (e) {
      if (!(e instanceof TypeError)) throw e;   // (an abort isn't one)
      await new Promise(res => setTimeout(res, wait));
    }
  }
  return send();
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
  const named = COLOUR_NAMES[store] ? ` data-s="${esc(tr(COLOUR_NAMES[store]))}"` : "";   // (the Treasure style's tag)
  return other ? `<i class="notch ${store} dup"${named} style="--c2: var(--${other})"></i>` : `<i class="notch ${store}"${named}></i>`;
}
// The Treasure style's row of facts in a product's details (web/looks.css): [label, value as HTML]
const dStats = facts => `<div class="d-stats">${facts.map(([k, v]) => `<span><small>${esc(tr(k))}</small><b>${v}</b></span>`).join("")}</div>`;
// a day as your language writes it, short: "12 Oct 2026" (the Workbench style's list, Treasure's details)
function shortDay(iso) {
  const d = iso ? new Date(iso) : null;
  return d && !isNaN(d) ? d.toLocaleDateString(document.documentElement.lang || "en", { year: "numeric", month: "short", day: "numeric" }) : "";
}
/* Stacking copies across stores (hoard/library.py): when two shops' copies of one product have the same name but
   their pictures aren't the same file, Hoard asks the page how the pictures look. A difference hash: the picture
   in grey, 9 by 8, and for each square whether it's brighter than the one to its right. A store re-saving a
   picture barely changes it; another product's picture changes most of it. */
function pictureLook(src) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      try {
        const W = 72, H = 64, c = document.createElement("canvas");   // 8 by 8 pixels to each square, averaged
        c.width = W; c.height = H;
        const g = c.getContext("2d", { willReadFrequently: true });
        g.imageSmoothingQuality = "high";
        g.drawImage(img, 0, 0, W, H);
        const d = g.getImageData(0, 0, W, H).data, grey = new Array(72).fill(0);
        for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
          const i = (y * W + x) * 4;
          grey[(y >> 3) * 9 + (x >> 3)] += d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114;
        }
        if (Math.max(...grey) - Math.min(...grey) < Math.max(...grey) * 0.02 + 1) { resolve(null); return; }   // flat: no look to go by
        let hex = "";
        for (let n = 0; n < 64; n += 4) {
          let v = 0;
          for (let b = n; b < n + 4; b++) { const y = b >> 3, x = b & 7; v = v * 2 + (grey[y * 9 + x] > grey[y * 9 + x + 1] ? 1 : 0); }
          hex += v.toString(16);
        }
        resolve(hex);
      } catch (e) { resolve(null); }
    };
    img.onerror = () => resolve(null);
    img.src = src;
  });
}
const lookedAt = new Set();   // pictures already worked out while this page is open, found or not
async function lookAtPictures(wanted) {   // [{look_for: its SHA-256, src}]: true when there's something new to stack by
  const looks = {};
  for (const w of wanted) {
    if (lookedAt.has(w.look_for) || Object.keys(looks).length >= 500) continue;
    lookedAt.add(w.look_for);
    const hex = await pictureLook(w.src);
    if (hex) looks[w.look_for] = hex;
  }
  if (!Object.keys(looks).length) return false;
  try { return (await apiPost("/api/picture-looks", { looks })).ok; } catch (e) { return false; }
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
// Appearance (hoard/themes.py): the themes, each with a swatch of its dark and light pages and their accent
function fillThemes() {
  const d = SETTINGS.display, box = $("#themeChoices");
  if (!box) return;
  const half = c => `<span style="background:${c[0]}"><i style="background:${c[2]}"></i></span>`;
  box.innerHTML = (d.themes || []).map(t => `<label class="theme-choice" title="${esc(t.mood)}"><input type="radio" name="setTheme" value="${esc(t.id)}"${t.id === d.theme ? " checked" : ""}>` +
    `<span class="theme-swatch" aria-hidden="true">${half(t.dark)}${half(t.light)}</span><span>${esc(t.name)}${t.tag ? `<small>${esc(t.tag)}</small>` : ""}</span></label>`).join("");
  for (const r of document.querySelectorAll('input[name="setMode"]')) r.checked = r.value === d.mode;
}
// Styles (Settings, Appearance; issue #159): how the pages are laid out (web/looks.css), each with a small picture
const STYLES = [["standard", "Standard", "Hoard as it has always looked: tiles with their store's colour along the bottom."],
                ["treasure", "Treasure", "Big pictures, each in a frame of its store's colour, and round buttons."],
                ["workbench", "Workbench", "Close-set lists and tables, in your computer's own font: more at a glance."]];
function stylePicture(id) {
  const stores = ["booth", "gumroad", "jinxxy", "payhip", "itch", "local"];
  const n = { standard: 4, treasure: 3, workbench: 12 }[id];
  return `<span class="style-pic ${id}" aria-hidden="true">` + Array.from({ length: n }, (_, i) =>
    `<i class="${id === "workbench" ? (i % 3 ? "" : stores[(i / 3) % stores.length]) : stores[i % stores.length]}"></i>`).join("") + `</span>`;
}
function styleChoices(name, now) {
  return STYLES.map(([id, label, about]) => `<label class="style-choice"><input type="radio" name="${name}" value="${id}"${id === (now || "standard") ? " checked" : ""}>` +
    `${stylePicture(id)}<span><b>${esc(tr(label))}</b><small>${esc(tr(about))}</small></span></label>`).join("");
}
function fillStyles() {
  const box = $("#styleChoices");
  if (box) box.innerHTML = styleChoices("setStyle", SETTINGS.display.style);
}
function applyDisplay(d) {
  if (!d) return;
  const look = d.style && d.style !== "standard" ? d.style : "";   // (Standard: no mark, the pages as written)
  if (look) document.documentElement.dataset.style = look; else delete document.documentElement.dataset.style;
  // the theme, in place of the one the page was served with (the same colours, from the same place)
  const theme = $("#theme");
  if (theme && typeof d.theme_css === "string" && theme.textContent.trim() !== d.theme_css.trim()) { theme.textContent = d.theme_css; }
  document.documentElement.style.zoom = d.text_size && d.text_size !== 100 ? String(d.text_size / 100) : "";
  // Zoom scales every length, the window's own size (vh, vw) included: --zoom undoes that for --vh and --vw, so
  // what's sized to the window still fits it at a larger text size (issue #48)
  document.documentElement.style.setProperty("--zoom", String((d.text_size || 100) / 100));
  document.body.classList.toggle("less-motion", !!d.reduce_motion);
  const html = document.documentElement;   // easier reading (the page is served with them: this is for a change)
  if (d.font === "dyslexic") html.dataset.font = "dyslexic"; else delete html.dataset.font;
  if (d.spacing) html.dataset.spacing = "wide"; else delete html.dataset.spacing;
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
    no.hidden = !cancel;   // (an empty cancel: something to read, with only the one button)
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
// Selecting several items: tick a tile's box, Ctrl/Cmd-click it, or Shift-click to take in everything from the last
// one; or choose Select (touch screens: there's no hover or Ctrl), where every tap ticks. sel.on is that Select mode.
const sel = { on: false, ids: new Set(), anchor: null, kind: "items" };
// The Sets tab's tiles of every set are chosen the same way, for what's done to sets: what's chosen is products, or
// sets, as the page shows (a set's id, in its tile's data-setopen)
const onSetTiles = () => state.store === "Sets" && !state.set;
const TILES = () => onSetTiles() ? "#setView .settile" : "#grid .slot";
const tileId = slot => slot.dataset.setopen || slot.dataset[T.slotKey];
const selecting = () => sel.on || sel.ids.size > 0;
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
// What a tag is about (hoard/tags.py, issue #157): the filters group your tags by it, and Mix and match takes avatars
// and clothes from it
const TAG_TYPES = { avatar: "Avatar", world: "World", clothing: "Clothing", gimmick: "Gimmick", script: "Script", texture: "Texture", other: "Other" };
const tagTypes = () => new Map(((DATA.tagset || {}).tags || []).filter(x => x.type).map(x => [x.name, x.type]));
const tagChip = ([t, n], kind) =>
  `<button class="chip ${kind}" data-tag="${esc(t)}" aria-pressed="${state.tags.has(t)}">${esc(t)}<span class="n">${n}</span></button>`;

function renderTagFacets(list) {
  const wish = openWish();   // (a wishlist open: its products', as they're narrowed down: wishTagItems)
  if (wish) list = wishTagItems(wish);
  const mine = new Map(), sugg = new Map();
  for (const a of list) {
    for (const t of a.tags) mine.set(t, (mine.get(t) || 0) + 1);
    for (const t of a.suggested) sugg.set(t, (sugg.get(t) || 0) + 1);
  }
  const yours = new Set(((DATA.tagset || {}).tags || []).map(x => x.name));
  for (const t of state.tags) if (!mine.has(t) && !sugg.has(t)) (yours.has(t) ? mine : sugg).set(t, 0);
  const order = (x, y) => state.tags.has(y[0]) - state.tags.has(x[0]) || y[1] - x[1] || coll.compare(x[0], y[0]);
  const m = [...mine].sort(order), s = [...sugg].sort(order);
  const kinds = tagTypes(), grouped = kinds.size && m.some(x => kinds.has(x[0]));
  $("#myTags").innerHTML = (grouped   // your tags by what they're about, those with no kind last
    ? [...Object.keys(TAG_TYPES), ""].map(k => { const these = m.filter(x => (kinds.get(x[0]) || "") === k);
        return these.length ? `<span class="tgroup">${esc(tr(k ? TAG_TYPES[k] : "Other tags"))}</span>` + these.map(x => tagChip(x, "mine")).join("") : ""; }).join("")
    : m.map(x => tagChip(x, "mine")).join("")) ||
    `<span class="none">${yours.size ? "None on these items" : "Add tags from an item's details, or select several items at once."}</span>`;
  $("#tags").innerHTML = (state.allTags ? s : s.slice(0, 36)).map(x => tagChip(x, "sugg")).join("") ||
    `<span class="none">No suggestions here</span>`;
  const more = $("#moreTags"); more.hidden = s.length <= 36;
  more.textContent = state.allTags ? "Show fewer" : `Show all ${s.length}`;
  $("#tagList").innerHTML = [...yours].sort(coll.compare).map(t => `<option value="${esc(t)}">`).join("");
}

function tagSection(a) {
  const mine = a.tags.map(t => `<span class="tagpill"><button class="chip" data-act="tag" data-tag="${esc(t)}" aria-pressed="${state.tags.has(t)}">${esc(t)}</button>` +
    `<button class="untag" data-act="untag" data-tag="${esc(t)}" aria-label="${esc(tr("Remove the tag {0}", t))}">×</button></span>`).join("");
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
  const kind = onSetTiles() ? "sets" : "items";
  if (sel.kind !== kind) { sel.ids.clear(); sel.anchor = null; sel.kind = kind; }   // (products and sets aren't chosen together)
  const on = selecting();
  document.body.classList.toggle("selecting", on);
  $("#bulk").hidden = !on;
  for (const s of document.querySelectorAll(TILES())) {
    if (on) s.setAttribute("aria-pressed", String(sel.ids.has(tileId(s))));
    else s.removeAttribute("aria-pressed");
  }
  if (!on) { closeSelMenu(); return; }
  $("#bulkAll").hidden = $("#bulkDone").hidden = !!PJPICK.for;   // (choosing for a project: Add to project or Cancel)
  $("#bulkCount").textContent = PJPICK.for
    ? tr(sel.ids.size === 1 ? "1 selected for {1}" : "{0} selected for {1}", sel.ids.size.toLocaleString(), PJPICK.for.name)
    : tr(sel.ids.size === 1 ? "1 selected" : "{0} selected", sel.ids.size.toLocaleString());
  renderBulk();
}
// a stacked tile stands for every copy in it: choosing it chooses them all
const idsFor = id => (sel.kind === "items" && T.membersOf && T.membersOf(id)) || [id];
function toggleSelected(id) {
  const add = !sel.ids.has(id);
  for (const i of idsFor(id)) add ? sel.ids.add(i) : sel.ids.delete(i);
  sel.anchor = id;
  markSelected();
}
function selectRange(id) {   // Shift-click: everything shown from the last one chosen to this one
  const order = [...document.querySelectorAll(TILES())].map(tileId);
  const a = order.indexOf(sel.anchor), b = order.indexOf(id);
  if (a < 0 || b < 0) return toggleSelected(id);
  for (const i of order.slice(Math.min(a, b), Math.max(a, b) + 1)) for (const m of idsFor(i)) sel.ids.add(m);
  markSelected();
}
/** A click on a tile: true when it chose the tile (or a range) rather than opening it. */
function selectClick(e, slot) {
  const id = tileId(slot);
  if (e.shiftKey && sel.anchor != null && selecting()) { selectRange(id); return true; }
  if (e.ctrlKey || e.metaKey || sel.on || e.target.closest(".tick")) { toggleSelected(id); return true; }
  return false;
}
function selectAllShown() {
  for (const id of onSetTiles() ? ((SETS || {}).sets || []).map(x => x.id) : T.shown().map(T.id)) sel.ids.add(id);
  markSelected();
}
function setSelecting(on) {   // the Select button: a mode where every tap ticks (and Done ends it, and the selection)
  if (!on && PJPICK.for) return pickEnd();   // (Done or Escape while choosing for a project: back to it, as Cancel is)
  sel.on = on;
  if (!on) { sel.ids.clear(); sel.anchor = null; }
  $("#selectBtn").textContent = on ? tr("Done") : tr("Select");
  $("#selectBtn").setAttribute("aria-pressed", String(on));
  $("#selectBtn").hidden = !!PJPICK.for;   // (choosing for a project: the bar's Add to project and Cancel are the way out)
  if (on) T.closeDetail();
  T.render();   // (stacks open while in Select mode, so each copy can be chosen)
  markSelected();
}
const clearSelection = () => setSelecting(false);
const chosenItems = () => [...sel.ids].map(sel.kind === "sets" ? id => ((SETS || {}).sets || []).find(x => x.id === id) : T.byId).filter(Boolean);
const actionsHere = () => PJPICK.for ? (sel.kind === "items" ? PICK_ACTIONS() : {}) : sel.kind === "sets" ? SET_TILE_ACTIONS() : T.actions();

/* what to do with the selection: the bar's buttons and menus, and the same menu on a right-click */
function renderBulk() {
  const { main = [], groups = [] } = actionsHere();
  const none = !sel.ids.size;
  $("#bulkActs").innerHTML =
    main.map((m, i) => `<button class="${m.primary ? "primary" : "ghost"} sm" data-main="${i}"${none ? " disabled" : ""}>${esc(tr(m.label))}</button>`).join("") +
    groups.filter(g => g.items.length).map(g => `<button class="ghost sm menu-btn" data-group="${esc(g.name)}" aria-haspopup="menu" ` +
      `aria-expanded="false"${none ? " disabled" : ""}>${esc(tr(g.name))}</button>`).join("") +
    (PJPICK.for ? `<button class="ghost sm" data-pickcancel>${esc(tr("Cancel"))}</button>` : "");
}
function runAction(item) {
  closeSelMenu();
  const chosen = chosenItems();
  if (!chosen.length) { toast("Select some items first."); return; }
  item.run(chosen);
}
let selMenu = null;   // {el, groups, from}: the open menu
function closeSelMenu(refocus = false) {
  if (!selMenu) return;
  const { el, from } = selMenu;
  selMenu = null;
  el.remove();
  if (from && from.setAttribute) from.setAttribute("aria-expanded", "false");
  if (refocus && from && from.focus) from.focus();
}
/** Open a menu of these groups' actions: under a bar button (from), or where the pointer is (at: {x, y}). */
// Text size (Settings) zooms the whole page. What the page reads of where things are (getBoundingClientRect, a click's
// clientX) is in the window's own pixels, but a fixed element's left and top, and its offsetWidth, are in the page's
// zoomed ones: positions are worked out in the window's pixels and divided by the zoom as they're set. (Without it,
// at 130% a menu opened near the window's edge went off it.)
const pageZoom = () => parseFloat(document.documentElement.style.zoom) || 1;
function openSelMenu(groups, from, at) {
  closeSelMenu();
  groups = groups.filter(g => g.items.length);
  if (!groups.length) return;
  const el = document.createElement("div");
  el.className = "selmenu"; el.setAttribute("role", "menu");
  const items = [];
  el.innerHTML = groups.map((g, gi) => (groups.length > 1 && g.name ? `<p class="selmenu-h" role="presentation">${esc(tr(g.name))}</p>` : "") +
    g.items.map(it => { items.push(it); return `<button role="menuitem" class="${it.danger ? "danger" : ""}" data-i="${items.length - 1}"` +
      `${it.raw ? ' translate="no"' : ""}>${esc(it.raw ? it.label : tr(it.label))}</button>`; }).join("") +
    (gi < groups.length - 1 ? `<hr role="separator">` : "")).join("");
  document.body.appendChild(el);
  selMenu = { el, from, since: performance.now() };
  const r = from ? from.getBoundingClientRect() : { left: at.x, right: at.x, top: at.y, bottom: at.y };
  const z = pageZoom(), w = el.offsetWidth * z, h = el.offsetHeight * z, vw = window.innerWidth, vh = window.innerHeight;
  const below = from ? r.top - h - 6 >= 8 ? r.top - h - 6 : r.bottom + 6 : (r.bottom + h + 8 > vh ? r.top - h : r.bottom);   // the bar is low: open above it
  el.style.left = Math.max(8, Math.min(r.left, vw - w - 8)) / z + "px";
  el.style.top = Math.max(8, Math.min(below, vh - h - 8)) / z + "px";
  if (from) from.setAttribute("aria-expanded", "true");
  el.addEventListener("click", e => { const b = e.target.closest("[data-i]"); if (b) runAction(items[+b.dataset.i]); });
  el.addEventListener("keydown", e => {
    const all = [...el.querySelectorAll("[role=menuitem]")], i = all.indexOf(document.activeElement);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); all[(i + (e.key === "ArrowDown" ? 1 : all.length - 1)) % all.length].focus(); }
    else if (e.key === "Home" || e.key === "End") { e.preventDefault(); all[e.key === "Home" ? 0 : all.length - 1].focus(); }
    else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closeSelMenu(true); }
    else if (e.key === "Tab") closeSelMenu();
  });
  const first = el.querySelector("[role=menuitem]");
  if (first) first.focus({ preventScroll: true });
}
/** Everything there is to do with the selection, for a right-click: the bar's main actions, then its menus. */
function allActions() {
  const { main = [], groups = [] } = actionsHere();
  return [...(main.length ? [{ name: "", items: main }] : []), ...groups];
}
function wireSelection() {
  $("#bulk").addEventListener("click", e => {
    const m = e.target.closest("[data-main]"), g = e.target.closest("[data-group]");
    if (e.target.closest("[data-pickcancel]")) pickEnd();
    else if (m) runAction(actionsHere().main[+m.dataset.main]);
    else if (g) {
      if (selMenu && selMenu.from === g) { closeSelMenu(); return; }
      openSelMenu(actionsHere().groups.filter(x => x.name === g.dataset.group), g);
    }
  });
  $("#selectBtn").addEventListener("click", () => setSelecting(!sel.on));
  $("#bulkDone").addEventListener("click", clearSelection);
  $("#bulkAll").addEventListener("click", selectAllShown);
  const menuFor = (slot, at) => {   // a right-click on a tile not chosen chooses just it, as file managers do
    const id = tileId(slot);
    if (!sel.ids.has(id)) { sel.ids.clear(); for (const i of idsFor(id)) sel.ids.add(i); sel.anchor = id; markSelected(); }
    openSelMenu(allActions(), null, at);
  };
  for (const [box, tiles] of [[$("#grid"), ".slot"], [$("#setView"), ".settile"]]) {   // products' tiles, and sets'
    box.addEventListener("contextmenu", e => {
      const slot = e.target.closest(tiles); if (!slot) return;
      e.preventDefault();
      menuFor(slot, { x: e.clientX, y: e.clientY });
    });
    box.addEventListener("keydown", e => {   // the menu key, or Shift+F10, on a tile
      const slot = e.target.closest(tiles);
      if (!slot || !(e.key === "ContextMenu" || (e.key === "F10" && e.shiftKey))) return;
      e.preventDefault();
      const r = slot.getBoundingClientRect();
      menuFor(slot, { x: r.left + 12, y: r.top + 12 });
    });
  }
  document.addEventListener("pointerdown", e => { if (selMenu && !selMenu.el.contains(e.target) && e.target !== selMenu.from) closeSelMenu(); }, true);
  window.addEventListener("resize", () => closeSelMenu());
  // scrolling closes the menu, but not the page settling as it opens: the bar appearing for a right-clicked tile can
  // move the page a little, and that closed the menu as it opened (near the end of the grid, the menu never showed)
  document.addEventListener("scroll", () => { if (selMenu && performance.now() - selMenu.since > 300) closeSelMenu(); }, true);
  document.addEventListener("keydown", e => {
    const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName) || document.querySelector("dialog[open]");
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a" && !typing) { e.preventDefault(); selectAllShown(); }
  });
}
async function bulkTag(mode) {   // a tag to add to, or take off, what's selected
  const chosen = chosenItems();
  if (!chosen.length) { toast("Select some items first."); return; }
  const t = (await askName(mode === "add" ? "Add a tag to the selected" : "Take a tag off the selected", "",
                           { list: "tagList", max: 40 })).trim();
  if (!t) return;
  const n = chosen.length, what = `${n} ${n === 1 ? "item" : "items"}`, tag = "#" + t.toLowerCase();
  await changeTags({ action: "assign", keys: keysOf(chosen), [mode]: [t] },
                   mode === "add" ? `Added ${tag} to ${what}.` : `Removed ${tag} from ${what}.`);
}
const TAG_ACTIONS = { name: "Tags", items: [{ label: "Add a tag...", run: () => bulkTag("add") },
                                            { label: "Remove a tag...", run: () => bulkTag("remove") }] };

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
    `<span class="tbtns"><select class="ttype" data-ttype="${esc(x.name)}" aria-label="${esc(tr("What {0} is about", x.name))}">` +
    `<option value="">${esc(tr("No kind"))}</option>${Object.entries(TAG_TYPES).map(([k, label]) => `<option value="${k}"${x.type === k ? " selected" : ""}>${esc(tr(label))}</option>`).join("")}</select>` +
    `${btn("rename", x.name, "Rename")}` +
    `${btn("match", x.name, x.match ? "Change match" : "Match names", `data-match="${esc(x.match || "")}"`)}` +
    `${btn("delete", x.name, "Delete", `data-count="${x.count}"`)}</span></li>`).join("") ||
    `<li class="none">No tags yet. Create one above, keep a suggestion below, or add one from an item's details.</li>`;
  $("#suggRows").innerHTML = ts.suggestions.slice(0, 60).map(x => `<li><span class="tname">${esc(x.name)}</span>` +
    `<span class="tmeta">${esc(tr(x.count === 1 ? "in 1 name" : "in {0} names", x.count))}</span>` +
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
const libText = l => l.main ? tr(l.label) : (l.label || l.path);   // "Downloads folder" in your language; others by their name
const libCount = n => tr(n === 1 ? "{0} product" : "{0} products", n.toLocaleString());
function renderLibs(list) {   // every library folder, the downloads folder first (hoard/libraries.py)
  $("#setLibs").innerHTML = (list || []).map(l => `<div class="librow${l.available ? "" : " away"}">${DRIVE_ICON}` +
    `<span class="lp"><b translate="no">${esc(libText(l))}</b><small><span translate="no">${esc(l.path)}</span>${l.main ? ` · <span>new downloads go here</span>` : ""}</small></span>` +
    `<span class="muted">${esc(l.available ? [libCount(l.products || 0), l.free != null && tr("{0} free", sizeText(l.free))].filter(Boolean).join(" · ")
      : tr("Drive not connected"))}</span>` +
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
  if (added) toast((added.products ? tr("Added {0}: {1} found there.", libText(added), libCount(added.products))
                                    : tr("Added {0}: nothing downloaded there yet.", libText(added))) + " " + tr("It has a tab in Downloads."));
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
      if (lib) { const r = await apiPost("/api/open", { path: lib.main ? "" : `@${lib.n}/` }); toast(r.ok ? tr("Opened in {0}", tr(r.data.opened_in)) : r.data.error); }
      return;
    }
    const b = e.target.closest("[data-lib-remove]"); if (!b) return;
    const lib = (SETTINGS.libraries || []).find(l => l.n === +b.dataset.libRemove);
    if (!lib || !await ask(tr("Stop reading {0} ({1}) as part of your library?", libText(lib), lib.path) + "\n\n" +
                           tr("Its files stay where they are, and come back to your library if you add the folder again."), "Remove")) return;
    if (await libraryChange("/api/libraries/remove", { n: lib.n })) toast(tr("{0} is no longer part of your library.", libText(lib)));
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
  const files = n => n ? tr(n === 1 ? ", {0} file" : ", {0} files", n) : "";
  const row = (e, skipped) => `<li>` + (skipped
    ? `<span class="dot ${esc(e.store)}"></span><span class="pk-nm" translate="no">${esc(e.name)}</span><span class="muted" translate="no">${esc(e.creator)}</span>` +
      `<button class="linkish" data-unskip="${esc(e.key)}">Stop skipping</button>`
    : `<label><input type="checkbox" data-pick="${esc(e.key)}"${PICK.off.has(e.key) ? "" : " checked"}> <span class="dot ${esc(e.store)}"></span>` +
      `<span class="pk-nm" translate="no">${esc(e.name)}</span><span class="muted" translate="no">${esc(e.creator)}${esc(files(e.files))}</span></label>` +
      `<button class="linkish" data-skip="${esc(e.key)}">Always skip</button>` + fileChoice(e)) + `</li>`;
  $("#pickList").innerHTML = PICK.items.map(e => row(e, false)).join("") ||
    `<li class="muted">Nothing here to download, apart from what you always skip.</li>`;
  $("#pickSkipped").hidden = !PICK.skipped.length;
  $("#pickSkipN").textContent = PICK.skipped.length;
  $("#pickSkipped ul").innerHTML = PICK.skipped.map(e => row(e, true)).join("");
  const n = PICK.items.length - PICK.off.size;
  $("#pickGo").textContent = !PICK.off.size ? tr(`${PICK.verb} all`) : tr(`${PICK.verb} {0}`, n);
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
/* ---------- the details' picture: shorter, so the name and buttons show; full size when it's clicked. And Settings'
   row of its parts: each scrolls to its part of the panel */
document.addEventListener("click", e => {
  const art = e.target.closest(".d-art");
  if (art && art.querySelector("img")) art.classList.toggle("big");
  const jump = e.target.closest("[data-jump]");
  if (jump) { const h = document.getElementById(jump.dataset.jump); if (h) h.scrollIntoView({ block: "start", behavior: motionOk() ? "smooth" : "auto" }); }
});
/* ---------- Settings, Backup (hoard/backup.py): what you've set up, in one file; and putting one back */
function wireBackup() {
  const note = $("#backupNote");
  $("#backupMake").addEventListener("click", async () => {
    const r = await apiPost("/api/backup/make");
    if (!r.ok) { toast(r.data.error || "The backup couldn't be made."); return; }
    note.innerHTML = `${esc(tr("Saved {0}.", r.data.path))} ` +
      (r.data.pin_set && !r.data.hidden ? esc(tr("Your hidden items were left out: unlock them first to include them.")) + " " : "") +
      `<button class="linkish" id="backupShow">Show in folder</button>`;
    toast("Backup saved.");
  });
  note.addEventListener("click", async e => {
    if (!e.target.closest("#backupShow")) return;
    const r = await apiPost("/api/backup/show");
    if (!r.ok) toast(r.data.error || "Couldn't open the backups folder.");
  });
  $("#backupRestore").addEventListener("click", () => $("#backupFile").click());
  $("#backupFile").addEventListener("change", async e => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    let content;
    try { content = await file.text(); } catch (err) { toast("That file couldn't be read."); return; }
    const check = await apiPost("/api/backup/check", { content });
    if (!check.ok) { toast(check.data.error || "That isn't a Hoard backup."); return; }
    const b = check.data, when = b.made ? new Date(b.made).toLocaleString(document.documentElement.lang || undefined) : file.name;
    const count = (n, one, many) => tr(n === 1 ? one : many, n.toLocaleString());
    if (!await ask(tr("Restore the backup from {0}? It has {1}, {2} and {3}.", when, count(b.tags, "{0} tag", "{0} tags"),
                      count(b.sets, "{0} set", "{0} sets"), count(b.items, "{0} product in its library list", "{0} products in its library list")) + "\n\n" +
                   tr(b.hidden ? "Your settings, tags, sets and archive choices are replaced with the backup's, and so are your hidden items and PIN."
                               : "Your settings, tags, sets and archive choices are replaced with the backup's.") + " " +
                   tr("Hoard saves how things are now first, in the same folder, so you can put them back."), "Restore")) return;
    const r = await apiPost("/api/backup/restore", { content });
    if (!r.ok) { toast(r.data.error || "The backup couldn't be restored."); return; }
    toast(r.data.skipped.length ? tr("Restored. Left as they are: {0}.", r.data.skipped.join("; ")) : "Restored.");
    setTimeout(() => location.reload(), 1500);
  });
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
  $("#setPrevious").value = String(SETTINGS.keep_previous ?? 1);
  $("#setOffline").checked = SETTINGS.offline_images;
  $("#setUpdates").checked = SETTINGS.check_for_updates;
  $("#setBetas").checked = !!SETTINGS.beta_updates;
  $("#setBackground").checked = !!SETTINGS.close_to_taskbar;
  $("#backgroundRow").hidden = !DATA.can_background;
  $("#setNotify").checked = SETTINGS.notify_found !== false;
  $("#notifyRow").hidden = !DATA.can_notify;
  showUpdate();
  $("#setBrowser").value = SETTINGS.browser_channel;
  showBrowserInUse();
  $("#setRoutine").value = String(SETTINGS.routine_hours ?? 0);
  $("#setTextSize").value = String(SETTINGS.display.text_size);
  $("#setPause").checked = SETTINGS.display.pause_animations;
  $("#setMotion").checked = SETTINGS.display.reduce_motion;
  $("#setFont").value = SETTINGS.display.font || "standard";
  $("#setSpacing").checked = !!SETTINGS.display.spacing;
  $("#setGlowOn").checked = SETTINGS.display.glow;
  $("#setColours").value = SETTINGS.display.colours;
  fillColours();
  fillThemes();
  fillStyles();
  $("#setLanguage").value = SETTINGS.display.language || "system";
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
  markBrand();
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
/* The logo glows, and shakes now and then, while an update to Hoard is waiting; choosing it then opens Updates */
function markBrand() {
  const b = $(".brand");
  if (!b) return;
  const on = !!(UPDATE && UPDATE.available);
  b.classList.toggle("has-update", on);
  if (on) b.title = `Hoard ${verText(UPDATE.latest.version)} is ready: choose to update`; else b.removeAttribute("title");
  b.querySelector("svg").setAttribute("aria-label", on ? `Hoard: version ${verText(UPDATE.latest.version)} is ready to install` : "Hoard");
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
  if (!await ask(tr("Update to Hoard {0}?", verText(UPDATE.latest.version)) + " " + tr("Hoard downloads it, closes, installs it and opens again.") + " " +
               tr("Your library, settings, sign-ins and downloads stay as they are."), "Update")) return;
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
  // light as the page shows it: Settings' Light or Dark, or the computer's
  const light = getComputedStyle(document.documentElement).colorScheme.includes("light");
  const key = (light ? "light:" : "dark:") + (store ? "one:" : "all:") + list.join(",");
  if (key === glowShown) return;
  glowShown = key;
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
// The sort a page shows: the link's, else the one last chosen on either page (kept with the other layout choices, so
// it stays between launches, and between the Library and Downloads), when this page has it; else by name
function sortFrom(given, sorts) {
  if (given === "newest") given = "added";   // (Downloads' own name for it, before 5.0)
  return sorts[given] ? given : sorts[UI.sort] ? UI.sort : "name";
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
  x.setAttribute("aria-label", title ? tr("Close {0}", title.textContent.trim()) : tr("Close panel"));
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
    const key = h.dataset.sec || name.toLowerCase().replace(/\W+/g, "-").slice(0, 40);   // data-sec: the same in every language
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
  if (el.name === "setTheme") return { display: { theme: el.value } };
  if (el.id === "setLanguage") return { display: { language: el.value } };
  if (el.name === "setMode") return { display: { mode: el.value } };
  if (el.name === "setStyle") return { display: { style: el.value } };
  switch (el.id) {
    case "setRoot": { const root = el.value.trim(); return { root: root === SETTINGS.default_root ? "" : root }; }
    case "setOffline": return { offline_images: el.checked };
    case "setUpdates": return { check_for_updates: el.checked };
    case "setBetas": return { beta_updates: el.checked };
    case "setBackground": return { close_to_taskbar: el.checked };
    case "setNotify": return { notify_found: el.checked };
    case "setBrowser": return { browser_channel: el.value };
    case "setRoutine": return { routine_hours: Number(el.value) };
    case "setNewDays": return { new_days: Number(el.value) };
    case "setRetries": return { download_retries: Number(el.value) };
    case "setPrevious": return { keep_previous: Number(el.value) };
    case "setGlowOn": return { display: { glow: el.checked } };
    case "setColours": return { display: { colours: el.value } };
    case "setFont": return { display: { font: el.value } };
    case "setSpacing": return { display: { spacing: el.checked } };
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
    if (part.display && "language" in part.display) { location.reload(); return; }   // the page comes again in it
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
  return i ? `${n.toFixed(1)} ${units[i]}` : tr("{0} bytes", Math.round(n));
}
function timeLeft(s) {
  s = Math.max(0, Math.round(s));
  return s < 60 ? tr("{0} s", s) : s < 3600 ? tr("{0} min", Math.round(s / 60)) : tr("{0} h {1} min", Math.floor(s / 3600), Math.round(s % 3600 / 60));
}
function transferHtml(t) {
  if (!t || !t.file) return "";
  const pct = t.total ? Math.min(100, (t.got || 0) * 100 / t.total) : null;
  const stats = [t.total ? tr("{0} of {1}", sizeText(t.got || 0), sizeText(t.total)) : tr("{0} so far", sizeText(t.got || 0))];
  if (t.speed != null) stats.push(`${sizeText(t.speed)}/s`);
  if (t.eta != null) stats.push(tr("{0} left", timeLeft(t.eta)));
  const bar = pct == null
    ? `<div class="xfer-bar unknown" role="progressbar" aria-label="${esc(t.file)}"><span></span></div>`
    : `<div class="xfer-bar" role="progressbar" aria-label="${esc(t.file)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.floor(pct)}"><span style="width: ${pct.toFixed(1)}%"></span></div>`;
  return `<div class="xfer"><div class="xfer-file" title="${esc(t.file)}" translate="no">${esc(t.file)}</div>${bar}` +
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
function whenDone(iso) { const d = new Date(iso); return isNaN(d) ? "" : d.toLocaleString(document.documentElement.lang || undefined, { dateStyle: "medium", timeStyle: "short" }); }
function tookTime(a, b) {
  const s = (Date.parse(b) - Date.parse(a)) / 1000;
  return isNaN(s) ? "" : s < 60 ? `${Math.max(0, Math.round(s))} s` : s < 3600 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`;
}
function renderTasks(t) {
  const json = JSON.stringify(t);
  if (json === tasksShown) return;
  tasksShown = json;
  const open = new Set([...document.querySelectorAll("#tasksBody details[open]")].map(d => d.dataset.id));
  // where each log was scrolled to, and the panel: drawn again, they'd start from the top on every new line
  const place = new Map([...document.querySelectorAll("#tasksBody details[data-id] pre")].map(pre =>
    [pre.closest("details").dataset.id, { top: pre.scrollTop, atEnd: pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 4 }]));
  const win = $("#tasksWin"), winTop = win ? win.scrollTop : 0;
  const cur = t.current, pj = t.project;   // (Projects' tasks run in a lane of their own, beside the rest)
  const problems = h => ((h.report && h.report.problems) || []);
  const running = (c, lane) => `<div class="task run"><div class="task-top"><span class="spin" aria-hidden="true"></span><b>${esc(c.label)}</b>` +
      (lane ? `<button class="ghost sm" data-task="stop" data-lane="${lane}" title="${esc(tr("Stop it at its next step: what it was changing is put back as it was"))}">Stop</button>`
        : (STOPPABLE.includes(c.task) ? `<button class="ghost sm" data-task="stop">Stop</button>` : "") +
          `<button class="ghost sm" data-task="force" title="End it now, whatever it's doing">Force stop</button>`) + `</div>` +
      (c.transfer ? transferHtml(c.transfer) : `<p class="task-msg">${esc(c.message || "Starting")}</p>`) +
      `<details class="live" data-id="${esc(c.id)}"${open.has(c.id) ? " open data-kept" : ""}><summary>Progress</summary><pre>${esc((c.log || []).join("\n"))}</pre></details></div>`;
  $("#tasksBody").innerHTML =
    `<h3>Running</h3>` + (cur || pj ? (cur ? running(cur) : "") + (pj ? running(pj, "projects") : "")
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
  for (const pre of document.querySelectorAll("#tasksBody details[data-id] pre")) {
    const d = pre.closest("details"), was = place.get(d.dataset.id);
    // what's running follows its newest lines, unless you've scrolled up to read; the rest stay where they were
    pre.scrollTop = d.classList.contains("live") && (!was || was.atEnd) ? pre.scrollHeight : was ? was.top : 0;
  }
  if (win) win.scrollTop = winTop;
  taskCount((cur ? 1 : 0) + (pj ? 1 : 0) + t.queue.length);
}
// Add packages: a repository folded away stays so while you're in Projects
document.addEventListener("toggle", e => {
  const d = e.target;
  if (!d.matches || !d.matches(".pj-repo") || PJ.pkFind) return;
  if (d.open) PJ.repoShut.delete(d.dataset.repo); else PJ.repoShut.add(d.dataset.repo);
}, true);
// opening what's running shows its newest lines (while it was closed, it had no size to scroll)
document.addEventListener("toggle", e => {
  const d = e.target;
  if (!d.matches || !d.matches("#tasksBody details.live[open]")) return;
  if (d.hasAttribute("data-kept")) { d.removeAttribute("data-kept"); return; }   // open before it was drawn again: left in place
  const pre = d.querySelector("pre");
  if (pre) pre.scrollTop = pre.scrollHeight;
}, true);
// What's running and waiting, in both lanes: Projects' tasks have a lane of their own (/api/status's project_job)
const jobCount = st => [st.job || {}, st.project_job || {}].reduce((n, j) => n + (j.running ? 1 : 0) + (j.queue || []).length, 0);
// A job the page was watching has ended: what it changed is read again (both pages' watchers call this)
function jobEnded(was, j) {
  if (was === "wishlists" && j.task !== "wishlists") loadSets();   // (the wishlists read show without a reload)
}
function taskCount(n) {
  const b = $("#tasksCount");
  if (b) { b.hidden = !n; b.textContent = n || ""; }
}
// A name for something new (a set): Hoard's own dialog, the name chosen, or "" when it's cancelled
function askName(title, value = "", opts = {}) {   // opts: {list: a datalist's id, max: longest}
  return new Promise(resolve => {
    const d = document.createElement("dialog");
    d.className = "ask";
    d.innerHTML = `<form method="dialog"><p><label for="askName">${esc(tr(title))}</label></p>` +
      `<p><input id="askName" maxlength="${opts.max || 60}"${opts.list ? ` list="${opts.list}"` : ""} style="width:100%;box-sizing:border-box"></p>` +
      `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("OK"))}</button></div></form>`;
    document.body.appendChild(d);
    const input = d.querySelector("input");
    input.value = value;
    // Enter is OK (a form's Enter goes to its first button, which is Cancel), but not while an input method is
    // still putting a word together (Japanese, Korean)
    input.addEventListener("keydown", e => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); d.close("yes"); } });
    d.addEventListener("close", () => { const v = d.returnValue === "yes" ? input.value.trim() : ""; d.remove(); resolve(v); }, { once: true });
    d.showModal();
    input.select();
  });
}
/* ---------- Projects (hoard/vpm): your Unity projects, shared with ALCOM and the VRChat Creator Companion (one list in
   all three), with their VPM packages, and your library in them: a new project made from a template with the packages
   and the products you choose (or a preset of them), and products put into a project later. What Hoard for Unity
   reports about a project (what it uses, its credits) shows with it. Changes are shown before they're made, and made
   as a task, so they show in Tasks and Stop stops them. */
const PJ = { view: "list", data: null, project: null, find: "", form: null, assets: null, busy: false, watching: false,
  reports: [], report: null, hiddenLeftOut: false,
  sub: "packages",       // a project's tab: packages, add (Add packages), library (From your library) or report
  pick: new Map(),       // Add packages: the ones ticked, each with the version chosen ("" for the newest)
  pkgs: null, pkFind: "", vers: {},   // the packages there are to add (for one Unity), and each one's versions
  repoShut: new Set(),   // Add packages' repositories you folded away
  job: {} };             // what Projects' own lane is doing (it runs beside the rest of Hoard's tasks)
const PJ_KINDS = { 0: "Unknown", 1: "Legacy SDK2", 2: "Legacy Worlds", 3: "Legacy Avatars", 4: "UPM Worlds", 5: "UPM Avatars",
  6: "UPM Starter", 7: "Worlds", 8: "Avatars", 9: "VPM Starter" };
const PJ_WHY = { requested: "Removed", legacy: "Replaced by a newer package", unused: "Nothing uses it any more" };
const PROJECT_STATUS = { yes: "In the project", partly: "Partly in the project", imported: "Imported, not found now" };
const CREDIT_STYLES = { List: "List", Markdown: "Markdown", ByCreator: "By creator" };
const pjKind = n => tr(PJ_KINDS[n] || "Unknown");
const pjQ = path => `?path=${encodeURIComponent(path)}`;
function openProjects(open) {   // Projects takes the whole window below the bar, until it's closed
  const w = $("#projectsWin"), show = open ?? w.hidden;
  w.hidden = !show;
  $("#projectsTab").setAttribute("aria-expanded", String(show));
  if (show) { loadProjects(); pjWatch(); }
}
let pjSplashing = null;
async function loadProjects(view) {
  if (view) PJ.view = view;
  const body = $("#projectsBody"), logo = $("#pjSplash");
  // the logo over Projects the first time it's opened on this page, until it's read them (as the page shows it while
  // it reads your library); then it's gone
  if (logo && !pjSplashing) pjSplashing = splash(logo, "hoard-projects-opened");
  try {
    // the shared list, and what Hoard for Unity reported (projects opened in Unity with Hoard, listed or not)
    const [r, rep] = await Promise.all([api("/api/vpm", { cache: "no-store" }), api("/api/projects", { cache: "no-store" })]);
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || String(r.status));
    PJ.data = data;
    const reported = rep.ok ? await rep.json() : {};
    PJ.reports = reported.projects || [];
    PJ.hiddenLeftOut = !!reported.hidden_left_out;
    if (PJ.view === "report") PJ.report = PJ.reports.find(x => x.id === (PJ.report || {}).id) || null;
    if (PJ.view === "report" && !PJ.report) PJ.view = "list";
    if (PJ.view === "project" && PJ.project) return openProject(PJ.project.path);
    if (PJ.view === "new" && !PJ.form) PJ.view = "list";
    if (PJ.view === "backups") await pjLoadBackups();
    drawProjects();
  } catch (e) { body.innerHTML = `<p class="none">${esc(tr("Projects couldn't be read just now."))} ${esc(e.message || "")}</p>`; }
  finally { if (pjSplashing) pjSplashing(); }
}
let pjDrawn = "";
const pjTicks = el => el.type === "checkbox";
function drawProjects() {
  const body = $("#projectsBody");
  const views = { list: pjList, project: pjProject, new: pjNew, repos: pjRepos, settings: pjSettings, report: pjReportView, backups: pjBackups,
                  addnew: pjAddNew, logs: pjLogs };
  // what you've typed or ticked in Repositories or Unity and folders and not saved yet stays when it's drawn again
  // (as it is when a task ends, or a save is refused)
  const typed = pjDrawn === PJ.view && (PJ.view === "repos" || PJ.view === "settings")
    ? [...body.querySelectorAll("input[id], textarea[id]")].filter(el => pjTicks(el) ? el.checked !== el.defaultChecked : el.value !== el.defaultValue)
      .map(el => [el.id, pjTicks(el) ? el.checked : el.value]) : [];
  body.innerHTML = (views[PJ.view] || pjList)();
  pjDrawn = PJ.view;
  for (const [id, v] of typed) {
    const el = document.getElementById(id);
    if (el) pjTicks(el) ? (el.checked = v) : (el.value = v);
  }
  if (PJ.view === "new") pjFillNew();
  if (PJ.view === "logs") pjLogWire();
  const find = $("#pjFind");
  if (find) { find.value = PJ.find; find.addEventListener("input", () => { PJ.find = find.value; pjFilter(); }); pjFilter(); }
  const pkFind = $("#pjPkFind");
  if (pkFind) { pkFind.addEventListener("input", () => { PJ.pkFind = pkFind.value; pjPkFilter(); }); pjPkFilter(); }
}
// Projects' views, as tabs along its top; a project, a new one, and Add packages open below them, with a way back
const PJ_TABS = [["list", "Projects"], ["repos", "Repositories"], ["backups", "Backups"], ["settings", "Unity and folders"], ["logs", "Logs"]];
const pjTabs = () => `<nav class="pj-tabs" aria-label="${esc(tr("Projects"))}">${PJ_TABS.map(([v, label]) =>
  `<button class="pj-tab" data-pj="${v === "list" ? "back" : v}"${PJ.view === v ? ' aria-current="page"' : ""}>${esc(tr(label))}</button>`).join("")}</nav>`;
// What Projects' own lane is doing now, above every view: its task, with Stop (what it was changing is put back)
function pjShowJob() {
  const box = $("#pjJob"), j = PJ.job || {};
  if (!box) return;
  const waiting = (j.queue || []).length;
  box.hidden = !j.running && !waiting;
  box.innerHTML = box.hidden ? "" : (j.running ? `<span class="spin" aria-hidden="true"></span><span class="pj-job-msg">${esc(j.message || j.job_label || "")}</span>` +
      `<button class="ghost sm" data-pj="stopjob">${esc(tr("Stop"))}</button>` : "") +
    (waiting ? `<span class="muted">${esc(tr("{0} more waiting", waiting))}</span>` : "");
}
const pjBack = () => `<button class="linkish pj-back" data-pj="back">${esc(tr("‹ All projects"))}</button>`;
function pjList() {
  const d = PJ.data, list = d.projects || [];
  const top = pjTabs() + `<div class="pj-top"><input type="search" id="pjFind" placeholder="${esc(tr("Find a project"))}" aria-label="${esc(tr("Find a project"))}">` +
    `<button class="primary sm" data-pj="new">${esc(tr("New project"))}</button>` +
    `<button class="ghost sm" data-pj="add">${esc(tr("Add a project..."))}</button></div>`;
  const bk = d.backups || {}, room = bk.room || {};
  const note = (room.low && bk.old_count ? `<p class="pj-warn pj-low">${esc(tr(bk.old_count === 1
      ? "The drive your project backups are on has {0} left, and {1} old backup takes {2}." : "The drive your project backups are on has {0} left, and {1} old backups take {2}.",
      sizeText(room.free), bk.old_count, sizeText(bk.old_size)))} <button class="linkish" data-pj="backups">${esc(tr("Delete or move them"))}</button></p>` : "") +
    `<p class="hint">${esc(tr("The same list as ALCOM's and the VRChat Creator Companion's: a project added in any of them shows in all three."))}</p>`;
  const others = pjUnlisted();
  if (!list.length) return top + note + `<p class="none">${esc(tr("No projects yet. Make one with New project, or add one you have."))}</p>` + others;
  const fav = list.filter(p => p.favorite), rest = list.filter(p => !p.favorite);
  return top + note + `<ul class="pj-list">${[...fav, ...rest].map(p => `<li class="pj-row${p.exists ? "" : " gone"}" data-path="${esc(p.path)}" data-hay="${esc(norm(p.name + " " + p.path))}">` +
    `<button class="pj-star" data-pj="star" aria-pressed="${p.favorite}" title="${esc(tr("Favourite"))}" aria-label="${esc(tr("Favourite"))}">★</button>` +
    `<span class="pj-main"><b translate="no">${esc(p.name)}</b><span class="meta" translate="no">${esc(p.path)}</span></span>` +
    `<span class="pj-what">${p.exists ? `${esc(pjKind(p.type))}${p.unity ? ` · <span translate="no">Unity ${esc(p.unity)}</span>` : ""}` +
      `${p.opened ? ` · ${esc(tr("opened {0}", ago(new Date(p.opened).toISOString())))}` : ""}` : esc(tr("The folder isn't there"))}</span>` +
    `<span class="pj-acts">${p.exists ? `<button class="primary sm" data-pj="unity">${esc(tr("Open in Unity"))}</button>` +
      `<button class="ghost sm" data-pj="manage">${esc(tr("Manage"))}</button>`
      : `<button class="ghost sm" data-pj="forget">${esc(tr("Take off the list"))}</button>`}</span></li>`).join("")}</ul>` + others;
}
// Projects Hoard for Unity reported (opened in Unity with Hoard's window) that aren't on the list: what's in them,
// and their credits, with a button to list them
const pjSame = (a, b) => String(a).replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase() === String(b).replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
function pjUnlisted() {
  const listedPaths = (PJ.data.projects || []).map(p => p.path);
  const rest = PJ.reports.filter(r => !listedPaths.some(p => pjSame(p, r.path)));
  if (!rest.length) return "";
  return `<h4>${esc(tr("Opened in Unity with Hoard, not on the list"))}</h4>` +
    (PJ.hiddenLeftOut ? `<p class="hint">${esc(tr("Hidden items are left out while your hidden library is locked."))}</p>` : "") +
    `<ul class="pj-list">${rest.map(r => {
      const used = r.assets.length, updates = r.assets.filter(a => a.update).length;
      return `<li class="pj-row" data-report="${esc(r.id)}" data-path="${esc(r.path)}" data-hay="${esc(norm(r.name + " " + r.path))}">` +
        `<span class="pj-main"><b translate="no">${esc(r.name)}</b><span class="meta" translate="no">${esc(r.path)}</span></span>` +
        `<span class="pj-what">${esc(tr(used === 1 ? "{0} asset from Hoard" : "{0} assets from Hoard", used))}` +
        `${updates ? ` · ${esc(tr(updates === 1 ? "{0} with an update" : "{0} with updates", updates))}` : ""}` +
        `${r.updated ? ` · ${esc(tr("opened {0}", ago(r.updated)))}` : ""}</span>` +
        `<span class="pj-acts"><button class="ghost sm" data-pj="list">${esc(tr("Add to the list"))}</button>` +
        `<button class="ghost sm" data-pj="report">${esc(tr("Credits"))}</button>` +
        `<button class="ghost sm" data-pj="forgetreport">${esc(tr("Forget"))}</button></span></li>`;
    }).join("")}</ul>`;
}
function pjReportView() {
  const r = PJ.report;
  return pjBack() + `<h3 class="pj-h" translate="no">${esc(r.name)}</h3><p class="meta" translate="no">${esc(r.path)}</p>` +
    `<div class="row"><button class="ghost sm" data-pj="list" data-path="${esc(r.path)}">${esc(tr("Add to the list"))}</button></div>` + pjReport(r);
}
const pjShownReport = () => PJ.view === "report" ? PJ.report : (PJ.project || {}).report;
function pjFilter() {
  const words = norm(PJ.find).split(/\s+/).filter(Boolean);
  for (const li of document.querySelectorAll(".pj-row")) li.hidden = !words.every(w => li.dataset.hay.includes(w));
}
async function openProject(path) {
  const r = await api(`/api/vpm/project${pjQ(path)}`, { cache: "no-store" });
  const data = await r.json();
  if (!r.ok) { toast(data.error || tr("That project couldn't be read.")); PJ.view = "list"; drawProjects(); return; }
  PJ.project = data; PJ.view = "project";
  drawProjects();
}
function pjProject() {
  const p = PJ.project;
  const editors = p.editors || [];
  const unity = p.editor ? `<button class="primary sm" data-pj="unity">${esc(tr("Open in Unity"))}</button>`
    : `<span class="pj-warn">${esc(tr("Unity {0} isn't installed. Install it with Unity Hub.", p.unity || "?"))}</span>` +
      (editors.length ? ` <select id="pjOther" aria-label="${esc(tr("Open in another version"))}"><option value="">${esc(tr("Open in another version…"))}</option>` +
        editors.map(e => `<option value="${esc(e.path)}" translate="no">Unity ${esc(e.version)}</option>`).join("") + `</select>` : "");
  const pk = p.packages || [], updates = pk.filter(x => x.latest).length;
  const rows = pk.map(x => `<tr data-name="${esc(x.name)}"><td><b translate="no">${esc(x.label)}</b><br><span class="muted" translate="no">${esc(x.name)}</span>` +
      (x.own ? ` <span class="pj-tag">${esc(tr("The project's own"))}</span>` : "") +
      (x.missing ? ` <span class="pj-tag warn">${esc(tr("Not installed"))}</span>` : "") + `</td>` +
    `<td class="v">${x.own || x.missing ? `<span translate="no">${esc(x.version)}</span>`
      : `<button class="ghost sm pj-ver" data-pj="versions" data-version="${esc(x.version)}" aria-label="${esc(tr("{0}, version {1}: choose another version", x.label, x.version))}">` +
        `<span translate="no">${esc(x.version)}</span> <span aria-hidden="true">▾</span></button>`}</td>` +
    `<td class="v">${x.latest ? `<button class="ghost sm" data-pj="update" data-version="${esc(x.latest)}">${esc(tr("Update to {0}", x.latest))}</button>` : ""}</td>` +
    `<td class="from" translate="no">${x.own ? "" : esc(x.repo || "")}</td>` +
    `<td class="v">${x.own ? "" : `<button class="ghost sm" data-pj="remove">${esc(tr("Remove"))}</button>`}</td></tr>`).join("");
  const head = `<thead><tr><th scope="col">${esc(tr("Package"))}</th><th scope="col" class="v">${esc(tr("Installed"))}</th>` +
    `<th scope="col" class="v">${esc(tr("Update"))}</th><th scope="col">${esc(tr("Comes from"))}</th>` +
    `<th scope="col" class="v"><span class="visually-hidden">${esc(tr("Remove"))}</span></th></tr></thead>`;
  const pre = (p.preloaded || []).slice().reverse();
  const subs = [["packages", tr("Packages")], ["add", tr("Add packages")], ["library", tr("From your library")],
                ...(p.report ? [["report", tr("What Hoard for Unity found")]] : [])];
  if (!subs.some(([k]) => k === PJ.sub)) PJ.sub = "packages";
  const part = {
    packages: () => (p.needs_repair ? `<p class="pj-warn">${esc(tr("Some packages aren't installed the way the project says."))} <button class="ghost sm" data-pj="repair">${esc(tr("Put it right"))}</button></p>` : "") +
      (updates ? `<div class="row"><button class="ghost sm" data-pj="updateall">${esc(tr(updates === 1 ? "Update {0} package" : "Update {0} packages", updates))}</button></div>` : "") +
      (pk.length ? `<table class="pj-pk">${head}<tbody>${rows}</tbody></table>` : `<p class="none">${esc(tr("No VPM packages in it yet. Add some in Add packages."))}</p>`),
    add: () => pjAddList(p.unity, new Set(pk.map(x => x.name))),
    library: () => `<div class="row"><button class="ghost sm" data-pj="addprod">${esc(tr("Put in products from your library"))}</button>` +
      (pre.length ? `<button class="ghost sm" data-pj="importlist">${esc(tr("Show the list in the project"))}</button>` : "") + `</div>` +
      (pre.length ? pjPutInTiles(pre) : `<p class="none">${esc(tr("Nothing from your library has been put in from Hoard yet."))}</p>`),
    report: () => pjReport(p.report) };
  return pjBack() + `<h3 class="pj-h" translate="no">${esc(p.name)}</h3><p class="meta" translate="no">${esc(p.path)}</p>` +
    `<p class="pj-facts">${esc(pjKind(p.type))}${p.unity ? ` · <span translate="no">Unity ${esc(p.unity)}</span>` : ""}</p>` +
    (p.open_in_unity ? `<p class="pj-warn">${esc(tr("Unity has this project open. Close it before changing packages, so nothing it has open is replaced under it."))}</p>` : "") +
    `<div class="row">${unity}<button class="ghost sm" data-pj="folder">${esc(tr("Open folder"))}</button>` +
    `<button class="ghost sm" data-pj="backup">${esc(tr("Back up"))}</button>` +
    `<button class="ghost sm" data-pj="forget">${esc(tr("Take off the list"))}</button>` +
    `<button class="ghost sm danger" data-pj="delete">${esc(tr("Delete from this computer..."))}</button></div>` +
    `<nav class="pj-tabs pj-subs" aria-label="${esc(tr("This project"))}">${subs.map(([k, label]) =>
      `<button class="pj-tab" data-pj="sub" data-sub="${k}"${PJ.sub === k ? ' aria-current="page"' : ""}>${esc(label)}${k === "packages" ? ` <span class="n">${pk.length}</span>` : ""}</button>`).join("")}</nav>` +
    `<div class="pj-part">${part[PJ.sub]()}</div>`;
}
// ---- Add packages: a tab of its own (a project's, or New project's), every package from your repositories that works
// in its Unity, each with a tick and, once ticked, the version to put in (the newest unless you choose another, #160)
const pjPkgKey = unityVersion => `${unityVersion || ""}|${(PJ.data.settings || {}).prerelease ? 1 : 0}`;
async function pjLoadPkgs(unityVersion) {
  const key = pjPkgKey(unityVersion);
  if (PJ.pkgs && (PJ.pkgs.for === key || PJ.pkgs.loading === key)) return;
  PJ.pkgs = { loading: key };
  const r = await api(`/api/vpm/packages?unity=${encodeURIComponent(unityVersion || "")}&pre=${(PJ.data.settings || {}).prerelease ? 1 : 0}`);
  PJ.pkgs = { for: key, list: r.ok ? (await r.json()).packages : [] };
  if (PJ.view === "addnew" || (PJ.view === "project" && PJ.sub === "add")) drawProjects();
}
function pjAddList(unityVersion, have) {
  const k = PJ.pkgs;
  if (!k || k.for !== pjPkgKey(unityVersion)) { pjLoadPkgs(unityVersion); return `<p class="none">${esc(tr("Reading the packages..."))}</p>`; }
  if (!k.list.length) return `<p class="none">${esc(tr("No packages yet: refresh the repositories first (Repositories, Refresh them all)."))}</p>`;
  const chosen = PJ.pick.size;
  // in groups by where they come from (a repository is usually one creator's): VRChat's own first, then yours by name,
  // then your package folders; each folds away, and stays as you left it
  const groups = new Map();
  for (const x of k.list) { if (!groups.has(x.repo)) groups.set(x.repo, []); groups.get(x.repo).push(x); }
  const rank = r => ({ vrchat: 0, repo: 1, folder: 2 })[groups.get(r)[0].source] ?? 1;
  const row = x => {
    const on = PJ.pick.has(x.name), already = have.has(x.name);
    return `<li data-hay="${esc(norm([x.label, x.name, x.author, x.repo, x.description, ...(x.keywords || [])].join(" ")))}" data-name="${esc(x.name)}">` +
      `<label class="check"><input type="checkbox" value="${esc(x.name)}"${on ? " checked" : ""}${already ? " disabled" : ""}> <span><b translate="no">${esc(x.label)}</b> <span class="muted" translate="no">${esc(x.version)}</span>` +
      (already ? ` <span class="pj-tag">${esc(tr("In it already"))}</span>` : "") + `<br>` +
      `<span class="muted" translate="no">${esc(x.name)}${x.author ? ` · ${esc(x.author)}` : ""}</span>` +
      (x.description ? `<br><span class="pj-desc">${esc(x.description)}</span>` : "") + `</span></label>` +
      (on ? pjVerPick(x.name, x.label) : "") + `</li>`;
  };
  return `<div class="pj-top"><input type="search" id="pjPkFind" value="${esc(PJ.pkFind)}" placeholder="${esc(tr("Find a package"))}" aria-label="${esc(tr("Find a package"))}"></div>` +
    [...groups.keys()].sort((a, b) => rank(a) - rank(b) || coll.compare(a, b)).map(r =>
      `<details class="pj-repo" data-repo="${esc(r)}"${PJ.repoShut.has(r) ? "" : " open"}><summary><b translate="no">${esc(r)}</b> ` +
      `<span class="n">${groups.get(r).length}</span></summary><ul class="pj-picklist pj-rows pj-addlist">${groups.get(r).map(row).join("")}</ul></details>`).join("") +
    `<div class="pj-addbar"><span class="muted" id="pjChosen">${esc(tr(chosen === 1 ? "{0} chosen" : "{0} chosen", chosen))}</span>` +
    `<button class="primary sm" data-pj="addchosen"${chosen ? "" : " disabled"}>${esc(tr("Add the chosen packages"))}</button></div>`;
}
function pjVerPick(name, label) {   // which version of a ticked package: the newest, unless you choose another
  const versions = PJ.vers[name] || [], picked = PJ.pick.get(name) || "";
  return `<select class="pj-pick-ver" data-name="${esc(name)}" aria-label="${esc(tr("Version of {0}", label))}"><option value="">${esc(tr("Newest"))}</option>` +
    versions.map(v => `<option value="${esc(v.version)}"${v.version === picked ? " selected" : ""} translate="no">${esc(v.version)}${v.pre ? ` (${esc(tr("prerelease"))})` : ""}</option>`).join("") + `</select>`;
}
function pjPkFilter() {   // (a repository with nothing found in it is left out while you look)
  const words = norm(PJ.pkFind).split(/\s+/).filter(Boolean);
  for (const li of document.querySelectorAll(".pj-addlist li")) li.hidden = !words.every(w => li.dataset.hay.includes(w));
  for (const g of document.querySelectorAll(".pj-repo")) {
    const shown = g.querySelectorAll(".pj-addlist li:not([hidden])").length;
    g.hidden = !shown;
    if (words.length && shown) g.open = true;   // (what you look for is shown, wherever it is)
  }
}
async function pjPickChanged(box) {   // a package ticked or not, in place (the list isn't drawn again, so it keeps its place)
  const li = box.closest("li"), name = box.value, unityVersion = PJ.view === "addnew" ? PJ.form.unity : PJ.project.unity;
  if (box.checked) {
    PJ.pick.set(name, "");
    li.insertAdjacentHTML("beforeend", pjVerPick(name, li.querySelector("b").textContent));
    if (!PJ.vers[name]) {
      PJ.vers[name] = await pjVersions(name, unityVersion);
      const sel = li.querySelector(".pj-pick-ver");
      if (sel && PJ.pick.has(name)) sel.outerHTML = pjVerPick(name, li.querySelector("b").textContent);
    }
  } else {
    PJ.pick.delete(name);
    li.querySelector(".pj-pick-ver")?.remove();
  }
  const n = PJ.pick.size, go = $("[data-pj=addchosen]");
  $("#pjChosen").textContent = tr(n === 1 ? "{0} chosen" : "{0} chosen", n);
  if (go) go.disabled = !n;
}
function pjAddNew() {   // New project's Add packages
  const f = PJ.form;
  return `<button class="linkish pj-back" data-pj="backnew">${esc(tr("‹ The new project"))}</button><h3 class="pj-h">${esc(tr("Add packages"))}</h3>` +
    `<p class="hint">${esc(tr("For Unity {0}. Each one ticked goes into the new project, with what it needs.", f.unity || "?"))}</p>` +
    pjAddList(f.unity, new Set(Object.keys(f.packages)));
}
// What Hoard for Unity reported about the project: what it uses, with updates, and its credits list
const inSet = p => [...new Set(p.assets.filter(a => a.tag_key && (a.status === "yes" || a.status === "partly")).map(a => a.tag_key))];
// ---- products as their library tiles, in Projects (what went into a project, and what Hoard for Unity found in one):
// the page's own item for each, found by its tag key and drawn as its tile is (its picture, name and creator, its
// store's colour), with a word beneath; choosing one shows it on the page. One that isn't in your library now is drawn
// from what's known of it, and only shown.
function pjItemsByKey() {
  const by = new Map();
  for (const a of T.all() || []) if (a.tag_key && !by.has(a.tag_key)) by.set(a.tag_key, a);
  return by;
}
function pjTile(item, known, below) {
  const name = item ? item.name : known.name || "", creator = item ? item.creator : known.creator || "";
  const fromKey = String(known.tag_key || "").split("/")[0];   // (one not in your library now: its store, from its key)
  const store = String((item || known).store || (STRIPE_STORES.includes(fromKey) ? fromKey : "local")).toLowerCase();
  const inner = `<span class="art">${item ? T.art(item) : setPlaceholder(name, creator)}${notch(store, [])}</span>` +
    `<span class="nm-t" translate="no">${esc(name)}</span><span class="cr" translate="no">${esc(creator ? tr("by {0}", creator) : "")}</span>`;
  return `<div class="slot ext pj-tile">` + (item ? `<button class="ext-main" data-pj="showitem" data-id="${esc(T.id(item))}">${inner}</button>`
    : `<span class="ext-main">${inner}</span>`) + (below ? `<span class="pj-below">${below}</span>` : "") + `</div>`;
}
// What went into a project from your library, newest first: a tile for each product, with its files and when beneath
// (and the folders each added, for a pointer that rests on it)
function pjPutInTiles(pre) {
  const items = pjItemsByKey(), by = new Map();
  for (const x of pre) { if (!by.has(x.tag_key)) by.set(x.tag_key, []); by.get(x.tag_key).push(x); }
  return `<div class="grid pj-tiles">${[...by.values()].map(xs => pjTile(items.get(xs[0].tag_key), xs[0],
    xs.slice(0, 3).map(x => `<span class="pj-file" translate="no"${(x.added || []).length ? ` title="${esc(tr("Added:") + " " + x.added.join(", "))}"` : ""}>${esc(x.label || x.file)}</span>`).join("") +
    (xs.length > 3 ? `<span class="muted">${esc(tr("{0} more", xs.length - 3))}</span>` : "") +
    (xs[0].when ? `<span class="muted">${esc(ago(xs[0].when))}</span>` : ""))).join("")}</div>`;
}
function pjReport(p) {
  const used = p.assets.length, style = p.credits.style, items = pjItemsByKey();
  return `<div class="proj"><h4>${esc(tr("What Hoard for Unity found in it"))}</h4>` +
    (used ? `<div class="grid pj-tiles">${p.assets.map(a => pjTile(items.get(a.tag_key), a,
        `<span class="st ${esc(a.status)}">${esc(tr(PROJECT_STATUS[a.status] || ""))}</span>${a.update ? ` <span class="upd">${esc(tr("Update"))}</span>` : ""}`)).join("")}</div>`
      : `<p class="none">${esc(tr("Nothing from Hoard is in it yet."))}</p>`) +
    `<h4>${esc(tr("Credits"))}</h4><div class="row"><select data-proj-style aria-label="${esc(tr("Credits style"))}">${Object.entries(CREDIT_STYLES).map(([k, v]) =>
      `<option value="${k}"${k === style ? " selected" : ""}>${esc(tr(v))}</option>`).join("")}</select>` +
    `<button class="ghost sm" data-proj="copy">${esc(tr("Copy"))}</button>` +
    (inSet(p).length ? `<button class="ghost sm" data-proj="set">${esc(tr("Make a set"))}</button>` : "") + `</div>` +
    `<textarea readonly aria-label="${esc(tr("Credits"))}">${esc(p.credits_text[style])}</textarea>` +
    `<p class="hint">The same list as <strong>Create Credits List</strong> in Unity, with what you changed there.</p></div>`;
}
// ---- a new project
function pjNewForm(preset) {
  const d = PJ.data, t = (d.templates || []).filter(x => x.available);
  const base = preset ? preset.template : (t.find(x => x.id.endsWith(".vrchat.avatars")) || t[0] || {}).id;
  const hoard = (d.hoard_for_unity || {}).package;   // Hoard for Unity: in every new project, unless you leave it out
  return { name: "", location: d.settings.projects_folder, template: base, unity: preset ? preset.unity : null,
           packages: { ...(preset ? preset.packages : hoard ? { [hoard]: "*" } : {}) }, picks: (preset ? preset.products : []).map(x => ({ ...x })),
           preset: preset ? preset.id : "" };
}
function pjNew() {
  const d = PJ.data, f = PJ.form;
  const templates = (d.templates || []).filter(x => x.available);
  const t = templates.find(x => x.id === f.template) || templates[0] || { unity: [] };
  const installed = new Set((d.editors || []).map(e => e.version));
  const presets = d.presets || [];
  return pjBack() + `<h3 class="pj-h">${esc(tr("New project"))}</h3>` +
    (presets.length ? `<div class="pj-field"><label for="pjPreset">${esc(tr("Start from a preset"))}</label><select id="pjPreset"><option value="">${esc(tr("None"))}</option>` +
      presets.map(x => `<option value="${esc(x.id)}"${x.id === f.preset ? " selected" : ""}>${esc(x.name)}</option>`).join("") + `</select></div>` : "") +
    `<div class="pj-field"><label for="pjName">${esc(tr("Name"))}</label><input id="pjName" maxlength="200" value="${esc(f.name)}"></div>` +
    `<p class="hint" id="pjNameNote" aria-live="polite"></p>` +
    `<div class="pj-field"><label for="pjWhere">${esc(tr("In the folder"))}</label><input id="pjWhere" value="${esc(f.location)}" translate="no">` +
    `<button class="ghost sm" data-browse data-pj="browse">${esc(tr("Browse…"))}</button></div>` +
    `<div class="pj-field"><label for="pjTemplate">${esc(tr("Template"))}</label><select id="pjTemplate">${templates.map(x =>
      `<option value="${esc(x.id)}"${x.id === t.id ? " selected" : ""}>${esc(tr(x.name))}</option>`).join("")}</select></div>` +
    `<div class="pj-field"><label for="pjUnity">${esc(tr("Unity"))}</label><select id="pjUnity">${(t.unity || []).map(u =>
      `<option value="${esc(u)}"${u === f.unity ? " selected" : ""} translate="no">${esc(u)}${installed.has(u) ? "" : " ✕"}</option>`).join("")}</select></div>` +
    `<p class="hint">${esc(tr("✕: not installed here. The project is made either way; install that Unity with Unity Hub to open it."))}</p>` +
    `<h4>${esc(tr("Packages"))}</h4><div class="pj-chips">${Object.entries(f.packages).map(([n, v]) =>
      `<button class="pill" data-pj="unpkg" data-name="${esc(n)}" title="${esc(tr("Leave out"))}"><span translate="no">${esc(n === (d.hoard_for_unity || {}).package ? "Hoard for Unity" : n)}</span> <b translate="no">${esc(v)}</b><span aria-hidden="true">×</span></button>`).join("") ||
      `<span class="muted">${esc(tr("Only the template's own."))}</span>`}</div>` +
    `<div class="row"><button class="ghost sm" data-pj="addpkg">${esc(tr("Add packages"))}</button></div>` +
    `<div id="pjSuggest"></div>` +
    `<h4>${esc(tr("From your library"))}</h4>` +
    (f.picks.length ? `<ul class="pj-pre">${f.picks.map((x, i) => `<li><b translate="no">${esc(x.product || "")}</b> <span class="muted" translate="no">${esc(x.label || x.file)}</span> ` +
      `<button class="linkish" data-pj="unpick" data-i="${i}">${esc(tr("Leave out"))}</button></li>`).join("")}</ul>` : `<p class="none">${esc(tr("Nothing yet."))}</p>`) +
    `<div class="row"><button class="ghost sm" data-pj="addprod">${esc(tr("Put in products from your library"))}</button>` +
    `<button class="ghost sm" data-pj="addset">${esc(tr("Put in a set"))}</button></div>` +
    `<div class="row pj-go"><button class="ghost sm" data-pj="savepreset">${esc(tr("Save as a preset"))}</button>` +
    (f.preset ? `<button class="ghost sm" data-pj="exportpreset">${esc(tr("Save it for ALCOM too"))}</button><button class="ghost sm" data-pj="delpreset">${esc(tr("Delete the preset"))}</button>` : "") +
    `<button class="primary" data-pj="make">${esc(tr("Make the project"))}</button></div>`;
}
function pjFillNew() {
  const f = PJ.form;
  syncBrowse();
  const name = $("#pjName"), where = $("#pjWhere");
  const check = async () => {
    f.name = name.value; f.location = where.value;
    const note = $("#pjNameNote");
    if (!f.name.trim()) { note.textContent = ""; return; }
    const r = await apiPost("/api/vpm/check-name", { name: f.name, location: f.location });
    note.textContent = r.ok ? tr(r.data.problem || r.data.warning || "") : "";
    note.classList.toggle("bad", !!(r.ok && r.data.problem));
  };
  name.addEventListener("input", check);
  where.addEventListener("change", check);
  $("#pjTemplate").addEventListener("change", e => { f.template = e.target.value; f.unity = null; drawProjects(); });
  $("#pjUnity").addEventListener("change", e => { f.unity = e.target.value; });
  if (!f.unity && $("#pjUnity").value) f.unity = $("#pjUnity").value;
  if ($("#pjPreset")) $("#pjPreset").addEventListener("change", e => {
    const p = (PJ.data.presets || []).find(x => x.id === e.target.value);
    const keep = { name: f.name, location: f.location };
    PJ.form = { ...pjNewForm(p), ...keep };
    drawProjects();
  });
  pjSuggest();
  name.focus();
}
// the VPM packages the chosen products need (lilToon, Modular Avatar...), to add with a tick
async function pjSuggest() {
  const box = $("#pjSuggest"), f = PJ.form;
  if (!box || !f.picks.length) return;
  const found = new Map();
  for (const key of [...new Set(f.picks.map(x => x.key))]) {
    const r = await api(`/api/vpm/product?key=${encodeURIComponent(key)}`);
    if (!r.ok) continue;
    for (const s of (await r.json()).suggested || []) if (!(s.package in f.packages)) found.set(s.package, s);
  }
  if (!found.size || !$("#pjSuggest")) return;
  box.innerHTML = `<p class="hint">${esc(tr("What you're putting in needs these:"))}</p><div class="pj-chips">` +
    [...found.values()].map(s => `<button class="chip pj-sugg" data-pj="sugg" data-name="${esc(s.package)}" data-repo="${esc(s.repo || "")}" data-added="${s.repo_added}" translate="no">${esc(s.package)}</button>`).join("") + `</div>`;
}
// ---- repositories, and Unity and folders
function pjRepos() {
  const rs = PJ.data.repos || [];
  return pjTabs() + `<p class="hint">${esc(tr("Where packages come from. The same list ALCOM and the Creator Companion use."))}</p>` +
    `<h4>${esc(tr("Add a repository"))}</h4><div class="pj-field"><label for="pjRepoUrl">${esc(tr("Its address"))}</label>` +
    `<input id="pjRepoUrl" placeholder="https://" translate="no"><button class="primary sm" data-pj="addrepo">${esc(tr("Add"))}</button></div>` +
    `<details class="pj-more"><summary>${esc(tr("For a private repository"))}</summary><p class="hint">${esc(tr("Headers it asks for, one a line (Name: value). They're sent to its own address only."))}</p>` +
    `<textarea id="pjRepoHeaders" rows="3" translate="no"></textarea></details>` +
    `<h4>${esc(tr(rs.length === 1 ? "{0} repository" : "{0} repositories", rs.length))}</h4>` +
    `<ul class="pj-list">${rs.map(r => `<li class="pj-row"><span class="pj-main"><b translate="no">${esc(r.label)}</b><span class="meta" translate="no">${esc(r.url || r.path)}</span>` +
      (r.error ? `<span class="pj-warn">${esc(r.error)}</span>` : "") + `</span>` +
      `<span class="pj-what">${r.loaded ? esc(tr(r.packages === 1 ? "{0} package" : "{0} packages", r.packages)) : esc(tr("Not fetched yet"))}</span>` +
      `<span class="pj-acts">${r.builtin ? `<span class="muted">${esc(tr("VRChat's"))}</span>` : `<button class="ghost sm" data-pj="unrepo" data-path="${esc(r.path)}">${esc(tr("Remove"))}</button>`}</span></li>`).join("")}</ul>` +
    `<div class="row"><button class="ghost sm" data-pj="refresh">${esc(tr("Refresh them all"))}</button></div>`;
}
function pjSettings() {
  const d = PJ.data, s = d.settings, eds = d.editors || [];
  return pjTabs() +
    `<h4>${esc(tr("Unity editors"))}</h4>` + (eds.length ? `<ul class="pj-pre">${eds.map(e => `<li translate="no"><b>Unity ${esc(e.version)}</b> <span class="muted">${esc(e.path)}</span></li>`).join("")}</ul>`
      : `<p class="none">${esc(tr("No Unity found. Install Unity with Unity Hub (the VRChat SDK's own version is 2022.3.22f1)."))}</p>`) +
    `<p class="hint">${esc(tr("Found the way ALCOM finds them: those Unity Hub installed or was told about."))}</p>` +
    `<h4>${esc(tr("Folders"))}</h4>` +
    `<div class="pj-field"><label for="pjProjectsFolder">${esc(tr("New projects go in"))}</label><input id="pjProjectsFolder" value="${esc(s.projects_folder)}" translate="no"></div>` +
    `<div class="pj-field"><label for="pjBackupsFolder">${esc(tr("Backups go in"))}</label><input id="pjBackupsFolder" value="${esc(s.backups_folder)}" translate="no"></div>` +
    `<label class="check"><input type="checkbox" id="pjPrerelease"${s.prerelease ? " checked" : ""}> ${esc(tr("Offer prerelease versions of packages"))}</label>` +
    `<div class="row"><button class="primary sm" data-pj="savesettings">${esc(tr("Save"))}</button></div>` +
    `<p class="hint">${esc(tr("Kept in the Creator Companion's settings, so ALCOM and the Creator Companion use them too."))}</p>`;
}
// ---- backups (vpm/backup.py): every project backup, which are old (past the newest few of a project, and older
// than some days), and the room left on their drive, to delete the old ones or move them to a drive with more room
const PJ_KEEP = [1, 2, 3, 5, 10], PJ_DAYS = { 7: "a week", 14: "2 weeks", 30: "a month", 90: "3 months", 180: "6 months", 365: "a year" };
async function pjLoadBackups() {
  const r = await apiPost("/api/vpm/backups", {});
  if (!r.ok) { toast(r.data.error || tr("Your backups couldn't be read just now.")); return false; }
  PJ.backups = r.data;
  return true;
}
function pjBackupRow(b) {
  return `<li class="pj-row pj-bk${b.old ? " old" : ""}"><label class="pj-main check"><input type="checkbox" class="pj-bkpick" value="${esc(b.path)}">` +
    `<span><b translate="no">${esc(b.project)}</b><span class="meta">${esc(whenDone(b.when))} · ${esc(sizeText(b.size))}</span></span></label>` +
    `<span class="pj-what">${b.old ? esc(tr("Old")) : ""}</span></li>`;
}
// ---- Logs, as ALCOM's Logs page and the Creator Companion's Logs tab have theirs: what Hoard did to your projects,
// packages and repositories since it started, and what went wrong (hoard/vpm/logbook.py), oldest first, found by its
// words and its level. New entries come in while it's open; each start of Hoard writes its own to the logs folder.
const PJ_LEVELS = [["info", "Info"], ["warning", "Warnings"], ["error", "Errors"]];
const PJ_LEVEL_NAMES = { info: "Info", warning: "Warning", error: "Error" };
const PJLOG = { run: null, entries: [], last: 0, find: "", follow: true, levels: new Set(["info", "warning", "error"]), timer: 0, gen: 0 };
try {   // (which levels you show is kept, in this browser)
  const kept = JSON.parse(localStorage.getItem("hoard-pj-log-levels") || "null");
  if (Array.isArray(kept)) PJLOG.levels = new Set(kept.filter(k => PJ_LEVEL_NAMES[k]));
} catch (e) { /* every level, then */ }
function pjLogs() {
  return pjTabs() + `<div class="pj-top pj-logtop"><input type="search" id="pjLogFind" placeholder="${esc(tr("Find in the log"))}" aria-label="${esc(tr("Find in the log"))}">` +
    `<span class="pj-levels">${PJ_LEVELS.map(([k, label]) => `<label class="check lv-${k}"><input type="checkbox" data-pjlevel="${k}"` +
      `${PJLOG.levels.has(k) ? " checked" : ""}> ${esc(tr(label))}</label>`).join("")}</span>` +
    `<button class="ghost sm" data-pj="logfollow" aria-pressed="${PJLOG.follow}">${esc(tr("Follow new entries"))}</button>` +
    `<button class="ghost sm" data-pj="logfolder">${esc(tr("Open logs folder"))}</button></div>` +
    `<p class="hint">${esc(tr("What Hoard did to your projects, packages and repositories since it started, and what went wrong, as ALCOM and the Creator Companion each keep a log of their own. Each time Hoard starts, it writes them to a log in the logs folder."))}</p>` +
    `<div class="pj-logbox" id="pjLogBox" tabindex="0" role="region" aria-label="${esc(tr("Logs"))}"><table class="pj-log">` +
    `<thead><tr><th>${esc(tr("Time"))}</th><th>${esc(tr("Level"))}</th><th>${esc(tr("Message"))}</th></tr></thead>` +
    `<tbody id="pjLogRows"></tbody></table><p class="none" id="pjLogNone" hidden></p></div>`;
}
function pjLogWire() {
  const find = $("#pjLogFind");
  find.value = PJLOG.find;
  find.addEventListener("input", () => { PJLOG.find = find.value; pjLogRows(); });
  for (const box of document.querySelectorAll("[data-pjlevel]")) box.addEventListener("change", () => {
    if (box.checked) PJLOG.levels.add(box.dataset.pjlevel); else PJLOG.levels.delete(box.dataset.pjlevel);
    try { localStorage.setItem("hoard-pj-log-levels", JSON.stringify([...PJLOG.levels])); } catch (e) { /* kept for now */ }
    pjLogRows();
  });
  pjLogRows(true);
  pjLogPoll();
}
const pjLogRow = e => `<tr class="lv-${e.level}"><td class="t">${esc(new Date(e.time).toLocaleString(document.documentElement.lang || undefined))}</td>` +
  `<td class="lv">${esc(tr(PJ_LEVEL_NAMES[e.level] || "Info"))}</td><td class="m" translate="no">${esc(e.message)}</td></tr>`;
function pjLogRows(toEnd = false) {
  const rows = $("#pjLogRows"), box = $("#pjLogBox");
  if (!rows) return;
  const words = norm(PJLOG.find).split(/\s+/).filter(Boolean);
  const shown = PJLOG.entries.filter(e => PJLOG.levels.has(e.level) && words.every(w => norm(e.message).includes(w)));
  rows.innerHTML = shown.map(pjLogRow).join("");
  const none = $("#pjLogNone");
  none.hidden = shown.length > 0;
  none.textContent = tr(PJLOG.entries.length ? "Nothing in the log matches." : "Nothing has been logged since Hoard started.");
  if (toEnd || PJLOG.follow) box.scrollTop = box.scrollHeight;
}
async function pjLogPoll() {   // while Logs is open: what's new, every second or so
  clearTimeout(PJLOG.timer);
  const mine = ++PJLOG.gen, open = () => !$("#projectsWin").hidden && PJ.view === "logs";
  if (!open()) return;
  try {
    const r = await api(`/api/vpm/logs?after=${PJLOG.last}`, { cache: "no-store" });
    const got = r.ok ? await r.json() : null;
    if (got && mine === PJLOG.gen) {
      if (got.run !== PJLOG.run) {   // Hoard started again: its log starts again too
        if (PJLOG.run !== null && PJLOG.last) { PJLOG.run = got.run; PJLOG.entries = []; PJLOG.last = 0; return pjLogPoll(); }
        PJLOG.run = got.run;
      }
      if (got.entries.length) {
        PJLOG.entries.push(...got.entries);
        PJLOG.entries.splice(0, Math.max(0, PJLOG.entries.length - 2000));
        PJLOG.last = got.entries[got.entries.length - 1].n;
        pjLogRows();
      }
    }
  } catch (e) { /* Hoard's away for now: tried again */ }
  if (mine === PJLOG.gen && open()) PJLOG.timer = setTimeout(pjLogPoll, 1500);
}
function pjBackups() {
  const k = PJ.backups;
  if (!k) return pjTabs() + `<p class="none">${esc(tr("Reading your backups..."))}</p>`;
  const room = k.room || {}, list = k.backups || [], moved = k.moved || [];
  const sel = (id, opts, value) => `<select id="${id}">${opts.map(([v, label]) => `<option value="${v}"${v === value ? " selected" : ""}>${esc(label)}</option>`).join("")}</select>`;
  return pjTabs() +
    `<p class="hint">${esc(tr(list.length === 1 ? "{0} backup, {1}, in" : "{0} backups, {1}, in", list.length, sizeText(k.size)))} <span translate="no">${esc(k.folder)}</span>` +
    (room.total ? `. ${esc(tr("Its drive has {0} free of {1}.", sizeText(room.free), sizeText(room.total)))}` : "") +
    ` <button class="linkish" data-pj="bkopen">${esc(tr("Open folder"))}</button></p>` +
    (room.low ? `<p class="pj-warn">${esc(tr("That drive is low on room: delete old backups, or move them to another drive."))}</p>` : "") +
    `<div class="pj-field pj-bkrule"><label for="pjBkKeep">${esc(tr("Old means past the newest"))}</label>` +
    sel("pjBkKeep", PJ_KEEP.map(n => [n, tr(n === 1 ? "{0} backup of a project" : "{0} backups of a project", n)]), k.keep) +
    `<label for="pjBkDays">${esc(tr("and older than"))}</label>` + sel("pjBkDays", Object.entries(PJ_DAYS).map(([d, label]) => [Number(d), tr(label)]), k.days) + `</div>` +
    (k.old_count ? `<p>${esc(tr(k.old_count === 1 ? "{0} old backup takes {1}." : "{0} old backups take {1}.", k.old_count, sizeText(k.old_size)))}</p>` +
      `<div class="row"><button class="ghost sm" data-pj="bkdelold">${esc(tr("Delete the old ones"))}</button>` +
      `<button class="ghost sm" data-pj="bkmoveold">${esc(tr("Move the old ones..."))}</button></div>`
      : `<p class="muted">${esc(tr("No old backups."))}</p>`) +
    (list.length ? `<ul class="pj-list">${list.map(pjBackupRow).join("")}</ul>` : `<p class="none">${esc(tr("No project backups here yet. Back up a project from Manage."))}</p>`) +
    (moved.length ? `<h4>${esc(tr("Moved to"))} <span translate="no">${esc(k.moved_to)}</span></h4><ul class="pj-list">${moved.map(pjBackupRow).join("")}</ul>` : "") +
    (list.length || moved.length ? `<div class="row"><button class="ghost sm" data-pj="bkdel">${esc(tr("Delete the chosen ones"))}</button>` +
      `<button class="ghost sm" data-pj="bkmove">${esc(tr("Move the chosen ones..."))}</button></div>` : "");
}
async function pjBackupsDelete(paths) {
  const all = [...(PJ.backups.backups || []), ...(PJ.backups.moved || [])].filter(b => paths.includes(b.path));
  if (!all.length) { toast(tr("Choose the backups first.")); return; }
  const size = sizeText(all.reduce((t, b) => t + b.size, 0));
  if (!await ask(tr(all.length === 1 ? "Delete {0} backup ({1})? It can't be got back." : "Delete {0} backups ({1})? They can't be got back.", all.length, size), tr("Delete"))) return;
  const r = await apiPost("/api/vpm/backups/delete", { paths: all.map(b => b.path) });
  if (!r.ok) { toast(r.data.error || tr("They couldn't be deleted.")); return; }
  toast(tr(r.data.deleted === 1 ? "Deleted {0} backup, freeing {1}." : "Deleted {0} backups, freeing {1}.", r.data.deleted, sizeText(r.data.freed)));
  if (await pjLoadBackups()) drawProjects();
}
async function pjBackupsMove(paths) {
  if (!paths.length) { toast(tr("Choose the backups first.")); return; }
  const shown = pjDialog(`<p>${esc(tr(paths.length === 1 ? "Move {0} backup to another folder, a drive with more room say? It's copied, checked, and only then deleted here." : "Move {0} backups to another folder, a drive with more room say? Each is copied, checked, and only then deleted here.", paths.length))}</p>` +
    `<div class="pj-field"><label for="pjBkTo">${esc(tr("Move them to"))}</label><input id="pjBkTo" value="${esc(PJ.backups.moved_to || "")}" placeholder="E:\\Old backups" translate="no">` +
    `<button type="button" class="ghost sm" data-browse>${esc(tr("Browse…"))}</button></div>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Move"))}</button></div>`);
  const dlg = [...document.querySelectorAll("dialog.pj-dlg")].pop();
  const browse = dlg && dlg.querySelector("[data-browse]");
  if (browse) { browse.hidden = !canPick(); browse.addEventListener("click", () => browseInto(dlg.querySelector("#pjBkTo"))); }
  const res = await shown;
  if (!res.ok) return;
  const to = res.dlg.querySelector("#pjBkTo").value.trim();
  if (!to) { toast(tr("Choose a folder to move them to, by its full path.")); return; }
  pjRun("/api/vpm/backups/move", { paths, to });
}
// ---- dialogs: choosing packages, choosing products, and the changes before they're made
function pjDialog(html, cls = "") {
  return new Promise(resolve => {
    const dlg = document.createElement("dialog");
    dlg.className = `ask pj-dlg ${cls}`;
    dlg.innerHTML = `<form method="dialog">${html}</form>`;
    document.body.appendChild(dlg);
    dlg.addEventListener("close", () => { const v = dlg.returnValue; resolve({ ok: v === "yes", value: v, dlg }); setTimeout(() => dlg.remove(), 0); }, { once: true });
    dlg.showModal();
  });
}
// A package's versions there are to choose from (newest first), for this Unity: [{version, pre}]
async function pjVersions(name, unityVersion, keep = "") {
  const pre = !!(PJ.data.settings || {}).prerelease;
  const r = await api(`/api/vpm/versions?name=${encodeURIComponent(name)}&unity=${encodeURIComponent(unityVersion || "")}` +
                      `&pre=${pre ? 1 : 0}&keep=${encodeURIComponent(keep)}`);
  return r.ok ? (await r.json()).versions : [];
}
// Another version of an installed package (issue #160): the one chosen, or "" for none
async function pjChooseVersion(name, label, current, unityVersion) {
  const list = await pjVersions(name, unityVersion, current);
  if (!list.some(v => v.version !== current)) { toast(tr("No other version of {0} works with this project's Unity.", label)); return ""; }
  const dlgP = pjDialog(`<p><b translate="no">${esc(label)}</b> <span class="muted" translate="no">${esc(name)}</span></p>` +
    `<p class="hint">${esc(tr("Choose the version to install. An older one replaces the one it has, and the packages it needs change to match."))}</p>` +
    (list.length > 12 ? `<p><input type="search" id="pjVerFind" placeholder="${esc(tr("Find a version"))}" aria-label="${esc(tr("Find a version"))}" style="width:100%;box-sizing:border-box"></p>` : "") +
    `<ul class="pj-picklist pj-vers" role="radiogroup" aria-label="${esc(tr("Versions"))}">${list.map(v => `<li data-hay="${esc(v.version)}"><label class="check">` +
      `<input type="radio" name="pjVer" value="${esc(v.version)}"${v.version === current ? " checked" : ""}> <span translate="no">${esc(v.version)}</span>` +
      (v.version === current ? ` <span class="pj-tag">${esc(tr("Installed now"))}</span>` : "") +
      (v.pre ? ` <span class="pj-tag warn">${esc(tr("Prerelease"))}</span>` : "") + `</label></li>`).join("")}</ul>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Use this version"))}</button></div>`, "wide");
  const dlg = document.querySelector("dialog.pj-dlg:last-of-type");
  const find = dlg.querySelector("#pjVerFind");
  if (find) find.addEventListener("input", () => {
    const q = find.value.trim();
    for (const li of dlg.querySelectorAll(".pj-vers li")) li.hidden = !!q && !li.dataset.hay.includes(q);
  });
  (dlg.querySelector(".pj-vers input:checked") || {}).scrollIntoView?.({ block: "nearest" });
  const res = await dlgP;
  const picked = res.ok ? (res.dlg.querySelector(".pj-vers input:checked") || {}).value || "" : "";
  return picked === current ? "" : picked;
}
// What to put in of one product: its .unitypackage files and VPM packages, each with a tick
async function pjProductContents(key) {
  const r = await api(`/api/vpm/product?key=${encodeURIComponent(key)}`);
  const data = await r.json();
  if (!r.ok) { toast(data.error || tr("That product couldn't be read.")); return null; }
  return data;
}
// ---- Put in products from your library (a project's From your library, and New project's): the Downloads page, in
// Select mode for that project, with nothing to do there but Add to project or Cancel. What's chosen goes in as Put in a
// project... puts it; both go back to the project. From the Library page it's Downloads that opens (sessionStorage
// carries what it's for, and a new project's form as far as it's filled in).
const PJPICK = { for: null };   // what's being chosen for: {view: "project", path, name} or {view: "new", name, form}
const PICK_KEY = "hoard-pick-for";
const PICK_ACTIONS = () => ({ main: [{ label: "Add to project", primary: true, run: list => pickAdd(list) }] });
function pjPickFromDownloads() {
  const f = PJ.form;
  if (PJ.view === "new") {   // (what's typed, as it is now)
    if ($("#pjName")) f.name = $("#pjName").value;
    if ($("#pjWhere")) f.location = $("#pjWhere").value;
  }
  const pick = PJ.view === "new" ? { view: "new", name: f.name.trim() || tr("the new project"), form: f }
    : { view: "project", path: PJ.project.path, name: PJ.project.name };
  if (T.pickHere) return pickStart(pick);
  try { sessionStorage.setItem(PICK_KEY, JSON.stringify(pick)); }
  catch (e) { toast(tr("That can't be done.")); return; }
  location.href = "/downloads";
}
function pickResume() {   // the Downloads page, opened from the Library page to choose for a project
  let pick = null;
  try { pick = JSON.parse(sessionStorage.getItem(PICK_KEY) || "null"); sessionStorage.removeItem(PICK_KEY); } catch (e) { return; }
  if (pick && (pick.view === "new" ? pick.form && Array.isArray(pick.form.picks) : typeof pick.path === "string")) pickStart(pick);
}
function pickStart(pick) {
  PJPICK.for = pick;
  openProjects(false);
  T.pickHere();   // (what's downloaded: products, not sets)
  setSelecting(true);
}
function pickEnd() {   // back to the project, or to the new one
  const pick = PJPICK.for;
  PJPICK.for = null;
  setSelecting(false);
  if (!pick) return;
  if (pick.view === "new") { PJ.form = pick.form; PJ.view = "new"; }
  else {
    if (!PJ.project || PJ.project.path !== pick.path) PJ.project = { path: pick.path, name: pick.name };
    PJ.view = "project"; PJ.sub = "library";
  }
  openProjects(true);
}
async function pickAdd(list) {
  const pick = PJPICK.for;
  if (pick && await (pick.view === "new" ? pjFormWith(pick.form, list) : pjPutIn(pick, list))) pickEnd();
}   // (nothing could go in, or a question was cancelled: still choosing)
// What to put in of one product: its .unitypackage files and VPM packages, each with a tick (one of several
// variants left to choose), and the VPM packages it needs. null when it's cancelled.
async function pjChooseContents(product) {
  const many = product.contents.filter(c => c.kind === "unitypackage").length > 1;
  const pick = await pjDialog(`<p><b translate="no">${esc(product.name)}</b></p>` +
    (many ? `<p class="hint">${esc(tr("It has more than one package: choose the ones this project needs (one for PC, say, not every variant)."))}</p>` : "") +
    `<ul class="pj-picklist">${product.contents.map((c, i) => `<li><label class="check"><input type="checkbox" value="${i}"${many && c.kind === "unitypackage" ? "" : " checked"}> ` +
      `<span><span translate="no">${esc(c.label)}</span> <span class="muted">${esc(c.kind === "unitypackage" ? tr("Unity package") : tr("VPM package"))}${c.member ? ` · <span translate="no">${esc(c.file)}</span>` : ""}</span></span></label></li>`).join("")}</ul>` +
    pjNeedsList(product.suggested, "It needs these too, from their own repositories:") + pjAlready(product.already || []) +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Put these in"))}</button></div>`);
  if (!pick.ok) return null;
  const boxes = [...pick.dlg.querySelectorAll("input[type=checkbox]:checked")];
  const picks = boxes.filter(b => !b.dataset.sugg).map(b => product.contents[+b.value]).map(c =>
    ({ key: product.key, kind: c.kind, file: c.file, member: c.member, label: c.label, product: product.name }));
  const sugg = boxes.filter(b => b.dataset.sugg).map(b => product.suggested[+b.dataset.sugg]);
  return { picks, suggested: sugg };
}
// What products need (/api/vpm/product), as the project stands: what it has already (or New project's form has) isn't
// offered again, only said; and a repository you have that gives a package already is used for it, never added again
// (in_repo), so one added in ALCOM or the Creator Companion under another address isn't added twice.
function pjSplitNeeds(product, have) {
  const keep = [], already = [];
  for (const s of product.suggested || []) (s.in_project != null || (have && have.has(s.package)) ? already : keep).push(s);
  product.suggested = keep;
  product.already = already;
  return product;
}
const pjNeedsList = (list, heading) => list.length ? `<p class="hint">${esc(tr(heading))}</p><ul class="pj-picklist">${list.map((s, i) =>
  `<li><label class="check"><input type="checkbox" data-sugg="${i}" checked> <span translate="no">${esc(s.package)}</span>` +
  (s.repo && !s.repo_added ? ` <span class="muted">(${esc(tr("adds the repository {0}", s.repo))})</span>`
    : s.in_repo ? ` <span class="muted">(${trHTML("from {0}", `<span translate="no">${esc(s.in_repo)}</span>`)})</span>` : "") +
  `</label></li>`).join("")}</ul>` : "";
const pjAlready = list => list.length ? `<p class="hint pj-already">${trHTML("Already in the project: {0}.",
  `<span translate="no">${esc(listed(list.map(s => s.package + (s.in_project ? " " + s.in_project : ""))))}</span>`)}</p>` : "";
// ---- products into a project from the selection bar and right-click, on both pages: Put in a project..., and New
// project with these... What's put in of each is all its packages, unless it has several to choose from (a PC and a
// Quest one, say), when it asks; what they need (lilToon, Modular Avatar...) comes with a tick to leave it out.
const PROJECT_ACTIONS = () => ({ name: "Projects", items: [
  { label: "Put in a project...", run: list => putInProject(list) },
  { label: "New project with these...", run: list => newProjectWith(list) }] });
// {picks, suggested, already (what the project has of what they need), skipped (not downloaded, or no package in it)},
// or null; where: {path} of a project on the list, or {have}: the packages New project's form has
async function pjPicksFor(list, where = {}) {
  const picks = [], suggested = new Map(), already = new Map(), skipped = [];
  for (const a of list) {
    const r = a.tag_key ? await api(`/api/vpm/product?key=${encodeURIComponent(a.tag_key)}${where.path ? "&path=" + encodeURIComponent(where.path) : ""}`) : null;
    const product = r && r.ok ? pjSplitNeeds(await r.json(), where.have) : null;
    if (!product || !product.contents.length) { skipped.push(a.name); continue; }
    for (const s of product.already) already.set(s.package, s);
    let got = { picks: product.contents.map(c => ({ key: product.key, kind: c.kind, file: c.file, member: c.member,
                                                     label: c.label, product: product.name })), suggested: product.suggested };
    if (product.contents.filter(c => c.kind === "unitypackage").length > 1) {
      got = await pjChooseContents(product);
      if (!got) return null;
    }
    picks.push(...got.picks);
    for (const s of got.suggested) suggested.set(s.package, s);
  }
  if (skipped.length) toast(tr("Left out, with no Unity package or VPM package downloaded: {0}.", listed(skipped)));
  return { picks, suggested: [...suggested.values()], already: [...already.values()], skipped };
}
async function pjLoaded() {   // the projects, for the menus (read when Projects hasn't been opened yet)
  if (!PJ.data) {
    const r = await api("/api/vpm", { cache: "no-store" });
    if (r.ok) PJ.data = await r.json();
  }
  return PJ.data;
}
async function putInProject(list) {
  const d = await pjLoaded();
  const projects = ((d && d.projects) || []).filter(p => p.exists);
  if (!projects.length) {
    toast(tr("No projects yet: New project with these makes one with them in it."));
    return;
  }
  const order = [...projects.filter(p => p.favorite), ...projects.filter(p => !p.favorite)];
  const res = await pjDialog(`<p><b>${esc(tr("Put in a project"))}</b></p>` +
    `<ul class="pj-picklist">${order.map(p => `<li><button class="linkish" value="${esc(p.path)}" translate="no">${esc(p.name)}</button> ` +
      `<span class="muted">${esc(pjKind(p.type))}${p.unity ? ` · <span translate="no">Unity ${esc(p.unity)}</span>` : ""}</span></li>`).join("")}</ul>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button>` +
    `<button class="ghost" value="new">${esc(tr("New project with these..."))}</button></div>`, "wide");
  if (res.value === "new") return newProjectWith(list);
  const project = projects.find(p => p.path === res.value);
  if (project) await pjPutIn(project, list);
}
// These products into a project: what's in each (asked when one has several to choose from), shown before it's put
// in, with what they need from their own repositories ticked to come too. True when it's started.
async function pjPutIn(project, list) {
  const got = await pjPicksFor(list, { path: project.path });
  if (!got || !got.picks.length) return false;
  const ok = await pjDialog(`<p><b>${esc(tr("Put these in {0}?", project.name))}</b></p>` +
    `<ul class="pj-picklist">${got.picks.map(x => `<li><b translate="no">${esc(x.product)}</b> <span class="muted" translate="no">${esc(x.label || x.file)}</span></li>`).join("")}</ul>` +
    pjNeedsList(got.suggested, "They need these too, from their own repositories:") + pjAlready(got.already) +
    `<p class="hint">${esc(tr("Nothing already in the project is replaced."))}</p>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Put them in"))}</button></div>`, "wide");
  if (!ok.ok) return false;
  const sugg = [...ok.dlg.querySelectorAll("input[data-sugg]:checked")].map(b => got.suggested[+b.dataset.sugg]);
  const extra = await pjAddSuggested(sugg);
  if (extra.length) await pjShowChanges({ path: project.path, add: extra.map(name => ({ name })) });
  return pjRun("/api/vpm/preload", { path: project.path, picks: got.picks });
}
async function newProjectWith(list) {   // Projects' New project, with these in it (and what they need)
  const d = await pjLoaded();
  if (!d) { toast(tr("Projects couldn't be read just now.")); return; }
  const form = pjNewForm();
  if (!await pjFormWith(form, list)) return;
  PJ.form = form;
  PJ.view = "new";
  openProjects(true);
}
async function pjFormWith(form, list) {   // these products, and what they need, into New project's form
  const got = await pjPicksFor(list, { have: new Set(Object.keys(form.packages)) });
  if (!got || !got.picks.length) return false;
  const extra = await pjAddSuggested(got.suggested);
  form.picks.push(...got.picks);
  for (const n of extra) form.packages[n] = form.packages[n] || "*";
  return true;
}
async function pjAddSuggested(list) {   // a tool's repository, added first when you don't have it yet
  const names = [];
  for (const s of list) {
    if (s.repo && !s.repo_added) {
      const r = await apiPost("/api/vpm/repos/add", { url: s.repo });
      if (!r.ok && !/already/i.test(r.data.error || "")) { toast(r.data.error || tr("That repository couldn't be added.")); continue; }
    }
    names.push(s.package);
  }
  return names;
}
async function pjShowChanges(body) {
  const r = await apiPost("/api/vpm/preview", body);
  if (!r.ok) { toast(r.data.error || tr("That can't be done.")); return false; }
  const c = r.data;
  if (!c.install.length && !c.remove.length) { toast(tr("Nothing needs changing.")); return false; }
  const res = await pjDialog(`<p><b>${esc(tr("These changes will be made"))}</b></p>` +
    (c.open_in_unity ? `<p class="pj-warn">${esc(tr("Unity has this project open. Close it first if you can."))}</p>` : "") +
    (c.install.length ? `<p>${esc(tr("Installed"))}</p><ul class="pj-picklist">${c.install.map(x => `<li><b translate="no">${esc(x.label)}</b> <span class="muted" translate="no">${esc(x.version)} · ${esc(x.from)}</span></li>`).join("")}</ul>` : "") +
    (c.remove.length ? `<p>${esc(tr("Removed"))}</p><ul class="pj-picklist">${c.remove.map(x => `<li><span translate="no">${esc(x.name)}</span> <span class="muted">${esc(tr(PJ_WHY[x.reason] || ""))}</span></li>`).join("")}</ul>` : "") +
    (c.conflicts.length ? `<p class="pj-warn">${esc(tr("Not every package's needs can be met at once:"))}</p><ul class="pj-picklist">${c.conflicts.map(x => `<li translate="no">${esc(x.name)}` +
      (x.with.length ? ` ← ${esc(x.with.filter(Boolean).join(", "))}` : "") + `</li>`).join("")}</ul>` +
      (c.conflicts.some(x => x.unlocked.length) ? `<p class="hint">${esc(tr("A package the project had of its own, with the same name, is replaced."))}</p>` : "") : "") +
    (c.legacy.length ? `<p>${esc(tr("Old files these packages replace, deleted:"))}</p><ul class="pj-picklist" translate="no">${c.legacy.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "") +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Make the changes"))}</button></div>`, "wide");
  if (!res.ok) return false;
  return pjRun("/api/vpm/apply", body);
}
async function pjRun(url, body) {   // a task: started (or waiting its turn), and the project shown again when it's done
  const r = await apiPost(url, body);
  if (!r.ok) { toast(r.data.error || tr("That can't be done.")); return false; }
  toast(tr(r.data.queued ? "It waits its turn after Projects' task that's running now." : "Started. It shows at the top of Projects, and in Tasks."));
  PJ.ran = true;
  pjWatch();
  return true;
}
// While Projects' own lane has a task running or waiting: shown at the top of Projects; then Projects is read again
async function pjWatch() {
  if (PJ.watching) return;
  PJ.watching = true;
  let changed = false;
  try {
    for (let n = 0; n < 7200; n++) {
      const st = await (await api("/api/status", { cache: "no-store" })).json(), j = st.project_job || {};
      PJ.job = j;
      pjShowJob();
      if (!j.running && !(j.queue || []).length) break;
      changed = true;
      await new Promise(res => setTimeout(res, 1500));
    }
  } catch (e) { /* the next look shows it */ }
  PJ.watching = false;
  if ((changed || PJ.ran) && !$("#projectsWin").hidden) { PJ.ran = false; PJ.pkgs = null; loadProjects(); }
}
function pjHeaders(text) {
  const out = {};
  for (const line of String(text || "").split("\n")) {
    const at = line.indexOf(":");
    if (at > 0) out[line.slice(0, at).trim()] = line.slice(at + 1).trim();
  }
  return out;
}
let afterSetMade = null;   // set by a page that shows sets, to show the new one
async function pjAct(b) {
  const act = b.dataset.pj, row = b.closest("[data-path]"), path = row ? row.dataset.path : (PJ.project || {}).path;
  const f = PJ.form;
  if (act === "back") { PJ.view = "list"; PJ.project = null; return loadProjects(); }
  if (act === "new") { PJ.form = pjNewForm(); PJ.view = "new"; PJ.pick.clear(); return drawProjects(); }
  if (act === "sub") { PJ.sub = b.dataset.sub; return drawProjects(); }   // a project's tab
  if (act === "backnew") { PJ.view = "new"; return drawProjects(); }
  if (act === "stopjob") {
    const r = await apiPost("/api/cancel", { lane: "projects" });
    if (r.ok && r.data.ok) toast(tr("Stopping: what it was changing is put back as it was."));
    return;
  }
  if (act === "repos" || act === "settings" || act === "logs") { PJ.view = act; return drawProjects(); }
  if (act === "logfollow") {
    PJLOG.follow = !PJLOG.follow;
    b.setAttribute("aria-pressed", String(PJLOG.follow));
    if (PJLOG.follow) pjLogRows();
    return;
  }
  if (act === "showitem") {
    const item = T.byId(b.dataset.id);
    if (!item) return;
    openProjects(false);
    showDetail(item);
    return;
  }
  if (act === "logfolder") {
    const r = await apiPost("/api/open-logs");
    toast(r.ok ? tr("Opened the logs folder.") : (r.data.error || tr("The logs folder didn't open.")));
    return;
  }
  if (act === "backups") { PJ.backups = null; PJ.view = "backups"; drawProjects(); if (await pjLoadBackups()) drawProjects(); return; }
  if (act === "bkopen") { const r = await apiPost("/api/vpm/backups/show", {}); if (!r.ok) toast(r.data.error || tr("That folder couldn't be opened.")); return; }
  if (act === "bkdelold" || act === "bkmoveold") {
    const old = (PJ.backups.backups || []).filter(x => x.old).map(x => x.path);
    return act === "bkdelold" ? pjBackupsDelete(old) : pjBackupsMove(old);
  }
  if (act === "bkdel" || act === "bkmove") {
    const chosen = [...document.querySelectorAll("#projectsBody .pj-bkpick:checked")].map(x => x.value);
    return act === "bkdel" ? pjBackupsDelete(chosen) : pjBackupsMove(chosen);
  }
  if (act === "manage") { PJ.sub = "packages"; PJ.pick.clear(); return openProject(path); }
  if (act === "report") { PJ.report = PJ.reports.find(x => x.id === row.dataset.report); PJ.view = "report"; return drawProjects(); }
  if (act === "list") {   // a project Hoard for Unity reported, onto the shared list
    const r = await apiPost("/api/vpm/add-project", { path });
    if (!r.ok) { toast(r.data.error || tr("That folder isn't a Unity project.")); return; }
    PJ.report = null; PJ.view = "list";
    await loadProjects();
    return openProject(path);
  }
  if (act === "forgetreport") {
    const name = (row.querySelector("b") || {}).textContent || "";
    if (!await ask(tr("Forget {0}? It comes back next time you open it in Unity with Hoard's window.", name), tr("Forget"))) return;
    await apiPost("/api/projects/forget", { id: row.dataset.report });
    return loadProjects();
  }
  if (act === "star") {
    const on = b.getAttribute("aria-pressed") !== "true";
    await apiPost("/api/vpm/favorite", { path, on });
    return loadProjects();
  }
  if (act === "unity") {
    const r = await apiPost("/api/vpm/open", { path });
    toast(r.ok ? tr("Unity is opening the project.") : (r.data.error || tr("Unity couldn't be opened.")));
    return;
  }
  if (act === "folder") { await apiPost("/api/vpm/open-folder", { path }); return; }
  if (act === "importlist") {   // Hoard imports.md, in the project's folder (#155)
    const r = await apiPost("/api/vpm/open-folder", { path, show: "imports" });
    if (!r.ok) toast(r.data.error || tr("That can't be done."));
    return;
  }
  if (act === "forget") {
    if (!await ask(tr("Take {0} off the list? Its folder is left as it is, and you can add it again.", (row && row.querySelector("b") || {}).textContent || PJ.project.name), tr("Take off"))) return;
    const r = await apiPost("/api/vpm/remove-project", { path });
    if (!r.ok) toast(r.data.error || tr("That can't be done."));
    PJ.view = "list"; PJ.project = null;
    return loadProjects();
  }
  if (act === "add") {   // a project you have: chosen with the system's folder picker (typed, in a web browser)
    let where = "";
    if (canPick()) {
      const r = await apiPost("/api/pick", { kind: "folder", start: "projects" });
      if (!r.ok) { toast(r.data.error || tr("The picker didn't open. Type the path instead.")); return; }
      where = r.data.path || "";
    } else where = await askName("The project's folder (its full path)", "", { max: 1000 });
    if (!where) return;
    const r = await apiPost("/api/vpm/add-project", { path: where });
    if (!r.ok) { toast(r.data.error || tr("That folder isn't a Unity project.")); return; }
    return loadProjects();
  }
  if (act === "backup") {
    const res = await pjDialog(`<p>${esc(tr("Back up {0}? Everything but what Unity makes again by itself goes into a zip, in your backups folder.", PJ.project.name))}</p>` +
      `<label class="check"><input type="checkbox" id="pjLeaveOut"> ${esc(tr("Leave out packages from repositories (they're downloaded again when it's opened)"))}</label>` +
      `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Back up"))}</button></div>`);
    if (res.ok) pjRun("/api/vpm/backup", { path, leave_out_packages: res.dlg.querySelector("#pjLeaveOut").checked });
    return;
  }
  if (act === "repair") return pjShowChanges({ path, repair: true });
  if (act === "updateall") return pjShowChanges({ path, upgrade_all: true });
  if (act === "update") return pjShowChanges({ path, add: [{ name: b.closest("tr").dataset.name, version: b.dataset.version }] });
  if (act === "versions") {
    const name = b.closest("tr").dataset.name, x = (PJ.project.packages || []).find(p => p.name === name) || {};
    const version = await pjChooseVersion(name, x.label || name, b.dataset.version, PJ.project.unity);
    return version ? pjShowChanges({ path, add: [{ name, version }] }) : undefined;
  }
  if (act === "remove") return pjShowChanges({ path, remove: [b.closest("tr").dataset.name] });
  if (act === "addpkg") {   // New project's Add packages: a view of its own
    f.name = $("#pjName").value; f.location = $("#pjWhere").value; f.unity = $("#pjUnity").value;
    PJ.pick.clear(); PJ.view = "addnew";
    return drawProjects();
  }
  if (act === "addchosen") {
    const picked = [...PJ.pick].map(([name, version]) => ({ name, version }));
    if (!picked.length) return;
    if (PJ.view === "addnew") {
      for (const x of picked) f.packages[x.name] = x.version || f.packages[x.name] || "*";
      PJ.pick.clear(); PJ.view = "new";
      return drawProjects();
    }
    if (await pjShowChanges({ path, add: picked.map(x => x.version ? x : { name: x.name }), prerelease: !!PJ.data.settings.prerelease })) {
      PJ.pick.clear(); PJ.sub = "packages"; drawProjects();
    }
    return;
  }
  if (act === "delete") return pjDelete(PJ.project);
  if (act === "unpkg") { delete f.packages[b.dataset.name]; return drawProjects(); }
  if (act === "sugg") {
    const names = await pjAddSuggested([{ package: b.dataset.name, repo: b.dataset.repo || null, repo_added: b.dataset.added === "true" }]);
    for (const n of names) f.packages[n] = "*";
    return drawProjects();
  }
  if (act === "addprod") return pjPickFromDownloads();   // (Downloads, in Select mode for this project)
  if (act === "unpick") { f.picks.splice(+b.dataset.i, 1); return drawProjects(); }
  if (act === "addset") {
    const r = await api("/api/sets", { cache: "no-store" });
    const sets = r.ok ? ((await r.json()).sets || []).filter(s => s.items.some(i => i.download != null)) : [];
    if (!sets.length) { toast(tr("None of your sets has anything downloaded in it yet.")); return; }
    const res = await pjDialog(`<p><b>${esc(tr("Put in a set"))}</b></p><ul class="pj-picklist">${sets.map(s =>
      `<li><button class="linkish" value="${esc(s.id)}" translate="no">${esc(s.name)}</button> <span class="muted">${esc(tr(s.items.length === 1 ? "{0} product" : "{0} products", s.items.length))}</span></li>`).join("")}</ul>` +
      `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button></div>`);
    const set = sets.find(s => s.id === res.value);
    if (!set) return;
    for (const item of set.items.filter(i => i.download != null)) {
      const product = await pjProductContents(item.key);
      if (!product) continue;
      for (const c of product.contents) f.picks.push({ key: product.key, kind: c.kind, file: c.file, member: c.member, label: c.label, product: product.name });
    }
    toast(tr("Put in what's downloaded of {0}. Leave out any package this project doesn't need.", set.name));
    return drawProjects();
  }
  if (act === "browse") { await browseInto($("#pjWhere")); f.location = $("#pjWhere").value; return; }
  if (act === "make") {
    f.name = $("#pjName").value.trim(); f.location = $("#pjWhere").value.trim(); f.unity = $("#pjUnity").value;
    if (!f.name) { toast(tr("Give the project a name.")); $("#pjName").focus(); return; }
    const ok = await pjRun("/api/vpm/create", { name: f.name, location: f.location, template: f.template, unity: f.unity,
      packages: f.packages, picks: f.picks });
    if (ok) { PJ.view = "list"; drawProjects(); }
    return;
  }
  if (act === "savepreset") {
    const name = await askName("Name the preset", (PJ.data.presets || []).find(x => x.id === f.preset)?.name || f.name || "");
    if (!name) return;
    f.unity = $("#pjUnity").value;
    const r = await apiPost("/api/vpm/presets", { action: "save", preset: { id: f.preset || undefined, name, template: f.template,
      unity: f.unity, packages: f.packages, products: f.picks } });
    if (!r.ok) { toast(r.data.error || tr("The preset couldn't be saved.")); return; }
    f.preset = r.data.preset.id;
    toast(tr("Saved the preset {0}.", name));
    const keep = PJ.form;
    await loadProjects();
    PJ.form = keep; PJ.view = "new";
    return drawProjects();
  }
  if (act === "exportpreset") {
    const r = await apiPost("/api/vpm/presets", { action: "export", id: f.preset });
    if (!r.ok) { toast(r.data.error || tr("That can't be done.")); return; }
    toast(r.data.left_out.length ? tr("ALCOM has it as a template now, without {0}: ALCOM can't open a package inside a zip.", listed(r.data.left_out))
      : tr("ALCOM has it as a template now."));
    return;
  }
  if (act === "delpreset") {
    if (!await ask(tr("Delete this preset? Projects made from it stay as they are."), tr("Delete"), true)) return;
    await apiPost("/api/vpm/presets", { action: "delete", id: f.preset });
    f.preset = "";
    const keep = PJ.form;
    await loadProjects();
    PJ.form = keep; PJ.view = "new";
    return drawProjects();
  }
  if (act === "refresh") return pjRun("/api/vpm/refresh", {});
  if (act === "addrepo") {
    const url = $("#pjRepoUrl").value.trim();
    if (!url) return;
    b.disabled = true;
    const r = await apiPost("/api/vpm/repos/add", { url, headers: pjHeaders(($("#pjRepoHeaders") || {}).value) });
    b.disabled = false;
    if (!r.ok) { toast(r.data.error || tr("That repository couldn't be added.")); return; }
    toast(tr(r.data.packages === 1 ? "Added {0}, with {1} package." : "Added {0}, with {1} packages.", r.data.label, r.data.packages));
    for (const el of [$("#pjRepoUrl"), $("#pjRepoHeaders")]) if (el) el.value = "";   // (added: not kept for the next one)
    return loadProjects();
  }
  if (act === "unrepo") {
    if (!await ask(tr("Remove this repository? Packages already in projects stay."), tr("Remove"))) return;
    await apiPost("/api/vpm/repos/remove", { path: b.dataset.path });
    return loadProjects();
  }
  if (act === "savesettings") {
    const r = await apiPost("/api/vpm/settings", { projects_folder: $("#pjProjectsFolder").value, backups_folder: $("#pjBackupsFolder").value,
      prerelease: $("#pjPrerelease").checked });
    toast(r.ok ? tr("Saved.") : (r.data.error || tr("That can't be done.")));
    if (!r.ok) return;   // (what you typed stays, to put right)
    for (const el of $("#projectsBody").querySelectorAll("input[id]")) pjTicks(el) ? (el.defaultChecked = el.checked) : (el.defaultValue = el.value);
    return loadProjects();   // (saved: as the settings have it now)
  }
}
// Delete a project from this computer: only with its name typed, backed up first unless you untick it; a task
async function pjDelete(p) {
  const shown = pjDialog(`<p><b>${esc(tr("Delete {0} from this computer?", p.name))}</b></p>` +
    `<p>${esc(tr("Its folder, and everything in it, is deleted:"))} <span translate="no">${esc(p.path)}</span></p>` +
    `<label class="check"><input type="checkbox" id="pjDelBackup" checked> ${esc(tr("Back it up first, into your backups folder"))}</label>` +
    `<p class="hint">${esc(tr("Without a backup, it can't be got back."))}</p>` +
    `<p><label for="pjDelName">${esc(tr("Type its name to delete it: {0}", p.name))}</label></p>` +
    `<p><input id="pjDelName" autocomplete="off" spellcheck="false" translate="no" style="width:100%;box-sizing:border-box"></p>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button>` +
    `<button class="primary danger" value="yes" id="pjDelGo" disabled>${esc(tr("Delete it"))}</button></div>`);
  const dlg = [...document.querySelectorAll("dialog.pj-dlg")].pop(), name = dlg.querySelector("#pjDelName");
  name.addEventListener("input", () => { dlg.querySelector("#pjDelGo").disabled = name.value.trim() !== p.name; });
  name.focus();
  const res = await shown;
  if (!res.ok || name.value.trim() !== p.name) return;
  if (await pjRun("/api/vpm/delete-project", { path: p.path, confirm: p.name, backup: res.dlg.querySelector("#pjDelBackup").checked })) {
    PJ.view = "list"; PJ.project = null;
    drawProjects();
  }
}
function wireProjects() {
  makeWindow($("#projectsWin"));
  WINDOWS.projectsWin = () => openProjects(false);
  $("#projectsTab").addEventListener("click", () => openProjects());
  const win = $("#projectsWin");
  win.addEventListener("change", async e => {
    if (e.target.matches(".pj-addlist input[type=checkbox]")) return pjPickChanged(e.target);   // Add packages
    if (e.target.matches(".pj-addlist .pj-pick-ver")) { PJ.pick.set(e.target.dataset.name, e.target.value); return; }
    const sel = e.target.closest("[data-proj-style]");
    if (sel) { sel.closest(".proj").querySelector("textarea").value = pjShownReport().credits_text[sel.value]; return; }
    if (e.target.id === "pjOther" && e.target.value) {
      const r = await apiPost("/api/vpm/open", { path: PJ.project.path, editor: e.target.value });
      toast(r.ok ? tr("Unity is opening the project. A different version may change it to its own.") : (r.data.error || tr("Unity couldn't be opened.")));
      e.target.value = "";
    }
  });
  win.addEventListener("click", async e => {
    const old = e.target.closest("[data-proj]");
    if (old) {
      const box = old.closest(".proj"), p = pjShownReport();
      if (old.dataset.proj === "copy") {
        const text = box.querySelector("textarea").value;
        try { await navigator.clipboard.writeText(text); }
        catch (err) { box.querySelector("textarea").select(); document.execCommand("copy"); }
        toast(tr("Copied the credits."));
      } else if (old.dataset.proj === "set") {   // a set of what's in the project, to import together elsewhere
        const items = inSet(p);
        const name = await askName("Name the new set", p.name || (PJ.project || {}).name || "");
        if (!name) return;
        const r = await apiPost("/api/sets", { action: "create", name, items });
        if (!r.ok) { toast(r.data.error || tr("That set couldn't be made.")); return; }
        toast(tr(items.length === 1 ? "Made the set {0}, with this in it." : "Made the set {0}, with {1} products in it.", name, items.length));
        if (afterSetMade) afterSetMade();
      }
      return;
    }
    const b = e.target.closest("[data-pj]");
    if (!b || PJ.busy) return;
    e.preventDefault();
    PJ.busy = true;
    try { await pjAct(b); } finally { PJ.busy = false; }
  });
  win.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.id === "pjRepoUrl") { e.preventDefault(); $("[data-pj=addrepo]").click(); } });
  win.addEventListener("change", async e => {   // the backups panel's rule for which are old
    if (e.target.id !== "pjBkKeep" && e.target.id !== "pjBkDays") return;
    const r = await apiPost("/api/vpm/backups/settings", { keep: Number($("#pjBkKeep").value), days: Number($("#pjBkDays").value) });
    if (r.ok) { PJ.backups = r.data; drawProjects(); }
  });
}
/* Sets (hoard/sets.py): products you use together, such as an avatar, its outfits and the shaders they need, whether
   you've downloaded them or not, and whether they're yours yet: a set shared with you lists what to buy, and where.
   Sets is a tab beside the stores, on both pages: each set is a big tile, and a set opened is a folder of its products,
   those this page has as its usual tiles (to choose, open and select as anywhere), then the rest: not downloaded, or
   not yours yet. A set is shared as a short link to the set viewer on Hoard's website: the set, locked, is kept on
   Hoard's share server for 14 days, and the key that opens it is after the link's "#" (so it's never sent anywhere).
   The same link pasted here adds the set, as does a long link (the set itself after its "#") from Hoard before 5.0. */
const setById = id => (DATA.sets || []).find(s => s.id === id);
function setOptions(first, withNew = true) {
  return `<option value="">${esc(tr(first))}</option>` +
    (DATA.sets || []).map(s => `<option value="${esc(s.id)}" translate="no">${esc(s.name)}</option>`).join("") +
    (withNew ? `<option value="new">${esc(tr("New set..."))}</option>` : "");
}
function setsSection(a) {   // a product's details: the sets it's in, and Add it to one
  const mine = (DATA.sets || []).filter(s => s.items.includes(a.tag_key));
  return `<h3>Sets</h3><div class="chips">${mine.map(s => `<span class="tagpill"><button class="chip" data-act="showset" data-set="${esc(s.id)}" translate="no">${esc(s.name)}</button>` +
      `<button class="untag" data-act="unset" data-set="${esc(s.id)}" aria-label="${esc(tr("Take it out of {0}", s.name))}">×</button></span>`).join("") ||
      `<span class="none">${esc(tr("In no set yet"))}</span>`}</div>` +
    `<div class="tagadd"><select id="setPick" aria-label="Set to add it to">${setOptions("Add it to a set")}</select>` +
    `<button class="ghost sm" data-act="toset">Add</button></div>`;
}
async function changeSets(body) {
  const r = await apiPost("/api/sets", body);
  if (!r.ok) { toast(r.data.error || "That set couldn't be changed."); return null; }
  await T.reload();   // (the Sets tab reads its sets again with the page)
  return r.data;
}
async function addToSet(list, id) {
  const items = [...new Set(list.filter(Boolean).map(a => a.tag_key))];
  if (!items.length) return;
  if (!id) { toast("Choose a set first."); return; }
  if (id === "new") {
    const name = await askName("Name the new set");
    if (!name) return;
    const done = await changeSets({ action: "create", name, items });
    if (done) toast(tr(items.length === 1 ? "Made the set {0}, with this in it." : "Made the set {0}, with {1} products in it.", name, items.length));
    return;
  }
  const done = await changeSets({ action: "add", id, items });
  if (done) toast(tr(items.length === 1 ? "Added it to {0}." : "Added {1} products to {0}.", (setById(id) || {}).name || "", items.length));
}
/* Mix and match (issue #156): an outfit picked at random from what you own, to try something new with what you have.
   An avatar from your tags whose kind is Avatar, and one product from each tag whose kind is Clothing (tops, shoes,
   hair...), only those tagged for that avatar too when you like; keep the picks you want and pick the rest again, then
   make a set of them. */
const MIX = { picks: [], held: new Set(), fit: true };
function mixPools() {
  const kinds = tagTypes(), items = T.all().filter(a => a.tag_key);
  const has = (a, kind) => (a.tags || []).some(t => kinds.get(t) === kind);
  const avatars = items.filter(a => has(a, "avatar"));
  const slots = [...kinds].filter(([, k]) => k === "clothing").map(([t]) => t).sort(coll.compare)
    .map(t => ({ tag: t, items: items.filter(a => (a.tags || []).includes(t) && !has(a, "avatar")) })).filter(s => s.items.length);
  return { avatars, slots };
}
function mixRoll() {
  const { avatars, slots } = mixPools(), any = list => list[Math.floor(Math.random() * list.length)];
  const kept = new Map(MIX.picks.filter(p => MIX.held.has(p.slot)).map(p => [p.slot, p]));
  const avatar = kept.get("") ? kept.get("").item : any(avatars);
  const avatarTags = new Set((avatar.tags || []).filter(t => tagTypes().get(t) !== "clothing"));
  const taken = new Set([avatar.tag_key, ...[...kept.values()].map(p => p.item.tag_key)]);   // (a kept pick isn't picked again for another slot)
  MIX.picks = [{ slot: "", label: tr("Avatar"), item: avatar }];
  MIX.unfit = [];
  for (const s of slots) {
    if (kept.get(s.tag)) { MIX.picks.push(kept.get(s.tag)); taken.add(kept.get(s.tag).item.tag_key); continue; }
    const fits = s.items.filter(a => (a.tags || []).some(t => avatarTags.has(t)));
    const pool = (MIX.fit && fits.length ? fits : s.items).filter(a => !taken.has(a.tag_key));
    if (MIX.fit && !fits.length) MIX.unfit.push(s.tag);
    const item = any(pool);
    if (item) { MIX.picks.push({ slot: s.tag, label: s.tag, item }); taken.add(item.tag_key); }
  }
}
function mixHTML() {
  return `<h3>${esc(tr("Mix and match"))}</h3>` +
    `<p class="hint">${esc(tr("An outfit from what you own, picked at random. Keep the picks you like, and pick the rest again."))}</p>` +
    `<ul class="mixlist">${MIX.picks.map(p => `<li><span class="mixart">${T.art(p.item)}</span><span class="mixtext">` +
      `<small>${esc(p.label)}</small><b translate="no">${esc(p.item.name)}</b><span class="muted" translate="no">${esc(p.item.creator || "")}</span></span>` +
      `<label class="check"><input type="checkbox" data-mixhold="${esc(p.slot)}"${MIX.held.has(p.slot) ? " checked" : ""}> ${esc(tr("Keep"))}</label></li>`).join("")}</ul>` +
    `<label class="check"><input type="checkbox" id="mixFit"${MIX.fit ? " checked" : ""}> ${esc(tr("Only clothes that share a tag with the avatar"))}</label>` +
    ((MIX.unfit || []).length ? `<p class="hint">${esc(tr("Nothing in {0} shares a tag with this avatar, so that pick is from all of them.", MIX.unfit.join(", ")))}</p>` : "") +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Close"))}</button>` +
    `<button class="ghost" type="button" data-mix="again">${esc(tr("Pick again"))}</button>` +
    `<button class="primary" value="yes">${esc(tr("Make a set of them"))}</button></div>`;
}
async function mixAndMatch() {
  const { avatars, slots } = mixPools();
  if (!avatars.length || !slots.length) {
    await ask(tr("Mix and match picks an avatar and an outfit from your tags. Give your tags a kind first, in Tags: an Avatar tag on your avatars, and Clothing tags on your clothes (a tag for each kind of thing, such as tops, shoes or hair, gives a pick of each)."), tr("OK"), false, "");
    return;
  }
  MIX.picks = []; MIX.held = new Set();
  mixRoll();
  const dlg = document.createElement("dialog");
  dlg.className = "ask mixdlg";
  dlg.innerHTML = `<form method="dialog">${mixHTML()}</form>`;
  document.body.appendChild(dlg);
  const redraw = () => { dlg.querySelector("form").innerHTML = mixHTML(); };
  dlg.addEventListener("click", e => { if (e.target.closest("[data-mix=again]")) { e.preventDefault(); mixRoll(); redraw(); } });
  dlg.addEventListener("change", e => {
    const hold = e.target.closest("[data-mixhold]");
    if (hold) { hold.checked ? MIX.held.add(hold.dataset.mixhold) : MIX.held.delete(hold.dataset.mixhold); return; }
    if (e.target.id === "mixFit") { MIX.fit = e.target.checked; mixRoll(); redraw(); }
  });
  const result = await new Promise(resolve => { dlg.addEventListener("close", () => resolve(dlg.returnValue), { once: true }); dlg.showModal(); });
  dlg.remove();
  if (result === "yes") await addToSet(MIX.picks.map(p => p.item), "new");
}
async function takeOutOfSet(list) {   // from the set that's open
  const s = setById(state.set), items = keysOf(list.filter(Boolean));
  if (!s || !items.length) return;
  const done = await changeSets({ action: "remove", id: s.id, items });
  if (done) toast(tr(list.length === 1 ? "Took it out of {0}." : "Took {1} products out of {0}.", s.name, list.length));
}
// the selection bar's and right-click's Sets menu, on both pages
const SET_ACTIONS = () => ({ name: "Sets", items: [
  ...(inSets() && setById(state.set) ? [{ label: tr("Take out of {0}", setById(state.set).name), raw: true, run: takeOutOfSet }] : []),
  { label: "New set from these...", run: list => addToSet(list, "new") },
  ...(DATA.sets || []).map(s => ({ label: tr("Add to {0}", s.name), raw: true, run: list => addToSet(list, s.id) }))] });

let SETS = null;   // the sets as /api/sets has them, each product as it is here (downloaded, yours, or where to buy it)
let setExtraOpen = true, setViewShown = "", setMoreShown = "", setKeysFor = null, setKeys = new Set();
const inSets = () => state.store === "Sets";
function setHas(a) {   // the open set has this product (by the key tags use); a wishlist's are in its own groups
  const s = setById(state.set);
  if (s && s.kind === "wishlist") return false;
  if (s !== setKeysFor) { setKeysFor = s; setKeys = new Set(s ? s.items : []); }
  return setKeys.has(a.tag_key);
}
function showSet(id) {   // the Sets tab, at a set (or at every set, for "")
  state.store = "Sets"; state.set = id || "";
  if (T.open()) T.closeDetail();
  T.render();
  window.scrollTo({ top: 0 });
}
async function loadSets() {
  const asked = DATA;
  let got;
  try {
    const r = await api("/api/sets", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    got = await r.json();
  } catch (e) { got = { error: true, sets: [] }; }
  got.for = asked;
  if (asked !== DATA) return;   // (the page has read everything again: it asks again)
  SETS = got;   // (where the page is is known now, a set or a wishlist: #180)
  if (wishScope() || openWish()) T.render(); else drawSets();   // (a wishlist's tags and creators are in the filters beside it)
}
const setPic = src => `<img src="${esc(keyed(src))}" alt="" loading="lazy" decoding="async">`;
const setPlaceholder = (name, by) => `<span class="ph" style="--h:${hue(by || name)}" translate="no"><b>${esc(initials(name))}</b></span>`;
function setArt(s) {   // the picture you chose for it, else up to four of its products' pictures
  if (s.cover) return setPic(s.cover);
  const pics = s.items.filter(i => i.pic).slice(0, 4);
  return pics.length ? `<span class="collage n${pics.length}">${pics.map(i => setPic(i.pic)).join("")}</span>` : setPlaceholder(s.name);
}
// Wishlists (issue #158): sets of the kind "wishlist", most read from a store's own list, each product with its price
const isWish = s => s.kind === "wishlist";
const cheaper = i => i.was && i.price && i.was.currency === i.price.currency && i.price.amount < i.was.amount;
function priceHTML(i) {   // what a product on a wishlist costs, and what it cost before, when that changed
  if (!i.price) return "";
  return `<span class="price${cheaper(i) ? " down" : ""}" translate="no">${esc(i.price.text)}</span>` +
    (i.was ? ` <s class="was" translate="no"><span class="visually-hidden">${esc(tr("was"))} </span>${esc(i.was.text)}</s>` : "");
}
function setCounts(s) {
  if (isWish(s)) {
    const yours = s.items.filter(i => i.owned).length, down = s.items.filter(cheaper).length;
    return { got: 0, owned: s.items.filter(i => i.owned && i.download == null).length, buy: s.items.length - yours,
      text: [tr(s.items.length === 1 ? "1 product" : "{0} products", s.items.length), yours && tr("{0} yours already", yours),
             down && tr(down === 1 ? "1 cheaper than before" : "{0} cheaper than before", down)].filter(Boolean).join(", ") };
  }
  const got = s.items.filter(i => i.download != null).length, owned = s.items.filter(i => i.owned && i.download == null).length;
  const buy = s.items.filter(i => !i.owned && !i.local && i.download == null).length;
  return { got, owned, buy, text: [tr(s.items.length === 1 ? "1 product" : "{0} products", s.items.length),
    got && tr("{0} downloaded", got), owned && tr("{0} to download", owned), buy && tr("{0} to buy", buy)].filter(Boolean).join(", ") };
}
function setTile(s) {
  const c = setCounts(s);
  return `<button class="slot settile" data-setopen="${esc(s.id)}" aria-label="${esc(tr("{0}: {1}", s.name, c.text))}">` +
    `<span class="art">${setArt(s)}<i class="tick" aria-hidden="true"></i></span><span class="nm-t" translate="no">${esc(s.name)}</span><span class="cr">${esc(c.text)}</span></button>`;
}
function setsRoot() {
  const top = `<div class="row sets-top"><button class="primary sm" data-setx="new">New set</button>` +
    `<button class="ghost sm" data-setx="import">Add a shared set...</button>` +
    `<button class="ghost sm" data-setx="mix">${esc(tr("Mix and match..."))}</button></div>` +
    (SETS.hidden_left_out ? `<p class="hint">Hidden items are left out while your hidden library is locked.</p>` : "");
  if (SETS.error) return top + `<p class="none">${esc(tr("Your sets couldn't be read just now."))}</p>`;
  const plain = SETS.sets.filter(s => !isWish(s)), wishes = SETS.sets.filter(isWish);
  const sets = plain.length ? `<div class="grid setgrid">${plain.map(setTile).join("")}</div>`
    : `<p class="none">No sets yet. A set groups products you use together, such as an avatar,
    its outfits and the shaders they need, downloaded or not. Make one here, or choose products in the Library or Downloads and
    use <strong>Sets</strong> in the selection bar. A set someone shares with you lists what it needs, and where to buy it.</p>`;
  return top + sets + `<h3 class="setmore-h wish-h">${esc(tr("Wishlists"))} <span class="n">${wishes.length.toLocaleString()}</span></h3>` +
    `<div class="row sets-top"><button class="primary sm" data-setx="readwish">${esc(tr("Read my wishlists..."))}</button>` +
    `<button class="ghost sm" data-setx="importwish">${esc(tr("Import saved wishlist pages..."))}</button>` +
    `<button class="ghost sm" data-setx="newwish">${esc(tr("New wishlist"))}</button></div>` +
    (wishes.length ? `<div class="grid setgrid">${wishes.map(setTile).join("")}</div>`
      : `<p class="none">${esc(tr("Your wishlists from Booth (your loved items), Gumroad, Jinxxy (your wishlist, likes and lists) and Payhip, with what each product costs. Read them from the stores you're signed in to, or import wishlist pages you saved from your own browser. Each time they're read again, a price that changed shows what it was."))}</p>`);
}
function setHead(s) {
  const c = setCounts(s);
  return `<nav class="crumbs" aria-label="${esc(tr("Where you are"))}"><button class="linkish" data-setx="back">${esc(tr("Sets and wishlists"))}</button>` +
      `<span aria-hidden="true">›</span><span translate="no">${esc(s.name)}</span></nav>` +
    `<div class="sethead"><span class="art">${setArt(s)}</span><div class="sethead-text">` +
      `<h2 translate="no">${esc(s.name)}</h2><p class="muted">${esc(c.text)}</p>` +
      (isWish(s) && s.source ? `<p class="muted">${esc(tr("Your wishlist from {0} ({1}), read {2}.", STORE_NAMES[s.source.store] || s.source.store, s.source.list, s.read ? ago(s.read) : "?"))} ` +
        `<button class="linkish" data-setx="reread" data-store="${esc(s.source.store)}">${esc(tr("Read it again"))}</button></p>` : "") +
      (s.note ? `<p class="setnote" translate="no">${esc(s.note)}</p>` : "") +
      `<div class="row"><button class="primary sm" data-setx="share">Share...</button>` +
      `<button class="ghost sm" data-setx="addlinks">${esc(tr("Add products by link..."))}</button>` +
      (c.owned ? `<button class="ghost sm" data-setx="download">${esc(tr(c.owned === 1 ? "Download the 1 not downloaded" : "Download the {0} not downloaded", c.owned))}</button>` : "") +
      `<button class="ghost sm" data-setx="picture">${esc(tr(s.cover ? "Change its picture..." : "Choose a picture..."))}</button>` +
      (s.cover ? `<button class="ghost sm" data-setx="unpicture">Take the picture off</button>` : "") +
      `<button class="ghost sm" data-setx="rename">Rename</button><button class="ghost sm" data-setx="delete">Delete</button></div></div></div>` +
    `<details class="setextra"${setExtraOpen ? " open" : ""}><summary>Note and photos</summary>` +
      `<textarea data-setnote maxlength="1000" rows="2" placeholder="${esc(tr("What it's for, or how to put it together. It's shared with the set."))}" ` +
      `aria-label="${esc(tr("Note for {0}", s.name))}">${esc(s.note || "")}</textarea>` +
      `<div class="row"><button class="ghost sm" data-setx="note">Save the note</button></div>` +
      (s.photos.length ? `<ul class="setphotos">${s.photos.map((u, n) => `<li><a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer" translate="no">` +
        `${esc(new URL(u).hostname)}/…${esc(u.slice(-12))}</a><button class="untag" data-setx="unphoto" data-n="${n}" aria-label="${esc(tr("Take this photo out"))}">×</button></li>`).join("")}</ul>` : "") +
      `<p class="hint">${esc(tr("Photos of the set (an avatar wearing it, say) show on its shared page. Put each picture on a photo site such as Imgur or Gyazo, then add its link, or the link to its page there. Hoard saves the link, not the picture."))}</p>` +
      `<div class="row"><button class="ghost sm" data-setx="photo">Add a photo link...</button></div></details>`;
}
// The set's products this page has no tile for: in the Library, ones not yours yet (and your own, which are in
// Downloads); in Downloads, ones not downloaded. Each says where it is, or where to buy it.
function setMoreHTML(s) {
  if (isWish(s)) return wishBar(s) + `<div id="wishGroups">${wishGroups(s)}</div>`;
  const here = new Set(T.all().map(a => a.tag_key)), words = norm(state.q).split(/\s+/).filter(Boolean);
  const rest = s.items.filter(i => !here.has(i.key) && words.every(w => norm([i.name, i.creator, i.store].join(" ")).includes(w)));
  const groups = [[tr("In your library, not downloaded"), rest.filter(i => i.owned)], [tr("Not yours yet"), rest.filter(i => !i.owned && !i.local)],
                  [tr("Your own packages (Local)"), rest.filter(i => !i.owned && i.local)]];
  return groups.filter(([, list]) => list.length).map(([title, list]) =>
    `<h3 class="setmore-h">${esc(title)} <span class="n">${list.length.toLocaleString()}</span></h3>` +
    `<div class="grid">${list.map(i => setExtraTile(s, i)).join("")}</div>`).join("");
}
// A wishlist open: its products in two groups that fold away, what isn't yours yet and what is, in the page's sort,
// narrowed by the filters beside it (its suggested tags, words its products' names share, your tags on the ones you
// have, and its creators), the search and a price range above it, in one of its currencies
const WISH = { set: "", cur: "", min: "", max: "" };
const openWish = () => { const s = inSets() && state.set && SETS && !SETS.error ? SETS.sets.find(x => x.id === state.set) : null; return s && isWish(s) ? s : null; };
let wishScoped;   // the wishlist the filters were last for ("" none, undefined not known yet)
function wishScope() {   // into a wishlist or out of one, the tags and creator chosen start again: they were another list's.
  if (inSets() && state.set && !SETS) return false;   // (not read yet: once it is, it's where the page was opened)
  const w = openWish(), id = w ? w.id : "";
  // its price range too, before anything of it is counted: another list's would empty its filters (issue #180)
  if (w && WISH.set !== id) Object.assign(WISH, { set: id, cur: "", min: "", max: "" });
  const changed = wishScoped !== undefined && id !== wishScoped && !!(id || wishScoped);
  if (changed) { state.tags.clear(); state.creator = ""; }
  wishScoped = id;
  return changed;
}
let ownTagsFor = null, ownTags = new Map();
function wishOwnTags(i) {   // your tags on a wishlist's product you have (by the key tags use)
  if (ownTagsFor !== DATA) {
    ownTagsFor = DATA; ownTags = new Map();
    for (const a of T.all()) if (a.tags.length) ownTags.set(a.tag_key, [...new Set([...(ownTags.get(a.tag_key) || []), ...a.tags])]);
  }
  return ownTags.get(i.key) || [];
}
const wishShown = (s, skip) => { const words = norm(state.q).split(/\s+/).filter(Boolean); return s.items.filter(i => wishFits(i, words, skip)); };
const wishTagItems = s => wishShown(s).map(i => ({ tags: wishOwnTags(i), suggested: i.words || [] }));
function wishCreators(s) {   // the filters' Creators, for a wishlist: its products', with the other filters on
  const n = new Map();
  for (const i of wishShown(s, "creator")) if (i.creator) n.set(i.creator, (n.get(i.creator) || 0) + 1);
  return n;
}
const wishStore = st => { const n = Object.keys(STORE_NAMES).indexOf(st); return n < 0 ? 99 : n; };
const WISH_SORTS = {   // the page's Sort; Recently added (and Largest) keep the list's own order, as the store has it
  name: (a, b) => coll.compare(a.name, b.name),
  creator: (a, b) => !a.creator - !b.creator || coll.compare(a.creator, b.creator) || coll.compare(a.name, b.name),
  store: (a, b) => wishStore(a.store) - wishStore(b.store) || coll.compare(a.name, b.name),
};
function wishCurrencies(s) {   // the currencies its prices are in, the most used first
  const n = new Map();
  for (const i of s.items) if (i.price) n.set(i.price.currency, (n.get(i.price.currency) || 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1]).map(([c]) => c);
}
function wishFits(i, words, skip) {
  if (!words.every(w => norm([i.name, i.creator, i.store].join(" ")).includes(w))) return false;
  if (skip !== "creator" && state.creator && i.creator !== state.creator) return false;
  for (const tag of state.tags) if (!(i.words || []).includes(tag) && !wishOwnTags(i).includes(tag)) return false;
  const lo = parseFloat(WISH.min), hi = parseFloat(WISH.max);
  if (isNaN(lo) && isNaN(hi)) return true;
  if (!i.price || i.price.currency !== WISH.cur) return false;   // (a range is in one currency: others aren't in it)
  return !(i.price.amount < lo) && !(i.price.amount > hi);
}
function wishBar(s) {
  if (WISH.set !== s.id) Object.assign(WISH, { set: s.id, cur: "", min: "", max: "" });
  const curs = wishCurrencies(s);
  if (!curs.includes(WISH.cur)) WISH.cur = curs[0] || "";
  const num = (k, hint, label) => `<input type="number" min="0" step="any" inputmode="decimal" data-wish="${k}" value="${esc(WISH[k])}" placeholder="${esc(hint)}" aria-label="${esc(label)}">`;
  return !curs.length ? "" : `<div class="wishbar">` +
    (`<div class="wish-price" role="group" aria-label="${esc(tr("Price range"))}"><span class="wish-l">${esc(tr("Price"))}</span>` +
      num("min", tr("From"), tr("Lowest price")) + `<span aria-hidden="true">–</span>` + num("max", tr("To"), tr("Highest price")) +
      (curs.length > 1 ? `<select data-wish="cur" aria-label="${esc(tr("Currency"))}">${curs.map(c => `<option value="${esc(c)}"${c === WISH.cur ? " selected" : ""} translate="no">${esc(c)}</option>`).join("")}</select>`
        : `<span translate="no">${esc(curs[0])}</span>`) +
      `<button class="linkish" data-setx="wclear"${WISH.min || WISH.max ? "" : " hidden"}>${esc(tr("Clear"))}</button></div>`) + `</div>`;
}
function wishGroups(s) {
  const shown = wishShown(s);
  if (WISH_SORTS[state.sort]) shown.sort(WISH_SORTS[state.sort]);
  const group = (id, title, list) => {
    const open = (UI.sections || {})[`wish-${id}`] !== false;
    return `<details class="wishgroup" data-fold="wish-${id}"${open ? " open" : ""}><summary>${esc(title)} <span class="n">${list.length.toLocaleString()}</span></summary>` +
      (list.length ? `<div class="grid">${list.map(i => setExtraTile(s, i)).join("")}</div>` : `<p class="none">${esc(tr("Nothing here matches."))}</p>`) + `</details>`;
  };
  return group("buy", tr("Not yours yet"), shown.filter(i => !i.owned && !i.local)) + group("yours", tr("Yours already"), shown.filter(i => i.owned || i.local));
}
function wishChanged() {   // the price range changed: the groups and filters again (the bar stays as it is, so typing
  const s = openWish(), box = $("#wishGroups");   // isn't interrupted)
  if (!s || !box) return;
  box.innerHTML = wishGroups(s);
  setMoreShown = null;   // (drawn again whole next time, or emptied: "" is what the list of sets has there)
  T.facets();
  const clear = $('#setMore [data-setx="wclear"]');
  if (clear) clear.hidden = !(WISH.min || WISH.max);
}
// A product's page on a site that isn't one of the stores (a Jinxxy list can send you to one): plain https on a
// public name, as Hoard keeps it (sets.outside_link)
const outsideUrl = u => {
  const s = safeUrl(u); if (!s) return "";
  const x = new URL(s);
  return x.protocol === "https:" && !x.username && !x.password && (!x.port || x.port === "443") && x.hostname.includes(".") &&
    !/^[\d.]+$/.test(x.hostname) && !x.hostname.startsWith("[") ? s : "";
};
function setExtraTile(s, i) {
  const away = !i.owned && !i.local && !storeUrl(i.store, i.url) ? outsideUrl(i.elsewhere) : "";
  const store = away ? new URL(away).hostname.replace(/^www\./, "") : STORE_NAMES[i.store] || (i.local ? "Local" : i.store);
  const buy = !i.owned && !i.local ? storeUrl(i.store, i.url) || away : "";
  const href = i.download != null ? `/downloads#open=${+i.download}`   // (Hoard's own pages, or the store's, checked)
    : i.owned && i.lib ? `/#store=Sets&set=${encodeURIComponent(s.id)}&open=${encodeURIComponent(i.lib)}` : buy;
  const what = i.download != null ? tr("Downloaded") : i.owned ? tr("In your library") : i.local ? tr("Not in Local now") : buy ? tr("Buy on {0}", store) : tr("No store link");
  const price = !i.owned && !i.local ? priceHTML(i) : "";
  const inner = `<span class="art">${i.pic ? setPic(i.pic) : setPlaceholder(i.name, i.creator)}${notch(i.store || "local", [])}</span>` +
    `<span class="nm-t" translate="no">${esc(i.name)}</span><span class="cr" translate="no">${esc(i.creator ? tr("by {0}", i.creator) + " · " : "")}${esc(store)}</span>`;
  return `<div class="slot ext${buy ? " wanted" : ""}">` +
    (href === buy && buy ? `<a class="ext-main" href="${esc(safeUrl(buy))}" target="_blank" rel="noopener noreferrer">${inner}</a>`
      : href ? `<a class="ext-main" href="${esc(safeUrl(new URL(href, location.href).href))}">${inner}</a>` : `<span class="ext-main">${inner}</span>`) +
    (price ? `<span class="ext-price">${price}</span>` : "") +
    `<span class="ext-row"><span class="ext-what">${esc(what)}${href === buy && buy ? `<span class="visually-hidden"> ${esc(tr("(opens in your browser)"))}</span>` : ""}</span>` +
    `<button class="untag" data-setx="out" data-key="${esc(i.key)}" aria-label="${esc(tr("Take {0} out of the set", i.name))}">×</button></span></div>`;
}
// Drawn with the page (render): the set tiles, or the open set's head and the rest of its products. Each part is put
// in again only when it changes, so a note being written isn't lost when the page is drawn again.
function drawSets() {
  const view = $("#setView"), more = $("#setMore"), on = inSets();
  view.hidden = more.hidden = !on;
  let head = "", rest = "";
  if (on) {
    if (!SETS || SETS.for !== DATA) loadSets();   // (once each time the page reads everything)
    const s = SETS && state.set ? SETS.sets.find(x => x.id === state.set) : null;
    if (SETS && SETS.for === DATA && state.set && !s && !SETS.error) { state.set = ""; T.render(); return; }   // (deleted)
    head = !SETS || (state.set && !s) ? `<p class="none">${esc(tr("Reading your sets..."))}</p>` : s ? setHead(s) : setsRoot();
    rest = s ? setMoreHTML(s) : "";
  }
  if (head !== setViewShown) { view.innerHTML = head; setViewShown = head; }
  if (rest !== setMoreShown) { more.innerHTML = rest; setMoreShown = rest; }
}
const setsCountText = () => { const n = (DATA.sets || []).filter(s => !isWish(s)).length; return tr(n === 1 ? "1 set" : "{0} sets", n.toLocaleString()); };
// A picture from this computer, made small enough to keep (at most 640 pixels across): a data: address, or "". PNG when
// it has see-through parts, else JPEG: both show in Hoard for Unity too.
async function choosePicture() {
  const input = Object.assign(document.createElement("input"), { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif" });
  const file = await new Promise(resolve => {
    input.addEventListener("change", () => resolve(input.files[0] || null), { once: true });
    input.addEventListener("cancel", () => resolve(null), { once: true });
    input.click();
  });
  if (!file) return "";
  let img;
  try { img = await createImageBitmap(file); } catch (e) { toast("That picture couldn't be read."); return ""; }
  const scale = Math.min(1, 640 / Math.max(img.width, img.height));
  const c = Object.assign(document.createElement("canvas"), { width: Math.max(1, Math.round(img.width * scale)), height: Math.max(1, Math.round(img.height * scale)) });
  const g = c.getContext("2d");
  g.drawImage(img, 0, 0, c.width, c.height);
  img.close();
  const px = g.getImageData(0, 0, c.width, c.height).data;
  let clear = false;
  for (let n = 3; n < px.length && !clear; n += 4) clear = px[n] < 255;
  let url = clear ? c.toDataURL("image/png") : c.toDataURL("image/jpeg", 0.88);
  if (url.length > 600000) url = c.toDataURL("image/jpeg", 0.8);   // (a big see-through picture)
  return url;
}
/* Short links (hoard/shortlinks.py): a set's code, locked here with AES-GCM and a random 128-bit key before Hoard
   sends it to its share server, which keeps it 14 days. The key is only ever in the link, after its "#"; the server
   can't read the set. site/set.js unlocks it the same way (a test checks the two agree). */
const SHORT_LINK = /(?:^|#)S1\.([0-9A-Za-z]{10})\.([A-Za-z0-9_-]{22})$/;
const LOCKED_AS = new TextEncoder().encode("Hoard set S1");   // (what it's locked as: a key opens only a set)
const b64u = bytes => {
  let t = "";
  for (let n = 0; n < bytes.length; n += 0x8000) t += String.fromCharCode(...bytes.subarray(n, n + 0x8000));
  return btoa(t).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
};
const unb64u = t => Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((t.length + 3) % 4)), c => c.charCodeAt(0));
async function lockSet(code, key) {
  const k = await crypto.subtle.importKey("raw", unb64u(key), "AES-GCM", false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv, additionalData: LOCKED_AS }, k, new TextEncoder().encode(code)));
  const out = new Uint8Array(12 + sealed.length);
  out.set(iv); out.set(sealed, 12);
  return b64u(out);
}
async function unlockSet(data, key) {
  const bytes = unb64u(data), k = await crypto.subtle.importKey("raw", unb64u(key), "AES-GCM", false, ["decrypt"]);
  return new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.subarray(0, 12), additionalData: LOCKED_AS }, k, bytes.subarray(12)));
}
const canLock = () => !!(window.crypto && crypto.subtle);   // (a page on 127.0.0.1 has it; one opened by its LAN address over http doesn't)
const NO_LOCK = "This browser can't lock a set for a short link here. Share it from Hoard on the computer it runs on.";
const NO_UNLOCK = "This browser can't open a short link here. Add the set from Hoard on the computer it runs on.";
const day = seconds => new Date(seconds * 1000).toLocaleDateString(document.documentElement.lang || "en", { year: "numeric", month: "long", day: "numeric" });
// The set behind a short link someone shared (Add a shared set): its code, or "" when it can't be had (said why)
async function openShortLink(text) {
  const m = text.replace(/\s+/g, "").match(SHORT_LINK);
  if (!canLock()) { toast(NO_UNLOCK); return ""; }
  const r = await apiPost("/api/sets", { action: "open-short", short: m[1] });
  if (!r.ok) { toast(r.data.error || "That short link couldn't be opened."); return ""; }
  try { return await unlockSet(r.data.data, m[2]); }
  catch (e) { toast("That short link's key doesn't open its set. Copy all of the link, and try again."); return ""; }
}
// A set's link to share (issue #162: only a short link, as a set's own long link was too long to pass around): made
// here, then copied, opened, updated (which keeps it {days} more days, by hand) or deleted
function showShare(s, got) {
  const d = document.createElement("dialog");
  d.className = "ask share";
  const left = got.left_out ? `<p class="hint">${esc(tr(got.left_out === 1 ? "1 product isn't included: your own packages (Local) and hidden products stay on this computer."
    : "{0} products aren't included: your own packages (Local) and hidden products stay on this computer.", got.left_out))}</p>` : "";
  d.innerHTML = `<form method="dialog"><p><b translate="no">${esc(s.name)}</b></p>` +
    `<p>${esc(tr(got.count === 1 ? "Anyone with this link can see the product in this set, where to buy it, and your note and photos."
      : "Anyone with this link can see the {0} products in this set, where to buy each one, and your note and photos.", got.count))} ` +
    `${esc(tr("To add the set to their own Hoard, they choose Add a shared set in Sets and paste the link."))}</p>` + left +
    `<section class="shortlink" aria-label="${esc(tr("Short link"))}"></section>` +
    `<div class="ask-row"><button class="ghost" value="no">Close</button></div></form>`;
  const box = d.querySelector(".shortlink");
  const drawShort = () => {
    const sh = got.short, days = got.short_days || 14, big = got.fits === false;
    // too big for one short link: split into sets that each fit (the set itself stays), and share each of those
    const split = !big ? "" : got.why   // (one product too big on its own: splitting wouldn't help, issue #178)
      ? `<p class="share-big"><b>${esc(tr("This set is too big for one short link."))}</b> ${esc(tr(got.why))}</p>`
      : `<p class="share-big"><b>${esc(tr("This set is too big for one short link."))}</b> ` +
        `${esc(tr("A short link holds about 500 products, depending on their names and links. Split it into {0} sets that each fit, and share each one. This set stays as it is.", got.parts))}</p>` +
        `<div class="ask-row"><button class="primary" type="button" data-short="split">${esc(tr("Split into {0} sets", got.parts))}</button></div>`;
    box.innerHTML = sh
      ? `<p><input readonly value="${esc(sh.link)}" aria-label="${esc(tr("The set's short link"))}" style="width:100%;box-sizing:border-box" translate="no"></p>` +
        `<p class="hint">${esc(tr("It works until {0}.", day(sh.expires)))} ${esc(big ? "" : tr(sh.changed
          ? "The set has changed since: update the link to share it as it is now." : "Updating it keeps it {0} days from today.", days))}</p>` +
        `<div class="ask-row"><button class="ghost danger" type="button" data-short="delete">Delete the short link</button>` +
        `<a class="ghost" href="${esc(safeUrl(sh.link))}" target="_blank" rel="noopener noreferrer">Open it</a>` +
        (big ? "" : `<button class="${sh.changed ? "primary" : "ghost"}" type="button" data-short="update">Update the link</button>`) +
        `<button class="${sh.changed || big ? "ghost" : "primary"}" type="button" data-copy="short">Copy the short link</button></div>` + split
      : big ? split
      : `<p class="hint">${esc(tr("A set is shared as a short link, which you can update to keep it going."))} ` +
        `${esc(tr("A short link keeps a locked copy of the set on Hoard's share server for {0} days. Only the link opens it: the key is in the link, and never sent to the server. You can delete it whenever you like.", days))}</p>` +
        `<div class="ask-row"><button class="primary" type="button" data-short="make">Make a short link</button></div>`;
  };
  drawShort();
  document.body.appendChild(d);
  d.addEventListener("click", async e => {
    const c = e.target.closest("[data-copy]"), act = e.target.closest("[data-short]");
    if (c) {
      try { await navigator.clipboard.writeText(got.short.link); toast("Copied the short link."); }
      catch (err) { box.querySelector("input").select(); }
      return;
    }
    if (!act || act.disabled) return;
    if (act.dataset.short === "delete") {
      if (!await ask("Delete this set's short link? Anyone who opens it will see that it's gone.", "Delete", true)) return;
      act.disabled = true;
      const r = await apiPost("/api/sets", { action: "unshort", id: s.id });
      act.disabled = false;
      if (!r.ok) { toast(r.data.error || "The short link couldn't be deleted."); return; }
      got.short = null; drawShort(); toast("Deleted the short link.");
      return;
    }
    if (act.dataset.short === "split") {
      act.disabled = true;
      const r = await apiPost("/api/sets", { action: "split", id: s.id });
      act.disabled = false;
      if (!r.ok) { toast(r.data.error || "That set couldn't be split."); return; }
      d.close();
      toast(tr("Made {0} sets from {1}, each small enough to share: share each one from its tile.", r.data.made.length, s.name));
      await T.reload();
      return;
    }
    if (!canLock()) { toast(NO_LOCK); return; }
    act.disabled = true;
    const key = got.short ? got.short.code.split(".")[2] : b64u(crypto.getRandomValues(new Uint8Array(16)));
    const r = await apiPost("/api/sets", { action: "short", id: s.id, code: got.code, key, data: await lockSet(got.code, key) });
    act.disabled = false;
    if (!r.ok) { toast(r.data.error || "The short link couldn't be made."); return; }
    const was = got.short;
    got.short = r.data.short; drawShort();
    toast(tr(was ? "Updated the short link. It works until {0}." : "Made a short link. It works until {0}.", day(got.short.expires)));
    box.querySelector("input").select();
  });
  d.addEventListener("close", () => d.remove(), { once: true });
  d.showModal();
  (box.querySelector("input") || box.querySelector("button") || d.querySelector('button[value="no"]')).focus();   // (nothing to do: Close)
}
async function shareSet(s) {
  const r = await apiPost("/api/sets", { action: "share", id: s.id });
  if (!r.ok) { toast(r.data.error || "That set couldn't be shared."); return; }
  showShare(s, r.data);
}
const notDownloaded = list => [...new Set(list.flatMap(s => s.items.filter(i => i.owned && i.download == null).map(i => i.key)))];
async function setPicture(s) {
  const image = await choosePicture();
  if (image && await changeSets({ action: "picture", id: s.id, image })) toast("Its tile shows that picture now.");
}
async function renameSet(s) {
  const name = await askName("Rename the set", s.name);
  if (name && name !== s.name) changeSets({ action: "rename", id: s.id, name });
}
async function deleteSets(list) {
  const shorts = list.filter(s => s.short).length;
  if (!list.length || !await ask((list.length === 1 ? tr("Delete the set {0}? The products in it stay as they are.", list[0].name)
                                  : tr("Delete these {0} sets? The products in them stay as they are.", list.length)) +
                                 (shorts ? " " + tr(shorts > 1 ? "Their short links are deleted too." : list.length === 1 ? "Its short link is deleted too."
                                                     : "One of them has a short link: it's deleted too.") : ""),
                                 "Delete", true)) return;
  let kept = 0;
  for (const s of list) {
    const r = await apiPost("/api/sets", { action: "delete", id: s.id });
    if (!r.ok) { toast(r.data.error || "That set couldn't be changed."); break; }
    kept = Math.max(kept, r.data.kept_short || 0);
  }
  if (kept) toast(tr("Hoard's share server couldn't be reached, so a short link wasn't deleted. It stops working on {0}.", day(kept)));
  sel.ids.clear();
  if (list.some(s => s.id === state.set)) state.set = "";
  await T.reload();
}
// what can be done to the sets chosen on the Sets tab (the selection bar, and a right-click on a set's tile)
const SET_TILE_ACTIONS = () => {
  const one = sel.ids.size === 1, got = chosenItems(), missing = notDownloaded(got);
  return { main: [], groups: [{ name: "Sets", items: [
    ...(one ? [{ label: "Open", run: list => showSet(list[0].id) }, { label: "Share...", run: list => shareSet(list[0]) }] : []),
    ...(missing.length ? [{ label: tr(missing.length === 1 ? "Download the 1 not downloaded" : "Download the {0} not downloaded", missing.length),
                            raw: true, run: list => T.download(notDownloaded(list)) }] : []),
    ...(one ? [{ label: "Choose a picture...", run: list => setPicture(list[0]) }, { label: "Rename", run: list => renameSet(list[0]) }] : []),
    { label: one ? "Delete" : "Delete these sets", danger: true, run: deleteSets }] }] };
};
async function setAct(e) {
  const open = e.target.closest("[data-setopen]");
  if (open && selectClick(e, open)) return;   // (chosen, not opened: Select, Ctrl or Shift)
  if (open) { showSet(open.dataset.setopen); return; }
  const b = e.target.closest("[data-setx]"); if (!b) return;
  const act = b.dataset.setx;
  if (act === "back") { showSet(""); return; }
  if (act === "new") {
    const name = await askName("Name the new set");
    if (!name) return;
    const done = await changeSets({ action: "create", name, items: [] });
    if (done && done.made) { showSet(done.made); toast("Now add products: select them in the Library or Downloads, then choose Sets in the selection bar."); }
    return;
  }
  if (act === "newwish") {   // one of your own, product by product: add them as you'd add to a set
    const name = await askName("Name the new wishlist");
    if (!name) return;
    const done = await changeSets({ action: "create", name, items: [], kind: "wishlist" });
    if (done && done.made) { showSet(done.made); toast("Now add products: select them in the Library or Downloads, then choose Sets in the selection bar, or add a shared set's products."); }
    return;
  }
  if (act === "readwish" || act === "reread") { readWishlists(act === "reread" ? [b.dataset.store] : null); return; }
  if (act === "mix") { mixAndMatch(); return; }
  if (act === "importwish") { importWishlists(); return; }
  if (act === "import") {
    let code = await askName("Paste the set's link or code", "", { max: 262144 });
    if (code && SHORT_LINK.test(code.replace(/\s+/g, ""))) code = await openShortLink(code);
    if (!code) return;
    const done = await changeSets({ action: "import", code });
    if (done && done.made) { showSet(done.made); toast("Added the shared set. Products you don't own yet show where to buy them."); }
    return;
  }
  const s = SETS && SETS.sets.find(x => x.id === state.set); if (!s) return;
  if (act === "wclear") {   // a wishlist's price range
    Object.assign(WISH, { min: "", max: "" });
    for (const x of document.querySelectorAll("#setMore input[data-wish]")) x.value = "";
    return wishChanged();
  }
  if (act === "addlinks") return addByLinks(s);
  if (act === "share") shareSet(s);
  else if (act === "download") { const keys = notDownloaded([s]); if (keys.length) T.download(keys); }
  else if (act === "picture") setPicture(s);
  else if (act === "unpicture") changeSets({ action: "picture", id: s.id, image: null });
  else if (act === "rename") renameSet(s);
  else if (act === "delete") deleteSets([s]);
  else if (act === "out") {
    changeSets({ action: "remove", id: s.id, items: [b.dataset.key] });
  } else if (act === "note") {
    const done = await changeSets({ action: "note", id: s.id, note: $("#setView [data-setnote]").value });
    if (done) toast("Saved the note.");
  } else if (act === "photo") {
    if (s.photos.length >= 8) { toast("A set has up to 8 photos."); return; }
    const url = await askName("Paste a picture's link, or its page on a photo site (Imgur, Gyazo, ImgBB, Bluesky...)", "", { max: 600 });
    if (url) changeSets({ action: "photos", id: s.id, photos: [...s.photos, url] });
  } else if (act === "unphoto") {
    changeSets({ action: "photos", id: s.id, photos: s.photos.filter((u, n) => n !== +b.dataset.n) });
  }
}
// Read my wishlists: from each store chosen, in its own signed-in window, as a task (hoard/wishlists.py)
const WISH_STORES = ["booth", "gumroad", "jinxxy", "payhip"];
async function readWishlists(only) {
  let stores = only;
  if (!stores) {
    const d = document.createElement("dialog");
    d.className = "ask";
    d.innerHTML = `<form method="dialog"><p><b>${esc(tr("Read my wishlists"))}</b></p>` +
      `<p class="hint">${esc(tr("Hoard opens each store's page in its signed-in window and reads your lists, with each product's price. A wishlist read before is brought up to date."))}</p>` +
      WISH_STORES.map(st => `<p><label class="check"><input type="checkbox" value="${st}" checked> ${esc(STORE_NAMES[st])}</label></p>`).join("") +
      `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Read them"))}</button></div></form>`;
    document.body.appendChild(d);
    stores = await new Promise(resolve => {
      d.addEventListener("close", () => {
        const got = d.returnValue === "yes" ? [...d.querySelectorAll("input:checked")].map(x => x.value) : [];
        d.remove(); resolve(got);
      }, { once: true });
      d.showModal();
    });
    if (!stores.length) return;
  }
  const r = await apiPost("/api/wishlists/read", { stores });
  if (!r.ok) { toast(r.data.error || "Hoard is busy. Try again when it's done."); return; }
  toast(r.data.started === "queued" ? "Reading your wishlists after what Hoard is doing now. See Tasks." : "Reading your wishlists. See Tasks for how it's going.");
  const done = await whenTaskEnds("wishlists");   // then they show as read, without opening them again
  await loadSets();
  if (done && done.message) toast(done.message);
}
// Waits for a task (running or waiting its turn) to end, then gives how it went (Tasks' finished entry), or null
async function whenTaskEnds(task, every = 1500) {
  for (let n = 0; n < 4800; n++) {
    await new Promise(ok => setTimeout(ok, every));
    let t;
    try { t = await (await api("/api/tasks", { cache: "no-store" })).json(); } catch (e) { return null; }
    const busy = [t.current, t.project].some(c => c && c.task === task) || (t.queue || []).some(q => q.task === task);
    if (!busy) return (t.history || []).find(h => h.task === task) || null;
  }
  return null;
}
// Import saved wishlist pages: wishlist pages you saved from your own browser, read on this computer
async function importWishlists() {
  const input = Object.assign(document.createElement("input"), { type: "file", multiple: true, accept: ".mhtml,.mht,.html,.htm" });
  const files = await new Promise(resolve => {
    input.addEventListener("change", () => resolve([...input.files]), { once: true });
    input.addEventListener("cancel", () => resolve([]), { once: true });
    input.click();
  });
  const pages = files.filter(f => /\.(mhtml|mht|html|htm)$/i.test(f.name));
  if (!pages.length) { if (files.length) toast('Those aren\'t saved pages. Save the wishlist page as "Webpage, Single File" (.mhtml), and import that.'); return; }
  const said = [], problems = [];
  let lists = 0;
  for (let i = 0; i < pages.length;) {
    const batch = [];
    let bytes = 0;
    while (i < pages.length && batch.length < 10 && (!batch.length || bytes + pages[i].size <= 24 * 1024 * 1024)) { bytes += pages[i].size; batch.push(pages[i++]); }
    toast(tr("Reading {0} of {1} pages...", i, pages.length));
    let sent;
    try { sent = await Promise.all(batch.map(async f => ({ filename: f.name, content: await f.text() }))); }
    catch (e) { batch.forEach(f => problems.push(tr("{0}: couldn't be opened.", f.name))); continue; }
    const r = await apiPost("/api/wishlists/import", { files: sent });
    if (!r.ok) { batch.forEach(f => problems.push(`${f.name}: ${tr(r.data.error || "couldn't be imported.")}`)); if (r.status === 0 || r.status >= 500) break; continue; }
    lists += r.data.lists || 0;
    for (const pg of r.data.pages || []) {
      if (pg.error) problems.push(`${pg.filename}: ${tr(pg.error)}`);
      else pg.lists.forEach(x => said.push(tr("{0}: {1} ({2} products)", pg.filename, x.list, x.products)));
    }
    if (r.data.sets) { SETS = { ...r.data, for: DATA }; drawSets(); }
  }
  await ask([tr(lists === 1 ? "1 wishlist imported." : "{0} wishlists imported.", lists), said.join("\n"),
             problems.length ? tr("Not imported:") + "\n" + problems.join("\n") : ""].filter(Boolean).join("\n\n"), "OK", false, "Close");
  loadSets();
}
function wireSets() {
  for (const box of [$("#setView"), $("#setMore")]) {
    box.addEventListener("click", setAct);
    box.addEventListener("error", e => {   // a picture that isn't there (any more): the tile's letters instead
      if (e.target.tagName !== "IMG") return;
      const tile = e.target.closest(".slot, .sethead");
      e.target.outerHTML = tile && !e.target.closest(".collage") ? setPlaceholder((tile.querySelector(".nm-t, h2") || {}).textContent || "?") : "";
    }, true);
  }
  $("#setView").addEventListener("toggle", e => { if (e.target.matches && e.target.matches("details.setextra")) setExtraOpen = e.target.open; }, true);
  $("#setMore").addEventListener("toggle", e => {   // a wishlist's groups: folded or not, kept with your other folds
    const d = e.target;
    if (!d.matches || !d.matches("details.wishgroup") || ((UI.sections || {})[d.dataset.fold] !== false) === d.open) return;
    uiSave({ sections: { [d.dataset.fold]: d.open } });
  }, true);
  $("#setMore").addEventListener("input", e => {   // a wishlist's price range
    const k = e.target.dataset && e.target.dataset.wish;
    if (!k) return;
    WISH[k] = e.target.value.trim();
    wishChanged();
  });
}
// Add products by link: store pages pasted, one a line; Hoard reads each one's public page (its name, creator, price
// and picture) and adds it to the set or wishlist, so a list of your own can hold what you don't own yet
async function addByLinks(s) {
  const d = document.createElement("dialog");
  d.className = "ask";
  d.innerHTML = `<form method="dialog"><p><b>${esc(tr("Add products by link"))}</b></p>` +
    `<p class="hint">${esc(tr("Paste the links of products on Booth, Gumroad, Jinxxy, Payhip or itch.io, one a line. Hoard reads each product's page, as anyone can see it, for its name, creator, price and picture."))}</p>` +
    `<p><textarea id="addLinks" rows="6" translate="no" style="width:100%;box-sizing:border-box" placeholder="https://booth.pm/en/items/..."></textarea></p>` +
    `<div class="ask-row"><button class="ghost" value="no" formnovalidate>${esc(tr("Cancel"))}</button><button class="primary" value="yes">${esc(tr("Add them"))}</button></div></form>`;
  document.body.appendChild(d);
  const links = await new Promise(resolve => {
    d.addEventListener("close", () => {
      const got = d.returnValue === "yes" ? d.querySelector("textarea").value.split(/\s+/).map(x => x.trim()).filter(Boolean) : [];
      d.remove(); resolve(got);
    }, { once: true });
    d.showModal();
  });
  if (!links.length) return;
  toast(tr(links.length === 1 ? "Reading the product's page..." : "Reading the {0} products' pages...", links.length));
  const done = await changeSets({ action: "add-links", id: s.id, links: links.slice(0, 30) });
  if (!done) return;
  const added = (done.links || []).filter(x => x.added), failed = (done.links || []).filter(x => x.error);
  toast([added.length ? tr(added.length === 1 ? "Added {0}." : "Added {0} products.", added.length === 1 ? added[0].added : added.length) : "",
         failed.length ? tr("Not added: {0}", failed.map(x => `${x.link} (${tr(x.error)})`).join("; ")) : ""].filter(Boolean).join(" "));
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
      const r = await apiPost("/api/cancel", { lane: b.dataset.lane || "" });
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
  let st = {};
  try { st = await (await api("/api/status", { cache: "no-store" })).json(); } catch (e) { /* stopped */ }
  const lanes = [st.job || {}, st.project_job || {}], on = lanes.filter(j => j.running);   // (and a project's task)
  const waiting = lanes.reduce((n, j) => n + (j.queue || []).length, 0);
  $("#closeWhat").textContent = (on.length ? `${on.map(j => j.job_label || "A job").join(" and ")} ${on.length === 1 ? "is" : "are"} running` : "Nothing is running")
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
    if ([t.current, t.project].some(c => c && c.task === task) || (t.queue || []).some(q => q.task === task)) continue;
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

/* ---------- a few things to find. Nothing here reads or changes your library; each stays still with reduced motion */
const motionOk = () => !document.body.classList.contains("less-motion") && !matchMedia("(prefers-reduced-motion: reduce)").matches;
function confetti(n = 90) {   // every store's colour, falling
  if (!motionOk()) return;
  const box = document.createElement("div");
  box.className = "confetti"; box.setAttribute("aria-hidden", "true");
  for (let i = 0; i < n; i++) {
    const p = document.createElement("i");
    p.style.left = `${Math.random() * 100}vw`;
    p.style.background = `var(--${STRIPE_STORES[i % STRIPE_STORES.length]})`;
    p.style.animationDuration = `${1.6 + Math.random() * 1.6}s`;
    p.style.animationDelay = `${Math.random() * 0.9}s`;
    p.style.setProperty("--spin", `${Math.round(Math.random() * 1080 - 540)}deg`);
    box.append(p);
  }
  document.body.append(box);
  setTimeout(() => box.remove(), 4000);
}
// up, up, down, down, left, right, left, right, B, A
const KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];
let konami = 0;
document.addEventListener("keydown", e => {
  if (e.target.closest && e.target.closest("input, textarea, select, [contenteditable]")) { konami = 0; return; }
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  konami = k === KONAMI[konami] ? konami + 1 : k === KONAMI[0] ? 1 : 0;
  if (konami === KONAMI.length) { konami = 0; confetti(); toast("Every store at once. A fine hoard."); }
});
// the logo: while an update waits, it opens Updates; on the Library with nothing filtered, poking it five times...
let pokes = [];
document.addEventListener("click", e => {
  const b = e.target.closest(".brand");
  if (!b || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
  if (b.classList.contains("has-update")) { e.preventDefault(); openSettings(true); return; }
  if (/downloads/.test(location.pathname) || location.hash) return;   // to the Library, or back to all of it
  e.preventDefault();
  const now = Date.now();
  pokes = [...pokes.filter(t => now - t < 2500), now];
  if (pokes.length < 5) return;
  pokes = [];
  b.classList.remove("tumble"); void b.offsetWidth; b.classList.add("tumble");
  toast("Careful: everything in here is somebody's treasure.");
});
// a few words in the search box
const SEARCH_EGGS = { hoard: "You're looking at it.", dragon: "Every hoard needs one. 🐉", treasure: "It's all treasure.",
                      gold: "Shiny." };
const eggSaid = new Set();
let eggTimer;
document.addEventListener("input", e => {
  if (e.target.id !== "q") return;
  clearTimeout(eggTimer);
  eggTimer = setTimeout(() => {
    const w = e.target.value.trim().toLowerCase();
    if (!SEARCH_EGGS[w] || eggSaid.has(w)) return;
    eggSaid.add(w);
    toast(SEARCH_EGGS[w]);
  }, 700);
});
// and on the 1st of April, the boxes have fallen over
if (new Date().getMonth() === 3 && new Date().getDate() === 1) document.documentElement.classList.add("april");

/* ---------- the tour: what Hoard can do, shown on your own library, one thing at a time. It's offered once, in the
   Library (when there's something in it, after setup), and Settings starts it again. Each step points at the part of
   the page it's about, the rest dimmed but still yours to use; a step that asks you to try something (open one of your
   own items, choose two) goes on by itself once you have. It carries on from the Library to Downloads (in
   sessionStorage), and a step about something you don't have yet (nothing downloaded, no updates) is passed by. */
const TOUR = { i: -1, steps: [], timer: null, card: null, ring: null, pick: null, ready: 0, tags: 0, offered: false };
const ON_DOWNLOADS = /downloads/.test(location.pathname);
const ON_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const tourName = s => `<strong>${esc(s)}</strong>`;
// the items the tour shows you: ones drawn near the top of the grid, not a stack of copies, one with a picture first
function tourPick() {
  const drawn = [...document.querySelectorAll("#grid .slot")].slice(0, 60)
    .map(s => T.byId(s.dataset[T.slotKey])).filter(a => a && !T.membersOf(T.id(a)));
  const pic = a => a.thumbnail || a.thumb;
  const inside = a => (a.files || []).some(f => !f.missing && /\.(unitypackage|zip)$/i.test(f.path));
  const item = (ON_DOWNLOADS ? drawn.find(a => inside(a) && pic(a)) || drawn.find(inside) : null) || drawn.find(pic) || drawn[0] || null;
  const words = item ? String(item.name).split(/[\s\-_|/()[\]【】「」『』〔〕.,:;!?+&]+/).filter(w => w.length >= 3) : [];
  return { item, word: words.sort((a, b) => b.length - a.length)[0] || (item ? String(item.name).slice(0, 12) : ""), inside: item && inside(item) };
}
const tourTile = () => TOUR.pick && TOUR.pick.item ? document.querySelector(`#grid .slot[data-${T.slotKey}="${CSS.escape(T.id(TOUR.pick.item))}"]`) : null;
const tourOpen = () => { const o = T.open(); return o && TOUR.pick && TOUR.pick.item && T.id(o) === T.id(TOUR.pick.item) ? o : null; };
// the stores your library is from, the one you have most from first, by name
function tourStores() {
  const n = {};
  for (const a of DATA.items || []) n[a.store] = (n[a.store] || 0) + 1;
  return Object.keys(n).sort((a, b) => n[b] - n[a]).map(s => (DATA.labels || {})[s] || s);
}
const tourCount = () => (ON_DOWNLOADS ? DATA.assets : DATA.items || []).length;
function tourClearSearch() {
  const q = $("#q");
  if (q && q.value) { q.value = ""; q.dispatchEvent(new Event("input", { bubbles: true })); }
}
function tourEnsureDetail() {
  if (!tourOpen() && TOUR.pick && TOUR.pick.item) showDetail(TOUR.pick.item, false);
}
// a section of the details: its heading and what's under it, up to the next heading
function tourSection(el) {
  if (!el) return null;
  let h = el.closest("#detail > *");
  while (h && h.tagName !== "H3" && h.previousElementSibling) h = h.previousElementSibling;
  const out = [h];
  for (let n = h.nextElementSibling; n && n.tagName !== "H3" && !n.classList.contains("path"); n = n.nextElementSibling) out.push(n);
  return out;
}
const tourInsideOpen = () => { const w = $("#insideWin"); return !!w && !w.hidden; };

const TOUR_STEPS = [
  { id: "welcome", page: "library",
    title: () => tr("A quick tour of Hoard"),
    body: () => tourCount()
      ? trHTML("Hoard does a lot more than download. This tour shows you around with your own library, {0} items from {1}, and you can try each thing as you go. It takes a few minutes.",
               esc(tourCount().toLocaleString()), esc(listed(tourStores())))
      : esc(tr("Hoard does a lot more than download. This tour shows you around, and you can try each thing as you go. It takes a few minutes.")),
    next: () => tr("Start") },
  { id: "stores", page: "library", at: () => $("#storeSeg"),
    title: () => tr("Your stores"),
    body: () => esc(tr("Everything you own, from every store you use, in one place. Choose a store to see only what you bought there.")) },
  { id: "search", page: "library", at: () => $(".bar .search"), when: () => TOUR.pick.word,
    title: () => tr("Search"),
    body: () => trHTML("Search finds names, creators and tags as you type. Press / to come here from anywhere. Try it: type {0}.", tourName(TOUR.pick.word)),
    done: () => ($("#q").value || "").trim().length >= 2,
    leave: tourClearSearch },
  { id: "open", page: "library", at: tourTile, when: () => TOUR.pick.item,
    enter: () => { tourClearSearch(); T.closeDetail(); },
    title: () => tr("Open one"),
    body: () => trHTML("Click {0} to see everything about it.", tourName(TOUR.pick.item.name)),
    done: () => !!T.open() },
  { id: "detail", page: "library", at: () => $("#detail.open"), when: () => T.open(),
    title: () => tr("Its details"),
    body: () => esc(tr("Download it from here, or open its store page. Once you have it, Show in Downloads takes you to its files. Tag it to find it again, and if you own it on another store too, it says so.")),
    leave: () => T.closeDetail() },
  { id: "choose", page: "library", at: () => $("#grid"), when: () => TOUR.pick.item,
    enter: () => T.closeDetail(),
    title: () => tr("Choose several"),
    body: () => esc(ON_MAC ? tr("⌘-click two or three items, or tick the box in a tile's corner. Shift-click chooses everything in between, and ⌘A everything shown.")
                           : tr("Ctrl-click two or three items, or tick the box in a tile's corner. Shift-click chooses everything in between, and Ctrl+A everything shown.")),
    done: () => chosenItems().length >= 2 },
  { id: "bar", page: "library", at: () => $("#bulk:not([hidden])"), when: () => chosenItems().length,
    title: () => tr("Do it to all of them"),
    body: () => esc(tr("This bar works on everything you chose: download them, tag them, or archive, hide or remove them. Right-click a tile for the same menu, and Esc lets go of them.")),
    leave: () => clearSelection() },
  { id: "views", page: "library", at: () => $("#views"),
    title: () => tr("Archive, Removed and Hidden"),
    body: () => esc(tr("Archive puts away what you're done with, without losing it. Removed is for what doesn't belong: a sync never downloads it again. Hidden keeps things behind a PIN.")) },
  { id: "sync", page: "library", at: () => $("#syncBtn"),
    title: () => tr("Sync"),
    body: () => esc(tr("Sync reads what you own from your stores, then downloads anything new. Stores is where you sign in, read one store again, or import saved pages instead. In Settings, a routine check can do this for you, and asks before it downloads anything.")) },
  { id: "to-downloads", page: "library", go: "downloads", at: () => $('.apptabs a[href="/downloads"]'),
    title: () => tr("On to your downloads"),
    body: () => esc(tr("Downloads is what Hoard has saved on this computer, with a lot more to do with each one. Click Downloads, or Next.")) },

  { id: "downloads", page: "downloads", at: () => (tourCount() ? $("#grid") : null),
    title: () => tr("Your downloads"),
    body: () => tourCount()
      ? esc(tr("{0} products, {1} on this computer, in folders by store, creator and product.", tourCount().toLocaleString(), sizeText(DATA.assets.reduce((t, a) => t + (a.size || 0), 0))))
      : esc(tr("Nothing's downloaded yet. Sync, or Download new, saves copies of what you own here. The rest of the tour shows what you can do with them then.")) },
  { id: "dl-open", page: "downloads", at: tourTile, when: () => TOUR.pick.item,
    title: () => tr("Open one"),
    body: () => trHTML("Click {0} to see its files.", tourName(TOUR.pick.item.name)),
    done: () => !!tourOpen() },
  { id: "inside", page: "downloads", at: () => $('#detail.open [data-act="inside"]'), when: () => TOUR.pick.inside,
    enter: tourEnsureDetail,
    title: () => tr("Look inside"),
    body: () => esc(tr("See what a Unity package or a zip holds, with pictures, without unpacking it or opening Unity. Try it: Look inside.")),
    done: tourInsideOpen },
  { id: "inside-win", page: "downloads", at: () => $("#insideWin:not([hidden])"), when: tourInsideOpen,
    title: () => tr("Search inside"),
    body: () => esc(tr("Open its folders, or search for a file by name. Hoard reads it where it is, and changes nothing.")),
    leave: () => { if (tourInsideOpen()) WINDOWS.insideWin(); } },
  { id: "needs", page: "downloads", at: () => tourSection($("#detail.open #needsHead")), when: () => TOUR.pick.item && TOUR.pick.item.needs,
    enter: tourEnsureDetail,
    title: () => tr("What it needs"),
    body: () => esc(tr("Hoard reads each package for what else it uses, such as a shader or a tool, with a link to get it. Hoard for Unity checks it too, and asks before importing something your project is missing.")) },
  { id: "tags", page: "downloads", at: () => tourSection($("#detail.open #tagInput")), when: () => TOUR.pick.item,
    enter: () => { tourEnsureDetail(); TOUR.tags = ((tourOpen() || {}).tags || []).length; },
    title: () => tr("Tags"),
    body: () => esc(tr("Tags are your own words for things: an outfit, a base, a style. Add one here, or to many at once from the selection bar. Suggested tags come from words in your items' names. In Tags, give a tag a kind, such as Avatar or Clothing, and your tags are grouped by it.")),
    done: () => ((tourOpen() || {}).tags || []).length > TOUR.tags },
  { id: "sets", page: "downloads", at: () => $('#stores [data-store="Sets"]'),
    enter: () => T.closeDetail(),
    title: () => tr("Sets and wishlists"),
    body: () => esc(tr("A set gathers products that go together, such as an avatar and its outfits, downloaded or not, with a picture of your choosing. Make one in Sets, from the selection bar, or from a project in Projects. Share it as a short link that shows what's in it and where to buy each, for 14 days. Hoard for Unity imports a whole set at once.")) +
      " " + esc(tr("Try it: open Sets and wishlists.")),
    done: inSets },
  // in the Sets tab, once it's open (else these two are passed by)
  { id: "wishlists", page: "downloads", at: () => { const b = $('[data-setx="readwish"]'); return b && b.closest(".sets-top"); }, when: inSets,
    title: () => tr("Wishlists"),
    body: () => esc(tr("Your wishlists from the stores live here too, with what each product costs: Read my wishlists brings them in from the stores you're signed in to. Read them again later, and what got cheaper is marked.")) },
  { id: "mix", page: "downloads", at: () => $('[data-setx="mix"]'), when: inSets,
    title: () => tr("Mix and match"),
    body: () => esc(tr("Mix and match picks an avatar and an outfit at random from what you own, by your tags' kinds: an Avatar tag on your bases, and Clothing tags on your clothes. Keep the picks you like, pick the rest again, and make a set of them.")),
    leave: () => { if (inSets()) { state.store = ""; state.set = ""; T.render(); } } },
  { id: "updates", page: "downloads", at: () => $('#views [data-view="updates"]'),
    title: () => tr("Updates"),
    body: () => esc(tr("When a store has newer files for something you downloaded, it's listed here. Settings can keep the previous version too, so you can go back.")) },
  { id: "space", page: "downloads", at: () => $('#views [data-view="space"]'),
    title: () => tr("Disk space"),
    body: () => esc(tr("What takes the most room, files kept twice, what no project uses, and products you have from more than one store. Try it: Disk space.")),
    done: () => state.view === "space" },
  { id: "dupes", page: "downloads", at: () => $('[data-space="dupes"]') || $("#viewBar:not([hidden])"), when: () => state.view === "space",
    title: () => tr("Free some room"),
    body: () => esc(tr("Choose from any of these lists to move things to another library folder, archive them or delete their files. From more than one store keeps one store's copy, and the others won't download again.")),
    leave: () => showView("downloads") },
  { id: "local", page: "downloads", at: () => $('.apptabs a[href="/downloads#store=Local"]'),
    title: () => tr("Local"),
    body: () => esc(tr("Your own packages, textures and materials can live here beside what you bought: tagged, searched and imported into Unity like the rest, each with a picture of your choosing. Add your own, in Local, brings them in.")) },
  { id: "projects", page: "downloads", at: () => $("#projectsTab"),
    title: () => tr("Projects"),
    body: () => esc(tr("Projects is your Unity projects, the same list as ALCOM's and the VRChat Creator Companion's: make one from a template with the packages and products from your library it needs, open it in Unity, and change its packages. With Hoard for Unity in a project, it shows what the project uses, and its credits.")) + " " +
      esc(tr("Backups, in Projects, lists your projects' backups, and deletes or moves the old ones when the drive runs low on room.")) },
  { id: "tasks", page: "downloads", at: () => $("#tasksTab"),
    title: () => tr("Tasks"),
    body: () => esc(tr("Everything Hoard does, such as a sync or a download, shows here as it runs, and what it found. You can carry on meanwhile.")) },
  { id: "settings", page: "downloads", at: () => $("#settingsBtn"),
    title: () => tr("Settings"),
    body: () => esc(tr("Your language, light or dark, themes, styles and text size; the routine check; previous versions; more library folders; and Backup, for your tags, sets and settings. This tour is there too.")) },
  { id: "end", page: "downloads",
    title: () => tr("That's the tour"),
    body: () => esc(tr("You've seen the main things. Hoard's wiki has the rest, and What's new, in Settings, lists every change.")),
    next: () => tr("Finish") },
];
TOUR.steps = TOUR_STEPS;

function tourSave(id) { try { if (id) sessionStorage.setItem("hoard-tour", id); else sessionStorage.removeItem("hoard-tour"); } catch (e) { /* this page only */ } }
function tourBuild() {
  if (TOUR.card) return;
  TOUR.ring = document.createElement("div");
  TOUR.ring.className = "tour-ring";
  TOUR.ring.setAttribute("aria-hidden", "true");
  TOUR.card = document.createElement("div");
  TOUR.card.className = "tour-card";
  TOUR.card.setAttribute("role", "dialog");
  TOUR.card.setAttribute("aria-labelledby", "tourTitle");
  TOUR.card.setAttribute("aria-describedby", "tourBody");
  TOUR.card.setAttribute("translate", "no");   // (in your language already: tr())
  TOUR.card.tabIndex = -1;
  TOUR.card.innerHTML = `<p class="tour-n" id="tourN"></p><h2 id="tourTitle"></h2><p id="tourBody"></p>` +
    `<p class="tour-try" id="tourTry" hidden></p>` +
    `<div class="tour-go"><button class="linkish" data-tour="end"></button>` +
    `<span><button class="ghost sm" data-tour="back"></button> <button class="primary sm" data-tour="next"></button></span></div>`;
  TOUR.card.addEventListener("click", e => {
    const b = e.target.closest("[data-tour]");
    if (b) tourMove(b.dataset.tour);
  });
  document.body.append(TOUR.ring, TOUR.card);
}
function tourStart(at = 0) {
  tourBuild();
  if ($("#tourNote")) $("#tourNote").hidden = true;
  for (const w of document.querySelectorAll(".win:not([hidden])")) if (WINDOWS[w.id]) WINDOWS[w.id]();   // (Settings, where it was started)
  uiSave({ toured: true });   // offered no more, however it ends
  TOUR.pick = tourPick();
  TOUR.i = -1;
  tourShow(at, 1);
  clearInterval(TOUR.timer);
  TOUR.timer = setInterval(tourTick, 250);
}
function tourEnd(finished) {
  clearInterval(TOUR.timer);
  const step = TOUR.steps[TOUR.i];
  if (step && step.leave) try { step.leave(); } catch (e) { /* gone already */ }
  TOUR.i = -1;
  if (TOUR.card) { TOUR.card.remove(); TOUR.ring.remove(); TOUR.card = TOUR.ring = null; }
  tourSave(null);
  if (finished) toast("Take the tour again any time, from Settings.");
}
// to step n, or the next one there's something to show for, going the way you went (dir 1 or -1)
function tourShow(n, dir) {
  const here = ON_DOWNLOADS ? "downloads" : "library";
  for (; n >= 0 && n < TOUR.steps.length; n += dir) {
    const s = TOUR.steps[n];
    if (s.page !== here) break;
    let ok = true;
    try { ok = !s.when || !!s.when(); } catch (e) { ok = false; }
    if (ok) break;
  }
  if (n < 0) n = TOUR.steps.findIndex(s => s.page === here);
  if (n >= TOUR.steps.length) { tourEnd(true); return; }
  const s = TOUR.steps[n];
  if (s.page !== here) {   // the next step is on the other page: off there
    tourSave(s.id);
    location.href = s.page === "downloads" ? "/downloads" : "/";
    return;
  }
  TOUR.i = n; TOUR.ready = Date.now() + 600;   // (what you did just before doesn't count for this step)
  tourSave(s.id);
  try { if (s.enter) s.enter(); } catch (e) { /* the page changed under it */ }
  const el = tourTarget(s)[0];
  if (el) el.scrollIntoView({ block: "center", inline: "nearest" });
  tourDraw();
}
function tourMove(how) {
  const s = TOUR.steps[TOUR.i];
  if (how === "end") { tourEnd(false); return; }
  if (s && s.leave) try { s.leave(); } catch (e) { /* gone already */ }
  if (how === "next" && s && s.go) { tourSave(s.id); location.href = s.go === "downloads" ? "/downloads" : "/"; return; }
  tourShow(TOUR.i + (how === "back" ? -1 : 1), how === "back" ? -1 : 1);
}
function tourDraw() {
  const s = TOUR.steps[TOUR.i], c = TOUR.card;
  if (!s || !c) return;
  const last = TOUR.i === TOUR.steps.length - 1;
  c.querySelector("#tourN").textContent = tr("{0} of {1}", TOUR.i + 1, TOUR.steps.length);
  c.querySelector("#tourTitle").textContent = s.title();
  c.querySelector("#tourBody").innerHTML = s.body();
  c.querySelector("#tourTry").hidden = !s.done;
  c.querySelector("#tourTry").textContent = tr("Try it, and the tour goes on by itself.");
  c.querySelector('[data-tour="end"]').textContent = last ? "" : tr("End the tour");
  c.querySelector('[data-tour="end"]').hidden = last;
  const back = c.querySelector('[data-tour="back"]');
  back.textContent = tr("Back");
  back.hidden = TOUR.i === 0 || TOUR.steps[TOUR.i - 1].page !== s.page;
  c.querySelector('[data-tour="next"]').textContent = s.next ? s.next() : s.done ? tr("Skip") : tr("Next");
  tourPlace();
  // the card has the focus, so its words are read out and Next is a Tab away, unless you're typing (the search)
  if (!document.activeElement || !document.activeElement.matches("input, textarea, select")) c.focus({ preventScroll: true });
}
// what a step points at: one element, or a few together (a section of the details), as they are on the page now
function tourTarget(s) {
  let got = null;
  try { got = s.at ? s.at() : null; } catch (e) { got = null; }
  return (Array.isArray(got) ? got : [got]).filter(e => e && e.isConnected);
}
// the ring round the part the step is about (the rest dimmed), and the card beside it where there's room
function tourPlace() {
  const s = TOUR.steps[TOUR.i], c = TOUR.card, ring = TOUR.ring;
  if (!s || !c) return;
  const rects = tourTarget(s).map(e => e.getBoundingClientRect()).filter(b => b.width > 0 && b.height > 0);
  const r = rects.length ? { left: Math.min(...rects.map(b => b.left)), top: Math.min(...rects.map(b => b.top)),
                             right: Math.max(...rects.map(b => b.right)), bottom: Math.max(...rects.map(b => b.bottom)) } : null;
  if (r) { r.width = r.right - r.left; r.height = r.bottom - r.top; }
  const seen = r && r.bottom > 0 && r.top < innerHeight;
  const z = pageZoom(), pad = 6, gap = 14, m = 12, w = c.offsetWidth * z, h = c.offsetHeight * z;   // (the window's pixels: see pageZoom)
  ring.classList.toggle("none", !seen);
  c.classList.toggle("middle", !seen);
  if (!seen) { c.style.left = c.style.top = ""; c.classList.remove("docked"); ring.removeAttribute("style"); return; }
  const top = Math.max(r.top - pad, 0), bottom = Math.min(r.bottom + pad, innerHeight);
  Object.assign(ring.style, { left: `${(r.left - pad) / z}px`, top: `${top / z}px`, width: `${(r.width + pad * 2) / z}px`, height: `${(bottom - top) / z}px` });
  if (innerWidth <= 560) { c.style.left = c.style.top = ""; c.classList.add("docked"); return; }
  c.classList.remove("docked");
  let x, y;
  if (innerHeight - bottom >= h + gap + m) { y = bottom + gap; x = r.left; }
  else if (top >= h + gap + m) { y = top - gap - h; x = r.left; }
  else if (innerWidth - r.right >= w + gap + m) { x = r.right + pad + gap; y = r.top; }
  else if (r.left >= w + gap + m) { x = r.left - pad - gap - w; y = r.top; }
  else { x = innerWidth - w - m; y = innerHeight - h - m; }   // a big part (the grid): in its corner
  c.style.left = `${Math.max(m, Math.min(x, innerWidth - w - m)) / z}px`;
  c.style.top = `${Math.max(m, Math.min(y, innerHeight - h - m)) / z}px`;
}
function tourTick() {
  const s = TOUR.steps[TOUR.i];
  if (!s || !TOUR.card) return;
  tourPlace();
  let done = false;
  try { done = !!(s.done && Date.now() > TOUR.ready && s.done()); } catch (e) { done = false; }
  if (done) { TOUR.ready = Infinity; setTimeout(() => { if (TOUR.steps[TOUR.i] === s) tourMove("next"); }, 700); }
}
// on each page: carry on where the tour was (from the Library to Downloads), and the Library offers it, once
function tourResume() {
  let id = null;
  try { id = sessionStorage.getItem("hoard-tour"); } catch (e) { id = null; }
  if (!id) return false;
  const n = TOUR.steps.findIndex(s => s.id === id), here = ON_DOWNLOADS ? "downloads" : "library";
  if (n < 0) { tourSave(null); return false; }
  const s = TOUR.steps[n];
  if (s.page === here) tourStart(n);
  else if (s.go === here) tourStart(n + 1);
  else tourSave(null);   // somewhere else since: it ends there
  return true;
}
function tourOffer() {
  const note = $("#tourNote");
  let going = null;
  try { going = sessionStorage.getItem("hoard-tour"); } catch (e) { going = null; }
  if (!note || going || TOUR.offered || TOUR.i >= 0 || (UI && UI.toured) || !DATA.setup_done || !tourCount() || ($("#setup") && !$("#setup").hidden)) return;
  TOUR.offered = true;
  note.hidden = false;
}
function wireTour() {
  const again = $("#tourAgain");
  if (again) again.addEventListener("click", () => {
    if (ON_DOWNLOADS) { tourSave(TOUR.steps[0].id); location.href = "/"; } else tourStart(0);
  });
  const note = $("#tourNote");
  if (note) note.addEventListener("click", e => {
    const b = e.target.closest("[data-tour-note]");
    if (!b) return;
    note.hidden = true;
    if (b.dataset.tourNote === "go") tourStart(0); else { uiSave({ toured: true }); toast("Take the tour any time, from Settings."); }
  });
  addEventListener("resize", () => { if (TOUR.i >= 0) tourPlace(); });
  document.addEventListener("scroll", () => { if (TOUR.i >= 0) tourPlace(); }, { capture: true, passive: true });
}
