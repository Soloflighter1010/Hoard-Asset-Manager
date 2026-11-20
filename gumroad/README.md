# Hoard's Gumroad page

The page at [soloflighter.gumroad.com/l/hoardvrc](https://soloflighter.gumroad.com/l/hoardvrc): the website's front
page, as one file Gumroad can serve, with Gumroad's buy buttons where the site has its downloads.

| | |
|---|---|
| `landing.src.html` | The template: the page's own parts (its bar, the hero, What is Hoard?, Get Hoard, Safe by design), and where the site's go |
| `landing.html` | The page, built: what's published to Gumroad. Don't edit it; edit the template or the site, and build again |
| `media.json` | Where each screenshot is in Gumroad's media library, with the fingerprint of the file it was uploaded from |
| `../scripts/build_gumroad_page.py` | Builds `landing.html` from the template and `site/`, and checks what Gumroad would refuse |

## What comes from the site

Each build takes these from `site/` again, so the Gumroad page follows the front page: the stylesheet (the sections
the front page uses, with its fonts inlined), the logo, the 11 tiles, the 11 screenshots of the tour, Hoard for Unity,
and the footer. The site's links become absolute and open in a new tab, as the page is on Gumroad.

What's the Gumroad page's own, in the template:

- **Buying.** `data-gumroad-action="buy"` on the Get Hoard buttons, `data-gumroad-field="price"` and `"name"`
  filled in by Gumroad, and a box to name a price, posted to checkout as a `gumroad:checkout` message.
- **The waitlist.** A `data-gumroad-waitlist` form, for a product not yet out with its waitlist on; hidden once it is
  (`html[data-gumroad-launched]`).
- **What is Hoard?** The product's first cover, served by Gumroad, in place of the site's video, linking to it.
- **The script.** site.js's store tabs, lightbox, toast and things to find; not its downloads or docs search.

## What Gumroad allows

A page is served from one file, sandboxed, and shows pictures only from Gumroad's own CDN. So the screenshots, at full
size (`site/img`'s 1600-wide copies), are uploaded to the account's public media library (`gumroad media`), and the page
uses their addresses there. Each is there twice, dark and light, shown as the visitor's system is. `--upload` sends
only the screenshots that are new or changed since `media.json` was written, 31 seconds apart (Gumroad takes 20
uploads in 10 minutes), and deletes the copies they replace. A display name with spaces, hyphens or a file's extension
is refused as spam, so each is one word (`LibraryDark`).

The build stops if a screenshot changed since it was uploaded, or if the page would break one of Gumroad's limits:
500,000 characters, or 25 pictures (it has 25: the hero's and the tour's, dark and light, and the cover).

## Building and publishing

Needs the [Gumroad CLI](https://github.com/antiwork/gumroad-cli), signed in (`gumroad auth login`).

```
python3 scripts/build_gumroad_page.py --upload
gumroad products page preview knkwuq gumroad/landing.html --json --no-input --non-interactive
gumroad products page publish knkwuq gumroad/landing.html --json --no-input --non-interactive
```

The preview runs Gumroad's sanitizer without publishing anything: its `sanitization_report` should list nothing
removed, and it has no `warning`. Then load the page and choose Get Hoard to check it reaches checkout.
