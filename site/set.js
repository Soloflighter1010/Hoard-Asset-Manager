// The set viewer (set.html): a set someone shared from Hoard, shown from the code after the page's "#". The code
// is the set itself (hoard/sets.py, share_code): a browser never sends what's after "#" anywhere, so the set is read
// here, in the page, and nothing about it reaches this site. Each product's picture comes from its store's own
// image host, and the sharer's photos from the photo sites they're on: only those hosts, checked here as Hoard
// checks them, and allowed by this page's Content-Security-Policy. Nothing from the code becomes page markup.
// A short link ("S1.<id>.<key>", hoard/shortlinks.py) is a set kept locked on Hoard's share server for 14 days:
// it's fetched from there by its id, and unlocked here with its key, which is never sent anywhere.
"use strict";
(function () {
  const STORES = { booth: "Booth", gumroad: "Gumroad", jinxxy: "Jinxxy", payhip: "Payhip", itch: "itch.io" };
  const STORE_IMAGE_HOSTS = { booth: ["booth.pximg.net"], gumroad: ["public-files.gumroad.com"], jinxxy: ["jinxxy-c.jinxxy-cdn.com"],
                              payhip: ["images.payhip.com"], itch: ["img.itch.zone"] };
  const PHOTO_HOSTS = ["i.imgur.com", "i.gyazo.com", "pbs.twimg.com", "cdn.bsky.app", "i.redd.it", "i.postimg.cc", "i.ibb.co",
                       "cdn.discordapp.com", "media.discordapp.net", "booth.pximg.net", "img.itch.zone",
                       "public-files.gumroad.com"];
  const PREFIX = "H1.", MAX_CODE = 256 * 1024, MAX_JSON = 1024 * 1024, MAX_ITEMS = 500, MAX_PHOTOS = 8;
  const SHARE_SERVER = "https://hoard-share.furryup.link";
  const SHORT = /^S1\.([0-9A-Za-z]{10})\.([A-Za-z0-9_-]{22})$/;

  const $ = s => document.querySelector(s);
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) e.setAttribute(k, v === true ? "" : v);
    for (const k of kids) if (k != null && k !== false) e.append(k);
    return e;
  }
  // an https address, with no user name or other port, on one of these hosts (or a subdomain, for a store's site)
  function https(value, hosts, subdomains) {
    if (typeof value !== "string" || value.length > 600) return "";
    let u;
    try { u = new URL(value); } catch (e) { return ""; }
    const host = u.hostname.replace(/\.$/, "").toLowerCase();
    if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return "";
    return hosts.some(h => host === h || (subdomains && host.endsWith("." + h))) ? u.href : "";
  }
  // A product's public page on its store, or its creator's, as hoard/sets.py's product_link checks it: never a page
  // of the buyer's own (a Gumroad purchase's download page, gumroad.com/d/..., which opens its files for whoever has
  // it; Jinxxy's inventory; an itch.io download page and its key). A set shared from Hoard 4.2.0 can carry those:
  // they're not shown.
  const NOT_A_SHOP = new Set(["www", "app", "accounts", "manage", "api", "assets", "help", "support", "checkout", "auth", "login"]);
  const JINXXY_NOT_A_CREATOR = new Set(["my", "market", "api", "auth", "cart", "checkout", "about", "login", "signup", "settings",
    "search", "help", "support", "feedback", "terms-of-service", "privacy-policy", "refund-policy", "_next", "static", "admin"]);
  const BOOTH_ITEM = /^\/(?:[a-z]{2}(?:-[a-z]+)?\/)?items\/\d{1,12}$/;
  function storePage(store, value) {
    if (typeof value !== "string" || value.length > 600) return "";
    let u;
    try { u = new URL(value); } catch (e) { return ""; }
    const host = u.hostname.replace(/\.$/, "").toLowerCase(), path = u.pathname.replace(/\/+$/, "");
    if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443") || !/^[\x00-\x7f]*$/.test(host)) return "";
    const dot = host.indexOf("."), name = host.slice(0, dot), rest = host.slice(dot + 1);
    const shop = site => rest === site && /^[a-z0-9-]{1,63}$/.test(name) && !NOT_A_SHOP.has(name);
    const on = site => host === site || host === "www." + site;
    const segs = path ? path.split("/").slice(1) : [];
    const ok = store === "booth" ? (on("booth.pm") && BOOTH_ITEM.test(path)) || (shop("booth.pm") && (!path || BOOTH_ITEM.test(path)))
      : store === "gumroad" ? ((on("gumroad.com") || shop("gumroad.com")) && /^\/l\/[A-Za-z0-9_-]{1,80}$/.test(path)) || (shop("gumroad.com") && !path)
      : store === "jinxxy" ? on("jinxxy.com") && segs.length >= 1 && segs.length <= 2 && segs.every(x => /^[A-Za-z0-9_.~-]{1,120}$/.test(x))
          && !JINXXY_NOT_A_CREATOR.has(segs[0].toLowerCase()) && (segs.length === 1 || !["products", "lists", "posts"].includes(segs[1].toLowerCase()))
      : store === "payhip" ? on("payhip.com") && /^\/b\/[A-Za-z0-9]{1,20}$/.test(path)
      : store === "itch" ? shop("itch.io") && (!path || /^\/[A-Za-z0-9_-]{1,120}$/.test(path)) : false;
    return ok ? `https://${host}${path}` : "";
  }
  const text = (v, n) => typeof v === "string" ? v.normalize("NFC").replace(/[\p{Cc}\p{Cf}]/gu, " ").replace(/\s+/g, " ").trim().slice(0, n) : "";
  const note = v => typeof v === "string" ? v.split(/\r?\n/).slice(0, 20).map(l => text(l, 1000)).join("\n").trim().slice(0, 1000) : "";

  async function unpack(code) {
    code = code.replace(/\s+/g, "");
    if (!code.startsWith(PREFIX) || code.length > MAX_CODE) throw new Error("not a code");
    const b64 = code.slice(PREFIX.length).replace(/-/g, "+").replace(/_/g, "/");
    const bytes = Uint8Array.from(atob(b64 + "===".slice((b64.length + 3) % 4)), c => c.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
    const reader = stream.getReader(), parts = [];
    let size = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.length;
      if (size > MAX_JSON) { reader.cancel(); throw new Error("too large"); }
      parts.push(value);
    }
    return JSON.parse(new TextDecoder().decode(await new Blob(parts).arrayBuffer()));
  }
  function check(doc) {   // as hoard/sets.py's from_code checks it
    if (!doc || doc.v !== 1 || !Array.isArray(doc.i)) throw new Error("not a set");
    const items = [];
    for (const row of doc.i.slice(0, MAX_ITEMS)) {
      if (!Array.isArray(row)) continue;
      const store = typeof row[0] === "string" ? row[0].toLowerCase() : "";
      const name = text(row[2], 300);
      if (!STORES[store] || !name) continue;
      items.push({ store, name, creator: text(row[3], 200), url: storePage(store, row[4]),
                   picture: https(row[5], STORE_IMAGE_HOSTS[store], false) });
    }
    if (!items.length) throw new Error("empty");
    const photos = (Array.isArray(doc.p) ? doc.p.slice(0, MAX_PHOTOS) : []).map(u => https(u, PHOTO_HOSTS, false)).filter(Boolean);
    return { name: text(doc.n, 60) || "A shared set", note: note(doc.d), photos: [...new Set(photos)], items };
  }

  // A short link's set, unlocked as Hoard's page locks it (hoard/web/shared.js: lockSet)
  const LOCKED_AS = new TextEncoder().encode("Hoard set S1");
  const unb64u = t => Uint8Array.from(atob(t.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((t.length + 3) % 4)), c => c.charCodeAt(0));
  async function unlockSet(data, key) {
    const bytes = unb64u(data), k = await crypto.subtle.importKey("raw", unb64u(key), "AES-GCM", false, ["decrypt"]);
    return new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.subarray(0, 12), additionalData: LOCKED_AS }, k, bytes.subarray(12)));
  }
  // The code behind a short link, and when the link runs out: {code, expires}, or {why} it can't be had
  async function fromServer(id, key) {
    let r, got = null;
    try {
      r = await fetch(`${SHARE_SERVER}/v1/sets/${id}`, { credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" });
    } catch (e) {
      return { why: "Couldn't reach Hoard's share server, where this short link's set is kept. Check your connection, and try again." };
    }
    if (r.status === 404) return { why: "This short link has run out (short links last 14 days), or whoever shared it deleted it. Ask them for the set again." };
    try { if (r.ok) got = await r.json(); } catch (e) { /* (not the server's answer: an error page on the way) */ }
    if (!got || typeof got.data !== "string" || !Number.isInteger(got.expires)) return { why: "Hoard's share server is busy. Try again in a while." };
    try { return { code: await unlockSet(got.data, key), expires: got.expires }; }
    catch (e) { return { why: "This link's key doesn't open its set: part of the link is missing or changed. Ask for it again, and copy all of it." }; }
  }

  function picture(src, alt, cls) {
    const img = el("img", { src, alt, loading: "lazy", decoding: "async", referrerpolicy: "no-referrer", class: cls });
    img.addEventListener("error", () => img.replaceWith(el("span", { class: cls + " none", "aria-hidden": "true" })), { once: true });
    return img;
  }
  function show(set, code, expires) {
    document.title = set.name + " · a set shared from Hoard";
    $("#setName").textContent = set.name;
    const stores = [...new Set(set.items.map(i => STORES[i.store]))];
    $("#setSummary").textContent = (set.items.length === 1 ? "1 product" : set.items.length + " products") + ", from " +
      (stores.length < 3 ? stores.join(" and ") : stores.slice(0, -1).join(", ") + " and " + stores[stores.length - 1]) + ".";
    if (set.note) for (const line of set.note.split("\n")) $("#setNote").append(el("p", {}, line || " "));
    $("#setNote").hidden = !set.note;
    if (set.photos.length) {
      const list = $("#setPhotos ul");
      set.photos.forEach((u, n) => list.append(el("li", {}, el("a", { href: u, target: "_blank", rel: "noopener noreferrer" },
        picture(u, `The sharer's photo ${n + 1} of ${set.photos.length}`, "photo")))));
      $("#setPhotos").hidden = false;
    }
    const grid = $("#setItems");
    for (const i of set.items) {
      const store = STORES[i.store];
      grid.append(el("li", { class: "sv-item" },
        i.picture ? picture(i.picture, "", "pic") : el("span", { class: "pic none", "aria-hidden": "true" }),
        el("span", { class: "sv-text" }, el("b", {}, i.name),
          el("span", { class: "sv-by" }, (i.creator ? "by " + i.creator + " · " : ""), el("span", { class: `dot ${i.store}`, "aria-hidden": "true" }), store)),
        i.url ? el("a", { class: "button ghost", href: i.url, target: "_blank", rel: "noopener noreferrer" }, "On " + store)
              : el("span", { class: "sv-none" }, "No store link")));
    }
    $("#setCode").value = location.href;
    if (expires) {   // (a short link: the code to copy is the set's own, which every Hoard reads)
      const until = new Date(expires * 1000).toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
      $("#setWhere").textContent = `This short link works until ${until}. Its set is kept on Hoard's share server until then, ` +
        "locked: the key that opens it is in this page's link, after the “#”, which your browser never sends anywhere, so " +
        "neither the server nor this site can read the set.";
    }
    $("#setView").hidden = false;
    $("#setCopy").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.href); $("#setCopied").textContent = "Copied."; }
      catch (e) { $("#setCode").select(); $("#setCopied").textContent = "Copy it from the box."; }
    });
    $("#setCopyCode").addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(code); $("#setCopied").textContent = "Copied the code."; }
      catch (e) { $("#setCode").value = code; $("#setCode").select(); $("#setCopied").textContent = "Copy it from the box."; }
    });
  }
  function problem(why) {
    $("#setProblem").hidden = false;
    $("#setProblemWhy").textContent = why;
  }
  async function start() {
    let code = decodeURIComponent(location.hash.slice(1)).replace(/\s+/g, ""), expires = 0;
    if (!code) { problem("This page shows a set someone shared from Hoard. Open the link they sent you: the set is in it."); return; }
    if (typeof DecompressionStream !== "function" || !(window.crypto && crypto.subtle)) {
      problem("This browser is too old to read the set. Open the link in a current Chrome, Edge, Firefox or Safari."); return;
    }
    const short = code.match(SHORT);
    if (short) {
      const got = await fromServer(short[1], short[2]);
      if (got.why) { problem(got.why); return; }
      ({ code, expires } = got);
    }
    let set;
    try { set = check(await unpack(code)); }
    catch (e) { problem("This link's set is damaged, or the link was cut short. Ask for it again, and copy all of it."); return; }
    show(set, code, expires);
  }
  window.addEventListener("hashchange", () => location.reload());
  start();
})();
