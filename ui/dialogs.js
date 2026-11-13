// Hoard's pop-ups (ui/Dialog.svelte): open one, and get its answer. shared.js's ask, askName, askFolder, askChoice and
// askForm, and the windows whose inside the page draws (Mix and match, Share, marks on a photo), call open();
// heading() turns a question's text into its title and the line under it.
//
// A form's blocks (askForm), each {type, ...}: "text" {text, tone: "hint" or "warn", strong}; "heading" {text}; "pre"
// {text} (a license, Git's rules); "list" {items: [{name, sub}]}; "field" {id, label, value, rows (a box of lines),
// browse, mustBe (its main button waits until it says this)}; "check" {id, label, checked}; "checks" {id, items:
// [{label, sub, tags, checked, keep}], allNone, required (its main button waits for a tick)}; "radios" {id, items:
// [{value, label, tags}], value, find}; "columns" {cols: [{heading, items, none}]}. Each may have cls, for the pages'
// styles and tests, and keep: the names in its words (a path, a package's id), which no browser's translation changes
// (as the pop-up's own keep does for everything it says). Its answer's fields hold each field's text, each check's true or false, each checks' list of which are
// ticked, and each radios' value, by id.
import { mount, unmount, flushSync } from 'svelte';
import Dialog from './Dialog.svelte';

// Open a pop-up (Dialog.svelte's props, but done) on the page; resolves with its answer when it closes: true or false
// for a question, the text (or "") for a name or folder, the value of the row chosen (or "") for a choice.
export function open(spec) {
  return new Promise(resolve => {
    let component;
    const done = answer => { resolve(answer); setTimeout(() => unmount(component), 0); };
    flushSync(() => { component = mount(Dialog, { target: document.body, props: { ...spec, done } }); });
  });
}

// The same pop-up drawn in this place on the page, as an example (the style guide); it answers nothing.
export function example(target, spec) {
  flushSync(() => { mount(Dialog, { target, props: { tr: s => s, ...spec, inline: true, done() {} } }); });
}

// A question's title and what follows it: "Delete 2 backups? They can't be restored." is titled with the question and
// says the rest under it; anything else with its first sentence. With colon (a box's title: "Rename {0}: its folder
// is renamed..."), what comes before a colon is the title. It works on the translated text, as each language marks a
// question or a sentence's end ("?" and "？", "." and "。"; Japanese's "?" with no space after it), and never cuts
// inside brackets or quotes (an address's "https://... or git@...", an example's) or at an ellipsis. Paragraphs
// after the first are returned as more.
export function heading(text, colon = false) {
  const [first = '', ...more] = String(text).split(/\n\s*\n/);
  let at = mark(first, (c, i) => c === '？' || c === '?' && ends(first, i + 1));
  if (at >= 0) return parts(first, at + 1, more);
  at = colon ? mark(first, (c, i) => c === '：' || c === ':' && i + 1 < first.length && ends(first, i + 1)) : -1;
  if (at > 0 && at <= 60) return parts(first, at, more, 1);
  at = mark(first, (c, i) => '。！'.includes(c) || '.!'.includes(c) && first[i - 1] !== '.' && /\s/.test(first[i + 1] || ''));
  if (at > 0 && first.slice(at + 1).trim()) return parts(first, at + 1, more);
  return { title: first.trim(), detail: '', more };
}

const OPEN = '([{（「『【“', CLOSE = ')]}）」』】”';
const CJK = /[\u3000-\u30ff\u3400-\u9fff\uac00-\ud7af\uff01-\uff60]/;
// Whether a mark ends a clause where it's followed by what's at i: a space, the end, or a Japanese or Korean letter.
const ends = (text, i) => i >= text.length || /\s/.test(text[i]) || CJK.test(text[i]);
// Where in text the first mark is that is(c, i) says ends a clause, outside brackets and quotes; -1 when there's none.
function mark(text, is) {
  let depth = 0;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (OPEN.includes(c)) depth++;
    else if (CLOSE.includes(c)) depth = Math.max(0, depth - 1);
    else if (!depth && is(c, i)) return i;
  }
  return -1;
}

// The text cut at this place, the cut mark (a colon's) left out; what follows starts with a capital in a language
// that has them.
function parts(text, at, more, skip = 0) {
  const rest = text.slice(at + skip).trim();
  return { title: text.slice(0, at).trim(), detail: rest.charAt(0).toUpperCase() + rest.slice(1), more };
}
