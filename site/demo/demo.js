/* Try Hoard (issue #394): Hoard's own pages, in the visitor's browser, with this standing in for Hoard's local server.
   scripts/build_site_demo.py builds the pages (index.html, downloads.html) from the app's, with what a real Hoard's
   server answered them (#demo-data): this runs before the app's own script, and answers its requests from that.

   - It starts at a pretend sign-in, the demo's accounts filled in: nothing is sent to any store, and there's no
     account anyone could use. Signing in shows the library.
   - Tags, marks (archive, remove, hide, 18+), sets and wishlists, and how Hoard looks (Settings) change as they do in
     Hoard, here in the page, until its tab is closed (sessionStorage).
   - Sets can be brought in as in Hoard: Add a shared set (a set's code, or its short link, fetched from Hoard's share
     server and unlocked here with its key, which is never sent), and Import JSON (a set's file, read here). The
     website's set viewer and set maker open one here: #import=<its code or short link>.
   - What needs Hoard on your computer (downloading, opening folders, Unity, reading the stores) says so, with
     Download Hoard.
   - Pictures come from the stores' own image hosts (and a shared set's photos from the photo sites Hoard takes). The
     page's policy lets nothing else leave the browser, but a short link's locked set from Hoard's share server: every
     other request the app makes is answered here. */
"use strict";
(() => {
  const DATA = JSON.parse(document.getElementById("demo-data").textContent);
  const KEPT = "hoard-demo";   // sessionStorage: what changed, and the sign-in, until the tab is closed
  const BASE = location.pathname.replace(/\/(downloads(\.html)?|index\.html)?$/, "");   // where the demo is: /demo
  const DOWNLOAD = "/#download";
  const NEEDS = "That needs Hoard on your computer: this is the demo, in your browser.";
  const OURS = /^\/(api|thumb|setpic|setphoto|files|look|preview)\//;
  const SHARE = "https://hoard-share.furryup.link";   // Hoard's share server: where a short link's set is kept, locked
  const SHORT_ID = /^[0-9A-Za-z]{10}$/;
  // where each store keeps its products' pictures, and the photo sites a shared set's photos may be on (as the set
  // viewer and Hoard take them: site/set.js, hoard/sets.py)
  const PICTURE_HOSTS = { booth: ["booth.pximg.net"], gumroad: ["public-files.gumroad.com"], jinxxy: ["jinxxy-c.jinxxy-cdn.com"],
                          payhip: ["images.payhip.com"], itch: ["img.itch.zone"] };
  const STORE_SITES = { booth: "booth.pm", gumroad: "gumroad.com", jinxxy: "jinxxy.com", payhip: "payhip.com", itch: "itch.io" };
  const PHOTO_HOSTS = ["i.imgur.com", "i.gyazo.com", "pbs.twimg.com", "cdn.bsky.app", "i.redd.it", "i.postimg.cc", "i.ibb.co",
                       "cdn.discordapp.com", "media.discordapp.net", "booth.pximg.net", "img.itch.zone", "public-files.gumroad.com"];
  const realFetch = window.fetch.bind(window);

  // An answer's key: its path, and its query as name and value pairs in order (but the access key).
  const keyOf = url => JSON.stringify([url.pathname, [...url.searchParams].filter(([k]) => k !== "k").sort()]);
  // A deep copy of something read from JSON.
  const copy = x => JSON.parse(JSON.stringify(x));

  const answers = new Map();   // keyOf(url) -> the answer, as it is now
  for (const [key, value] of Object.entries(DATA.answers)) answers.set(keyOf(new URL(key, location.origin)), copy(value));
  const state = { signedIn: false, changed: {} };   // changed: answers changed here, by key, kept for the tab
  // a set to bring in, from the website's set viewer or set maker (#import=...): out of the address before the app
  // reads it, and offered once the library's shown
  const address = new URLSearchParams(location.hash.slice(1)), bringIn = address.get("import");
  if (bringIn !== null) {
    address.delete("import");
    history.replaceState(null, "", location.pathname + location.search + (address.toString() ? "#" + address : ""));
  }
  try {
    const kept = JSON.parse(sessionStorage.getItem(KEPT) || "null");
    if (kept && typeof kept === "object") {
      state.signedIn = kept.signedIn === true;
      for (const [key, value] of Object.entries(kept.changed || {})) if (answers.has(key)) answers.set(key, value);
      state.changed = kept.changed || {};
    }
  } catch (e) { /* no storage (a private window, say): it lasts until the page is left */ }

  // The answer at a path (no query), or null.
  const at = path => answers.get(keyOf(new URL(path, location.origin))) || null;
  // Keep the answers that changed, for the rest of the tab's life.
  function keep(...paths) {
    for (const path of paths) {
      const key = keyOf(new URL(path, location.origin));
      if (answers.has(key)) state.changed[key] = answers.get(key);
    }
    try { sessionStorage.setItem(KEPT, JSON.stringify({ signedIn: state.signedIn, changed: state.changed })); }
    catch (e) { /* full, or none: it lasts until the page is left */ }
  }

  // ---- the requests the app makes, answered here

  let signedInNow, libraryShown;
  const signIn = new Promise(done => { signedInNow = done; });
  const shown = new Promise(done => { libraryShown = done; });   // once the app has the library (for #import)
  if (state.signedIn) signedInNow();

  // A JSON answer.
  const json = (value, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

  // Every product the library and Downloads list, wherever it is (for a change to reach both).
  function everyProduct() {
    return [...((at("/api/library") || {}).items || []), ...((at("/api/assets") || {}).assets || [])];
  }
  // The products a change names (by their tag_key).
  const named = keys => { const want = new Set(Array.isArray(keys) ? keys : []); return everyProduct().filter(p => want.has(p.tag_key)); };

  // Tags (hoard/tags.py's actions): onto and off products, and new ones.
  function tagsChange(body) {
    const tagset = (at("/api/library") || {}).tagset || { tags: [] };
    // A tag as Hoard keeps it (tags.clean_tag): lower case, letters, digits and a few marks, 40 at most.
    const tidy = t => String(t || "").toLowerCase().replace(/[^\p{L}\p{N} _.+&'-]+/gu, " ").replace(/\s+/g, " ").trim().slice(0, 40);
    // A tag in the list of tags, when it's new.
    const known = name => { if (name && !tagset.tags.some(t => t.name === name)) tagset.tags.push({ name, match: null, type: null, count: 0 }); };
    if (body.action === "assign") {
      const add = (body.add || []).map(tidy).filter(Boolean), remove = (body.remove || []).map(tidy).filter(Boolean);
      if (!add.length && !remove.length) return json({ error: "Choose items and a tag." }, 400);
      add.forEach(known);
      for (const p of named(body.keys)) p.tags = [...new Set([...(p.tags || []), ...add])].filter(t => !remove.includes(t)).sort();
    } else if (body.action === "create") {
      known(tidy(body.name));
    } else if (body.action === "note") {
      for (const p of named(body.keys)) p.your_note = String(body.note || "").slice(0, 2000);
    } else if (body.action === "set-type") {
      for (const p of named(body.keys)) { p.type = body.type || p.type; p.type_from = body.type ? "you" : p.type_from; }
    } else if (body.action === "delete") {
      const name = tidy(body.name);
      tagset.tags = tagset.tags.filter(t => t.name !== name);
      for (const p of everyProduct()) p.tags = (p.tags || []).filter(t => t !== name);
    } else return needs("Hoard's tag lists");
    const counts = new Map();
    for (const p of (at("/api/library") || {}).items || []) for (const t of p.tags || []) counts.set(t, (counts.get(t) || 0) + 1);
    for (const t of tagset.tags) t.count = counts.get(t.name) || 0;
    keep("/api/library", "/api/assets");
    return json({ ok: true });
  }

  // Marks (Archive, Remove, Hide, 18+, Not a copy): on or off for products.
  function marksChange(body) {
    const on = body.on !== false, products = named(body.keys);
    const mark = { archived: "archived", removed: "removed", hidden: "hidden" }[body.kind];
    for (const p of products) {
      if (mark) p.mark = on ? mark : (p.mark === mark ? null : p.mark);
      else if (body.kind === "unarchived") p.mark = p.mark === "archived" ? null : p.mark;
      else if (body.kind === "apart") p.apart = on;
      else if (body.kind === "adult") { p.adult = on; p.adult_from = on ? "you" : null; if (on) p.not_adult = false; }   // (adult.why's)
      else if (body.kind === "not_adult") { p.not_adult = on; if (on) { p.adult = false; p.adult_from = null; } }
      else return needs("That mark");
    }
    keep("/api/library", "/api/assets");
    return json({ ok: true });
  }

  // A value as plain text of at most n characters, or "".
  const text = (v, n) => typeof v === "string" ? v.normalize("NFC").replace(/[\p{Cc}\p{Cf}]/gu, " ").replace(/\s+/g, " ").trim().slice(0, n) : "";
  // An https address on one of these hosts (or, with subdomains, under one), or "".
  function https(value, hosts, subdomains = false) {
    if (typeof value !== "string" || value.length > 600) return "";
    let u;
    try { u = new URL(value); } catch (e) { return ""; }
    const host = u.hostname.toLowerCase();
    if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return "";
    return hosts.some(h => host === h || (subdomains && host.endsWith("." + h))) ? u.href : "";
  }
  // A set's code unpacked (hoard/sets.py's _pack, as the set viewer reads it): its JSON. Throws when it isn't one.
  async function unpack(code) {
    if (!code.startsWith("H1.") || code.length > 256 * 1024) throw new Error("That isn't a Hoard set code. A set's code starts with H1.");
    try { return await unpacked(code); }
    catch (e) { throw e instanceof TooLarge ? e : new Error("That set code is damaged, or cut short: copy all of it, and try again."); }
  }
  class TooLarge extends Error {}
  // A set code's JSON (unpack, which says what's wrong with one in Hoard's words).
  async function unpacked(code) {
    const b64 = code.slice(3).replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(b64 + "===".slice((b64.length + 3) % 4)), c => c.charCodeAt(0));
    const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader(), parts = [];
    let size = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > 1024 * 1024) { reader.cancel(); throw new TooLarge("That set is too large."); }
      parts.push(value);
    }
    return JSON.parse(new TextDecoder().decode(await new Blob(parts).arrayBuffer()));
  }
  // A product a shared set or a set's file brings, checked as Hoard checks one: its store, name, creator, store page
  // and picture (from its store's own host). null when it isn't one.
  function product(store, id, name, creator, url, picture, adult) {
    store = String(store || "").toLowerCase();
    name = text(name, 300);
    if (!PICTURE_HOSTS[store] || !name) return null;
    return { store, id: text(id == null ? "" : String(id), 120), name, creator: text(creator, 200), url: https(url, [STORE_SITES[store]], true),
             picture: https(picture, PICTURE_HOSTS[store]), adult: adult === true || adult === 1 };
  }
  // A shared set from its code, or a link with it (hoard/sets.py's from_code).
  async function fromCode(given) {
    let code = String(given || "").trim();
    if (code.includes("#")) code = code.split("#")[1];
    const doc = await unpack(code.replace(/\s+/g, ""));
    if (!doc || doc.v !== 1 || !Array.isArray(doc.i)) throw new Error("That isn't a Hoard set code.");
    const items = doc.i.slice(0, 500).filter(Array.isArray).map(r => product(r[0], r[1], r[2], r[3], r[4], r[5], r[6])).filter(Boolean);
    if (!items.length) throw new Error("That set has no products Hoard can show.");
    const photos = (Array.isArray(doc.p) ? doc.p.slice(0, 8) : []).map(u => https(u, PHOTO_HOSTS)).filter(Boolean);
    const note = typeof doc.d === "string" ? doc.d.split(/\r?\n/).slice(0, 20).map(l => text(l, 1000)).join("\n").trim() : "";
    return { name: text(doc.n, 60) || "A shared set", note, photos, items };
  }
  // A set from its JSON file (Export JSON...'s: hoard/sets.py's import_json).
  function fromFile(raw) {
    const s = raw && raw.format === "hoard-set" && raw.version === 1 && raw.set;
    if (!s || !Array.isArray(s.items) || !text(s.name, 60)) throw new Error("That file isn't a set's or wishlist's JSON.");
    const known = s.products && typeof s.products === "object" ? s.products : {};
    const items = s.items.slice(0, 500).map(k => { const p = known[k] || {}; return product(p.store, p.id, p.name, p.creator, p.url || p.page, p.thumbnail || p.picture, p.adult); })
      .filter(Boolean);
    return { name: text(s.name, 60), note: typeof s.note === "string" ? s.note.slice(0, 4000) : "",
             photos: (Array.isArray(s.photos) ? s.photos.slice(0, 8) : []).map(u => https(u, PHOTO_HOSTS)).filter(Boolean),
             items, kind: s.kind === "wishlist" ? "wishlist" : null };
  }
  // A short link's locked set, from Hoard's share server (the page unlocks it with the link's key, never sent).
  async function fromShare(id) {
    if (!SHORT_ID.test(String(id || ""))) return json({ error: "That short link has run out (short links last 14 days), or whoever shared it deleted it." }, 404);
    try {
      const r = await realFetch(`${SHARE}/v1/sets/${id}`, { credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" });
      const got = r.ok ? await r.json() : null;
      if (!got || typeof got.data !== "string" || !/^[A-Za-z0-9_-]{1,400000}$/.test(got.data))
        return json({ error: r.status === 404 || r.status === 410 ? "That short link has run out (short links last 14 days), or whoever shared it deleted it."
                                                                   : "That short link's set couldn't be had. Try again in a moment." }, r.ok ? 502 : 404);
      return json({ ok: true, data: got.data, expires: Number(got.expires) || 0 });
    } catch (e) { return json({ error: "Hoard's share server didn't answer. Try again in a moment." }, 502); }
  }

  // Sets and wishlists (hoard/sets.py's actions): made, renamed, deleted, noted, products in and out, and brought in
  // (a shared set's code or short link, or a set's file).
  async function setsChange(body) {
    if (body.action === "open-short") return fromShare(body.short);
    if (body.action === "import" || body.action === "import-json") {
      let got;
      try { got = body.action === "import" ? await fromCode(body.code) : fromFile(body.file); }
      catch (e) { return json({ error: e.message || "That isn't a set Hoard can add." }, 400); }
      return json({ ok: true, made: addSet(got, true, body.action === "import") });
    }
    return setsChangeOwn(body);
  }

  // A set (or wishlist) added to the Sets tab, its products shown as owned when they're in the library; brought in
  // (a shared one), its name made its own when it's taken. One from someone's link (a code or a short link) is kept
  // apart from your own, its photos shown when you ask, as Hoard does (hoard/sets.py's from_link). Returns its id.
  function addSet(got, broughtIn, fromLink = false) {
    const view = at("/api/sets") || { sets: [] }, lib = at("/api/library") || {};
    const summary = lib.sets || (lib.sets = []), library = (lib.items || []);
    let name = got.name;
    for (let n = 2; broughtIn && view.sets.some(s => s.name === name); n++) name = `${got.name} (${n})`;
    const id = Math.random().toString(16).slice(2, 10);
    const seen = new Set();
    const items = got.items.map(p => {
      // the library's own product: by its key, its store page, its id there, or its name (as Hoard matches them)
      const mine = library.find(i => i.tag_key === p.key) || (p.url && library.find(i => i.url === p.url)) ||
                   (p.id && library.find(i => i.store === p.store && String(i.id) === p.id)) ||
                   library.find(i => i.store === p.store && i.name.toLowerCase() === String(p.name).toLowerCase());
      return { key: mine ? mine.tag_key : `${p.store}:${p.id || p.name.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "")}`, store: p.store,
               name: mine ? mine.name : p.name, creator: mine ? mine.creator : p.creator, url: (mine && mine.url) || p.url,
               pic: "", picture: (mine && mine.thumbnail) || p.picture, owned: !!mine, lib: null, download: null, local: false,
               placeholder: false, mark: null, adult: !!(p.adult || (mine && mine.adult)) };
    }).filter(i => !seen.has(i.key) && seen.add(i.key));   // (each product once, as Hoard keeps a set)
    view.sets.push({ id, name, note: got.note || "", dependencies: [], photos: got.photos || [], marks: {}, photo_p: [],
                     cover: null, short: null, short_ended: null, items, ...(got.kind === "wishlist" ? { kind: "wishlist" } : {}),
                     ...(fromLink ? { from_link: true } : {}) });
    summary.push({ id, name, kind: got.kind === "wishlist" ? "wishlist" : null, items: items.map(i => i.key),
                   owned: items.filter(i => i.owned).length, adult: items.some(i => i.adult) });
    downloadsSets();
    keep("/api/sets", "/api/library", "/api/assets");
    return id;
  }

  // Sets' own changes: made, renamed, deleted, noted, and products in and out.
  function setsChangeOwn(body) {
    const view = at("/api/sets") || { sets: [] }, lib = at("/api/library") || {};
    const summary = lib.sets || (lib.sets = []);
    const one = view.sets.find(s => s.id === body.id), short = summary.find(s => s.id === body.id);
    const byKey = new Map(everyProduct().map(p => [p.tag_key, p]));
    // A product as a set lists it (what the Sets tab shows of it).
    const entry = key => {
      const p = byKey.get(key) || {};
      return { key, store: p.store, name: p.name || key, creator: p.creator, url: p.url, pic: "", owned: byKey.has(key),
               lib: null, download: null, local: false, placeholder: false, mark: p.mark || null, adult: !!p.adult };
    };
    const name = String(body.name || "").trim().slice(0, 120);
    if (body.action === "create") {
      if (!name) return json({ error: "Give the set a name." }, 400);
      const items = [...new Set(body.items || [])].map(entry);
      const id = addSet({ name, note: String(body.note || ""), photos: [], kind: body.kind,
                          items: items.map(i => ({ ...i, picture: (byKey.get(i.key) || {}).thumbnail || "" })) }, false);
      return json({ ok: true, made: id });
    }
    if (!one) return json({ error: "That set isn't there anymore." }, 400);
    if (body.action === "rename") { if (!name) return json({ error: "Give the set a name." }, 400); one.name = name; short.name = name; }
    else if (body.action === "delete") { view.sets = view.sets.filter(s => s !== one); lib.sets = summary.filter(s => s !== short); }
    else if (body.action === "note") one.note = String(body.note || "").slice(0, 4000);
    else if (body.action === "add" || body.action === "remove") {
      const keys = new Set(body.items || []);
      if (body.action === "add") { for (const k of keys) if (!one.items.some(i => i.key === k)) one.items.push(entry(k)); }
      else one.items = one.items.filter(i => !keys.has(i.key));
      short.items = one.items.map(i => i.key);
      short.owned = short.items.filter(k => byKey.has(k)).length;
    } else return needs("That change to a set");
    downloadsSets();
    keep("/api/sets", "/api/library", "/api/assets");
    return json({ ok: true });
  }

  // Downloads' own list of the sets (hoard/api/downloads.py's), from the Sets tab's: each set with what of it is
  // downloaded, so a set made, renamed or deleted shows there too.
  function downloadsSets() {
    const downloads = at("/api/assets"), view = at("/api/sets");
    if (!downloads || !view) return;
    const downloaded = new Set((downloads.assets || []).map(a => a.tag_key)), was = new Map((downloads.sets || []).map(s => [s.id, s]));
    downloads.sets = view.sets.map(s => ({ ...(was.get(s.id) || {}), id: s.id, name: s.name, note: s.note || "",
                                           ...(s.kind ? { kind: s.kind } : {}), items: s.items.map(i => i.key).filter(k => downloaded.has(k)),
                                           adult: s.items.some(i => i.adult) }));
  }

  // Settings: how Hoard looks (its theme, style, text and the rest) changes here; the rest needs Hoard.
  function settingsChange(body) {
    const settings = at("/api/settings");
    if (!settings) return needs("Settings");
    const language = body.display && "language" in body.display;
    if (Object.keys(body).some(k => k !== "display") || language)
      return needs(language ? "Hoard in Japanese or Korean" : "That setting");
    const d = settings.display = { ...settings.display, ...body.display };
    const theme = (DATA.themes || {})[d.theme];
    if (theme) d.theme_css = theme[d.mode] || theme.system;
    const lib = at("/api/library");
    if (lib) lib.display = d;
    keep("/api/settings", "/api/library");
    return json({ ok: true, settings });
  }

  // What the page asks for by itself, in the background (a set's prices, pictures' looks): answered as Hoard answers
  // when there's nothing to do, without a word, as nobody asked.
  const quiet = () => json({ ok: true, started: false });
  const CHANGES = { "/api/tags": tagsChange, "/api/marks": marksChange, "/api/sets": setsChange, "/api/settings": settingsChange,
                    "/api/unlock/touch": () => json({ unlocked: false, lock_in: 0 }), "/api/sets/prices": quiet,
                    "/api/picture-looks": quiet, "/api/tasks/pictures": quiet, "/api/tasks/background": quiet,
                    "/api/unity-picture": quiet };

  // An answer saying what needs Hoard itself, and the note that says so on the page.
  function needs(what) {
    notice(what);
    return json({ error: NEEDS }, 409);
  }

  // One of the app's requests, answered.
  function answer(method, url, body) {
    if (method !== "GET") return (CHANGES[url.pathname] || (() => needs("")))(body || {});   // (a Response, or one to come)
    const got = answers.get(keyOf(url)) || answers.get(keyOf(new URL(url.pathname, location.origin)));
    if (!got) return json({ error: NEEDS }, 404);
    if (url.pathname === "/api/library") {   // signed in to the demo's stores, as the pretend sign-in said
      libraryShown();
      const signed = {};
      for (const s of Object.keys(got.signed_in || {})) signed[s] = (DATA.signin || []).some(x => x.store === s);
      return json({ ...got, signed_in: signed });
    }
    return json(got);
  }

  // The app's requests: Hoard's own answered here (once signed in), anything else as the browser would (the page's
  // policy refuses it).
  window.fetch = async (input, init = {}) => {
    const raw = input instanceof Request ? input.url : String(input);
    const url = new URL(raw, location.href);
    if (url.origin !== location.origin || !OURS.test(url.pathname)) return realFetch(input, init);
    await signIn;
    const method = String(init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
    let body = null;
    try { body = typeof init.body === "string" && init.body ? JSON.parse(init.body) : null; } catch (e) { body = null; }
    return answer(method, url, body);
  };

  // ---- pictures and files: the app's addresses for them, as the demo has them

  window.HOARD_DEMO = {
    // A picture's address (the app asks Hoard for /thumb/, /setpic/, /files/): the store's own, or none.
    keyed(url) {
      const u = new URL(url, location.origin), pictures = DATA.pictures || {};
      if (u.pathname.startsWith("/thumb/")) {
        const key = decodeURIComponent(u.pathname.slice(7));
        const p = everyProduct().find(x => x.key === key || x.tag_key === key);
        return (p && p.thumbnail) || pictures[key] || "data:,";
      }
      if (u.pathname.startsWith("/files/")) return pictures[decodeURIComponent(u.pathname.slice(7))] || "data:,";
      if (u.pathname.startsWith("/setpic/") || u.pathname.startsWith("/setphoto/")) {
        const [sid, n] = u.pathname.split("/").slice(2);
        const s = ((at("/api/sets") || {}).sets || []).find(x => x.id === sid);
        if (u.pathname.startsWith("/setphoto/")) return (s && s.photos[+n]) || "data:,";
        const item = s && s.items[+n];
        const p = item && (DATA.products || []).find(x => x.name === item.name && x.store === item.store);
        return (item && item.picture) || (p && p.thumbnail) || (item && pictures[item.key]) || "data:,";
      }
      return "data:,";
    },
  };

  // ---- the address: the app's / and /downloads are the demo's own

  // An address the app makes (/, /downloads...), where the demo is.
  const here = url => typeof url === "string" && /^\/(downloads)?([?#]|$)/.test(url) ? BASE + url : url;
  for (const name of ["pushState", "replaceState"]) {
    const real = history[name].bind(history);
    history[name] = (s, title, url) => real(s, title, url === undefined ? url : here(String(url)));
  }
  // A link opened in a new tab (middle click, or with a key held) opens the demo's page, not the website's.
  // (for that click only: the link's own address is back straight after, for the app's tabs to go on working)
  const newTab = e => {
    const a = e.target.closest && e.target.closest("a[href^='/']");
    if (!a || !(e.button === 1 || e.ctrlKey || e.metaKey || e.shiftKey)) return;
    const was = a.getAttribute("href"), demo = here(was);
    if (demo === was) return;
    a.setAttribute("href", demo);
    setTimeout(() => { if (a.getAttribute("href") === demo) a.setAttribute("href", was); });
  };
  window.addEventListener("click", newTab, true);
  window.addEventListener("auxclick", newTab, true);

  // ---- what's drawn: the pretend sign-in, the demo's note, and what needs Hoard

  const STYLE = `
.demo-cover { position: fixed; inset: 0; z-index: 2147483000; display: grid; place-items: center; padding: 16px;
  background: color-mix(in srgb, var(--cave, #211C18) 88%, transparent); backdrop-filter: blur(6px); }
.demo-card { width: min(520px, 100%); max-height: calc(100vh - 32px); overflow: auto; padding: 28px; border-radius: 18px;
  background: var(--panel, #2B2420); color: var(--text, #F4EDE3); box-shadow: 0 20px 60px rgba(0,0,0,.45);
  font: 15px/1.5 "Zen Maru Gothic", system-ui, sans-serif; }
.demo-card h1 { margin: 0 0 6px; font: 28px "Dela Gothic One", system-ui, sans-serif; }
.demo-card p { margin: 0 0 14px; opacity: .85; }
.demo-store { border: 1px solid color-mix(in srgb, currentColor 18%, transparent); border-radius: 12px; padding: 12px 14px; margin: 10px 0; }
.demo-store b { display: block; margin-bottom: 6px; }
.demo-store label { display: grid; grid-template-columns: 90px 1fr; gap: 8px; align-items: center; margin: 4px 0; font-size: 13px; }
.demo-store input { min-width: 0; font: inherit; padding: 6px 10px; border-radius: 8px;
  border: 1px solid color-mix(in srgb, currentColor 22%, transparent); background: transparent; color: inherit; }
.demo-go { width: 100%; margin-top: 12px; padding: 12px; border: 0; border-radius: 12px; cursor: pointer;
  font: 700 16px "Zen Maru Gothic", system-ui, sans-serif; background: var(--accent, #F2A93B); color: var(--on-accent, #211C18); }
.demo-go[disabled] { opacity: .7; cursor: progress; }
.demo-note { position: fixed; left: 16px; bottom: 16px; z-index: 2147482000; display: flex; gap: 10px; align-items: center;
  max-width: calc(100vw - 32px); padding: 8px 10px 8px 14px; border-radius: 999px; background: var(--panel, #2B2420);
  color: var(--text, #F4EDE3); box-shadow: 0 6px 24px rgba(0,0,0,.35); font: 13px/1.3 "Zen Maru Gothic", system-ui, sans-serif; }
.demo-note a { padding: 6px 12px; border-radius: 999px; background: var(--accent, #F2A93B); color: var(--on-accent, #211C18);
  font-weight: 700; text-decoration: none; white-space: nowrap; }
.demo-note.said { outline: 2px solid var(--accent, #F2A93B); }
@media (max-width: 600px) { .demo-note { right: 16px; border-radius: 14px; } }`;

  // An element, with its text (never markup).
  function el(tag, props = {}, ...children) {
    const e = Object.assign(document.createElement(tag), props);
    for (const c of children) e.append(c);
    return e;
  }

  let note = null, noteText = null, noteTimer = 0;
  const SAYS = "This is the demo: nothing leaves your browser.";
  // The demo's note, at the page's corner: that it's the demo, with Download Hoard.
  function drawNote() {
    noteText = el("span", { textContent: SAYS });
    note = el("div", { className: "demo-note", role: "status" }, noteText,
              el("a", { href: DOWNLOAD, textContent: "Download Hoard", target: "_top" }));
    document.body.append(note);
  }
  // Say on the note what needs Hoard itself, for a while.
  function notice(what) {
    if (!note) return;
    noteText.textContent = (what ? what + ": " : "") + "that needs Hoard on your computer.";
    note.classList.add("said");
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => { noteText.textContent = SAYS; note.classList.remove("said"); }, 6000);
  }

  // The pretend sign-in: the demo's accounts, filled in; signing in shows the library.
  function drawSignIn() {
    const stores = (DATA.signin || []).map(s => el("div", { className: "demo-store" },
      el("b", { textContent: s.label }),
      el("label", {}, "Email", el("input", { value: `demo@${s.store}.example`, readOnly: true, type: "email" })),
      el("label", {}, "Password", el("input", { value: "demo-password", readOnly: true, type: "password" }))));
    const go = el("button", { className: "demo-go", type: "button", textContent: "Sign in" });
    const card = el("div", { className: "demo-card" },
      el("h1", { textContent: "Try Hoard" }),
      el("p", { textContent: "This is Hoard, in your browser, with a library of real products. Sign in as you would " +
                             "in Hoard: here the demo's accounts are filled in, and nothing is sent to any store." }),
      ...stores, go,
      el("p", { textContent: "Nothing you do here leaves your browser. Downloading, opening folders and Unity need " +
                             "Hoard on your computer." }));
    const cover = el("div", { className: "demo-cover", role: "dialog" }, card);
    cover.setAttribute("aria-modal", "true");
    cover.setAttribute("aria-label", "Try Hoard");
    go.addEventListener("click", () => {
      go.disabled = true;
      go.textContent = "Reading your library…";
      setTimeout(() => {
        state.signedIn = true;
        keep();
        cover.remove();
        drawNote();
        signedInNow();
      }, 700);
    });
    document.body.append(cover);
    go.focus();
  }

  // A set from the address (the website's set viewer or set maker): offered as Add a shared set does, with its code
  // in the box, once the library's shown. Nothing's added until it's said so.
  if (bringIn) shown.then(() => setTimeout(() => { if (typeof window.addSharedSet === "function") window.addSharedSet(bringIn); }, 900));

  document.addEventListener("DOMContentLoaded", () => {
    document.head.append(el("style", { textContent: STYLE }));
    if (state.signedIn) drawNote(); else drawSignIn();
  });
})();
