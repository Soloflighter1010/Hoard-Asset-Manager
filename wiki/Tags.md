Hoard has two kinds of tags:

- **Your tags**, which you create and put on items yourself.
- **Suggested tags**: words that turn up in several item names (`FoxyHoodie v2` gives `foxy` and `hoodie`), with
  filler words and version numbers left out.

Tags work the same in the Library and in Downloads, and they share one set: tag something in one and it's
tagged in the other. Filter by any tag from the sidebar; filters combine.

## Tagging

- **One item:** open it, then type a tag under **Tags**, or click a suggestion to add it. Remove a tag with the
  **×** next to it. A tag you add applies to every copy of that product you own on other stores.
- **Many items:** choose **Select**, click the items (or **Select all shown** after filtering, say by a
  creator), type a tag, then **Add tag** or **Remove tag**.

## The Tags panel

The **Tags** button opens a list of all your tags and the suggestions:

- **Keep** a suggestion to make it your tag on every item whose name has that word, including items you buy
  later. **Hide** one to stop it being suggested.
- **Rename** a tag. Renaming it to an existing tag's name merges the two.
- **Match names** gives any tag that automatic matching, and **Delete** removes a tag.

## What a tag can be

Lower case letters, marks and digits in any script (so Japanese works), plus spaces and `- _ . + & '`, up to 40
characters. Hoard cleans what you type to fit.

## Where tags are kept

Your tags live in `tags.json` in Hoard's private app-data folder. The downloads folder also gets a `tags.json`,
rebuilt after each download, listing which downloaded products have each tag, for other programs to read. See
[Where Hoard keeps things](Where-Hoard-Keeps-Things).

When suggestions appear (how many items a word needs, and how common is too common) can be tuned in
`config.json`: see [Settings](Settings#settings-only-in-configjson).
