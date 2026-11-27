<script>
  // The filters' views (issue #448): each with its icon from Hoard's own set (ui/Icon.svelte), its name, and how many
  // it has (Disk space: their size; Hidden, while it's locked, a lock in place of a count). The page chooses a view by
  // its data-view, as it did when it drew them itself. Its words are the page's to translate, as the rest of it.
  import { untrack } from 'svelte';
  import Icon from './Icon.svelte';
  let { views = [] } = $props();
  let list = $state(untrack(() => views));

  // The views as they are now (the page draws them again as what's in them changes).
  export function set(next) { list = next; }
</script>

{#each list as v (v.key)}
  <button role="radio" data-view={v.key} aria-checked={String(!!v.checked)}>
    <span class="vi"><Icon name={v.icon} size={16} /></span>{v.label}
    {#if v.locked}<span class="n" aria-label="locked"><Icon name="lock" size={13} /></span>{:else}<span class="n">{v.count}</span>{/if}
  </button>
{/each}

<style>
  .vi { display: inline-flex; flex: none; color: var(--dust); }
  button[aria-checked="true"] .vi, button:hover .vi { color: var(--gold-text); }
  .n :global(svg) { vertical-align: -2px; }
</style>
