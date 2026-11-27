// What's being dragged, shown under the pointer (HoardUI.drag; ui/DragGhost.svelte, issue #419): shared.js starts it
// as a drag begins (a product, several, or a project), moves it with the pointer, and ends it as the drag does.
import { mount, unmount, flushSync } from 'svelte';
import DragGhost from './DragGhost.svelte';
let ghost = null;
// The page's zoom (Settings' text size, on the html element: shared.js's pageZoom): the pointer is in the window's pixels,
// the ghost on the zoomed page, so it's placed at the pointer over the zoom (issue #436: it was far from it, zoomed).
const zoom = () => parseFloat(document.documentElement.style.zoom) || 1;

// Show what's dragged at x, y: {kind: "product" or "project", name, src, initials, hue, blur, more}.
export function start(what, x, y) {
  end();
  flushSync(() => { ghost = mount(DragGhost, { target: document.body, props: what }); ghost.moveTo(x / zoom(), y / zoom()); });
}
// Move it with the pointer.
export function move(x, y) {
  if (ghost) ghost.moveTo(x / zoom(), y / zoom());
}
// The drag is over: it goes.
export function end() {
  if (ghost) { unmount(ghost); ghost = null; }
}
