"""Read-only newsroom calendar journeys through owner HTTP routes."""

from contextlib import closing
from datetime import date
from html.parser import HTMLParser
import sqlite3

from support import ServerFixture


class CalendarHTML(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.days = {}
        self.day = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-calendar-date" in attrs:
            self.day = attrs["data-calendar-date"]
            self.days[self.day] = []
        if tag == "a" and self.day:
            self.days[self.day].append(attrs["href"].rsplit("/", 1)[-1])

    def handle_endtag(self, tag):
        if tag == "li":
            self.day = None


class CalendarJourneys(ServerFixture):
    def calendar(self, month=None):
        response = self.client.get(
            "/newsroom" + (f"?month={month}" if month else ""), headers=self.owner
        )
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="reporting-calendar"', html)
        return CalendarHTML(html).days

    def snapshot(self):
        with closing(sqlite3.connect(self.database)) as connection:
            return list(connection.iterdump())

    def test_all_cadences_and_links_without_creating_future_runs(self):
        self.at("2026-09-30T12:00:00-07:00")
        daily = self.reporter()
        weekly = self.reporter("weekly", weekdays=["mon", "thu"])
        monthly = self.reporter("monthly", day_of_month="31")
        contractor = self.reporter("once", dates=["2026-10-01", "2026-10-03", "2026-11-02"])
        before = self.snapshot()
        days = self.calendar("2026-10")
        self.assertEqual(len(days), 31)
        for number in range(1, 32):
            day = date(2026, 10, number)
            expected = {daily}
            if day.weekday() in (0, 3):
                expected.add(weekly)
            if number == 31:
                expected.add(monthly)
            if number in (1, 3):
                expected.add(contractor)
            self.assertCountEqual(days[day.isoformat()], expected)
        self.assertIn(monthly, self.calendar("2026-11")["2026-11-30"])
        self.assertIn(monthly, self.calendar("2027-02")["2027-02-28"])
        self.assertIn(monthly, self.calendar("2028-02")["2028-02-29"])
        self.assertIn(monthly, self.calendar("2028-03")["2028-03-31"])
        for identity in (daily, weekly, monthly, contractor):
            self.assertEqual(self.client.get(
                f"/newsroom/reporters/{identity}", headers=self.owner
            ).status_code, 200)
        self.assertEqual(before, self.snapshot())

    def test_pacific_today_effective_dates_and_unchanged_today_after_edits(self):
        self.at("2026-09-29T12:00:00-07:00")
        daily = self.reporter()
        weekly = self.reporter("weekly", weekdays=["fri"])
        self.at("2026-10-01T01:00:00+00:00")  # September 30 in Pacific Time.
        new = self.reporter()
        self.assertEqual(self.calendar()["2026-09-30"], [daily])
        self.assertEqual(self.edit(daily, cadence="weekly", weekdays=["fri"]).status_code, 303)
        self.assertEqual(self.edit(weekly).status_code, 303)
        before = self.snapshot()
        self.assertEqual(self.calendar()["2026-09-30"], [daily])
        days = self.calendar("2026-10")
        self.assertCountEqual(days["2026-10-01"], [weekly, new])
        self.assertCountEqual(days["2026-10-02"], [weekly, new, daily])
        self.assertTrue(all(not entries for day, entries in self.calendar().items()
                            if day < "2026-09-30"))
        self.assertEqual(before, self.snapshot())

    def test_lifecycle_and_contractor_edits_reload_without_changing_assignments(self):
        self.at("2026-09-30T12:00:00-07:00")
        recurring = self.reporter()
        contractor = self.reporter("once", dates=["2026-10-01", "2026-10-03"])
        completed = self.reporter("once", dates=["2026-10-01"])
        self.at("2026-10-01T06:00:00-07:00")
        jobs = {run["reporter_id"]: run for run in self.work()}
        for identity in (recurring, completed):
            run = jobs[identity]["id"]
            self.assertEqual(self.result(run, self.envelope(self.claim(run))).status_code, 200)
        self.assertEqual(self.edit(contractor, cadence="once", dates=["2026-10-01", "2026-10-04"]).status_code, 303)
        days = self.calendar()
        self.assertEqual(days["2026-10-01"], [contractor])
        self.assertEqual(days["2026-10-03"], [recurring])
        self.assertCountEqual(days["2026-10-04"], [recurring, contractor])
        self.assertEqual(self.form(f"/newsroom/reporters/{recurring}/pause").status_code, 303)
        self.assertEqual(self.calendar()["2026-10-04"], [contractor])
        self.assertEqual(self.form(f"/newsroom/reporters/{recurring}/resume").status_code, 303)
        self.assertCountEqual(self.calendar()["2026-10-04"], [recurring, contractor])
        self.assertEqual(self.form(f"/newsroom/reporters/{contractor}/delete").status_code, 303)
        before = self.snapshot()
        self.assertEqual(self.calendar()["2026-10-04"], [recurring])
        archive = self.client.get("/newsroom?view=archive&month=2026-10", headers=self.owner)
        self.assertEqual(CalendarHTML(archive.get_data(as_text=True)).days["2026-10-04"], [recurring])
        self.assertEqual(before, self.snapshot())

    def test_month_validation_empty_months_and_navigation_boundaries(self):
        self.assertTrue(all(not entries for entries in self.calendar().values()))
        for month in ("2026-00", "2026-13", "0000-01", "2026-2", "bad", "2026-01-01"):
            with self.subTest(month=month):
                self.assertEqual(self.client.get(f"/newsroom?month={month}", headers=self.owner).status_code, 422)
        for month, count in (("0001-01", 31), ("9999-12", 31), ("2026-12", 31), ("2027-01", 31)):
            with self.subTest(month=month):
                self.assertEqual(len(self.calendar(month)), count)
        html = self.client.get("/newsroom?month=2026-12", headers=self.owner).get_data(as_text=True)
        self.assertIn("month=2026-11", html)
        self.assertIn("month=2027-01", html)
        self.assertIn("No upcoming reports this month.", html)

    def test_pacific_dates_across_dst(self):
        self.at("2026-03-06T12:00:00-08:00")
        reporter = self.reporter()
        for instant, expected in (("2026-03-08T07:30:00+00:00", "2026-03-07"),
                                  ("2026-03-08T10:30:00+00:00", "2026-03-08"),
                                  ("2026-11-01T08:30:00+00:00", "2026-11-01"),
                                  ("2026-11-01T09:30:00+00:00", "2026-11-01")):
            with self.subTest(instant=instant):
                self.at(instant)
                days = self.calendar()
                self.assertEqual(days[expected], [reporter])
                self.assertTrue(all(not entries for day, entries in days.items() if day < expected))
