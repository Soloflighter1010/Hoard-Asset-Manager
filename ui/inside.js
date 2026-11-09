// The compiled trial has one small public boundary; Python releases serve the checked-in bundle without Node.
import { mount, unmount, flushSync } from 'svelte';
import LookInside from './LookInside.svelte';
const windows = new WeakMap();

// Mount once, then update the component's model synchronously for the existing window's delegated events.
export function render(target, model, tr) {
  let component = windows.get(target);
  flushSync(() => {
    if (component) component.update(model);
    else { target.replaceChildren(); component = mount(LookInside, { target, props: { initial: model, tr } }); windows.set(target, component); }
  });
}
// Update selection/busy state without redrawing package folders or the focused search field.
export function bar(target, model) {
  const component = windows.get(target);
  if (component) flushSync(() => component.updateBar(model));
}
// Release the component before showing a different file's loading/error state.
export function clear(target) {
  const component = windows.get(target);
  if (component) { unmount(component); windows.delete(target); }
}
