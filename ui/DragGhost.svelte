<script>
  // Issue #419: what's being dragged, under the pointer: a small copy of its tile (its picture, or a project's
  // initials in its kind's colour, and its name), with how many more go with it. It never takes the pointer, so what's
  // under it still says what a drop will do (shared.js's dropTarget, on the tile or tab beneath).
  let { kind, name, src = "", initials = "", hue = "", blur = false, more = 0 } = $props();
  let x = $state(-1000), y = $state(-1000);   // (out of sight until it's put under the pointer)

  // Follow the pointer.
  export function moveTo(nx, ny) { x = nx; y = ny; }
</script>

<div class="ghost {kind}" style:transform="translate({x + 14}px, {y + 12}px)" aria-hidden="true" data-drag-ghost>
  <span class="pic k-{hue}">
    {#if src}<img src={src} alt="" class:blur draggable="false">{:else}<b translate="no">{initials}</b>{/if}
  </span>
  <span class="nm" translate="no">{name}</span>
  {#if more}<span class="more">+{more}</span>{/if}
</div>

<style>
  .ghost { position: fixed; left: 0; top: 0; z-index: 70; display: flex; align-items: center; gap: 9px; max-width: 260px;
    padding: 6px 12px 6px 6px; border-radius: 12px; background: var(--ledge); color: var(--bone);
    box-shadow: 0 0 0 1px var(--seam), 0 12px 30px rgb(0 0 0 / .35); pointer-events: none; opacity: .94;
    font: 700 13px/1.3 var(--body); will-change: transform; }
  .pic { flex: none; display: grid; place-items: center; width: 44px; height: 44px; border-radius: 8px; overflow: hidden;
    background: color-mix(in srgb, var(--c, var(--seam)) 30%, var(--stone)); box-shadow: inset 0 -3px 0 var(--c, var(--seam)); }
  .project .pic { width: 64px; height: 32px; }   /* (a project's tile is twice as wide as it's tall) */
  .k-avatars { --c: var(--pj-avatars, var(--jinxxy)); } .k-worlds { --c: var(--pj-worlds, var(--itch)); }
  .k-other { --c: var(--pj-other, var(--payhip)); }
  .pic img { width: 100%; height: 100%; object-fit: cover; }
  .pic img.blur { filter: blur(8px) saturate(.6); transform: scale(1.2); }
  .pic b { font: 400 15px var(--display); color: var(--bone); }
  .nm { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .more { flex: none; padding: 1px 7px; border-radius: 999px; background: var(--gold); color: var(--gold-ink); font-size: 11.5px; }
  :global([data-style="treasure"]) .ghost { border-radius: 999px; padding-right: 16px; }
  :global([data-style="treasure"]) .pic { border-radius: 999px; }
  :global([data-style="workbench"]) .ghost { border-radius: 6px; }
  :global([data-style="workbench"]) .pic { border-radius: 4px; }
</style>
