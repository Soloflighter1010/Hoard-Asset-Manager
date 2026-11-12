<script module>
  let made = 0;   // (each dialog's ids, for its title and text)
</script>

<script>
  // Hoard's pop-ups: a card like a product's details panel, with an icon, a title in the display font, a line saying
  // what it's about, a close button, what it asks, and its buttons under a hairline. ui/dialogs.js opens one for
  // shared.js's ask (a question), askName (a name or a tag), askFolder (a folder) and the set picker (a choice).
  // Everything shown is text: no user text is ever taken as markup.
  import { onMount, untrack } from "svelte";
  import Icon from "./Icon.svelte";

  let {
    kind,                 // "confirm", "text", "folder" or "pick"
    id = undefined,       // the dialog's id (askDialog for a question, as the pages and their tests know it)
    textId = undefined,   // the id of what it says (askText for a question)
    title, detail = "", paras = [],   // its title, the line under it, and any more paragraphs
    icon = "help", tone = "gold",     // its icon, in gold or (for something that can't be undone) the warning colour
    ok = "OK", cancel = "Cancel", danger = false,
    inputId = undefined, value = "", max = 60, placeholder = "",   // a name's or a folder's box
    suggest = null, create = true, prefix = "",   // a tag's: your tags to choose from, and whether a new one can be made
    browse = null,        // a folder's Browse...: given the box, fills it in (shared.js's browseInto)
    groups = [], find = "", norm = s => s.toLowerCase(),   // a choice's rows, by group, and its box to find one
    inline = false,       // shown in the page as an example (the style guide), not over it
    tr, done,
  } = $props();

  const uid = `hd${++made}`;
  let dlg, input = $state(null), findBox = $state(null);
  let query = $state(""), typed = $state(untrack(() => value)), broken = $state(new Set());

  onMount(() => {
    if (inline) return;
    dlg.returnValue = "no";
    dlg.showModal();
    if (input) { input.focus(); input.select(); }
    else if (findBox) findBox.focus();
    else (dlg.querySelector(danger ? "footer [value=no]" : "footer [value=yes]") || dlg.querySelector("footer button"))?.focus();   // (Enter never deletes by accident)
  });

  // End it with this answer ("yes", "no", or the value of a row chosen).
  function close(answer) { if (dlg.open && !inline) dlg.close(answer); }
  // What it resolves with: yes or no for a question, the box's text (or "") for a name or folder, the row's value
  // (or "") for a choice.
  function ended() {
    const v = dlg.returnValue;
    done(kind === "confirm" ? v === "yes" : kind === "pick" ? (v === "no" ? "" : v) : v === "yes" ? input.value.trim() : "");
  }
  // Enter in the box is OK, but not while an input method is still putting a word together (Japanese, Korean).
  function enter(e) {
    if (e.key !== "Enter" || e.isComposing) return;
    e.preventDefault();
    if (kind === "pick") { const first = dlg.querySelector(".hd-row"); if (first) close(first.value); }
    else close("yes");
  }
  // A tag chosen from your tags: the box takes it, and it's added.
  function choose(name) { input.value = name; close("yes"); }

  const lines = p => String(p).split("\n");
  const words = $derived(norm(query).split(/\s+/).filter(Boolean));
  const shown = $derived(groups.map(g => ({ ...g, items: g.items.filter(i => words.every(w => norm(i.name).includes(w))) }))
                                .filter(g => g.items.length));
  const typedTag = $derived(typed.trim().replace(/^#/, ""));
  const tags = $derived(suggest ? suggest.filter(t => !typedTag || norm(t.name).includes(norm(typedTag))).slice(0, 12) : []);
  const isNew = $derived(create && typedTag && !(suggest || []).some(t => norm(t.name) === norm(typedTag)));
</script>

<dialog bind:this={dlg} {id} class="hd hd-{kind}" class:danger class:inline open={inline || undefined} aria-labelledby="{uid}-t"
        aria-describedby={detail || paras.length ? `${uid}-d` : undefined}
        onclose={ended} oncancel={() => { dlg.returnValue = "no"; }}
        onclick={e => { if (e.target === dlg && (kind === "confirm" || kind === "pick")) close("no"); }}>
  <div class="hd-card">
    <header>
      <span class="hd-ic {tone}"><Icon name={icon} size={20} /></span>
      <div class="hd-text" id={textId}>
        <h2 id="{uid}-t" class:long={title.length > 64}>{title}</h2>
        {#if detail || paras.length}
          <div id="{uid}-d">
            {#if detail}<p class="hd-detail">{#each lines(detail) as line, i}{#if i}<br>{/if}{line}{/each}</p>{/if}
            {#each paras as p}<p>{#each lines(p) as line, i}{#if i}<br>{/if}{line}{/each}</p>{/each}
          </div>
        {/if}
      </div>
      <button type="button" class="hd-x" aria-label={tr("Close")} onclick={() => close("no")}><Icon name="x" size={18} /></button>
    </header>

    {#if kind === "text" || kind === "folder"}
      <div class="hd-body">
        <div class="hd-field">
          <span class="hd-fi"><Icon name={kind === "folder" ? "folder" : icon} size={17} /></span>
          <input bind:this={input} id={inputId} maxlength={max} {placeholder} {value} spellcheck={kind === "folder" ? "false" : undefined}
                 aria-labelledby="{uid}-t" oninput={e => { typed = e.currentTarget.value; }} onkeydown={enter}>
          {#if kind === "folder" && browse}
            <button type="button" class="ghost" data-browse onclick={() => browse(input)}>{tr("Browse…")}</button>
          {/if}
        </div>
        {#if suggest}
          {#if tags.length || isNew}
            <p class="hd-lab">{tr("Your tags")}</p>
            <div class="hd-chips">
              {#each tags as t (t.name)}
                <button type="button" class="hd-chip" onclick={() => choose(t.name)}>{prefix}{t.name}{#if t.count}<i>{t.count}</i>{/if}</button>
              {/each}
              {#if isNew}
                <button type="button" class="hd-chip new" onclick={() => choose(typedTag)}><Icon name="plus" size={14} />{tr("New tag {0}", prefix + typedTag)}</button>
              {/if}
            </div>
          {/if}
        {/if}
      </div>
    {:else if kind === "pick"}
      <div class="hd-body">
        <div class="hd-field">
          <span class="hd-fi"><Icon name="search" size={17} /></span>
          <input bind:this={findBox} type="search" placeholder={find} aria-label={find} bind:value={query} onkeydown={enter}>
        </div>
        <div class="hd-groups">
          {#each shown as g (g.title)}
            <h4>{g.title}</h4>
            <div class="hd-rows">
              {#each g.items as item (item.value)}
                <button type="button" class="hd-row" value={item.value} onclick={() => close(item.value)}>
                  <span class="hd-th" style:--h={item.hue}>
                    {#if item.pic && !broken.has(item.value)}
                      <img src={item.pic} alt="" loading="lazy" decoding="async" onerror={() => { broken = new Set([...broken, item.value]); }}>
                    {:else}<b translate="no">{item.letters}</b>{/if}
                  </span>
                  <span class="hd-name" translate="no">{item.name}</span>
                  {#if item.sub}<span class="hd-sub">{item.sub}</span>{/if}
                </button>
              {/each}
            </div>
          {:else}
            <p class="hd-none">{tr("Nothing has that name.")}</p>
          {/each}
        </div>
      </div>
    {/if}

    <footer>
      {#if cancel}<button type="button" class="ghost" value="no" onclick={() => close("no")}>{cancel}</button>{/if}
      {#if kind !== "pick"}
        <button type="button" class="primary" class:danger value="yes" onclick={() => close("yes")}>{ok}</button>
      {/if}
    </footer>
  </div>
</dialog>

<style>
  /* One look for every pop-up, from the page's own colours (the theme's): the details panel's ground and seam, its
     display font for the title. A style's corners (Treasure's rounder, Workbench's squarer) come from --dlg-radius
     and --dlg-field-radius, set in web/looks.css. */
  dialog.hd { width: min(480px, calc(var(--vw, 100vw) - 32px)); max-height: calc(var(--vh, 100vh) - 32px); padding: 0;
    border: 0; border-radius: var(--dlg-radius, 18px); overflow: auto; color: var(--bone); background: var(--ledge);
    box-shadow: 0 0 0 1px var(--seam), 0 30px 80px rgb(0 0 0 / .55); font-family: var(--body); }
  dialog.hd-pick { width: min(540px, calc(var(--vw, 100vw) - 32px)); }
  dialog.hd::backdrop { background: rgb(10 8 6 / .62); }
  dialog.hd.inline { position: relative; inset: auto; margin: 0; max-width: 100%; }
  .hd-card { display: flex; flex-direction: column; min-height: 0; }
  header { display: flex; align-items: flex-start; gap: 14px; padding: 22px 20px 4px 24px; }
  .hd-ic { flex: none; width: 40px; height: 40px; border-radius: 12px; display: grid; place-items: center;
    background: color-mix(in srgb, var(--gold) 16%, transparent); color: var(--gold-text, var(--gold)); }
  .hd-ic.warn { background: color-mix(in srgb, var(--warn) 16%, transparent); color: var(--warn); }
  .hd-text { flex: 1; min-width: 0; }
  h2 { margin: 3px 0 0; font: 400 21px/1.25 var(--display); overflow-wrap: anywhere; }
  h2.long { font-size: 17px; line-height: 1.35; }
  .hd-text p { margin: 6px 0 0; color: var(--dust); font-size: 14px; line-height: 1.55; overflow-wrap: anywhere; }
  .hd-text p.hd-detail { color: var(--bone); opacity: .82; }
  .hd-x { flex: none; width: 36px; height: 36px; margin: -4px 0 0 auto; padding: 0; border: 0; border-radius: 10px;
    display: grid; place-items: center; background: var(--stone); color: var(--bone); cursor: pointer; }
  .hd-x:hover { filter: brightness(1.15); }
  .hd-x:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  .hd-body { padding: 14px 24px 2px; min-height: 0; }
  .hd-field { position: relative; display: flex; gap: 8px; align-items: center; }
  .hd-fi { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--dust); display: grid; pointer-events: none; }
  .hd-field input { flex: 1; min-width: 0; box-sizing: border-box; height: 44px; margin: 0; padding: 0 14px 0 42px; border: 0;
    border-radius: var(--dlg-field-radius, 12px); background: var(--cave); color: var(--bone); font: inherit; font-size: 15px;
    box-shadow: inset 0 0 0 1px var(--seam); }
  .hd-field input:focus { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  .hd-field input::placeholder { color: var(--dust); }
  .hd-field button { flex: none; height: 44px; }
  .hd-lab, h4 { margin: 16px 0 8px; font: 700 12px var(--body); color: var(--dust); }
  .hd-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .hd-chip { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border: 0; border-radius: 999px;
    background: var(--stone); color: var(--bone); font: inherit; font-size: 14px; cursor: pointer; }
  .hd-chip i { font-style: normal; color: var(--dust); font-size: 12px; }
  .hd-chip:hover { filter: brightness(1.12); }
  .hd-chip:focus-visible, .hd-row:focus-visible { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  .hd-chip.new { background: none; box-shadow: inset 0 0 0 1.5px var(--gold); color: var(--gold-text, var(--gold)); }
  .hd-groups { max-height: min(48vh, 440px); overflow: auto; margin: 0 -6px; padding: 0 6px 4px; }
  .hd-rows { display: grid; gap: 6px; }
  .hd-row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 8px 12px 8px 8px; border: 0; border-radius: 12px;
    background: var(--cave); color: var(--bone); box-shadow: inset 0 0 0 1px var(--seam); font: inherit; text-align: left; cursor: pointer; }
  .hd-row:hover { box-shadow: inset 0 0 0 1.5px var(--gold); }
  .hd-th { flex: none; width: 38px; height: 38px; border-radius: 9px; overflow: hidden; display: grid; place-items: center;
    background: hsl(var(--h, 30) var(--ph-s, 28%) var(--ph-l, 30%)); }
  .hd-th img { width: 100%; height: 100%; object-fit: cover; }
  .hd-th b { font: 400 14px/1 var(--display); opacity: .85; }
  .hd-name { font-weight: 700; overflow-wrap: anywhere; }
  .hd-sub { margin-left: auto; padding-left: 12px; color: var(--dust); font-size: 13px; text-align: right; }
  .hd-none { margin: 14px 0 4px; color: var(--dust); font-size: 14px; }
  footer { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 20px; padding: 14px 20px 18px;
    border-top: 1px solid var(--seam); }
  footer .primary.danger { background: var(--warn); color: var(--gold-ink); }
  @media (max-width: 460px) {
    header { padding: 18px 14px 4px 16px; gap: 12px; }
    .hd-body { padding: 12px 16px 2px; }
    footer { padding: 12px 14px 14px; }
    .hd-sub { display: none; }
  }
</style>
