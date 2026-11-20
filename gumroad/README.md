# Hoard's Gumroad page

The page at [soloflighter.gumroad.com/l/hoardvrc](https://soloflighter.gumroad.com/l/hoardvrc): the website's front
page, as one file Gumroad can serve, with Gumroad's buy buttons where the site has its downloads.

| | |
|---|---|
| `landing.src.html` | The template: the page's own parts (its bar, the hero, What is Hoard?, Get Hoard, Safe by design), and where the site's go |
| `landing.html` | The page, built: what's published to Gumroad. Don't edit it; edit the template or the site, and build again |
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

A page is served whole from one file, sandboxed: nothing it links to loads, apart from the product's own covers. So
the screenshots go in as data addresses, made smaller (`HERO` and `TOUR` in the script), each twice for dark and light
(a data address can't go in a `srcset`, as its comma splits it). The script stops if the page would break one of
Gumroad's limits: 500,000 characters, 25 pictures, or a data address in a `srcset`.

## Building and publishing

Needs Python with Pillow (`promo/requirements.txt`), and the
[Gumroad CLI](https://github.com/antiwork/gumroad-cli), signed in (`gumroad auth login`).

```
python3 scripts/build_gumroad_page.py
gumroad products page preview knkwuq gumroad/landing.html --json --no-input --non-interactive
gumroad products page publish knkwuq gumroad/landing.html --json --no-input --non-interactive
```

The preview runs Gumroad's sanitizer without publishing anything: its `sanitization_report` should list nothing
removed, and it has no `warning`. Then load the page and choose Get Hoard to check it reaches checkout.
