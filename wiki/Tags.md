Hoard has two kinds of tags:

- **Your tags**, which you create and put on items yourself.
- **Suggested tags**: words that turn up in several item names (`FoxyHoodie v2` gives `foxy` and `hoodie`), with
  filler words and version numbers left out.

Tags work the same in the Library and in Downloads, and they share one set: tag something in one and it's
tagged in the other. Filter by any tag from the sidebar; filters combine.

## Tagging

- **One item:** open it, then type a tag under **Tags**, or click a suggestion to add it. Remove a tag with the
  **×** next to it. A tag you add applies to every copy of that product you own on other stores.
- **Its creator's tags** (5.2.0): on Booth, Jinxxy and itch.io, the tags a creator gave a product on its store's
  page show in its details, under its suggestions: click one to make it your tag on it. They're among the suggested
  tags beside the grid too, to filter by, and the search finds them (`tag:`). They never change your own tags.
  Hoard reads a few products' pages each time it reads a store, until each one has been read once; turn it off in
  [Settings](Settings) (**Store tags**). Gumroad's and Payhip's product pages don't show their tags.
- **Many items:** choose them (tick their boxes, Ctrl- or Shift-click, or **Select** then click; or **Select all
  shown** after filtering, say by a creator), then **Tags** in the selection bar, or right-click: **Add a tag** or
  **Remove a tag**.

## The Tags panel

**Tags** (in the **Menu**, top right) opens a list of all your tags and the suggestions:

- **Keep** a suggestion to make it your tag on every item whose name has that word, including items you buy
  later. **Hide** one to stop it being suggested.
- **Rename** a tag. Renaming it to an existing tag's name merges the two.
- **Match names** gives any tag that automatic matching, and **Delete** removes a tag.

## Kinds of tags

A tag of yours can say what it's about: **Avatar**, **World**, **Clothing**, **Gimmick**, **Script**, **Texture** or
**Other** (5.0). Choose it beside the tag in the **Tags** panel; a tag has one kind, or none. Your tags in the filters
are then grouped by kind, and [Mix and match](Sets#mix-and-match) takes avatars and clothes from them: tag your bases
with an Avatar tag, and your outfits with Clothing tags (one tag for each kind of thing, such as tops, shoes or hair, if
you'd like a pick of each).

## Product types

What a product is (**Avatar**, **Clothing**, **Accessory**, **Hair**, **Texture**, **Shader**, **Gimmick**,
**Script**, **Tool**, **Animation**, **World** or **Other**) is a field of its own, not a tag (5.2.0). Hoard guesses
it from the product's name and its creator's tags on its store, or one of your tags says (a tag of kind Avatar, as
you said it before 5.2.0). Set it yourself in a product's details, under **Product type**; **Let Hoard guess** goes
back. Filter by it with **Product type** beside the grid, or search for `type:avatar`. Your tags stay for your own
words.

## What a tag can be

Lower case letters, marks and digits in any script (so Japanese works), plus spaces and `- _ . + & '`, up to 40
characters. Hoard cleans what you type to fit.

## Where tags are kept

Your tags live in `tags.json` in Hoard's private app-data folder. The downloads folder also gets a `tags.json`,
rebuilt after each download, listing which downloaded products have each tag, for other programs to read. See
[Where Hoard keeps things](Where-Hoard-Keeps-Things).

When suggestions appear (how many items a word needs, and how common is too common) can be tuned in
`config.json`: see [Settings](Settings#settings-only-in-configjson).
