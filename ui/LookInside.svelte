<script>
  // A bounded Svelte trial: window content, search, code summary and extraction controls. The existing lazy file
  // tree enters through an owned DOM node while it is migrated separately; no user text is accepted as HTML.
  import { untrack } from "svelte";
  let { initial, tr } = $props();
  let model = $state.raw(untrack(() => initial));   // later changes arrive through the explicit update boundary

  // Refresh the window model without replacing its search field or losing keyboard focus.
  export function update(next) { model = next; }
  // Progress and selection update only the controls; the open folder tree stays mounted.
  export function updateBar(next) { model = { ...model, ...next }; }
  // Attach the existing tree's DOM at a single documented migration boundary, without parsing HTML here.
  function treeContent(node, fragment) {
    node.replaceChildren(fragment);
    let current = fragment;
    return { update(next) { if (next !== current) { current = next; node.replaceChildren(next); } } };
  }
</script>

<p class="file-name" translate="no">{model.name}</p>
{#if model.code}
  <div class:has={model.hasCode} class="code-sum">
    <p>{model.code}</p>
    {#if model.hasCode}
      <p class="hint">{tr("Hoard says what's here; it doesn't call a package safe or unsafe, and sends nothing anywhere to be checked.")}</p>
      <button class="ghost sm" data-only-code aria-pressed={!!model.onlyCode}>{tr("Only code")}</button>
    {/if}
  </div>
{/if}
{#if model.controls}
  <input type="search" id="insideQ" placeholder={tr("Search in it")} aria-label={tr("Search in it")} value={model.query}>
  <div class="inside-bar">
    <button class="primary sm" data-x="extract" data-what="chosen" disabled={!model.chosen || model.busy}>
      {model.busy ? tr("Taking them out...") : model.chosen ? tr(model.chosen === 1 ? "Extract the chosen file" : "Extract the {0} chosen files", model.chosen.toLocaleString()) : tr("Choose files to extract")}
    </button>
    <button class="ghost sm" data-x="extract" data-what="all" disabled={!!model.busy}>{tr("Extract everything")}</button>
    {#if model.packaged}
      <label class="check"><input type="checkbox" id="insideMetas" checked={!!model.metas}> {tr("With Unity's .meta files")}</label>
    {/if}
  </div>
{/if}
<div class="inside-content" use:treeContent={model.content}></div>
