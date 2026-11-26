// Projects' parts drawn in Svelte (HoardUI.projects): a folder's tile (ui/FolderTile.svelte, issue #424). shared.js
// draws the list as markup with a placeholder for each folder's tile, then puts the tiles in their places here; the
// tiles drawn before (a list drawn again replaces them) are let go first.
import { mount, unmount, flushSync } from 'svelte';
import FolderTile from './FolderTile.svelte';
let shown = [];

// Put each folder's tile in place of its placeholder ([data-folder-slot] with the folder's number) in box: tiles[i] is
// the folder's {name, index, hay, count, projects: [{initials, hue}], updates}.
export function folders(box, tiles, tr) {
  clear();
  flushSync(() => {
    for (const slot of box.querySelectorAll('[data-folder-slot]')) {
      const props = tiles[+slot.dataset.folderSlot];
      if (props) shown.push(mount(FolderTile, { target: slot.parentNode, anchor: slot, props: { ...props, tr } }));
      slot.remove();
    }
  });
}
// Let go of the folders' tiles (the list is drawn again, or put away).
export function clear() {
  for (const tile of shown) unmount(tile);
  shown = [];
}
