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
function applyDisplay(d) {
  if (!d) return;
  // the theme, in place of the one the page was served with (the same colours, from the same place)
  const theme = $("#theme");
  if (theme && typeof d.theme_css === "string" && theme.textContent.trim() !== d.theme_css.trim()) { theme.textContent = d.theme_css; }
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
  $("#setGlowOn").checked = SETTINGS.display.glow;
  $("#setColours").value = SETTINGS.display.colours;
  fillColours();
  fillThemes();
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
  const cur = t.current;
  const problems = h => ((h.report && h.report.problems) || []);
  $("#tasksBody").innerHTML =
    `<h3>Running</h3>` + (cur
      ? `<div class="task run"><div class="task-top"><span class="spin" aria-hidden="true"></span><b>${esc(cur.label)}</b>` +
        (STOPPABLE.includes(cur.task) ? `<button class="ghost sm" data-task="stop">Stop</button>` : "") +
        `<button class="ghost sm" data-task="force" title="End it now, whatever it's doing">Force stop</button></div>` +
        (cur.transfer ? transferHtml(cur.transfer) : `<p class="task-msg">${esc(cur.message || "Starting")}</p>`) +
        `<details class="live" data-id="${esc(cur.id)}"${open.has(cur.id) ? " open data-kept" : ""}><summary>Progress</summary><pre>${esc((cur.log || []).join("\n"))}</pre></details></div>`
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
  taskCount((cur ? 1 : 0) + t.queue.length);
}
// opening what's running shows its newest lines (while it was closed, it had no size to scroll)
document.addEventListener("toggle", e => {
  const d = e.target;
  if (!d.matches || !d.matches("#tasksBody details.live[open]")) return;
  if (d.hasAttribute("data-kept")) { d.removeAttribute("data-kept"); return; }   // open before it was drawn again: left in place
  const pre = d.querySelector("pre");
  if (pre) pre.scrollTop = pre.scrollHeight;
}, true);
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
  if (!list.length) return `<p class="none">No projects yet. Open <strong>Hoard › Open Hoard</strong> in a Unity project
    (<strong>Window › Hoard</strong> before Hoard for Unity 0.7.0) and it appears here, with every asset it uses and its credits list.</p>`;
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
