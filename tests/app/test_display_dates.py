"""Human-readable Pacific dates in pages and the schedule preview."""

from datetime import date, datetime
from html.parser import HTMLParser
import re
import unittest
from unittest.mock import patch

from news import clock
from support import ServerFixture

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class VisibleText(HTMLParser):
    """Text nodes only; attributes, including input values, are excluded."""

    def __init__(self, html):
        super().__init__()
        self.parts = []
        self.feed(html)

    def handle_data(self, data):
        self.parts.append(data)


class DateFormats(unittest.TestCase):
    def setUp(self):
        self.clock = self.enterContext(patch("time.time"))
        self.at("2026-10-12T12:00:00-07:00")

    def at(self, value):
        self.clock.return_value = datetime.fromisoformat(value).timestamp()

    def test_every_format_in_the_current_and_another_pacific_year(self):
        cases = (
            (clock.short_date, ("2026-10-11",), "Sun, Oct 11"),
            (clock.short_date, ("2025-10-11",), "Sat, Oct 11, 2025"),
            (clock.long_date, ("2026-10-11",), "Sunday, Oct 11"),
            (clock.long_date, ("2025-10-11",), "Saturday, Oct 11, 2025"),
            (clock.date_range, ("2026-10-05", "2026-10-11"), "Oct 5–11"),
            (clock.date_range, ("2025-10-05", "2025-10-11"), "Oct 5–11, 2025"),
            (clock.date_range, ("2026-09-28", "2026-10-04"), "Sep 28 – Oct 4"),
            (clock.date_range, ("2025-09-28", "2025-10-04"), "Sep 28 – Oct 4, 2025"),
            (clock.date_range, ("2025-12-29", "2026-01-04"), "Dec 29, 2025 – Jan 4, 2026"),
            (clock.date_range, ("2024-12-30", "2025-01-05"), "Dec 30, 2024 – Jan 5, 2025"),
            (clock.date_range, ("2026-10-11", "2026-10-11"), "Sun, Oct 11"),
            (clock.date_range, ("2025-10-11", "2025-10-11"), "Sat, Oct 11, 2025"),
        )
        for format, values, expected in cases:
            with self.subTest(format=format.__name__, values=values):
                self.assertEqual(format(*values), expected)
                self.assertEqual(format(*map(date.fromisoformat, values)), expected)

    def test_missing_single_date_reads_as_a_dash(self):
        self.assertEqual(clock.short_date(None), "—")
        self.assertEqual(clock.long_date(None), "—")

    def test_current_year_changes_at_pacific_midnight_not_utc(self):
        self.at("2026-12-31T23:59:59-08:00")  # Already 2027 in UTC.
        self.assertEqual(clock.short_date("2026-12-31"), "Thu, Dec 31")
        self.assertEqual(clock.short_date("2027-01-01"), "Fri, Jan 1, 2027")
        self.assertEqual(clock.long_date("2026-12-31"), "Thursday, Dec 31")
        self.assertEqual(clock.date_range("2026-12-21", "2026-12-27"), "Dec 21–27")
        self.at("2027-01-01T00:00:00-08:00")
        self.assertEqual(clock.short_date("2026-12-31"), "Thu, Dec 31, 2026")
        self.assertEqual(clock.short_date("2027-01-01"), "Fri, Jan 1")
        self.assertEqual(clock.long_date("2026-12-31"), "Thursday, Dec 31, 2026")
        self.assertEqual(clock.date_range("2026-12-21", "2026-12-27"), "Dec 21–27, 2026")


class ReadableDatePages(ServerFixture):
    def page(self, path):
        response = self.client.get(path, headers=self.owner)
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for text in VisibleText(html).parts:
            self.assertNotRegex(text, ISO_DATE)
        return html

    def test_feed_and_articles_show_short_dates_and_coverage_ranges(self):
        reporter, run = self.due()
        coverage = {
            "Within one month": ("2026-09-01", "2026-09-30"),
            "Across two months": ("2026-09-28", "2026-10-04"),
            "Across two years": ("2025-12-29", "2026-01-04"),
            "One covered day": ("2026-09-26", "2026-09-26"),
        }
        response = self.result(run, self.envelope(self.claim(run), articles=[
            self.article(title=title, coverage_start=start, coverage_end=end)
            for title, (start, end) in coverage.items()
        ]))
        self.assertEqual(response.status_code, 200)
        articles = dict(zip(coverage, response.json["article_ids"]))
        published = '<time datetime="2026-09-26">Sat, Sep 26</time>'
        self.assertIn(published, self.page("/"))
        expected = {
            "Within one month": '<time datetime="2026-09-01">Sep 1</time>–<time datetime="2026-09-30">30</time>',
            "Across two months": '<time datetime="2026-09-28">Sep 28</time> – <time datetime="2026-10-04">Oct 4</time>',
            "Across two years": '<time datetime="2025-12-29">Dec 29, 2025</time> – <time datetime="2026-01-04">Jan 4, 2026</time>',
            "One covered day": '<time datetime="2026-09-26">Sat, Sep 26</time>',
        }
        for title, markup in expected.items():
            with self.subTest(title=title):
                html = self.page("/articles/" + articles[title])
                self.assertIn(f'<span class="meta-divider">/</span> {published}', html)
                self.assertIn(f"<span>Covers {markup}</span>", html)
                self.assertNotIn("Coverage", html)
        self.at("2027-01-05T12:00:00-08:00")
        self.assertIn('<time datetime="2026-09-26">Sat, Sep 26, 2026</time>', self.page("/"))
        self.assertIn(
            '<time datetime="2026-09-01">Sep 1</time>–<time datetime="2026-09-30">30, 2026</time>',
            self.page("/articles/" + articles["Within one month"]),
        )

    def test_newsroom_and_reporter_history_show_short_dates(self):
        single = self.reporter("once", dates=["2026-10-14"])
        catch_up = self.reporter("once", dates=["2026-09-26", "2026-09-28", "2026-10-03"])
        self.at("2026-09-28T06:00:00-07:00")
        run = next(run for run in self.work() if run["reporter_id"] == catch_up)
        self.assertEqual(run["assignment_dates"], ["2026-09-26", "2026-09-28"])
        response = self.result(run["id"], self.envelope(self.claim(run["id"])))
        self.assertEqual(response.status_code, 200)

        newsroom = self.page("/newsroom")
        oct_14 = '<time datetime="2026-10-14">Wed, Oct 14</time>'
        self.assertRegex(newsroom, rf"<dt>Schedule</dt>\s*<dd>\s*Contractor · {oct_14}\s*</dd>")
        self.assertRegex(newsroom, rf"<dt>Next due</dt>\s*<dd>\s*{oct_14}\s*</dd>")
        self.assertRegex(newsroom, r'<dt>Next due</dt>\s*<dd>\s*<time datetime="2026-10-03">Sat, Oct 3</time>\s*</dd>')
        self.assertIn("Contractor · 3 dates", newsroom)

        sep_26 = '<time datetime="2026-09-26">Sat, Sep 26</time>'
        sep_28 = '<time datetime="2026-09-28">Mon, Sep 28</time>'
        html = self.page("/newsroom/reporters/" + catch_up)
        self.assertIn(f'<li>{sep_26}<input type="hidden" name="dates" value="2026-09-26"></li>', html)
        self.assertIn(f'<li>{sep_28}<input type="hidden" name="dates" value="2026-09-28"></li>', html)
        self.assertIn(f"<summary><span>{sep_28}</span>", html)
        self.assertIn(f"<p>Assignment dates: {sep_26}; {sep_28}</p>", html)
        self.assertIn(f'<p class="muted">{sep_26}</p>', html)
        self.page("/newsroom/trash")

        self.at("2027-01-05T12:00:00-08:00")
        html = self.page("/newsroom/reporters/" + catch_up)
        self.assertIn('<time datetime="2026-09-28">Mon, Sep 28, 2026</time>', html)

    def test_schedule_preview_adds_a_label_and_keeps_the_iso_date(self):
        response = self.form("/newsroom/schedule-preview", cadence="daily")
        self.assertEqual(response.json["next_date"], "2026-09-26")
        self.assertEqual(response.json["next_date_label"], "Sat, Sep 26")
        contractor = self.reporter("once", dates=["2026-09-26"])
        self.at("2026-12-31T12:00:00-08:00")
        response = self.form("/newsroom/schedule-preview", cadence="daily")
        self.assertEqual(response.json["next_date"], "2027-01-01")
        self.assertEqual(response.json["next_date_label"], "Fri, Jan 1, 2027")
        response = self.form(
            "/newsroom/schedule-preview", cadence="once",
            dates=["2026-09-26"], reporter_id=contractor,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json["next_date"])
        self.assertIsNone(response.json["next_date_label"])


if __name__ == "__main__":
    unittest.main()
