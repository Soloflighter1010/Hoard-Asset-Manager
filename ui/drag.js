// What's being dragged, shown under the pointer (HoardUI.drag; ui/DragGhost.svelte, issue #419): shared.js starts it
// as a drag begins (a product, several, or a project), moves it with the pointer, and ends it as the drag does.
import { mount, unmount, flushSync } from 'svelte';
import DragGhost from './DragGhost.svelte';
let ghost = null;

// Show what's dragged at x, y: {kind: "product" or "project", name, src, initials, hue, blur, more}.
export function start(what, x, y) {
  end();
  flushSync(() => { ghost = mount(DragGhost, { target: document.body, props: what }); ghost.moveTo(x, y); });
}
// Move it with the pointer.
export function move(x, y) {
  if (ghost) ghost.moveTo(x, y);
}
// The drag is over: it goes.
export function end() {
  if (ghost) { unmount(ghost); ghost = null; }
}
