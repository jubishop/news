"""Site icons and link preview tags, which only public reading pages carry."""

from html.parser import HTMLParser
import struct
import unittest

from support import ServerFixture

SITE_DESCRIPTION = "The world, on your beat. An independent, personal edition."
PHOTO = {
    "url": "https://images.example.com/lab.jpg?w=1200&h=800",
    "alt": 'Researchers at the "Fish & Chips" <bench>',
    "credit": "Lab Photographer",
    "credit_url": "https://example.com/gallery",
}


class Head(HTMLParser):
    """The <meta> and <link> tags in a page's <head>, as a browser reads them."""

    def __init__(self, html):
        super().__init__()
        self.inside = False
        self.previews = {}
        self.raw_previews = []
        self.links = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "head":
            self.inside = True
        elif self.inside and tag == "link":
            self.links.append(attrs)
        elif self.inside and tag == "meta":
            key = attrs.get("property") or attrs.get("name") or ""
            if key == "description" or key.startswith(("og:", "twitter:")):
                if key in self.previews:
                    raise AssertionError("Duplicate preview tag: " + key)
                self.previews[key] = attrs.get("content")
                self.raw_previews.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if tag == "head":
            self.inside = False


def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise AssertionError("Not PNG data")
    return struct.unpack(">II", data[16:24])


class SiteMetadataTests(ServerFixture):
    def head(self, path, headers=None, status=200):
        response = self.client.get(path, headers=headers or {})
        self.assertEqual(response.status_code, status, path)
        return Head(response.get_data(as_text=True))

    def publish(self, *articles):
        reporter, run = self.due()
        response = self.result(
            run, self.envelope(self.claim(run), articles=list(articles))
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return reporter, response.json["article_ids"]

    def test_icons_are_public_and_linked_from_every_page(self):
        for path, mimetype, size in [
            ("/favicon.ico", "image/png", (32, 32)),
            ("/apple-touch-icon.png", "image/png", (180, 180)),
            ("/static/icon.svg", "image/svg+xml", None),
        ]:
            with self.subTest(path=path), self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, mimetype)
                if size:
                    self.assertEqual(png_size(response.data), size)
                else:
                    self.assertIn(b'<svg xmlns="http://www.w3.org/2000/svg"', response.data)
        for path, headers, status in [
            ("/", None, 200),
            ("/newsroom", self.owner, 200),
            ("/articles/missing", None, 404),
        ]:
            with self.subTest(page=path):
                links = self.head(path, headers, status).links
                self.assertIn(
                    {"rel": "icon", "href": "/favicon.ico", "sizes": "32x32"}, links
                )
                self.assertIn(
                    {"rel": "icon", "href": "/static/icon.svg", "type": "image/svg+xml"},
                    links,
                )
                self.assertIn(
                    {"rel": "apple-touch-icon", "href": "/apple-touch-icon.png"}, links
                )

    def test_article_previews_carry_escaped_story_text_and_lead_photo(self):
        # "&amp;" would decode to "&" if the page did not escape it.
        title = 'R&amp;D: the "lab" <notes> & more'
        summary = 'Findings in <b>bold</b> & "quotes" from R&amp;D.'
        _, (photographed, plain) = self.publish(
            self.article(title=title, summary=summary, lead_image=PHOTO),
            self.article(title="Text-only study", summary="No photo here."),
        )
        page = self.head("/articles/" + photographed)
        self.assertEqual(
            page.previews,
            {
                "description": summary,
                "og:description": summary,
                "og:type": "article",
                "og:title": title,
                "og:url": "https://news.example.com/articles/" + photographed,
                "og:site_name": "News",
                "twitter:card": "summary_large_image",
                "og:image": PHOTO["url"],
                "og:image:alt": PHOTO["alt"],
            },
        )
        for raw in page.raw_previews:
            self.assertNotIn("<", raw[1:])
        self.assertEqual(
            self.head("/articles/" + plain).previews,
            {
                "description": "No photo here.",
                "og:description": "No photo here.",
                "og:type": "article",
                "og:title": "Text-only study",
                "og:url": "https://news.example.com/articles/" + plain,
                "og:site_name": "News",
                "twitter:card": "summary",
            },
        )

    def test_every_feed_variant_shares_the_site_preview(self):
        reporter, _ = self.publish(
            self.article(title='A "filtered" story', lead_image=PHOTO)
        )
        site = {
            "description": SITE_DESCRIPTION,
            "og:description": SITE_DESCRIPTION,
            "og:type": "website",
            "og:title": "News",
            "og:url": "https://news.example.com/",
            "og:site_name": "News",
            "twitter:card": "summary",
        }
        for path in [
            "/",
            "/?reporter_id=" + reporter,
            "/?q=filtered&reporter_id=" + reporter,
            "/?q=no+such+story",
            "/?page=2",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.head(path).previews, site)

    def test_newsroom_and_error_pages_have_no_preview_tags(self):
        reporter, (trashed,) = self.publish(self.article(lead_image=PHOTO))
        response = self.form(f"/newsroom/articles/{trashed}/delete")
        self.assertEqual(response.status_code, 303)
        for path, headers, status in [
            ("/newsroom", self.owner, 200),
            ("/newsroom?view=archive", self.owner, 200),
            ("/newsroom/reporters/new", self.owner, 200),
            ("/newsroom/reporters/" + reporter, self.owner, 200),
            ("/newsroom/trash", self.owner, 200),
            ("/newsroom", None, 401),
            ("/articles/" + trashed, None, 404),
            ("/?page=0", None, 422),
            ("/no-such-page", None, 404),
        ]:
            with self.subTest(path=path, status=status):
                self.assertEqual(self.head(path, headers, status).previews, {})


if __name__ == "__main__":
    unittest.main()
