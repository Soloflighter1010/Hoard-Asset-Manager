<script module>
  let made = 0;   // (each dialog's ids, for its title and text)
</script>

<script>
  // Hoard's pop-ups: a card like a product's details panel, with an icon, a title in the display font, a line saying
  // what it's about, a close button, what it asks, and its buttons under a hairline. ui/dialogs.js opens one for
  // shared.js's ask (a question), askName (a name or a tag), askFolder (a folder), a choice from a list (the set and
  // project pickers), a form (Projects', Git's, backups' and the rest: blocks of text, lists, boxes and ticks, in
  // steps when it has them), and a window whose inside is still drawn by the page (Mix and match, Share, marks on a
  // photo). Everything shown is text: no user text is ever taken as markup.
  import { onMount, tick, untrack } from "svelte";
  import Icon from "./Icon.svelte";

  let {
    kind,                 // "confirm", "text", "folder", "pick", "form" or "host"
    id = undefined,       // the dialog's id (askDialog for a question, as the pages and their tests know it)
    cls = "",             // more classes for it (pj-dlg, share...), as the pages' styles and tests know it
    width = "",           // "" (a question's), "mid" (a link and its buttons), "wide" (a form with lists) or "huge" (a photo)
    textId = undefined,   // the id of what it says (askText for a question)
    title, detail = "", paras = [],   // its title, the line under it, and any more paragraphs
    nameTitle = false,    // its title is a name (a product's, a package's): never translated by the browser
    keep = [],            // names in what it says (a project's, a path, a package's id), kept from the browser's translation
    icon = "help", tone = "gold",     // its icon, in gold or (for something that can't be undone) the warning colour
    ok = "OK", okId = undefined, cancel = "Cancel", danger = false,
    buttons = [],         // more beside them: {label, value} closes with value; {label, act} does act and stays open; attrs: its own
    inputId = undefined, value = "", max = 60, placeholder = "",   // a name's or a folder's box
    suggest = null, create = true, prefix = "",   // a tag's: your tags to choose from, and whether a new one can be made
    browse = null,        // Browse...: given a box, fills it in (shared.js's browseInto)
    groups = [], find = "", norm = s => s.toLowerCase(),   // a choice's rows, by group, and its box to find one
    steps = null, blocks = null,   // a form's blocks (dialogs.js says what each kind is), in steps or not
    content = null,       // a window's inside, drawn by the page (its own DOM node, moved in whole)
    control = null,       // given {close(answer)}, for the page to end it from inside
    inline = false,       // shown in the page as an example (the style guide), not over it
    tr, done,
  } = $props();

  const uid = `hd${++made}`;
  const pages = untrack(() => steps || (blocks ? [{ blocks }] : []));
  let dlg, input = $state(null), findBox = $state(null);
  let query = $state(""), typed = $state(untrack(() => value)), broken = $state(new Set()), step = $state(0);
  // A form's answers so far, by the id of each box, tick, list of ticks (which are ticked) and list of choices
  let vals = $state(untrack(() => Object.fromEntries(pages.flatMap(p => p.blocks).flatMap(b =>
    b.type === "field" ? [[b.id, b.value || ""]] : b.type === "check" ? [[b.id, !!b.checked]]
      : b.type === "checks" ? [[b.id, b.items.map(i => !!i.checked)]] : b.type === "radios" ? [[b.id, b.value || ""]] : []))));
  let finds = $state({});   // what's typed in a list of choices' find box, by its id

  onMount(() => {
    if (control) control.close = close;
    if (inline) return;
    dlg.returnValue = "no";
    dlg.showModal();
    tick().then(first);   // (once a window's inside, which an action puts in, is there)
  });
  // Where the keyboard starts: the box to type in, else the list's find box, else its first row, else Cancel when it
  // can't be undone, else the main button (Enter never deletes by accident). The choice already made in a list (the
  // version installed now) is scrolled into view, with its find box or without.
  function first() {
    const here = dlg.querySelector(`[data-step="${step + 1}"]`) || dlg;
    const box = input || findBox || here.querySelector(".hd-body input:not([type=checkbox]):not([type=radio]):not([readonly]), .hd-body textarea");
    const picked = here.querySelector(".hd-body input[type=radio]:checked");
    if (box) { box.focus(); if (box.select && box === input) box.select(); picked?.scrollIntoView?.({ block: "nearest" }); return; }
    if (picked) { picked.focus(); picked.scrollIntoView?.({ block: "nearest" }); return; }
    const row = kind === "pick" && here.querySelector(".hd-row");
    if (row) { row.focus(); return; }
    if (kind === "host") { const own = here.querySelector(".hd-inside :is(button, input, a, textarea, [tabindex])"); if (own) { own.focus(); return; } }
    const pick = sel => [...here.querySelectorAll(sel)].find(b => !b.disabled && b.offsetParent !== null);
    (pick(danger ? "footer [value=no]" : "footer .primary") || pick("footer button"))?.focus();
  }

  // End it with this answer ("yes", "no", or the value of a row or button chosen).
  function close(answer) { if (dlg.open && !inline) dlg.close(answer); }
  // What it resolves with: yes or no for a question, the box's text (or "") for a name or folder, the row's value
  // (or "") for a choice, {ok, value, fields} for a form, {ok, value} for a window.
  function ended() {
    const v = dlg.returnValue;
    const answer = kind === "confirm" ? v === "yes" : kind === "pick" ? (v === "no" ? "" : v)
      : kind === "form" ? { ok: v === "yes", value: v, fields: $state.snapshot(vals) } : kind === "host" ? { ok: v === "yes", value: v }
      : v !== "yes" ? "" : suggest ? tagAnswer() : input.value.trim();
    // Its ids go with it, so the next pop-up's are the only ones on the page while this one is taken away
    for (const el of [dlg, ...dlg.querySelectorAll("[id]")]) el.removeAttribute("id");
    done(answer);
  }
  // A tag's answer: one of your tags whose name it is (as you wrote it), else what's typed (without its "#") when a
  // new one can be made, else the first of your tags shown; "" when there's none.
  function tagAnswer() {
    if (!typedTag) return "";
    const same = (suggest || []).find(t => norm(t.name) === norm(typedTag));
    return same ? same.name : create ? typedTag : tags[0]?.name || "";
  }
  // Enter in a box is OK (or Next), but not while an input method is still putting a word together (Japanese,
  // Korean: WebKit says so only with keyCode 229, its Enter coming after compositionend), nor while the button it
  // would press can't be, nor in a tag's box that would take none of your tags (taking one off).
  function enter(e) {
    if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    if (suggest && kind === "text" && !tagAnswer()) return;
    if (kind === "pick") { const row = dlg.querySelector(".hd-row"); if (row) close(row.value); return; }
    if (kind === "form") { const go = dlg.querySelector(`[data-step="${step + 1}"] footer .primary`); if (go && !go.disabled) go.click(); return; }
    close("yes");
  }
  // A tag chosen from your tags: the box takes it, and it's added.
  function choose(name) { input.value = typed = name; close("yes"); }
  // To another step of a form, the keyboard with it.
  function go(n) { step = n; queueMicrotask(first); }
  // Whether a step's main button waits: a list that needs a tick has none, or a box isn't what it must be.
  function waits(n) {
    return (pages[n] || { blocks: [] }).blocks.some(b => b.type === "checks" && b.required && !vals[b.id].some(Boolean)
      || b.type === "field" && b.mustBe != null && vals[b.id].trim() !== b.mustBe);
  }
  // A long name (a package's, a file's) that may break after a dot, a slash or a dash, never in the middle of a word.
  function breaks(node, text) {
    // (each piece up to and with its mark: no lookbehind, which WebKit before Safari 16.4 can't read)
    const set = t => node.replaceChildren(...(String(t ?? "").match(/[^._/-]*[._/-]|[^._/-]+/g) || []).flatMap((p, i) => i ? [document.createElement("wbr"), p] : [p]));
    set(text);
    return { update: set };
  }
  // A window's inside, drawn by the page: moved in whole (never parsed here).
  function own(node, inside) {
    if (inside) node.replaceChildren(inside);
    return { update(next) { if (next) node.replaceChildren(next); } };
  }

  // What it says cut around the names in it (keep, and a block's own): [words, whether it's a name] in turn.
  function pieces(text, more) {
    const names = [...keep, ...(more || [])].filter(n => n != null && String(n).trim()).map(String).sort((a, b) => b.length - a.length);
    const all = String(text ?? "");
    if (!names.length) return [[all, false]];
    const rx = new RegExp(`(${names.map(n => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`);
    return all.split(rx).map((p, i) => [p, i % 2 === 1]).filter(([p]) => p);
  }
  // A click outside it (on its backdrop) closes a question or a choice: only one that began there too, never a drag
  // from inside it (selecting its words, say) let go outside.
  let pressed = null;
  const outside = e => e.target === dlg && pressed === dlg;

  const lines = p => String(p).split("\n");
  const words = $derived(norm(query).split(/\s+/).filter(Boolean));
  const shown = $derived(groups.map(g => ({ ...g, items: g.items.filter(i => words.every(w => norm(i.name).includes(w))) }))
                                .filter(g => g.items.length));
  const typedTag = $derived(typed.trim().replace(/^#/, ""));
  const tags = $derived(suggest ? suggest.filter(t => !typedTag || norm(t.name).includes(norm(typedTag))).slice(0, 12) : []);
  const isNew = $derived(create && typedTag && !(suggest || []).some(t => norm(t.name) === norm(typedTag)));
</script>

{#snippet said(text, more)}{#each pieces(text, more) as [words, name]}{#if name}<span translate="no">{words}</span>{:else}{words}{/if}{/each}{/snippet}

{#snippet tagsOf(list)}
  {#each list || [] as t}<span class="pj-tag" class:warn={t.warn} translate="no">{t.text}</span>{/each}
{/snippet}

{#snippet block(b)}
  {#if b.type === "text"}
    <p class="hd-p {b.tone || ''}" class:strong={b.strong} translate={b.translate === false ? "no" : undefined}>{@render said(b.text, b.keep)}</p>
  {:else if b.type === "heading"}
    <h4>{@render said(b.text, b.keep)}</h4>
  {:else if b.type === "pre"}
    <pre class="hd-pre {b.cls || ''}" translate="no">{b.text}</pre>
  {:else if b.type === "list"}
    <ul class="hd-list {b.cls || ''}">
      {#each b.items as it}
        <li>{#if it.name}<b translate="no" use:breaks={it.name}></b>{/if}{#if it.sub}{" "}<span class="muted" translate={it.subTranslate === false ? "no" : undefined}>{it.sub}</span>{/if}</li>
      {/each}
    </ul>
  {:else if b.type === "field"}
    <div class="hd-ff">
      <label for={b.id}>{@render said(b.label, b.keep)}</label>
      <div class="hd-field plain">
        {#if b.rows}
          <textarea id={b.id} rows={b.rows} placeholder={b.placeholder || ""} translate="no" bind:value={vals[b.id]}></textarea>
        {:else}
          <input id={b.id} placeholder={b.placeholder || ""} maxlength={b.max || 1000} autocomplete="off" spellcheck="false" translate="no"
                 bind:value={vals[b.id]} onkeydown={enter}>
          {#if b.browse && browse}
            <button type="button" class="ghost" data-browse onclick={async e => {
              const box = e.currentTarget.previousElementSibling;
              await browse(box);
              vals[b.id] = box.value;
            }}>{tr("Browse…")}</button>
          {/if}
        {/if}
      </div>
    </div>
  {:else if b.type === "check"}
    <label class="check hd-check"><input type="checkbox" id={b.id} bind:checked={vals[b.id]}> {@render said(b.label, b.keep)}</label>
  {:else if b.type === "checks"}
    {#if b.allNone}
      <p class="pj-allnone hd-allnone">
        <button type="button" class="linkish" data-all="1" onclick={() => { vals[b.id] = b.items.map(() => true); }}>{tr("Select all")}</button>
        <button type="button" class="linkish" data-all="0" onclick={() => { vals[b.id] = b.items.map(() => false); }}>{tr("Select none")}</button>
      </p>
    {/if}
    <ul class="hd-list {b.cls || ''}">
      {#each b.items as it, i}
        <li><label class="check">
          <input type="checkbox" value={i} data-sugg={b.sugg ? i : undefined} checked={vals[b.id][i]}
                 onchange={e => { vals[b.id][i] = e.currentTarget.checked; }}>
          <span class="pj-c">
            <span><span translate="no" use:breaks={it.label}></span>{#if it.tags?.length}{" "}{@render tagsOf(it.tags)}{/if}</span>
            {#if it.sub}<span class="muted">{@render said(it.sub, it.keep)}</span>{/if}
          </span>
        </label></li>
      {/each}
    </ul>
  {:else if b.type === "radios"}
    {#if b.find}
      <div class="hd-field">
        <span class="hd-fi"><Icon name="search" size={17} /></span>
        <input type="search" id={b.findId} placeholder={b.find} aria-label={b.find} bind:value={finds[b.id]}>
      </div>
    {/if}
    <ul class="hd-list {b.cls || ''}" role="radiogroup" aria-label={b.label}>
      {#each b.items as it}
        <li hidden={!!finds[b.id] && !String(it.value).includes(finds[b.id].trim())}><label class="check">
          <input type="radio" name="{uid}-{b.id}" value={it.value} checked={vals[b.id] === it.value} onchange={() => { vals[b.id] = it.value; }}>
          <span translate="no">{it.label}</span>{#if it.tags?.length}{" "}{@render tagsOf(it.tags)}{/if}
        </label></li>
      {/each}
    </ul>
  {:else if b.type === "columns"}
    <div class="hd-cols {b.cls || ''}">
      {#each b.cols as col}
        <div>
          <h4>{col.heading}</h4>
          {#if col.items.length}
            <ul class="hd-list small" translate="no">{#each col.items as x}<li>{x}</li>{/each}</ul>
          {:else}<p class="hd-p hint">{col.none}</p>{/if}
        </div>
      {/each}
    </div>
  {/if}
{/snippet}

{#snippet more()}
  {#each buttons as b}
    <button type="button" class={b.primary ? "primary" : "ghost"} {...b.attrs || {}}
            onclick={() => { if (b.act) b.act(); else close(b.value); }}>{b.label}</button>
  {/each}
{/snippet}

<dialog bind:this={dlg} {id} class="hd hd-{kind} {cls}" class:danger class:inline class:mid={width === "mid"} class:wide={width === "wide"} class:huge={width === "huge"}
        open={inline || undefined} aria-labelledby="{uid}-t" aria-describedby={detail || paras.length ? `${uid}-d` : undefined}
        onclose={ended} oncancel={() => { dlg.returnValue = "no"; }} onpointerdown={e => { pressed = e.target; }}
        onclick={e => { if (outside(e) && (kind === "confirm" || kind === "pick")) close("no"); }}>
  <div class="hd-card">
    <header>
      <span class="hd-ic {tone}"><Icon name={icon} size={20} /></span>
      <div class="hd-text" id={textId}>
        <h2 id="{uid}-t" class:long={title.length > 64} translate={nameTitle ? "no" : undefined}>{@render said(title)}</h2>
        {#if detail || paras.length}
          <div id="{uid}-d">
            {#if detail}<p class="hd-detail">{#each lines(detail) as line, i}{#if i}<br>{/if}{@render said(line)}{/each}</p>{/if}
            {#each paras as p}<p>{#each lines(p) as line, i}{#if i}<br>{/if}{@render said(line)}{/each}</p>{/each}
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
        {#if find}
          <div class="hd-field">
            <span class="hd-fi"><Icon name="search" size={17} /></span>
            <input bind:this={findBox} type="search" placeholder={find} aria-label={find} bind:value={query} onkeydown={enter}>
          </div>
        {/if}
        <div class="hd-groups">
          {#each shown as g, n (g.title || n)}
            {#if g.title}<h4>{g.title}</h4>{/if}
            <div class="hd-rows">
              {#each g.items as item (item.value)}
                <button type="button" class="hd-row" value={item.value} onclick={() => close(item.value)}>
                  {#if item.pic || item.letters}
                    <span class="hd-th" style:--h={item.hue}>
                      {#if item.pic && !broken.has(item.value)}
                        <img src={item.pic} alt="" loading="lazy" decoding="async" onerror={() => { broken = new Set([...broken, item.value]); }}>
                      {:else}<b translate="no">{item.letters}</b>{/if}
                    </span>
                  {/if}
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
    {:else if kind === "form"}
      {#each pages as page, n}
        <section class="hd-step pj-step" data-step={n + 1} hidden={n !== step}>
          <div class="hd-body">
            {#if page.label}<p class="pj-stepno hd-stepno">{page.label}</p>{/if}
            {#each page.blocks as b}{@render block(b)}{/each}
          </div>
          <footer>
            {#if n === 0}
              {#if cancel}<button type="button" class="ghost" value="no" onclick={() => close("no")}>{cancel}</button>{/if}
            {:else}
              <button type="button" class="ghost" data-step-go={n} onclick={() => go(n - 1)}>{tr("Back")}</button>
            {/if}
            {#if n === pages.length - 1}
              {@render more()}
              {#if ok}<button type="button" class="primary" class:danger id={okId} value="yes" disabled={waits(n)} onclick={() => close("yes")}>{ok}</button>{/if}
            {:else}
              <button type="button" class="primary" data-step-go={n + 2} disabled={waits(n)} onclick={() => go(n + 1)}>{page.ok || tr("Next")}</button>
            {/if}
          </footer>
        </section>
      {/each}
    {:else if kind === "host"}
      <div class="hd-body hd-inside" use:own={content}></div>
    {/if}

    {#if kind !== "form"}
      <footer>
        {#if cancel}<button type="button" class="ghost" value="no" onclick={() => close("no")}>{cancel}</button>{/if}
        {@render more()}
        {#if kind !== "pick" && ok}
          <button type="button" class="primary" class:danger id={okId} value="yes" disabled={suggest && kind === "text" && !tagAnswer()}
                  onclick={() => close("yes")}>{ok}</button>
        {/if}
      </footer>
    {/if}
  </div>
</dialog>

<style>
  /* One look for every pop-up, from the page's own colours (the theme's): the details panel's ground and seam, its
     display font for the title. A style's corners (Treasure's rounder, Workbench's squarer) come from --dlg-radius
     and --dlg-field-radius, set in web/looks.css. Its body scrolls between its title and its buttons. */
  dialog.hd { width: min(480px, calc(var(--vw, 100vw) - 32px)); max-height: calc(var(--vh, 100vh) - 32px); padding: 0;
    border: 0; border-radius: var(--dlg-radius, 18px); overflow: hidden; color: var(--bone); background: var(--ledge);
    box-shadow: 0 0 0 1px var(--seam), 0 30px 80px rgb(0 0 0 / .55); font-family: var(--body); }
  dialog.hd-pick { width: min(540px, calc(var(--vw, 100vw) - 32px)); }
  dialog.hd.mid { width: min(600px, calc(var(--vw, 100vw) - 32px)); }
  dialog.hd.wide { width: min(720px, calc(var(--vw, 100vw) - 32px)); }
  dialog.hd.huge { width: min(1100px, calc(var(--vw, 100vw) - 32px)); }
  dialog.hd::backdrop { background: rgb(10 8 6 / .62); }
  dialog.hd.inline { position: relative; inset: auto; margin: 0; max-width: 100%; }
  .hd-card { display: flex; flex-direction: column; max-height: calc(var(--vh, 100vh) - 32px); min-height: 0; }
  header { flex: none; display: flex; align-items: flex-start; gap: 14px; padding: 22px 20px 4px 24px; }
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
  .hd-step { display: flex; flex-direction: column; min-height: 0; flex: 1 1 auto; }
  .hd-step[hidden] { display: none; }
  .hd-body { padding: 14px 24px 2px; min-height: 0; flex: 1 1 auto; overflow: auto; overflow-wrap: anywhere; }
  .hd-field { position: relative; display: flex; gap: 8px; align-items: center; }
  .hd-fi { position: absolute; left: 14px; top: 50%; transform: translateY(-50%); color: var(--dust); display: grid; pointer-events: none; }
  .hd-field input, .hd-field textarea { flex: 1; min-width: 0; box-sizing: border-box; height: 44px; margin: 0; padding: 0 14px 0 42px;
    border: 0; border-radius: var(--dlg-field-radius, 12px); background: var(--cave); color: var(--bone); font: inherit; font-size: 15px;
    box-shadow: inset 0 0 0 1px var(--seam); }
  .hd-field.plain input { padding-left: 14px; }
  .hd-field textarea { height: auto; min-height: 120px; padding: 10px 14px; line-height: 1.5; resize: vertical; }
  .hd-field input:focus, .hd-field textarea:focus { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  .hd-field input::placeholder, .hd-field textarea::placeholder { color: var(--dust); }
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
  .hd-field + .hd-groups { margin-top: 4px; }
  .hd-rows { display: grid; gap: 6px; }
  .hd-groups > .hd-rows:first-child { margin-top: 2px; }
  .hd-row { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 48px; padding: 8px 12px; border: 0; border-radius: 12px;
    background: var(--cave); color: var(--bone); box-shadow: inset 0 0 0 1px var(--seam); font: inherit; text-align: left; cursor: pointer; }
  .hd-row:has(.hd-th) { padding-left: 8px; }
  .hd-row:hover { box-shadow: inset 0 0 0 1.5px var(--gold); }
  .hd-th { flex: none; width: 38px; height: 38px; border-radius: 9px; overflow: hidden; display: grid; place-items: center;
    background: hsl(var(--h, 30) var(--ph-s, 28%) var(--ph-l, 30%)); }
  .hd-th img { width: 100%; height: 100%; object-fit: cover; }
  .hd-th b { font: 400 14px/1 var(--display); opacity: .85; }
  .hd-name { font-weight: 700; overflow-wrap: anywhere; }
  .hd-sub { margin-left: auto; padding-left: 12px; color: var(--dust); font-size: 13px; text-align: right; }
  .hd-none { margin: 14px 0 4px; color: var(--dust); font-size: 14px; }
  /* a form's blocks */
  .hd-stepno { margin: 0 0 8px; font-size: 12.5px; font-weight: 600; color: var(--dust); }
  .hd-p { margin: 0 0 10px; font-size: 14px; line-height: 1.55; }
  .hd-p.hint { color: var(--dust); font-size: 13.5px; }
  .hd-p.warn { color: var(--warn); font-size: 13.5px; }
  .hd-p.strong { font-weight: 700; }
  .hd-pre { margin: 0 0 12px; padding: 10px 12px; max-height: min(50vh, 480px); overflow: auto; border-radius: 10px; background: var(--cave);
    box-shadow: inset 0 0 0 1px var(--seam); white-space: pre-wrap; overflow-wrap: anywhere; font: 12px/1.5 ui-monospace, monospace; }
  .hd-list { list-style: none; margin: 0 0 12px; padding: 0; font-size: 13.5px; }
  .hd-list li { padding: 7px 2px; border-top: 1px solid var(--seam); overflow-wrap: break-word; }
  .hd-list li:first-child { border-top: 0; }
  .hd-list li[hidden] { display: none; }
  .hd-list .muted { color: var(--dust); }
  .hd-list.small li { padding: 3px 0; border: 0; font-size: 13px; }
  .hd-list label.check { display: flex; align-items: flex-start; gap: 10px; cursor: pointer; }
  .hd-list label.check input { margin-top: 3px; flex: none; }
  .hd-list .pj-c { display: flex; flex-direction: column; min-width: 0; }
  .hd-ff { margin: 0 0 12px; }
  .hd-ff label { display: block; margin: 0 0 6px; font-size: 13px; color: var(--dust); }
  .hd-check { display: flex; align-items: flex-start; gap: 8px; margin: 4px 0 12px; font-size: 14px; line-height: 1.45; cursor: pointer; }
  .hd-check input { margin-top: 3px; flex: none; }
  .hd-allnone { display: flex; gap: 16px; margin: 0 0 6px; }
  .hd-allnone button { font-size: 13px; }
  .hd-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 0 18px; margin: 0 0 8px; }
  .hd-cols h4 { margin-top: 4px; }
  .hd-body > .hd-field:has(+ .hd-list) { margin-bottom: 8px; }
  footer { flex: none; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 16px; padding: 14px 20px 18px;
    border-top: 1px solid var(--seam); }
  footer .primary.danger { background: var(--warn); color: var(--gold-ink); }
  /* A window's inside, still drawn by the page (Mix and match, Share, marks on a photo): its boxes and rows of
     buttons as a pop-up's own, until it's drawn here too */
  .hd-inside :global(input:not([type=checkbox]):not([type=radio])) { height: var(--btn-h-sm, 34px); padding: 0 12px; border-radius: 8px;
    border: 0; background: var(--cave); color: var(--bone); box-shadow: inset 0 0 0 1px var(--seam); font: inherit; }
  .hd-inside :global(input:focus) { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  .hd-inside :global(p) { margin: 0 0 10px; font-size: 14px; line-height: 1.55; overflow-wrap: anywhere; }
  .hd-inside :global(.ask-row) { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin: 12px 0 4px; }
  .hd-inside :global(.ask-row a.ghost) { height: var(--btn-h, 38px); }
  .hd-inside :global(.ghost.danger) { color: var(--warn); }
  @media (max-width: 560px) {
    header { padding: 18px 14px 4px 16px; gap: 12px; }
    .hd-body { padding: 12px 16px 2px; }
    footer { padding: 12px 14px 14px; }
    .hd-sub { display: none; }
    .hd-cols { grid-template-columns: 1fr; }
  }
</style>
