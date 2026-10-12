"""Front-page day sections, story kickers, and the filter bar's story count."""

from html.parser import HTMLParser
import unittest

from support import ServerFixture


class Feed(HTMLParser):
    """The front page as a reader meets it, in document order."""

    KINDS = {"h1": "heading", "h2": "day", "h3": "title"}
    CLASSES = {"story-meta": "kicker", "edition-count": "count", "status-line": "status"}

    def __init__(self, html):
        super().__init__()
        self.order, self.headings, self.days = [], [], []
        self.count = self.status = self.kicker = None
        self.capture = None
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("aria-label") == "Filter stories":
            self.order.append("filter")
        if self.capture:
            self.capture["depth"] += tag == self.capture["tag"]
            return
        classes = (attrs.get("class") or "").split()
        kind = self.KINDS.get(tag) or next(
            (kind for name, kind in self.CLASSES.items() if name in classes), None
        )
        if kind:
            self.capture = {"kind": kind, "tag": tag, "depth": 1, "text": []}

    def handle_endtag(self, tag):
        if not self.capture or tag != self.capture["tag"]:
            return
        self.capture["depth"] -= 1
        if self.capture["depth"]:
            return
        kind, text = self.capture["kind"], " ".join("".join(self.capture["text"]).split())
        self.capture = None
        if kind == "heading":
            self.headings.append(text)
        elif kind == "day":
            self.order.append("day")
            self.days.append((text, []))
        elif kind == "kicker":
            self.kicker = text
        elif kind == "title":
            self.days[-1][1].append((self.kicker, text))
        elif kind == "count":
            self.count = text
        else:
            self.order.append("status")
            self.status = text

    def handle_data(self, data):
        if self.capture:
            self.capture["text"].append(data)

    def titles(self):
        """Each day header with its story titles, sorted where publish times tie."""
        return [(day, sorted(title for _, title in stories)) for day, stories in self.days]


class FeedDays(ServerFixture):
    def desk(self, name):
        response = self.form(
            "/newsroom/reporters", name=name, prompt="Report the news.", cadence="daily"
        )
        self.assertEqual(response.status_code, 303, response.get_data(as_text=True))
        return response.headers["Location"].rsplit("/", 1)[-1]

    def publish(self, when, reporter, *titles, **fields):
        """Publish at a Pacific time; article dates default to that Pacific day."""
        self.at(when)
        run = next(run["id"] for run in self.work() if run["reporter_id"] == reporter)
        articles = [
            self.article(title=title, **{"article_date": when[:10], **fields})
            for title in titles
        ]
        response = self.result(run, self.envelope(self.claim(run), articles=articles))
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def page(self, path="/"):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return Feed(response.get_data(as_text=True))

    def test_days_follow_the_pacific_publish_date_with_today_and_yesterday(self):
        science = self.desk("Science desk")
        self.desk("Quiet desk")  # Never reports, so its runs fall late.
        self.publish("2026-10-10T20:00:00-07:00", science, "Saturday evening")  # Sunday in UTC.
        self.publish("2026-10-11T17:30:00-07:00", science, "Sunday evening")  # Monday in UTC.
        self.publish("2026-10-12T00:30:00-07:00", science, "Just after midnight")
        self.at("2026-10-12T17:30:00-07:00")  # Already Tuesday in UTC.
        feed = self.page()
        self.assertEqual(feed.days, [
            ("Today · Monday, Oct 12", [("Science desk", "Just after midnight")]),
            ("Yesterday · Sunday, Oct 11", [("Science desk", "Sunday evening")]),
            ("Saturday, Oct 10", [("Science desk", "Saturday evening")]),
        ])
        self.assertEqual(feed.order, ["filter", "day", "day", "day"])
        self.assertEqual(feed.count, "3 stories")
        # One page-level heading; the hero and the "Read the story" links are gone.
        self.assertEqual(len(feed.headings), 1)
        html = self.client.get("/").get_data(as_text=True)
        self.assertFalse("Your daily perspective" in html or "Read the story" in html)

        self.at("2026-10-13T00:30:00-07:00")
        feed = self.page()
        self.assertEqual(
            [day for day, _ in feed.days],
            ["Yesterday · Monday, Oct 12", "Sunday, Oct 11", "Saturday, Oct 10"],
        )
        # The quiet desk's Monday report is now late; the status line stays above the days.
        self.assertEqual(feed.order, ["filter", "status", "day", "day", "day"])
        self.assertIn("1 scheduled report is late", feed.status)

    def test_days_use_pacific_standard_time_in_winter(self):
        science = self.desk("Science desk")
        self.publish("2026-12-14T23:30:00-08:00", science, "Monday night")  # Tuesday in UTC.
        self.publish("2026-12-15T23:30:00-08:00", science, "Tuesday night")  # 00:30 at UTC−7.
        self.at("2026-12-16T08:00:00-08:00")
        feed = self.page()
        self.assertEqual(feed.days, [
            ("Yesterday · Tuesday, Dec 15", [("Science desk", "Tuesday night")]),
            ("Monday, Dec 14", [("Science desk", "Monday night")]),
        ])

    def test_kicker_adds_the_article_date_only_when_it_differs_from_the_publish_day(self):
        science = self.desk("Science desk")
        self.publish("2026-10-11T17:30:00-07:00", science, "Same day")  # Monday in UTC.
        self.publish("2026-10-12T09:00:00-07:00", science, "Earlier article", article_date="2026-10-10")
        feed = self.page()
        self.assertEqual(feed.days, [
            ("Today · Monday, Oct 12", [("Science desk · Sat, Oct 10", "Earlier article")]),
            ("Yesterday · Sunday, Oct 11", [("Science desk", "Same day")]),
        ])

    def test_a_page_that_starts_mid_day_repeats_that_days_header(self):
        science = self.desk("Science desk")
        self.publish("2026-10-10T09:00:00-07:00", science, "Saturday story")
        self.publish("2026-10-11T09:00:00-07:00", science, *(f"Sunday story {n}" for n in range(15)))
        self.publish("2026-10-12T09:00:00-07:00", science, *(f"Monday story {n}" for n in range(20)))
        first, second = self.page(), self.page("/?page=2")
        self.assertEqual(
            [(day, len(stories)) for day, stories in first.days],
            [("Today · Monday, Oct 12", 20), ("Yesterday · Sunday, Oct 11", 10)],
        )
        self.assertEqual(
            [(day, len(stories)) for day, stories in second.days],
            [("Yesterday · Sunday, Oct 11", 5), ("Saturday, Oct 10", 1)],
        )
        sunday = first.titles()[1][1] + second.titles()[0][1]
        self.assertEqual(sorted(sunday), sorted(f"Sunday story {n}" for n in range(15)))
        self.assertEqual([first.count, second.count], ["36 stories"] * 2)

    def test_filtered_and_search_results_use_the_same_days(self):
        science, sports = self.desk("Science desk"), self.desk("Sports desk")
        self.publish("2026-10-11T09:00:00-07:00", science, "Cell biology update", "Telescope survey")
        self.publish("2026-10-11T09:00:00-07:00", sports, "Match report")
        self.publish("2026-10-12T09:00:00-07:00", science, "Cell biology follow-up")
        self.publish("2026-10-12T09:00:00-07:00", sports, "Cell signal at the stadium")
        today, yesterday = "Today · Monday, Oct 12", "Yesterday · Sunday, Oct 11"
        for path, days, count in [
            (f"/?reporter_id={science}", [
                (today, ["Cell biology follow-up"]),
                (yesterday, ["Cell biology update", "Telescope survey"]),
            ], "3 stories"),
            ("/?q=Cell", [
                (today, ["Cell biology follow-up", "Cell signal at the stadium"]),
                (yesterday, ["Cell biology update"]),
            ], "3 stories"),
            (f"/?q=Match&reporter_id={sports}", [(yesterday, ["Match report"])], "1 story"),
        ]:
            with self.subTest(path=path):
                feed = self.page(path)
                self.assertEqual(feed.titles(), days)
                self.assertEqual(feed.count, count)


if __name__ == "__main__":
    unittest.main()
