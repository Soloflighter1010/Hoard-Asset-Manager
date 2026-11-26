<script>
  // Settings (issues #421 and #422): its parts as cards, each with a heading and a line saying what it's for, every
  // setting a row in one, Find a setting to find one by its words, and Features, the parts of Hoard you can turn off.
  // A card's rows are shared.js's markup, each setting's heading and controls moved whole into its row (adopt), so
  // their ids and the code that fills and saves them stay as they were; Features is this component's own.
  import { untrack } from 'svelte';

  let { parts, features, on: initial = {}, change = () => {}, tr = s => s } = $props();
  let q = $state('');
  let on = $state(untrack(() => ({ ...initial })));   // a part's key: false when it's turned off

  // The parts turned on or off from elsewhere (one turned on where something needed it): the switches show it.
  export function setFeatures(next) { on = { ...next }; }
  // Settings opened or closed: what was typed in Find a setting goes, so every card shows again (and the bar's
  // settings: search, which leaves out what's hidden, finds them all).
  export function clearFind() { q = ''; }

  // Whether a part of Hoard is on: it, and the part it's in (a feature's needs). '' (not a part's): always.
  const isOn = key => !key || (on[key] !== false && isOn(needsOf(key)));
  // The part a part is in ('' for none).
  const needsOf = key => (features.find(f => f.key === key) || {}).needs || '';
  // The part to turn on first for this one: the one it's in, or the one that's in, as far up as is off (Prices, with
  // Sets and Wishlists off, needs that turned on first, not Wishlists, whose own switch is greyed then).
  const firstOff = key => { let k = needsOf(key); while (needsOf(k) && !isOn(needsOf(k))) k = needsOf(k); return k; };
  // Words as Find compares them: the same width and case however they were typed.
  const norm = s => String(s || '').normalize('NFKC').toLowerCase();
  // Whether a setting's piece shows: not hidden (Closing Hoard outside Hoard's window), nor a part turned off's.
  const shows = el => !el.hidden && !(el.dataset.feature || '').split(' ').some(k => k && !isOn(k));
  // What a node says that shows, for Find: its words, and its boxes' names, placeholders and tips.
  const words = n => n.nodeType === 3 ? n.textContent : n.nodeType !== 1 || !shows(n) ? '' :
    [n.getAttribute('aria-label'), n.getAttribute('placeholder'), n.getAttribute('title'), ...[...n.childNodes].map(words)]
      .filter(Boolean).join(' ');
  // What a row says, for Find (what's hidden in it isn't found: a card with nothing showing that matches stays out).
  const said = row => norm(row.nodes.map(words).join(' '));
  // Whether anything in a row shows now (Closing Hoard doesn't, outside Hoard's own window).
  const showing = row => row.nodes.some(n => n.nodeType === 1 ? shows(n) : n.textContent.trim() !== '');
  const found = $derived.by(() => {
    const want = norm(q.trim());
    return parts.map(part => {
      const whole = !want || norm(tr(part.title) + ' ' + tr(part.about)).includes(want);
      const rows = part.features ? features.map(f => whole || norm(tr(f.title) + ' ' + tr(f.about)).includes(want))
                                 : part.rows.map(r => isOn(r.feature) && (!want || (showing(r) && (whole || said(r).includes(want)))));
      return { rows, any: isOn(part.feature) && rows.some(Boolean) };
    });
  });
  const none = $derived(q.trim() !== '' && !found.some(f => f.any));

  // Move a setting's own markup into its row (it stays there: Settings is drawn once).
  function adopt(el, nodes) { el.append(...nodes); }
  // A part turned on or off: shared.js keeps it, and shows or hides that part of Hoard.
  function flip(key, value) {
    on = { ...on, [key]: value };
    change(key, value);
  }
</script>

<nav class="setjump" aria-label={tr("Parts of Settings")}>
  <input type="search" id="setFind" class="set-find" bind:value={q} placeholder={tr("Find a setting")}
         aria-label={tr("Find a setting")} autocomplete="off" spellcheck="false">
  {#each parts as part, i}
    <button data-jump={part.id} hidden={!found[i].any}>{tr(part.title)}</button>
  {/each}
</nav>
<div class="set-body">
  <p class="set-saved">{tr("Changes are saved as you make them.")}</p>
  {#each parts as part, i}
    <section class="set-card" id={part.id} hidden={!found[i].any} aria-labelledby="{part.id}-title">
      <header class="set-card-head">
        <h3 id="{part.id}-title">{tr(part.title)}</h3>
        <p>{tr(part.about)}</p>
      </header>
      {#if part.features}
        <div class="set-row set-switches" role="group" aria-label={tr(part.title)}>
          {#each features as f, k}
            <label class="set-switch" class:needs={!isOn(f.needs)} hidden={!found[i].rows[k]} data-feature-switch={f.key}>
              <span class="set-switch-words"><b>{tr(f.title)}</b><small>{tr(f.about)}</small>
                {#if !isOn(f.needs)}<small class="set-needs">{tr("Turn on {0} first.", tr(features.find(x => x.key === firstOff(f.key)).title))}</small>{/if}
              </span>
              <input type="checkbox" role="switch" checked={isOn(f.key)} disabled={!isOn(f.needs)}
                     onchange={e => flip(f.key, e.currentTarget.checked)}>
            </label>
          {/each}
        </div>
      {:else}
        {#each part.rows as row, k (row.id)}
          <div class="set-row" class:pair={row.pair} hidden={!found[i].rows[k]} use:adopt={row.nodes}></div>
        {/each}
      {/if}
    </section>
  {/each}
  {#if none}<p class="none set-none">{tr("Nothing in Settings has those words.")}</p>{/if}
</div>

<style>
  /* the cards: each part of Settings on its own ground, its heading and what it's for at the top */
  .set-card { margin: 0 0 18px; padding: 4px 22px 10px; border-radius: var(--card-radius, 14px); background: var(--ledge);
    box-shadow: 0 0 0 1px var(--seam); scroll-margin-top: 12px; }
  .set-card-head { padding: 16px 0 12px; border-bottom: 1px solid var(--seam); }
  .set-card-head h3 { margin: 0; padding: 0; border: 0; font: 400 21px/1.2 var(--display); color: var(--bone); }   /* (not .stores h3's line above it) */
  .set-card-head p { margin: 4px 0 0; color: var(--dust); font-size: 13.5px; }
  .set-saved { margin: 0 0 12px; color: var(--dust); font-size: 13px; }
  /* a setting: its name and what it does, then what it is now; a setting with one dropdown, beside it */
  .set-row { padding: 12px 0 14px; border-top: 1px solid var(--seam); }
  .set-card-head + .set-row { border-top: 0; }
  @media (min-width: 720px) {
    .set-row.pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(200px, 300px); column-gap: 24px; align-items: start; }
    .set-row.pair > :global(*) { grid-column: 1; }
    .set-row.pair > :global(select) { grid-column: 2; grid-row: 1 / span 3; align-self: center; }
  }
  /* Find a setting, at the top of the parts' list */
  .set-find { width: 100%; height: var(--btn-h-sm, 34px); margin: 0 0 8px; padding: 0 12px; border: 0; border-radius: 9px;
    background: var(--stone); color: var(--bone); font: 500 13.5px var(--body); box-shadow: inset 0 0 0 1px var(--seam); }
  .set-find:focus { outline: none; box-shadow: inset 0 0 0 2px var(--gold); }
  /* Features: a switch for each part of Hoard you can turn off */
  .set-switches { display: grid; gap: 0; padding: 0; }
  .set-switch { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 12px 0;
    border-top: 1px solid var(--seam); cursor: pointer; }
  .set-switch:first-child { border-top: 0; }
  .set-switch-words { display: grid; gap: 2px; min-width: 0; }
  .set-switch-words b { font: 700 14px var(--body); color: var(--bone); }
  .set-switch-words small { font-size: 13px; color: var(--dust); line-height: 1.45; }
  .set-switch input { appearance: none; -webkit-appearance: none; flex: none; position: relative; width: 42px; height: 24px; margin: 0;
    border-radius: 999px; background: var(--seam); cursor: pointer; transition: background .15s; }
  .set-switch input::after { content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%;
    background: var(--bone); transition: transform .15s; }
  .set-switch input:checked { background: var(--gold); }
  .set-switch input:checked::after { transform: translateX(18px); background: var(--gold-ink); }
  .set-switch input:focus-visible { outline: 2px solid var(--gold); outline-offset: 2px; }
  .set-switch.needs { cursor: default; }
  .set-switch.needs input { opacity: .5; cursor: default; }
  .set-switch-words .set-needs { color: var(--gold-text); }
  @media (prefers-reduced-motion: reduce) { .set-switch input, .set-switch input::after { transition: none; } }
  :global(body.less-motion) .set-switch input, :global(body.less-motion) .set-switch input::after { transition: none; }
  .set-none { margin: 30px 0; }
  :global([data-style="workbench"]) .set-card { border-radius: 6px; }
  :global([data-style="treasure"]) .set-card { border-radius: 18px; }
</style>
