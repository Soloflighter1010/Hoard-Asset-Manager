// The set viewer (set.html): a set someone shared from Hoard, shown from the code after the page's "#". The code
// is the set itself (hoard/sets.py, share_code): a browser never sends what's after "#" anywhere, so the set is read
// here, in the page, and nothing about it reaches this site. Each product's picture comes from its store's own
// image host, and the sharer's photos from the photo sites they're on: only those hosts, checked here as Hoard
// checks them, and allowed by this page's Content-Security-Policy. Nothing from the code becomes page markup.
"use strict";
(function () {
  const STORES = { booth: "Booth", gumroad: "Gumroad", jinxxy: "Jinxxy", payhip: "Payhip", itch: "itch.io" };
  const STORE_SITES = { booth: ["booth.pm"], gumroad: ["gumroad.com"], jinxxy: ["jinxxy.com"], payhip: ["payhip.com"],
                        itch: ["itch.io"] };
  const STORE_IMAGE_HOSTS = { booth: ["booth.pximg.net"], gumroad: ["public-files.gumroad.com"], jinxxy: ["cdn.jinxxy.com"],
                              payhip: ["images.payhip.com"], itch: ["img.itch.zone"] };
  const PHOTO_HOSTS = ["i.imgur.com", "i.gyazo.com", "pbs.twimg.com", "cdn.bsky.app", "i.redd.it", "i.postimg.cc", "i.ibb.co",
                       "cdn.discordapp.com", "media.discordapp.net", "booth.pximg.net", "img.itch.zone",
                       "public-files.gumroad.com"];
  const PREFIX = "H1.", MAX_CODE = 256 * 1024, MAX_JSON = 1024 * 1024, MAX_ITEMS = 500, MAX_PHOTOS = 8;

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
      items.push({ store, name, creator: text(row[3], 200), url: https(row[4], STORE_SITES[store], true),
                   picture: https(row[5], STORE_IMAGE_HOSTS[store], false) });
    }
    if (!items.length) throw new Error("empty");
    const photos = (Array.isArray(doc.p) ? doc.p.slice(0, MAX_PHOTOS) : []).map(u => https(u, PHOTO_HOSTS, false)).filter(Boolean);
    return { name: text(doc.n, 60) || "A shared set", note: note(doc.d), photos: [...new Set(photos)], items };
  }

  function picture(src, alt, cls) {
    const img = el("img", { src, alt, loading: "lazy", decoding: "async", referrerpolicy: "no-referrer", class: cls });
    img.addEventListener("error", () => img.replaceWith(el("span", { class: cls + " none", "aria-hidden": "true" })), { once: true });
    return img;
  }
  function show(set, code) {
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
    const code = decodeURIComponent(location.hash.slice(1));
    if (!code) { problem("This page shows a set someone shared from Hoard. Open the link they sent you: the set is in it."); return; }
    if (typeof DecompressionStream !== "function") { problem("This browser is too old to read the set. Open the link in a current Chrome, Edge, Firefox or Safari."); return; }
    let set;
    try { set = check(await unpack(code)); }
    catch (e) { problem("This link's set is damaged, or the link was cut short. Ask for it again, and copy all of it."); return; }
    show(set, code);
  }
  window.addEventListener("hashchange", () => location.reload());
  start();
})();
