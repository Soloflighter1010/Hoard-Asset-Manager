// The filters' views drawn in Svelte (HoardUI.views, ui/Views.svelte, issue #448): each page (library.js,
// downloads.js) says which views it has and how many each holds, and they're drawn in its box with their icons.
import { mount, flushSync } from 'svelte';
import Views from './Views.svelte';
const shown = new WeakMap();   // a box: the views drawn in it

// Draw views in box: [{key, label, icon, count, checked, locked}], each a button with its data-view.
export function show(box, views) {
  flushSync(() => {
    const was = shown.get(box);
    if (was) { was.set(views); return; }
    box.replaceChildren();
    shown.set(box, mount(Views, { target: box, props: { views } }));
  });
}
