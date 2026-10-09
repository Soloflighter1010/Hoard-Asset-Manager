"""The app's themes (Settings, Appearance): each a set of the pages' colours, dark and light, and the mode that picks
between them (Match my computer, Light, Dark). The pages are built on these colours by name (--cave, --gold and so
on), so a theme is just their values; the server puts the chosen one into each page as it serves it (no flash of
another theme first), and Settings swaps it in place.

Every theme keeps to the same promises as the default (tests/test_themes.py checks them): text 4.5:1 or more on its
backgrounds, the accent as text 4.5:1, text on the accent 4.5:1, and each store's colour 3:1 on the background and
far enough from the accent not to be taken for it. Standard library only.
"""
from __future__ import annotations

MODES = ("system", "light", "dark")
DEFAULT = "hoard"

# What each colour is for: cave (the page), ledge (panels, tiles' ground), stone (hover), seam (lines), bone (text),
# dust (quieter text), gold (the accent: "yours" or "do this"), gold-ink (text on the accent), gold-text (the accent as
# text), warn (problems), then each store's colour, and the stand-in pictures' lightness and saturation.
KEYS = ("cave", "ledge", "stone", "seam", "bone", "dust", "gold", "gold-ink", "gold-text", "warn",
        "booth", "gumroad", "jinxxy", "payhip", "itch", "local", "ph-l", "ph-s")
STORES = ("booth", "gumroad", "jinxxy", "payhip", "itch", "local")

_STORES_DARK = {"booth": "#FF6259", "gumroad": "#FF8AD8", "jinxxy": "#56D1DC", "payhip": "#95A0FF", "itch": "#7ED67A", "local": "#E8C26A"}
_STORES_LIGHT = {"booth": "#D8332B", "gumroad": "#C8339A", "jinxxy": "#07808B", "payhip": "#5360D6", "itch": "#2B7F35", "local": "#8A6410"}
_BASE_DARK = {"warn": "#FF9F6B", "ph-l": "30%", "ph-s": "28%", **_STORES_DARK}
_BASE_LIGHT = {"warn": "#A34818", "ph-l": "82%", "ph-s": "30%", **_STORES_LIGHT}


def _mode(cave, ledge, stone, seam, bone, dust, gold, ink, gold_text, base, **more) -> dict:
    return {**base, "cave": cave, "ledge": ledge, "stone": stone, "seam": seam, "bone": bone, "dust": dust,
            "gold": gold, "gold-ink": ink, "gold-text": gold_text, **more}


def _theme(name, tag, mood, dark, light, dark_more=None, light_more=None) -> dict:
    return {"name": name, "tag": tag, "mood": mood,
            "dark": _mode(*dark, _BASE_DARK, **(dark_more or {})), "light": _mode(*light, _BASE_LIGHT, **(light_more or {}))}


THEMES = {
    "hoard": _theme("Hoard", "", "The cave and its gold.",
                    ("#211C18", "#2B2520", "#372F28", "#4A4037", "#F4EDE3", "#B3A695", "#F0B429", "#2A1D00", "#F0B429"),
                    ("#EEECE8", "#FFFFFF", "#E3DFD8", "#D2CCC3", "#211C18", "#6B6157", "#B07A00", "#1F1500", "#7A5100")),
    "dragonfire": _theme("Dragonfire", "", "Embers and molten metal.",
                         ("#1A1210", "#261A16", "#33231D", "#4D342A", "#F7E9E1", "#C2A497", "#FF7A3D", "#2B0E00", "#FF8A52"),
                         ("#F3ECE8", "#FFFFFF", "#E8DDD7", "#D8C8BF", "#23140F", "#735D53", "#C2410C", "#FFFFFF", "#9A3412"),
                         {"booth": "#FF4F7E"}, {"booth": "#C81E4A"}),
    "frost": _theme("Frost Cave", "", "Ice and cold blue light.",
                    ("#11171F", "#19222D", "#222E3B", "#34475A", "#EAF2F8", "#9DB0C2", "#8AD4FF", "#05263A", "#8AD4FF"),
                    ("#EDF2F6", "#FFFFFF", "#DFE7EE", "#C9D5E0", "#13202C", "#566878", "#0B6FA4", "#FFFFFF", "#08557F"),
                    {"jinxxy": "#46E0C2"}, {"jinxxy": "#08806E"}),
    "geode": _theme("Geode", "", "Amethyst crystals.",
                    ("#16121E", "#211A2B", "#2C2338", "#433653", "#F1EBF8", "#B0A3C2", "#B98CFF", "#1E0A3D", "#C3A0FF"),
                    ("#F1EDF6", "#FFFFFF", "#E5DEEE", "#D3C9E0", "#1E1628", "#665A75", "#6D3FC4", "#FFFFFF", "#5B2FB0"),
                    {"payhip": "#7FA8FF"}, {"payhip": "#1F6BC9"}),
    "moss": _theme("Mossy Ruins", "", "An overgrown temple: green stone and jade.",
                   ("#121814", "#1A231D", "#233027", "#37483B", "#ECF2EC", "#A3B3A5", "#4ADE9A", "#052814", "#5FE3A5"),
                   ("#ECF1EB", "#FFFFFF", "#DDE6DC", "#C6D3C5", "#142018", "#56665A", "#1F7A4D", "#FFFFFF", "#186640"),
                   {"itch": "#C9E05A"}, {"itch": "#6B7F00"}),
    "synthwave": _theme("Synthwave", "", "A club at night: deep indigo and neon pink.",
                        ("#110E1D", "#1B1730", "#262043", "#3C3363", "#F3EEFF", "#A99FCC", "#FF4FD8", "#2B0026", "#FF6FE0"),
                        ("#F5F1FA", "#FFFFFF", "#E9E2F3", "#D6CBE8", "#1A1430", "#625880", "#B0158F", "#FFFFFF", "#960D79"),
                        {"gumroad": "#FF8F70"}, {"gumroad": "#C2512E"}),
    "sakura": _theme("Sakura", "", "Cherry blossom.",
                     ("#1D1418", "#291C22", "#35252C", "#4E3741", "#F9EDF1", "#C3A5B0", "#FF8FB5", "#3A0718", "#FF9FC0"),
                     ("#FAF0F3", "#FFFFFF", "#F0E1E7", "#E2CCD5", "#2A1820", "#7A5A66", "#B4245A", "#FFFFFF", "#9C1D4C"),
                     {"gumroad": "#D98BFF"}, {"gumroad": "#9B2FC2"}),
    "midnight": _theme("Midnight & Paper", "OLED", "True black (it saves battery on OLED screens), and white paper by day.",
                       ("#000000", "#0D0D0D", "#1A1A1A", "#2E2E2E", "#F2F2F2", "#A0A0A0", "#F0B429", "#1F1500", "#F0B429"),
                       ("#FFFFFF", "#FFFFFF", "#F2F2F2", "#DADADA", "#111111", "#5E5E5E", "#8A5A00", "#FFFFFF", "#7A4F00"),
                       {"ph-l": "24%"}),
    "contrast": _theme("High contrast", "Accessibility", "As much contrast as there can be, with lines around everything.",
                       ("#000000", "#000000", "#1F1F1F", "#FFFFFF", "#FFFFFF", "#E0E0E0", "#FFD000", "#000000", "#FFD000"),
                       ("#FFFFFF", "#FFFFFF", "#EAEAEA", "#000000", "#000000", "#2B2B2B", "#7A4F00", "#FFFFFF", "#6B4400"),
                       {"booth": "#FF7A70", "gumroad": "#FF9EE0", "jinxxy": "#6FE6F0", "payhip": "#AEB6FF", "itch": "#94EC90",
                        "local": "#FFFFFF", "warn": "#FFB38A"},
                       {"booth": "#B01E17", "gumroad": "#A11F7A", "jinxxy": "#006670", "payhip": "#3A46B8", "itch": "#1E6428",
                        "local": "#000000", "warn": "#9A3F0C"}),
    "spooky": _theme("Spooky Hoard", "Seasonal", "Pumpkin orange on a dusk purple.",
                     ("#140F1C", "#1F1729", "#2A2037", "#43345A", "#F5EEDF", "#B5A8C4", "#FF8A1F", "#2B1300", "#FF9A3C"),
                     ("#F4EFE6", "#FFFDF8", "#E9E1D2", "#D6CAB4", "#241A2E", "#6B5E75", "#B5520A", "#FFFFFF", "#9A4508"),
                     {"booth": "#FF4F7A"}, {"booth": "#C41E50"}),
}

# Store colours easier to tell apart with colour blindness (Okabe and Ito's palette), as Settings offers them: the
# same in every theme, for the mode shown.
COLOURBLIND = {"dark": {"booth": "#E69F00", "gumroad": "#CC79A7", "jinxxy": "#56B4E9", "payhip": "#F0E442", "itch": "#2BB58C", "local": "#D8D8D8"},
               "light": {"booth": "#A86A00", "gumroad": "#A84D86", "jinxxy": "#1F72AE", "payhip": "#7D7300", "itch": "#00775A", "local": "#5E5E5E"}}


def theme_id(value) -> str:
    return value if isinstance(value, str) and value in THEMES else DEFAULT


def mode_id(value) -> str:
    return value if isinstance(value, str) and value in MODES else "system"


def _block(selector: str, values: dict, scheme: str | None = None) -> str:
    body = "; ".join(f"--{k}: {v}" for k, v in values.items())
    return f"{selector} {{ {body}{'; color-scheme: ' + scheme if scheme else ''}; }}"


def _mode_css(t: dict, mode: str) -> list[str]:
    return [_block(":root", {k: t[mode][k] for k in KEYS}, mode),
            _block(':root[data-colours="colourblind"]', COLOURBLIND[mode])]


def css(theme: str, mode: str) -> str:
    """The chosen theme's colours for a page, after its own (which are Hoard's, following the computer): the same
    selectors, so these win by coming later. Match my computer keeps both modes; Light or Dark only the one."""
    t, mode = THEMES[theme_id(theme)], mode_id(mode)
    if mode != "system":
        return "\n".join(_mode_css(t, mode))
    return "\n".join(_mode_css(t, "dark") + ["@media (prefers-color-scheme: light) {"] + _mode_css(t, "light") + ["}"])


def choices() -> list[dict]:
    """The themes as Settings lists them: name, a word about it, and a swatch of each mode (page, panel, accent)."""
    return [{"id": k, "name": t["name"], "tag": t["tag"], "mood": t["mood"],
             "dark": [t["dark"]["cave"], t["dark"]["ledge"], t["dark"]["gold"]],
             "light": [t["light"]["cave"], t["light"]["ledge"], t["light"]["gold"]]} for k, t in THEMES.items()]
