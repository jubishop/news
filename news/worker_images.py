"""Reader-side image checks: published photos must load from their external hosts."""

import http.client
import re
from urllib import error, request

from markdown_it.common.normalize_url import normalizeLink

TIMEOUT = 10
# Rate limits, outages, and timeouts do not show that an image is gone; keep it,
# and let the page remove it if it still fails for a reader.
INCONCLUSIVE = (408, 425, 429, 500, 502, 503, 504)
# Readers' browsers fetch photos directly, without a referrer; check the same way.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/26.0 Safari/605.1.15",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}
# Inline Markdown images; destinations may be <bracketed> or contain balanced parentheses.
IMAGE = re.compile(r"""!\[(?:[^\]\\]|\\.)*\]\(\s*(<[^<>\n]*>|(?:[^\s()]|\([^\s()]*\))+)"""
                   r"""(?:\s+(?:"[^"\n]*"|'[^'\n]*'|\([^()\n]*\)))?\s*\)""")


def image_bytes(head):
    return (head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a"))
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP") or head[4:8] == b"ftyp")


def loads(url, checked):
    if url not in checked:
        try:
            req = request.Request(normalizeLink(url), headers=HEADERS)
            with request.urlopen(req, timeout=TIMEOUT) as response:
                head = response.read(16)
                checked[url] = 200 <= response.status < 300 and (
                    response.headers.get_content_type().startswith("image/") or image_bytes(head))
        except error.HTTPError as exc:
            exc.close()
            checked[url] = exc.code in INCONCLUSIVE
        except (OSError, ValueError, http.client.HTTPException) as exc:
            checked[url] = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
    return checked[url]


def remove_broken(result):
    """Drop lead and inline images that would not load; return each URL's outcome."""
    checked = {}
    for article in result["articles"]:
        if "lead_image" in article and not loads(article["lead_image"]["url"], checked):
            del article["lead_image"]

        def keep(match):
            destination = match.group(1).removeprefix("<").removesuffix(">")
            return match.group(0) if loads(destination, checked) else ""

        body = IMAGE.sub(keep, article["body_markdown"])
        if body.strip():
            article["body_markdown"] = body
    return checked
