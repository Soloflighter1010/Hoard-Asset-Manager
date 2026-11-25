<script>
  // Issue #424: a folder of projects (projects dropped on each other, #281) drawn as a folder in Hoard's gold, with its
  // first projects' tiles tucked into it (their initials, in their kinds' colours), its name and how many it holds.
  // It opens and takes a project dropped on it as the plain tile did: the button keeps what Projects' clicks, Find and
  // drops read from it (data-pj, data-i, data-folder, data-hay). A project dragged over it opens it a little.
  let { name, index, hay, count, projects = [], updates = 0, tr } = $props();
  const shown = $derived(projects.slice(0, 3));
</script>

<button class="pj-tile pj-folder-tile" data-pj="folderpick" data-i={index} data-folder={name} data-hay={hay}
        aria-label={tr("Folder {0}, {1} projects", name, count)}>
  <span class="pj-tile-art folder" aria-hidden="true">
    <span class="back"></span>
    <span class="papers">
      {#each shown as p, i}
        <i class="k-{p.hue}" style:--at={i - (shown.length - 1) / 2} translate="no">{p.initials}</i>
      {/each}
    </span>
    <span class="front"><span class="n">{count}</span></span>
  </span>
  <span class="nm-t" translate="no">{name}</span>
  <span class="cr">{tr(count === 1 ? "1 project" : "{0} projects", count)}{#if updates}{" · "}{tr("updates inside")}{/if}</span>
</button>

<style>
  .folder { background: none; box-shadow: none; overflow: visible; }
  /* the folder's back, with its tab, and its front, in Hoard's gold; the projects' tiles between them */
  .back { position: absolute; inset: 14% 5% 4%; border-radius: 10px; background: color-mix(in srgb, var(--gold) 62%, var(--cave)); }
  .back::before { content: ""; position: absolute; left: 0; top: -12%; width: 36%; height: 20%; border-radius: 8px 8px 0 0;
    background: inherit; }
  .papers { position: absolute; inset: 6% 18% 34%; display: flex; justify-content: center; align-items: flex-start; }
  .papers i { display: grid; place-items: center; width: 34%; aspect-ratio: 2 / 1; margin: 0 -2%; border-radius: 6px;
    font: 400 clamp(11px, 1.6vw, 17px) var(--display); font-style: normal; color: var(--bone);
    background: color-mix(in srgb, var(--c) 40%, var(--stone)); box-shadow: inset 0 -3px 0 var(--c), 0 2px 6px rgb(0 0 0 / .25);
    transform: translateY(calc(var(--at) * var(--at) * 9%)) rotate(calc(var(--at) * 7deg)); transition: transform .15s ease-out; }
  .k-avatars { --c: var(--pj-avatars); } .k-worlds { --c: var(--pj-worlds); } .k-other { --c: var(--pj-other); }
  .front { position: absolute; inset: 38% 2% 0; border-radius: 10px; transform-origin: 50% 100%; transition: transform .15s ease-out;
    background: linear-gradient(color-mix(in srgb, var(--gold) 92%, #fff), var(--gold));
    box-shadow: 0 -1px 0 color-mix(in srgb, var(--gold) 60%, #fff) inset, 0 6px 14px -6px rgb(0 0 0 / .4); }
  .n { position: absolute; right: 12px; bottom: 8px; font: 400 26px/1 var(--display); color: var(--gold-ink); }
  /* pointed at, its projects rise; a project dragged over it, it opens */
  button:hover .papers i, button:focus-visible .papers i { translate: 0 -10%; }
  button:global(.drop-on) .front { transform: perspective(300px) rotateX(-16deg); }
  button:global(.drop-on) .papers i { translate: 0 -16%; }
  :global(body.less-motion) .papers i, :global(body.less-motion) .front { transition: none; }
  @media (prefers-reduced-motion: reduce) { .papers i, .front { transition: none; } }
  :global([data-style="treasure"]) .back, :global([data-style="treasure"]) .front { border-radius: 16px; }
  :global([data-style="workbench"]) .back, :global([data-style="workbench"]) .front { border-radius: 5px; }
  :global([data-style="workbench"]) .papers i { border-radius: 3px; }
</style>
