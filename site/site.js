// Hoard's website. Everything works without this; it only helps:
// - the main button names your system and goes to its download,
// - each download button gets its file's own address from the latest release (else it opens the releases page),
// - Copy copies the VCC listing's address.
(() => {
  "use strict";
  const REPO = "Soloflighter1010/Hoard-Asset-Manager";

  const ua = navigator.userAgent || "", platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
  const os = /Win/i.test(platform) || /Windows/i.test(ua) ? "windows"
    : /Mac/i.test(platform) || /Mac OS X/i.test(ua) ? (/iPhone|iPad/i.test(ua) ? null : "mac")
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
  fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } })
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
      setTimeout(() => { copy.textContent = "Copy"; }, 1800);
    });
    field.addEventListener("focus", () => field.select());
  }
})();
