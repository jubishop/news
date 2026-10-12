"""The "More from <reporter>" list that ends each public article page."""

from html.parser import HTMLParser
import unittest

from support import ServerFixture


class MoreFrom(HTMLParser):
    """The heading, story links, dates, and feed link of the section, if present."""

    def __init__(self, html):
        super().__init__()
        self.found = False
        self.depth = 0
        self.heading = ""
        self.in_heading = False
        self.stories = []
        self.see_all = None
        self.link = None
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if not self.depth:
            if tag == "section" and "more-from" in (attrs.get("class") or "").split():
                self.found = True
                self.depth = 1
            return
        if tag == "section":
            self.depth += 1
        elif tag == "h2":
            self.in_heading = True
        elif tag == "a":
            self.link = {"href": attrs["href"], "text": ""}
        elif tag == "time" and self.stories:
            self.stories[-1]["date"] = attrs["datetime"]

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "section":
            self.depth -= 1
        elif tag == "h2":
            self.in_heading = False
        elif tag == "a" and self.link:
            link, self.link = self.link, None
            link["text"] = " ".join(link["text"].split())
            if link["href"].startswith("/articles/"):
                self.stories.append({"id": link["href"].rsplit("/", 1)[-1], "title": link["text"]})
            else:
                self.see_all = link

    def handle_data(self, data):
        if self.in_heading:
            self.heading += data
        if self.link is not None:
            self.link["text"] += data


class MoreFromReporterTests(ServerFixture):
    def publish(self, run, *articles):
        response = self.result(
            run, self.envelope(self.claim(run), articles=list(articles))
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.json["article_ids"]

    def more_from(self, article):
        response = self.client.get("/articles/" + article)
        self.assertEqual(response.status_code, 200)
        return MoreFrom(response.get_data(as_text=True))

    def test_lists_three_other_readable_stories_in_feed_order(self):
        reporter, run = self.due()
        # Article dates run opposite to publication, so only feed order passes.
        dates = {26: "2026-09-30", 27: "2026-09-29", 28: "2026-09-28", 29: "2026-09-27", 30: "2026-09-26"}
        ids = self.publish(run, self.article(title="Story 26", article_date=dates[26]))
        for day in (27, 28, 29, 30):
            self.at(f"2026-09-{day}T12:00:00-07:00")
            run = next(job["id"] for job in self.work() if job["reporter_id"] == reporter)
            ids += self.publish(run, self.article(title=f"Story {day}", article_date=dates[day]))
        story = dict(zip((26, 27, 28, 29, 30), ids))
        self.assertEqual(self.form(f"/newsroom/articles/{story[29]}/delete").status_code, 303)
        response = self.form(
            "/newsroom/reporters", name="Other desk", prompt="Report.", cadence="daily"
        )
        other = response.headers["Location"].rsplit("/", 1)[-1]
        self.at("2026-10-01T12:00:00-07:00")
        run = next(job["id"] for job in self.work() if job["reporter_id"] == other)
        self.publish(run, self.article(title="Another reporter's story"))

        def expected(*days):
            return [{"id": story[day], "title": f"Story {day}", "date": dates[day]} for day in days]

        newest = self.more_from(story[30])
        self.assertTrue(newest.found)
        self.assertEqual(newest.heading.strip(), "More from Science desk")
        self.assertEqual(newest.stories, expected(28, 27, 26))
        self.assertEqual(
            newest.see_all,
            {"href": f"/?reporter_id={reporter}", "text": "See all from Science desk →"},
        )
        self.assertEqual(self.more_from(story[27]).stories, expected(30, 28, 26))
        self.assertEqual(self.more_from(story[26]).stories, expected(30, 28, 27))
        html = self.client.get("/articles/" + story[30]).get_data(as_text=True)
        self.assertIn(f'<time datetime="{dates[28]}">Mon, Sep 28</time>', html)
        self.assertNotIn("Another reporter", html)

        # A removed reporter's articles stay public, in the feed and in this list.
        self.assertEqual(self.form(f"/newsroom/reporters/{reporter}/delete").status_code, 303)
        self.assertEqual(self.more_from(story[30]).stories, expected(28, 27, 26))
        feed = self.client.get(f"/?reporter_id={reporter}").get_data(as_text=True)
        for day in (30, 28, 27, 26):
            self.assertIn(f"/articles/{story[day]}", feed)

    def test_ties_follow_the_feed_order(self):
        reporter, run = self.due()
        ids = self.publish(run, *(self.article(title=f"Same moment {n}") for n in range(5)))
        feed = [
            article["id"]
            for article in self.client.get(
                f"/api/v1/worker/articles/search?reporter_id={reporter}", headers=self.worker
            ).json["articles"]
        ]
        self.assertEqual(sorted(feed), sorted(ids))
        for article in ids:
            with self.subTest(article=article):
                listed = [story["id"] for story in self.more_from(article).stories]
                self.assertEqual(listed, [other for other in feed if other != article][:3])

    def test_section_is_omitted_without_other_readable_stories(self):
        reporter, run = self.due()
        only = self.publish(run, self.article(title="The only story"))[0]
        self.assertFalse(self.more_from(only).found)
        self.at("2026-09-27T12:00:00-07:00")
        run = next(job["id"] for job in self.work() if job["reporter_id"] == reporter)
        kept, trashed = self.publish(
            run, self.article(title="Kept story"), self.article(title="Trashed story")
        )
        self.assertEqual(
            {story["id"] for story in self.more_from(kept).stories}, {only, trashed}
        )
        self.assertEqual(self.form(f"/newsroom/articles/{only}/delete").status_code, 303)
        self.assertEqual(self.form(f"/newsroom/articles/{trashed}/delete").status_code, 303)
        html = self.client.get("/articles/" + kept).get_data(as_text=True)
        self.assertFalse(MoreFrom(html).found)
        self.assertNotIn("More from", html)
        self.assertNotIn("See all from", html)


if __name__ == "__main__":
    unittest.main()
