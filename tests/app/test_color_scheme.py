"""Light and dark palettes: complete, readable, and the only colors in news.css."""

import re
import unittest

from stylesheet import colors, read, schemes

# Each text color with the background the stylesheet puts it on.
TEXT_PAIRS = [
    ("ink", "paper", "body text"),
    ("ink", "panel", "cards, form fields, and calendar days"),
    ("muted", "paper", "metadata, summaries, captions, and past calendar days"),
    ("muted", "panel", "card prompts and facts, and empty calendar days"),
    ("accent", "paper", "eyebrows, kickers, day labels, hovered links, and danger links"),
    ("accent", "panel", "card eyebrows and the calendar's Today label"),
    ("green", "paper", "article links"),
    ("green", "panel", "the empty feed's ornament"),
    ("warning-ink", "paper", "the feed's late-reporting line"),
    ("panel", "ink", "buttons"),
    ("on-green", "green", "hovered buttons"),
    ("ink", "quiet-hover", "hovered quiet buttons"),
    ("ink", "raised", "the focused skip link"),
    ("ink", "well", "code blocks"),
    ("ink", "history-well", "instructions in reporting history"),
    ("green", "badge-bg", "Active and outcome badges"),
    ("danger-ink", "danger-bg", "Late and failed badges"),
    ("muted", "subtle-bg", "Paused badges"),
    ("notice-ink", "notice-bg", "confirmation notices"),
    ("ink", "alert-bg", "newsroom alerts"),
    ("accent", "alert-bg", "hovered links in newsroom alerts"),
    ("green", "tint", "calendar entries"),
    ("ink", "tint-hover", "hovered calendar entries"),
    ("ink", "tint", "the calendar's no-reports note"),
    ("tint-ink", "tint", "the schedule preview"),
]

# Borders and rings that mark controls need 3:1 against what surrounds them
# (WCAG 1.4.11). Light field borders predate dark mode and are not covered here.
NON_TEXT_PAIRS = [
    ("field-border", "paper", ("dark",), "the feed's transparent search and reporter fields"),
    ("field-border", "panel", ("dark",), "form fields on the editor"),
    ("accent", "paper", ("light", "dark"), "focus rings"),
    ("accent", "panel", ("light", "dark"), "focus rings on cards and the calendar's Today ring"),
]
# Tokens that are not colors.
FONTS = {"serif", "sans"}

# CSS Color 4 named and system colors; transparent and currentColor are exempt.
NAMED_COLORS = set("""
aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum
powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown
seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen
steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
yellowgreen
accentcolor accentcolortext activetext buttonborder buttonface buttontext canvas
canvastext field fieldtext graytext highlight highlighttext linktext mark marktext
selecteditem selecteditemtext visitedtext
""".split())
COLOR_FUNCTIONS = {
    "rgb", "rgba", "hsl", "hsla", "hwb", "lab", "lch", "oklab", "oklch",
    "color", "color-mix", "light-dark",
}
# Custom properties, hex colors, then identifiers and function names.
VALUE_WORD = re.compile(r"--[\w-]+|#[0-9a-fA-F]+|[a-zA-Z][\w-]*\(?")
STRING = re.compile(r"\"[^\"]*\"|'[^']*'")


def is_color(word):
    """Whether a word from a declaration value is a color literal."""
    if word.endswith("("):
        return word[:-1].lower() in COLOR_FUNCTIONS
    return word.startswith("#") or word.lower() in NAMED_COLORS


def luminance(color):
    """WCAG 2 relative luminance of an sRGB color."""
    channels = []
    for value in color:
        value /= 255
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first, second):
    """WCAG 2 contrast ratio, from 1 to 21."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class ColorFormulas(unittest.TestCase):
    def test_contrast_matches_known_wcag_ratios(self):
        black, white = (0, 0, 0), (255, 255, 255)
        self.assertAlmostEqual(contrast(black, white), 21)
        self.assertAlmostEqual(contrast(white, white), 1)
        # #767676 is the lightest gray that reaches 4.5:1 on white.
        self.assertAlmostEqual(contrast((118, 118, 118), white), 4.54, places=2)
        self.assertAlmostEqual(contrast((119, 119, 119), white), 4.48, places=2)


class ColorSchemes(unittest.TestCase):
    def test_dark_scheme_redefines_every_light_color(self):
        palettes = schemes()
        light, dark = colors(palettes["light"]), colors(palettes["dark"])
        # A light color written another way would otherwise leak into dark unchecked.
        self.assertEqual(set(palettes["light"]) - FONTS, set(light), "Every light color must be hex")
        self.assertEqual(set(palettes["dark"]), set(light), "Dark tokens must match the light colors")
        self.assertEqual(set(dark), set(light), "Every dark token must be a hex color")
        for surface in ("paper", "panel"):
            self.assertLess(luminance(dark[surface]), luminance(dark["ink"]))
        _, rest = read()
        used = set(re.findall(r"var\(\s*--([\w-]+)", rest))
        self.assertEqual(used - set(palettes["light"]), set(), "Undefined tokens")

    def test_text_reaches_four_and_a_half_to_one_in_both_schemes(self):
        palettes = schemes()
        for scheme, tokens in palettes.items():
            palette = colors(tokens)
            for text, background, used_for in TEXT_PAIRS:
                with self.subTest(scheme=scheme, text=text, background=background, used_for=used_for):
                    ratio = contrast(palette[text], palette[background])
                    self.assertGreaterEqual(ratio, 4.5, f"{ratio:.2f}:1")

    def test_control_borders_and_focus_rings_reach_three_to_one(self):
        palettes = {scheme: colors(tokens) for scheme, tokens in schemes().items()}
        for border, background, applies, used_for in NON_TEXT_PAIRS:
            for scheme in applies:
                with self.subTest(scheme=scheme, border=border, background=background, used_for=used_for):
                    ratio = contrast(palettes[scheme][border], palettes[scheme][background])
                    self.assertGreaterEqual(ratio, 3, f"{ratio:.2f}:1")

    def test_colors_appear_only_in_the_token_blocks(self):
        _, rest = read()
        literals = []
        for selector, block in re.findall(r"([^{}]*)\{([^{}]*)\}", STRING.sub("''", rest)):
            for declaration in block.split(";"):
                name, _, value = declaration.partition(":")
                if any(map(is_color, VALUE_WORD.findall(value))):
                    literals.append(f"{selector.strip()} {{ {name.strip()}: {value.strip()} }}")
        self.assertEqual(literals, [])


if __name__ == "__main__":
    unittest.main()
