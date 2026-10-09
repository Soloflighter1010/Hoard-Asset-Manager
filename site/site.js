// Hoard's website. Everything works without this; it only helps:
// - the main button names your system and goes to its download,
// - each download button gets its file's own address from the latest release (else it opens the releases page),
// - Copy copies the VCC listing's address,
// - the store tabs on the front page tint the glow and say what Hoard does on each store, as the app's tabs do,
// - the docs' search box finds any section of the docs (docs/search.json),
// - and there are a few things to find, as in the app.
(() => {
  "use strict";
  document.documentElement.classList.add("js");
  const REPO = "Soloflighter1010/Hoard-Asset-Manager";

  const ua = navigator.userAgent || "", platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  // an iPad says it's a Mac (since iPadOS 13): a Mac has no touch screen
  const ios = /iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(platform + ua) && navigator.maxTouchPoints > 1);
  const os = /Win/i.test(platform) || /Windows/i.test(ua) ? "windows"
    : /Mac/i.test(platform) || /Mac OS X/i.test(ua) ? (ios ? null : "mac")
    : /Linux/i.test(platform) && !/Android/i.test(ua) ? "linux" : null;
  const names = { windows: "Windows", mac: "macOS", linux: "Linux" };

  const card = os && document.querySelector(`[data-os="${os}"]`);
  const getIt = document.getElementById("getIt");
  if (card && getIt) {
    card.classList.add("here");
    getIt.textContent = `Download for ${names[os]}`;
    getIt.href = card.querySelector("a.button.primary").href;
    document.getElementById("getItNote").textContent = "Also for " +
      Object.keys(names).filter(k => k !== os).map(k => names[k]).join(" and ") + ".";
  }

  // The latest release's files, by name. Asked of GitHub's public API; nothing about you is sent with it.
  if (document.querySelector("a[data-file]")) fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } })
    .then(r => (r.ok ? r.json() : Promise.reject(r.status)))
    .then(release => {
      const assets = Array.isArray(release.assets) ? release.assets : [];
      for (const a of document.querySelectorAll("a[data-file]")) {
        const want = a.dataset.file;
        const hit = assets.find(x => typeof x.name === "string" && x.name.includes(want) &&
                                     (want.endsWith(".pkg") || want.endsWith(".flatpak") || x.name.endsWith(".exe")));
        if (hit && /^https:\/\/github\.com\//.test(hit.browser_download_url)) a.href = hit.browser_download_url;
      }
      if (card && getIt) getIt.href = card.querySelector("a.button.primary").href;
      const tag = String(release.tag_name || "").replace(/[^\w.-]/g, "");
      if (tag) {
        const latest = document.getElementById("latest");
        latest.textContent = `Hoard ${tag.replace(/^v/, "")}, from the `;
        const link = document.createElement("a");
        link.href = `https://github.com/${REPO}/releases/tag/${encodeURIComponent(tag)}`;
        link.textContent = "release on GitHub";
        latest.append(link, ".");
      }
    })
    .catch(() => { /* the buttons open the releases page instead */ });

  const copy = document.getElementById("copyListing"), field = document.getElementById("listingUrl");
  if (copy && field) {
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(field.value); }
      catch (e) { field.select(); document.execCommand && document.execCommand("copy"); }
      copy.textContent = "Copied";
      toast("Copied. Paste it in VCC › Settings › Packages › Add Repository.");
      setTimeout(() => { copy.textContent = "Copy"; }, 1800);
    });
    field.addEventListener("focus", () => field.select());
  }

  // A moment's note at the foot of the window, as the app shows them
  let toastTimer;
  function toast(text) {
    let t = document.querySelector(".toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "toast"; t.setAttribute("role", "status");
      document.body.append(t);
    }
    t.textContent = text;
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 3200);
  }

  // The store tabs: choosing one raises it, tints the glow with that store's colour, and says what Hoard does there.
  // Everything shows every store's colour, drifting, as the app's library does.
  const STORES = ["booth", "gumroad", "jinxxy", "payhip", "itch"];
  const glow = document.querySelector(".glow-in"), tabs = document.querySelectorAll(".seg [data-store]");
  function showStore(store) {
    for (const b of tabs) b.setAttribute("aria-checked", String(b.dataset.store === store));
    for (const p of document.querySelectorAll(".store-notes [data-for]")) p.classList.toggle("here", p.dataset.for === store);
    if (glow) {
      // (the glow is twice the window's width, drifting: its colour at each quarter, so it's there wherever it stops)
      const at = x => `radial-gradient(ellipse 70% 95% at ${x}% 115%, color-mix(in srgb, var(--${store}) var(--glow), transparent) 0%, transparent 75%)`;
      glow.style.backgroundImage = store ? [12.5, 37.5, 62.5, 87.5].map(at).join(", ") : "";
      glow.style.animationPlayState = store ? "paused" : "";
    }
  }
  if (tabs.length) {
    showStore("");
    for (const b of tabs) {
      b.addEventListener("click", () => showStore(b.dataset.store));
      b.addEventListener("keydown", e => {   // arrow keys move along the tabs, as in a radio group
        const i = [...tabs].indexOf(b), step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (!step) return;
        e.preventDefault();
        const next = tabs[(i + step + tabs.length) % tabs.length];
        next.focus(); showStore(next.dataset.store);
      });
    }
  }

  // The docs' search: every section of every page (search.json, built with the docs), by its heading and words.
  // Results are made as elements, never as markup.
  const search = document.getElementById("docSearch"), results = document.getElementById("docResults");
  if (search && results) {
    let sections = null;
    const load = () => sections || fetch("search.json").then(r => r.json()).then(j => (sections = Array.isArray(j) ? j : []))
      .catch(() => (sections = []));
    const norm = s => String(s).toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
    async function find() {
      const words = norm(search.value).split(/\s+/).filter(Boolean);
      results.replaceChildren();
      if (!words.length) { results.hidden = true; return; }
      const all = await load();
      const hits = all.map(s => {
        const head = norm(s.heading), text = norm(s.text);
        if (!words.every(w => head.includes(w) || text.includes(w))) return null;
        return { s, score: words.filter(w => head.includes(w)).length * 3 + (s.anchor ? 0 : 1) };
      }).filter(Boolean).sort((a, b) => b.score - a.score).slice(0, 12);
      for (const { s } of hits) {
        const li = document.createElement("li"), a = document.createElement("a"), small = document.createElement("small");
        a.href = s.page + (s.anchor ? "#" + s.anchor : "");
        a.textContent = s.heading;
        small.textContent = s.anchor ? s.title : "";
        a.append(small);
        li.append(a);
        results.append(li);
      }
      if (!hits.length) {
        const li = document.createElement("li");
        li.className = "none"; li.textContent = "Nothing in the docs matches that.";
        results.append(li);
      }
      results.hidden = false;
    }
    let timer;
    search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(find, 120); });
    search.addEventListener("focus", load, { once: true });
    search.addEventListener("keydown", e => {
      if (e.key === "Enter") { const first = results.querySelector("a"); if (first) location.href = first.href; }
      if (e.key === "Escape") { search.value = ""; find(); }
    });
    document.addEventListener("keydown", e => {   // "/" goes to the search box, as in the app
      if (e.key === "/" && !e.target.closest("input, textarea")) { e.preventDefault(); search.focus(); }
    });
  }

  // ---------- a few things to find, as in the app. Each stays still when motion is reduced.
  const motionOk = () => !matchMedia("(prefers-reduced-motion: reduce)").matches;
  function confetti(n = 90) {   // every store's colour, falling
    if (!motionOk()) return;
    const box = document.createElement("div");
    box.className = "confetti"; box.setAttribute("aria-hidden", "true");
    for (let i = 0; i < n; i++) {
      const p = document.createElement("i");
      p.style.left = `${Math.random() * 100}vw`;
      p.style.background = `var(--${STORES[i % STORES.length]})`;
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
    if (e.target.closest && e.target.closest("input, textarea, select, [role=radio]")) { konami = 0; return; }
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    konami = k === KONAMI[konami] ? konami + 1 : k === KONAMI[0] ? 1 : 0;
    if (konami === KONAMI.length) { konami = 0; confetti(); toast("Every store at once. A fine hoard."); }
  });
  // the logo, poked five times on the front page
  let pokes = [];
  const brand = document.querySelector(".brand");
  if (brand) {
    brand.addEventListener("click", e => {
      const home = /\/(index\.html)?$/.test(location.pathname) && !location.hash;
      if (!home || e.ctrlKey || e.metaKey || e.shiftKey) return;
      e.preventDefault();
      const now = Date.now();
      pokes = [...pokes.filter(t => now - t < 2500), now];
      if (pokes.length < 5) return;
      pokes = [];
      brand.classList.remove("tumble"); void brand.offsetWidth; brand.classList.add("tumble");
      toast("Careful: everything in here is somebody's treasure.");
    });
  }
})();
