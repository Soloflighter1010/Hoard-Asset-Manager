// Settings (issues #421 and #422; ui/Settings.svelte, HoardUI.settings): its parts as cards, each setting a row, Find
// a setting, and Features. The settings themselves are still shared.js's markup in #settingsPanel's .set-body: each
// setting, a heading (h4) and what follows it, is moved whole into its row here, so its ids and the code that fills
// and saves it stay as they were, as Look inside's tree and the pop-ups' windows are.
import { mount, flushSync } from 'svelte';
import Settings from './Settings.svelte';

// Settings' parts, fewer than its old list of headings: each a card, its settings by their headings' ids. pair: a
// setting with one dropdown, shown beside its name on a wide window. feature: the part of Hoard (FEATURES) a card is
// for, or each of its settings that's for one, by its id: turned off, it isn't shown.
export const PARTS = [
  { id: 'card-folders', title: 'Folders', about: 'Where Hoard keeps what it downloads, the other folders it reads, and its own.',
    rows: ['part-folders', 'set-libs', 'part-places', 'part-sync'], feature: { 'part-sync': 'local' } },
  { id: 'card-stores', title: 'Stores', about: 'The stores you use, and how Hoard reads them and signs in to them.',
    rows: ['part-stores', 'set-shops', 'set-tags', 'part-signins'] },
  { id: 'card-downloading', title: 'How Hoard downloads', about: "What's saved, what's left out, and when Hoard looks for more.",
    rows: ['part-downloading', 'set-rules', 'set-new', 'set-retries', 'set-previous', 'set-routine'],
    pair: ['set-new', 'set-retries', 'set-previous', 'set-routine'] },
  { id: 'card-notify', title: 'Notifications', about: 'News Hoard sends you, through Apprise: to Discord, Telegram, email and more.',
    rows: ['part-apprise'], feature: 'notifications' },
  { id: 'card-look', title: 'Look and feel', about: 'How Hoard looks, in your language, and how easy it is to read and use.',
    rows: ['part-look', 'set-access'] },
  { id: 'card-features', title: 'Features', features: true,
    about: "Turn off the parts of Hoard you don't use, so they're out of your way. Nothing they keep is deleted: turned on again, they're as you left them." },
  { id: 'card-hoard', title: 'Hoard itself', about: "Closing it, its updates, backups, and another tool's library brought in.",
    rows: ['set-closing', 'part-updates', 'part-backup', 'set-import'] },
  { id: 'card-help', title: 'Help', about: "When something isn't working, supporting Hoard, and who it thanks.",
    rows: ['part-help', 'part-tip', 'part-thanks'] },
];

// The parts of Hoard you can turn off (issue #422), by their keys in the pages' settings (ui.features; hoard/server.py's
// FEATURES has the same keys). needs: the part it's a part of, which turned off turns it off too.
export const FEATURES = [
  { key: 'local', title: 'Local', about: 'Your own packages, textures and materials, and the Local sync folder.' },
  { key: 'sets', title: 'Sets and Wishlists', about: 'Sets of products you use together, and wishlists of products you want.' },
  { key: 'wishlists', title: 'Wishlists', needs: 'sets', about: 'Wishlists alone: your sets stay. Wishlists from your stores are no longer read.' },
  { key: 'prices', title: 'Prices', needs: 'wishlists', about: "Wishlists' prices, and the news when a product on one gets cheaper." },
  { key: 'projects', title: 'Projects', about: 'Your Unity projects, and the parts of Hoard that are for them.' },
  { key: 'notifications', title: 'Notifications', about: "Your system's notifications, and the news sent through Apprise." },
  { key: 'adult', title: 'Products for adults', about: "Products marked 18+, and everything that's about them. Off, they aren't shown anywhere." },
];

let shown = null;

// Draw Settings' frame in panel's #setFrame, once (Settings is drawn once, and filled each time it opens). on: the
// parts of Hoard turned off ({key: false}); change(key, on): one turned on or off.
export function frame(panel, { on = {}, change = () => {}, tr = s => s } = {}) {
  if (shown) return shown;
  const body = panel.querySelector('.set-body'), rows = new Map();
  let row = null;
  for (const node of [...body.childNodes]) {
    const heading = node.nodeType === 1 && (node.matches('h4') ? node : node.querySelector(':scope > h4'));
    if (heading) { row = { id: heading.id, nodes: [] }; rows.set(heading.id, row); }
    if (row) row.nodes.push(node);
  }
  body.remove();
  const parts = PARTS.map(part => ({
    ...part, feature: typeof part.feature === 'string' ? part.feature : '',
    rows: (part.rows || []).filter(id => rows.has(id)).map(id => {
      const r = rows.get(id);
      return { ...r, pair: (part.pair || []).includes(id), feature: (part.feature || {})[id] || '' };
    }),
  }));
  flushSync(() => {
    shown = mount(Settings, { target: panel.querySelector('#setFrame'), props: { parts, features: FEATURES, on, change, tr } });
  });
  return shown;
}

// The parts of Hoard turned on or off from elsewhere (one turned on where something needed it): the switches show it.
export function features(on) {
  if (shown) flushSync(() => shown.setFeatures(on));
}

// Settings opened or closed: Find a setting starts empty again.
export function clearFind() {
  if (shown) flushSync(() => shown.clearFind());
}
