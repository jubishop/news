"""The light and dark color tokens in news.css, read the way the tests need them."""

from pathlib import Path
import re

STYLESHEET = Path(__file__).resolve().parents[2] / "news" / "static" / "news.css"
COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
DARK = re.compile(
    r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{\s*:root\s*\{([^{}]*)\}\s*\}"
)
ROOT = re.compile(r":root\s*\{([^{}]*)\}")
TOKEN = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
HEX = re.compile(r"#(?:[0-9a-f]{3}|[0-9a-f]{6})", re.IGNORECASE)


def read():
    """Return the token blocks and the CSS outside them.

    The light tokens are the top-level :root block; the dark tokens are the
    :root block inside the prefers-color-scheme: dark media query. Each scheme
    maps to a list of blocks, so callers can check that there is one of each.
    """
    css = COMMENT.sub("", STYLESHEET.read_text())
    dark = DARK.findall(css)
    rest = DARK.sub("", css)
    light = ROOT.findall(rest)
    blocks = {
        scheme: [dict((name, value.strip()) for name, value in TOKEN.findall(block)) for block in found]
        for scheme, found in (("light", light), ("dark", dark))
    }
    return blocks, ROOT.sub("", rest)


def schemes():
    """{"light": tokens, "dark": tokens}, failing unless each scheme has one block."""
    blocks, _ = read()
    counts = {scheme: len(found) for scheme, found in blocks.items()}
    if counts != {"light": 1, "dark": 1}:
        raise AssertionError(f"news.css needs one :root token block per scheme; found {counts}")
    return {scheme: found[0] for scheme, found in blocks.items()}


def colors(tokens):
    """The tokens whose values are hex colors, as (red, green, blue) tuples."""
    result = {}
    for name, value in tokens.items():
        if HEX.fullmatch(value):
            digits = value[1:] if len(value) == 7 else "".join(c * 2 for c in value[1:])
            result[name] = tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    return result


def css_rgb(color):
    """A color tuple as getComputedStyle() reports it."""
    return "rgb({}, {}, {})".format(*color)
