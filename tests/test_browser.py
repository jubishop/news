"""One real-browser owner journey, plus mobile reading and layout checks."""

import base64
from contextlib import ExitStack
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect
from preview import preview
from stylesheet import colors, css_rgb, schemes

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class BrowserJourney(unittest.TestCase):
    def test_calendar_navigation_pacific_dates_keyboard_and_reporter_links(self):
        with preview() as fixture, sync_playwright() as playwright:
            fixture.at("2026-10-01T01:00:00+00:00")  # September 30 in Pacific Time.
            contractor = fixture.reporter("once", dates=["2026-10-01", "2026-10-03"])
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner, timezone_id="Asia/Tokyo")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                page.goto(fixture.base_url + "/newsroom")
                calendar = page.locator("#reporting-calendar")
                expect(calendar.get_by_role("heading", name="September 2026")).to_be_visible()
                expect(calendar.locator('[aria-current="date"]')).to_have_attribute("datetime", "2026-09-30")
                next_month = calendar.get_by_role("link", name="Next month")
                next_month.focus()
                page.keyboard.press("Enter")
                expect(calendar.get_by_role("heading", name="October 2026")).to_be_visible()
                first = calendar.locator('[data-calendar-date="2026-10-01"]')
                # October 1, 2026 is Thursday, the fourth column of a Monday-first grid.
                first_box = first.bounding_box()
                headings = calendar.locator(".calendar-weekdays span")
                self.assertAlmostEqual(first_box["x"], headings.nth(3).bounding_box()["x"], delta=2)
                expect(first.get_by_role("link")).to_have_count(3)
                links = first.get_by_role("link")
                for index in range(3):
                    href = links.nth(index).get_attribute("href")
                    links.nth(index).focus()
                    page.keyboard.press("Enter")
                    expect(page).to_have_url(fixture.base_url + href)
                    expect(page.get_by_role("button", name="Save changes", exact=True)).to_be_visible()
                    page.go_back()
                links.first.focus()
                page.keyboard.press("Tab")
                expect(links.nth(1)).to_be_focused()
                page.keyboard.press("Tab")
                expect(links.nth(2)).to_be_focused()
                expect(calendar.locator('[data-calendar-date="2026-10-03"]')
                       .locator(f'a[href$="/{contractor}"]')).to_have_count(1)
                page.goto(fixture.base_url + "/newsroom?view=archive&month=2026-12")
                calendar.get_by_role("link", name="Next month").click()
                expect(calendar.get_by_role("heading", name="January 2027")).to_be_visible()
                self.assertIn("view=archive", page.url)
                calendar.get_by_role("link", name="Previous month").click()
                expect(calendar.get_by_role("heading", name="December 2026")).to_be_visible()
                calendar.get_by_role("link", name="Today", exact=True).click()
                expect(calendar.get_by_role("heading", name="September 2026")).to_be_visible()
                expect(calendar.locator('[aria-current="date"]')).to_have_attribute("datetime", "2026-09-30")
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_calendar_busy_days_long_names_mobile_and_empty_dates(self):
        with preview() as fixture, sync_playwright() as playwright:
            fixture.at("2026-09-30T12:00:00-07:00")
            names = ["A long reporter name about science and our changing world " * 2, "X" * 120]
            names += [f"Special assignment {number}" for number in range(10)]
            for name in names:
                response = fixture.form(
                    "/newsroom/reporters", name=name, prompt="Report useful changes.",
                    cadence="once", dates=["2026-10-01"],
                )
                self.assertEqual(response.status_code, 303)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner)
                for width in (1280, 768, 390, 320):
                    with self.subTest(width=width):
                        page.set_viewport_size({"width": width, "height": 900})
                        page.goto(fixture.base_url + "/newsroom?month=2026-10")
                        calendar = page.locator("#reporting-calendar")
                        day = calendar.locator('[data-calendar-date="2026-10-01"]')
                        expect(day.get_by_role("link")).to_have_count(14)
                        for name in names:
                            expect(day.get_by_role("link", name=name.strip(), exact=True)).to_be_visible()
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                        previous = None
                        for link in day.get_by_role("link").all():
                            box = link.bounding_box()
                            self.assertGreaterEqual(box["height"], 44)
                            self.assertGreaterEqual(box["x"], 0)
                            self.assertLessEqual(box["x"] + box["width"], width)
                            self.assertTrue(link.evaluate("element => element.scrollWidth <= element.clientWidth"))
                            if previous:
                                self.assertGreaterEqual(box["y"], previous["y"] + previous["height"])
                            previous = box
                        if width <= 600:
                            expect(day.get_by_role("heading", name="Thursday, October 1")).to_be_visible()
                            link = day.get_by_role("link").last
                            link.focus()
                            page.keyboard.press("Enter")
                            expect(page.get_by_role("button", name="Save changes", exact=True)).to_be_visible()
                            page.go_back()
                        Path("test-results").mkdir(exist_ok=True)
                        calendar.screenshot(path=f"test-results/calendar-{width}.png")
                page.goto(fixture.base_url + "/newsroom?month=2026-08")
                expect(calendar.get_by_text("Past reports for August 2026 are in each reporter's history.")).to_be_visible()
                expect(calendar.locator("[data-calendar-date]")).to_have_count(31)
                expect(calendar.get_by_role("link")).to_have_count(3)  # Navigation only.
            finally:
                browser.close()

    def assert_padding_matches(self, calendar, last_date, trailing):
        """Cells after the last day fill its week like the cells before the first day."""
        cells = calendar.locator(".calendar-days > li")
        leading = calendar.locator(".calendar-days > li.calendar-padding:first-child")
        expect(leading).to_have_count(1)  # Compare with a real leading cell, not a trailing one.
        after = calendar.locator(f'[data-calendar-date="{last_date}"] ~ li')
        expect(after).to_have_count(trailing)
        last = calendar.locator(f'[data-calendar-date="{last_date}"]').bounding_box()
        sunday = calendar.locator(".calendar-weekdays span").nth(6).bounding_box()
        style = "cell => [getComputedStyle(cell).backgroundColor, cell.textContent.trim()]"
        self.assertEqual(cells.count() % 7, 0)
        for index in range(trailing):
            cell = after.nth(index)
            expect(cell).to_have_class("calendar-padding")
            self.assertEqual(cell.evaluate(style), leading.evaluate(style))
            box = cell.bounding_box()
            self.assertAlmostEqual(box["y"], last["y"], delta=1)
            self.assertAlmostEqual(box["height"], last["height"], delta=1)
        if trailing:
            box = after.last.bounding_box()
            self.assertAlmostEqual(box["x"] + box["width"], sunday["x"] + sunday["width"], delta=2)

    def test_newsroom_lists_reporters_before_an_upcoming_calendar(self):
        with preview() as fixture, sync_playwright() as playwright:
            # New reporters start tomorrow, so create them before moving to October 12.
            weekly = fixture.reporter("weekly", weekdays=["mon"])
            retired = fixture.reporter("weekly", weekdays=["tue"])
            self.assertEqual(fixture.form(f"/newsroom/reporters/{retired}/delete").status_code, 303)
            fixture.at("2026-10-12T12:00:00-07:00")
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                calendar = page.locator("#reporting-calendar")
                days = calendar.locator("[data-calendar-date]")
                past = calendar.locator(".calendar-past")
                history = "Past reports for September 2026 are in each reporter's history."
                for width, height in ((390, 844), (1440, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    for path in ("/newsroom", "/newsroom?view=archive"):
                        with self.subTest(width=width, path=path):
                            page.goto(fixture.base_url + path)
                            boxes = [page.locator(selector).bounding_box() for selector in (
                                ".stat-strip", ".section-nav", ".reporter-grid",
                                "#reporting-calendar", ".operating-note",
                            )]
                            for above, below in zip(boxes, boxes[1:]):
                                self.assertLessEqual(above["y"] + above["height"], below["y"])
                            expect(page.get_by_role("link", name="Newsroom", exact=True)).to_have_text("Newsroom →")
                            for link in page.get_by_role("link", name="Open reporter", exact=True).all():
                                expect(link).to_have_text("Open reporter →")
                            expect(page.get_by_text("Past date")).to_have_count(0)
                            expect(days).to_have_count(31)
                            expect(past).to_have_count(11)
                            expect(calendar.locator('[data-calendar-date="2026-10-12"]')
                                   .locator(f'a[href$="/{weekly}"]')).to_be_visible()
                            if width <= 600:
                                # The phone list starts at today; earlier days stay in the HTML only.
                                for index in range(11):
                                    expect(past.nth(index)).to_be_hidden()
                                expect(days.filter(visible=True)).to_have_count(20)
                                expect(days.filter(visible=True).first).to_have_attribute(
                                    "data-calendar-date", "2026-10-12")
                            else:
                                # Desktop keeps dimmed past cells that show only the date number.
                                expect(days.filter(visible=True)).to_have_count(31)
                                first = calendar.locator('[data-calendar-date="2026-10-01"]')
                                expect(first).to_have_text("Thursday, October 1")
                                expect(first.locator("time")).to_have_attribute("datetime", "2026-10-01")
                                color = "cell => getComputedStyle(cell.querySelector('time')).color"
                                for index in range(11):
                                    expect(past.nth(index)).to_be_visible()
                                    self.assertNotEqual(
                                        past.nth(index).evaluate(color),
                                        calendar.locator('[data-calendar-date="2026-10-13"]').evaluate(color),
                                    )
                                self.assert_padding_matches(calendar, "2026-10-31", 1)
                    with self.subTest(width=width, month="2026-09"):
                        page.goto(fixture.base_url + "/newsroom?month=2026-09")
                        expect(calendar.get_by_text(history)).to_be_visible()
                        expect(calendar.get_by_text("No upcoming reports this month.")).to_have_count(0)
                        expect(days).to_have_count(30)
                        expect(past).to_have_count(30)
                        if width <= 600:
                            expect(days.filter(visible=True)).to_have_count(0)
                            expect(calendar.locator(".calendar-days")).to_be_hidden()
                        else:
                            expect(days.filter(visible=True)).to_have_count(30)
                            self.assert_padding_matches(calendar, "2026-09-30", 4)
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def save_changes(self, page):
        # Save redirects to the same URL; wait for the new document before reload.
        with page.expect_event("load"):
            page.get_by_role("button", name="Save changes", exact=True).click()

    def assert_assignment_dates(self, page, dates):
        expect(page.locator('input[type="date"][name="dates"]')).to_have_count(len(dates))
        for index, day in enumerate(dates, 1):
            expect(page.get_by_label(f"Assignment date {index}", exact=True)).to_have_value(day)

    def test_contractor_dates_edit_catch_up_and_retained_history(self):
        with preview() as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                previews = []
                page.on("request", lambda request: previews.append(request)
                        if "/schedule-preview" in request.url else None)
                page.goto(fixture.base_url + "/newsroom/reporters/new")
                page.get_by_label("Reporter name").fill("A finite assignment")
                page.get_by_label("Beat & instructions").fill("Report useful changes.")
                page.get_by_label("How often").select_option(label="Contractor")
                page.get_by_label("Assignment date 1", exact=True).fill("2026-10-05")
                for index, day in enumerate(("2026-10-01", "2026-10-03"), 2):
                    page.get_by_role("button", name="Add another", exact=True).click()
                    field = page.get_by_label(f"Assignment date {index}", exact=True)
                    expect(field).to_be_focused()
                    field.fill(day)
                expect(page.locator("[data-schedule-preview]")).to_contain_text("Thu, Oct 1")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                expect(page.get_by_role("heading", name="A finite assignment")).to_be_visible()
                reporter = page.url.rsplit("/", 1)[-1]
                page.reload()
                self.assert_assignment_dates(page, ["2026-10-01", "2026-10-03", "2026-10-05"])
                fixture.at("2026-10-04T06:00:00-07:00")
                page.reload()
                expect(page.get_by_text("Original dates already due", exact=True)).to_be_visible()
                self.assert_assignment_dates(page, ["2026-10-05"])
                expect(page.get_by_role("button", name="Delete assignment date")).to_have_count(1)
                expect(page.get_by_text("Dates already due cannot be changed or deleted.", exact=False)).to_be_visible()
                page.get_by_label("Assignment date 1", exact=True).fill("2026-10-06")
                for index, day in enumerate(("2026-10-07", "2026-10-08"), 2):
                    page.get_by_role("button", name="Add another", exact=True).click()
                    page.get_by_label(f"Assignment date {index}", exact=True).fill(day)
                page.get_by_role("button", name="Delete assignment date 2", exact=True).click()
                self.assert_assignment_dates(page, ["2026-10-06", "2026-10-08"])
                expect(page.get_by_label("Assignment date 2", exact=True)).to_be_focused()
                expect(page.locator("[data-schedule-preview]")).to_contain_text("Tue, Oct 6")
                for width in (1280, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    for control in page.locator('input[type="date"], [data-delete-date], [data-add-date]').all():
                        box = control.bounding_box()
                        self.assertGreaterEqual(box["height"], 40)
                        self.assertGreaterEqual(box["x"], 0)
                        self.assertLessEqual(box["x"] + box["width"], width)
                    Path("test-results").mkdir(exist_ok=True)
                    page.screenshot(path=f"test-results/contractor-editor-{width}.png", full_page=True)
                self.save_changes(page)
                page.reload()
                self.assert_assignment_dates(page, ["2026-10-06", "2026-10-08"])
                job = next(run for run in fixture.work() if run["reporter_id"] == reporter)
                self.assertEqual(job["assignment_dates"], ["2026-10-01", "2026-10-03"])
                fixture.result(job["id"], fixture.envelope(fixture.claim(job["id"])))
                fixture.at("2026-10-08T06:00:00-07:00")
                job = next(run for run in fixture.work() if run["reporter_id"] == reporter)
                fixture.result(job["id"], fixture.envelope(fixture.claim(job["id"]), outcome="nothing_to_publish", articles=[], reason="No updates"))
                page.reload()
                expect(page.locator(".section-heading .badge").first).to_have_text("Completed")
                expect(page.get_by_role("button", name="Save changes")).to_have_count(0)
                expect(page.get_by_role("link", name="This week in research")).to_be_visible()
                self.assertEqual(page.locator(".run-row").count(), 4)
                page.locator(".run-row").filter(has_text="Sat, Oct 3").locator("summary").first.click()
                expect(page.get_by_text("Assignment dates: Thu, Oct 1; Sat, Oct 3", exact=True)).to_be_visible()
                for width in (1280, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                Path("test-results").mkdir(exist_ok=True)
                page.screenshot(path="test-results/contractor-history-mobile.png", full_page=True)
                self.assertEqual(errors, [])
                self.assertTrue(previews)
                self.assertTrue(all(request.method == "POST" and "?" not in request.url for request in previews))
            finally:
                browser.close()

    def test_contractor_date_validation_and_keyboard_controls(self):
        with preview() as fixture, sync_playwright() as playwright:
            fixture.at("2026-10-01T01:00:00+00:00")  # Still September 30 in Pacific Time.
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner, timezone_id="Asia/Tokyo")
                page.goto(fixture.base_url + "/newsroom/reporters/new")
                original_url = page.url
                page.get_by_label("Reporter name").fill("One chosen date")
                page.get_by_label("Beat & instructions").fill("Report useful changes.")
                page.get_by_label("How often").select_option("once")
                first = page.get_by_label("Assignment date 1", exact=True)
                expect(first).to_have_attribute("min", "2026-10-01")
                first.fill("2026-09-30")
                expect(page.locator("[data-schedule-preview]")).to_contain_text("tomorrow or later")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                self.assertEqual(page.url, original_url)
                self.assertTrue(first.evaluate("input => input.validity.rangeUnderflow"))
                self.assertTrue(first.evaluate("input => Boolean(input.validationMessage)"))
                first.fill("2026-10-01")
                add = page.get_by_role("button", name="Add another", exact=True)
                add.focus()
                page.keyboard.press("Enter")
                second = page.get_by_label("Assignment date 2", exact=True)
                expect(second).to_be_focused()
                second.fill("2026-10-01")
                expect(page.locator("[data-schedule-preview]")).to_contain_text("must be distinct")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                self.assertEqual(page.url, original_url)
                self.assertIn("distinct", second.evaluate("input => input.validationMessage"))
                second.fill("2026-10-03")
                expect(page.locator("[data-schedule-preview]")).to_contain_text("Thu, Oct 1")
                first.focus()
                # Native date controls have several keyboard segments before Delete.
                delete = page.get_by_role("button", name="Delete assignment date 1", exact=True)
                for _ in range(6):
                    page.keyboard.press("Tab")
                    if delete.evaluate("button => button === document.activeElement"):
                        break
                expect(delete).to_be_focused()
                page.keyboard.press("Space")
                self.assert_assignment_dates(page, ["2026-10-03"])
                expect(first).to_be_focused()
                expect(page.locator("[data-schedule-preview]")).to_contain_text("Sat, Oct 3")
                page.get_by_role("button", name="Delete assignment date 1", exact=True).click()
                expect(add).to_be_focused()
                expect(page.locator("[data-schedule-preview]")).to_contain_text("Choose at least one assignment date")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                expect(page.get_by_text("Choose at least one assignment date.", exact=True)).to_be_visible()
                page.goto(original_url)
                page.get_by_label("Reporter name").fill("One chosen date")
                page.get_by_label("Beat & instructions").fill("Report useful changes.")
                page.get_by_label("How often").select_option("once")
                page.get_by_label("Assignment date 1", exact=True).fill("2026-10-02")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                expect(page.get_by_role("heading", name="One chosen date")).to_be_visible()
                page.reload()
                self.assert_assignment_dates(page, ["2026-10-02"])
            finally:
                browser.close()

    def test_contractor_delete_last_future_date_retains_due_work_and_history(self):
        with preview() as fixture, sync_playwright() as playwright:
            reporter = fixture.reporter("once", dates=["2026-10-01", "2026-10-03"])
            fixture.at("2026-10-01T06:00:00-07:00")
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner, viewport={"width": 390, "height": 844})
                page.goto(fixture.base_url + "/newsroom/reporters/" + reporter)
                page.get_by_role("button", name="Delete assignment date 1", exact=True).click()
                expect(page.locator("[data-schedule-preview]")).to_contain_text("No future dates")
                self.save_changes(page)
                page.reload()
                self.assert_assignment_dates(page, [])
                expect(page.locator(".section-heading .badge").first).to_have_text("Active")
                expect(page.get_by_role("button", name="Delete assignment date")).to_have_count(0)
                job = next(run for run in fixture.work() if run["reporter_id"] == reporter)
                self.assertEqual(job["assignment_dates"], ["2026-10-01"])
                page.get_by_role("button", name="Add another", exact=True).click()
                page.get_by_label("Assignment date 1", exact=True).fill("2026-10-04")
                self.save_changes(page)
                fixture.result(job["id"], fixture.envelope(fixture.claim(job["id"])))
                page.reload()
                page.get_by_role("button", name="Delete assignment date 1", exact=True).click()
                self.save_changes(page)
                page.reload()
                expect(page.locator(".section-heading .badge").first).to_have_text("Completed")
                self.assert_assignment_dates(page, [])
                expect(page.get_by_role("button", name="Add another", exact=True)).to_have_count(0)
                expect(page.get_by_role("button", name="Save changes", exact=True)).to_have_count(0)
                expect(page.get_by_role("link", name="This week in research")).to_be_visible()
                expect(page.locator(".run-row")).to_have_count(1)
                page.locator(".run-row > summary").click()
                expect(page.get_by_text("Assignment dates: Thu, Oct 1", exact=True)).to_be_visible()
            finally:
                browser.close()

    def test_feed_has_one_column_and_equal_story_prominence(self):
        with preview() as fixture, sync_playwright() as playwright:
            for day in (27, 28):
                fixture.at(f"2026-09-{day}T12:00:00-07:00")
                run = fixture.work()[0]["id"]
                claim = fixture.claim(run)
                response = fixture.result(
                    run,
                    fixture.envelope(
                        claim,
                        articles=[
                            fixture.article(
                                title=f"Bulletin {day}: research update {index}",
                                summary="A sample report with useful context. "
                                * (1 + index % 3),
                            )
                            for index in range(16)
                        ],
                    ),
                )
                self.assertEqual(response.status_code, 200)
            reporter = claim["reporter"]["id"]
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                for width in (1280, 768, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    for query, count in (
                        ("", 30),
                        ("?page=2", 4),
                        (f"?reporter_id={reporter}&q=Bulletin", 30),
                    ):
                        with self.subTest(width=width, query=query):
                            page.goto(fixture.base_url + "/" + query)
                            stories = page.get_by_role("article")
                            expect(stories).to_have_count(count)
                            boxes = [story.bounding_box() for story in stories.all()]
                            for previous, current in zip(boxes, boxes[1:]):
                                self.assertAlmostEqual(current["x"], previous["x"])
                                self.assertAlmostEqual(
                                    current["width"], previous["width"]
                                )
                                self.assertGreaterEqual(
                                    current["y"], previous["y"] + previous["height"]
                                )
                            for selector in ("h3", "p"):
                                styles = stories.locator(selector).evaluate_all(
                                    """elements => elements.map(element => {
                                        const style = getComputedStyle(element);
                                        return [style.fontSize, style.fontFamily,
                                                style.fontWeight, style.lineHeight];
                                    })"""
                                )
                                self.assertEqual(len(styles), count)
                                self.assertTrue(
                                    all(style == styles[0] for style in styles),
                                    f"Unequal {selector} typography: {styles}",
                                )
                            self.assertTrue(
                                page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                            )
                            # A story without a photo starts at its padding, with no empty photo row.
                            offsets = stories.evaluate_all(
                                """stories => stories.map(story => Math.round(
                                    story.querySelector(".story-meta").getBoundingClientRect().top
                                    - story.getBoundingClientRect().top
                                    - parseFloat(getComputedStyle(story).paddingTop)))"""
                            )
                            self.assertEqual(set(offsets), {0})
                page.get_by_role("link", name="Older stories →").click()
                expect(page.get_by_role("article")).to_have_count(2)
                expect(page.get_by_label("Search stories")).to_have_value("Bulletin")
                expect(page.get_by_label("From the desk of")).to_have_value(reporter)
                story = page.get_by_role("article").first
                title = story.get_by_role("heading").inner_text()
                story.get_by_role("link", name=title, exact=True).click()
                expect(page.get_by_role("heading", name=title)).to_be_visible()
            finally:
                browser.close()

    def test_lead_photos_sit_beside_summaries_and_broken_photos_disappear(self):
        with preview() as fixture, sync_playwright() as playwright:
            fixture.at("2026-09-27T12:00:00-07:00")
            run = fixture.work()[0]["id"]

            def photo(name):
                return {
                    "url": f"https://images.example.com/{name}.png",
                    "alt": f"Photo of the {name} scene",
                    "credit": "Example Photo Desk",
                    "credit_url": "https://example.com/photos",
                }

            response = fixture.result(
                run,
                fixture.envelope(
                    fixture.claim(run),
                    articles=[
                        fixture.article(title="Photographed story", lead_image=photo("lead")),
                        fixture.article(title="Story with a missing photo", lead_image=photo("missing")),
                        fixture.article(title="Text-only story"),
                    ],
                ),
            )
            self.assertEqual(response.status_code, 200)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.route(
                    "https://images.example.com/**",
                    lambda route: route.fulfill(status=404)
                    if "missing" in route.request.url
                    else route.fulfill(content_type="image/png", body=PNG),
                )
                for width in (1280, 390):
                    with self.subTest(width=width):
                        page.set_viewport_size({"width": width, "height": 900})
                        page.goto(fixture.base_url + "/")
                        stories = page.get_by_role("article")
                        story = stories.filter(has_text="Photographed story")
                        image = story.locator("img")
                        expect(image).to_be_visible()
                        expect(image).to_have_attribute("referrerpolicy", "no-referrer")
                        page.wait_for_function(
                            "image => image.complete && image.naturalWidth > 0",
                            arg=image.element_handle(),
                        )
                        picture = image.bounding_box()
                        heading = story.get_by_role("heading").bounding_box()
                        summary = story.locator("p").bounding_box()
                        if width == 1280:
                            self.assertGreaterEqual(picture["x"], summary["x"] + summary["width"])
                            self.assertLess(picture["y"], summary["y"] + summary["height"])
                            self.assertGreater(picture["width"], 150)
                        else:
                            self.assertLessEqual(picture["y"] + picture["height"], heading["y"])
                            self.assertGreater(picture["width"], 300)
                        missing = stories.filter(has_text="Story with a missing photo")
                        missing.scroll_into_view_if_needed()
                        expect(missing.locator("img")).to_have_count(0)
                        text_only = stories.filter(has_text="Text-only story")
                        expect(text_only.locator("img")).to_have_count(0)
                        self.assertAlmostEqual(
                            missing.locator(".story-text").bounding_box()["width"],
                            text_only.locator(".story-text").bounding_box()["width"],
                        )
                        boxes = [box.bounding_box() for box in stories.all()]
                        self.assertTrue(all(box["x"] == boxes[0]["x"] and box["width"] == boxes[0]["width"] for box in boxes))
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                story.get_by_role("link", name="Photographed story", exact=True).click()
                expect(page.get_by_role("heading", name="Photographed story")).to_be_visible()
                hero = page.get_by_role("img", name="Photo of the lead scene")
                expect(hero).to_be_visible()
                credit = page.get_by_role("link", name="Example Photo Desk")
                expect(credit).to_have_attribute("href", "https://example.com/photos")
                self.assertLess(hero.bounding_box()["y"], page.locator(".prose").bounding_box()["y"])
            finally:
                browser.close()

    def test_front_page_starts_near_the_top_with_fixed_story_columns(self):
        # Layout criteria are CSS-determined widths or leave room for CI's wider fallback serif.
        headline = "Open-weight models close the gap on long-context reasoning benchmarks"
        summary = "Researchers released results that change how practitioners approach the problem. " * 4
        with preview() as fixture, sync_playwright() as playwright:
            for day, lead_image in (("27", None), ("28", "https://images.example.com/lead.png")):
                fixture.at(f"2026-09-{day}T12:00:00-07:00")
                run = fixture.work()[0]["id"]  # The only due run, so no report is late.
                photo = lead_image and {"url": lead_image, "alt": "Photo of the lead scene",
                                        "credit": "Example Photo Desk", "credit_url": "https://example.com/photos"}
                article = fixture.article(title=headline, summary=summary, lead_image=photo)
                response = fixture.result(run, fixture.envelope(fixture.claim(run), articles=[article]))
                self.assertEqual(response.status_code, 200)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.route("https://images.example.com/**",
                           lambda route: route.fulfill(content_type="image/png", body=PNG))
                for width, height in ((1440, 900), (390, 844)):
                    with self.subTest(width=width):
                        page.set_viewport_size({"width": width, "height": height})
                        page.goto(fixture.base_url + "/")
                        expect(page.locator(".status-line")).to_have_count(0)
                        expect(page.get_by_role("heading", level=2).first).to_have_text("Today · Monday, Sep 28")
                        stories = page.get_by_role("article").filter(has_text=headline)
                        pictured, plain = stories.first, stories.last
                        expect(pictured.locator("img")).to_be_visible()
                        expect(plain.locator("img")).to_have_count(0)
                        title = pictured.get_by_role("heading").bounding_box()
                        photo = pictured.locator("img").bounding_box()
                        if width == 1440:
                            self.assertLessEqual(title["y"], 420)
                            self.assertGreaterEqual(photo["x"], title["x"] + title["width"])
                            for story in (pictured, plain):
                                self.assertLessEqual(story.locator("p").bounding_box()["width"], 680)
                        else:
                            self.assertLessEqual(photo["y"] + photo["height"], title["y"])
                            self.assertLessEqual(title["y"] + title["height"], height)
                        self.assertEqual(title["width"], plain.get_by_role("heading").bounding_box()["width"])
                        for story in (pictured, plain):
                            text = story.locator(".story-text").bounding_box()
                            self.assertLessEqual(story.locator("p").bounding_box()["width"], text["width"])
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            finally:
                browser.close()

    def test_filter_applies_immediately_with_javascript_and_through_apply_without(self):
        with preview() as fixture, sync_playwright() as playwright:
            response = fixture.form("/newsroom/reporters", name="Sports desk",
                                    prompt="Cover the home team.", cadence="daily")
            sports = response.headers["Location"].rsplit("/", 1)[-1]
            fixture.at("2026-09-27T12:00:00-07:00")
            run = next(run["id"] for run in fixture.work() if run["reporter_id"] == sports)
            articles = [fixture.article(title="Match report")]
            fixture.result(run, fixture.envelope(fixture.claim(run), articles=articles))
            fits = """input => {
                const style = getComputedStyle(input);
                const context = document.createElement("canvas").getContext("2d");
                context.font = style.font;
                const room = input.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
                return context.measureText(input.placeholder).width <= room;
            }"""
            browser = playwright.chromium.launch()
            try:
                for scripts in (True, False):
                    context = browser.new_context(java_script_enabled=scripts)
                    page = context.new_page()
                    page.goto(fixture.base_url + "/")
                    stories = page.get_by_role("article")
                    expect(stories).to_have_count(3)
                    apply = page.get_by_role("button", name="Apply")
                    for width in (390, 320):
                        with self.subTest(scripts=scripts, width=width):
                            page.set_viewport_size({"width": width, "height": 844})
                            self.assertTrue(page.get_by_label("Search stories").evaluate(fits))
                            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    page.set_viewport_size({"width": 1280, "height": 900})
                    reporter = page.get_by_label("From the desk of")
                    if scripts:
                        expect(apply).to_be_hidden()
                        reporter.select_option(label="Sports desk")
                    else:
                        expect(apply).to_be_visible()
                        reporter.select_option(label="Sports desk")
                        expect(page).to_have_url(fixture.base_url + "/")
                        apply.click()
                    expect(page).to_have_url(f"{fixture.base_url}/?reporter_id={sports}&q=")
                    expect(stories).to_have_count(1)
                    expect(page.locator("form .edition-count")).to_have_text("1 story")
                    if scripts:
                        # Keyboard users stay on the menu, and Back restores the page's own choice.
                        expect(reporter).to_be_focused()
                        page.go_back()
                        expect(page).to_have_url(fixture.base_url + "/")
                        expect(stories).to_have_count(3)
                        expect(reporter).to_have_value("")
                    reporter.select_option(label="All reporters")
                    if scripts:
                        expect(page).to_have_url(f"{fixture.base_url}/?reporter_id=&q=")
                        expect(stories).to_have_count(3)
                    page.get_by_label("Search stories").fill("curiosity")
                    page.get_by_label("Search stories").press("Enter")
                    expect(page).to_have_url(f"{fixture.base_url}/?reporter_id=&q=curiosity")
                    expect(stories).to_have_count(1)
                    expect(stories.get_by_role("heading")).to_have_text("A little curiosity goes a long way")
                    context.close()
            finally:
                browser.close()

    def test_long_reporter_names_wrap_in_phone_kickers(self):
        name = "Correspondent" * 6  # 78 characters with nowhere to break.
        with preview() as fixture, sync_playwright() as playwright:
            response = fixture.form("/newsroom/reporters", name=name,
                                    prompt="Report useful changes.", cadence="daily")
            reporter = response.headers["Location"].rsplit("/", 1)[-1]
            fixture.at("2026-09-27T12:00:00-07:00")
            run = next(run for run in fixture.work() if run["reporter_id"] == reporter)["id"]
            article = fixture.article(article_date="2026-09-20")  # The kicker adds the date.
            response = fixture.result(run, fixture.envelope(fixture.claim(run), articles=[article]))
            self.assertEqual(response.status_code, 200)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                for path in ("/", f"/?reporter_id={reporter}"):
                    with self.subTest(path=path):
                        page.goto(fixture.base_url + path)
                        expect(page.locator(".story-meta").first).to_contain_text("Sun, Sep 20")
                        expect(page.get_by_role("article").get_by_role("link", name=name)).to_be_visible()
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            finally:
                browser.close()

    def test_pages_show_readable_dates_and_text_at_phone_and_desktop_widths(self):
        with preview() as fixture, sync_playwright() as playwright:
            contractor = fixture.reporter("once", dates=["2026-09-27", "2026-09-29", "2026-10-03"])
            fixture.at("2026-09-29T06:00:00-07:00")
            job = next(run for run in fixture.work() if run["reporter_id"] == contractor)
            # The kept article carries every small-text element: a photo credit, a table, and code.
            kept_article = fixture.article(
                title="Kept story",
                lead_image={
                    "url": "https://images.example.com/lead.png",
                    "alt": "Photo of the lead scene",
                    "credit": "Example Photo Desk",
                    "credit_url": "https://example.com/photos",
                },
                body_markdown="## Findings\n\nRun `pip list` first.\n\n"
                "| Tool | Command |\n| --- | --- |\n| pip | `pip list` |\n\n"
                "```\npip install news\n```\n",
            )
            articles = [kept_article, fixture.article(title="Trashed story"), fixture.article(title="Another story")]
            receipt = fixture.result(job["id"], fixture.envelope(fixture.claim(job["id"]), articles=articles))
            self.assertEqual(receipt.status_code, 200)
            kept, trashed, _ = receipt.json["article_ids"]
            self.assertEqual(fixture.form(f"/newsroom/articles/{trashed}/delete").status_code, 303)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner)
                page.route("https://images.example.com/**",
                           lambda route: route.fulfill(content_type="image/png", body=PNG))
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                for width, height in ((390, 844), (1440, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    for path in ("/", "/articles/" + kept, "/newsroom",
                                 "/newsroom/reporters/" + contractor, "/newsroom/trash"):
                        with self.subTest(width=width, path=path):
                            page.goto(fixture.base_url + path)
                            if path.startswith("/articles/"):
                                for element in (".lead-photo figcaption", ".prose table code", ".prose pre"):
                                    expect(page.locator(element)).to_be_visible()
                                more = page.get_by_role("region", name="More from Science desk")
                                expect(more.get_by_role("link")).to_have_count(2)
                            if "/reporters/" in path:
                                expect(page.locator("[data-schedule-preview]")).to_contain_text(
                                    "First future date for this schedule: Sat, Oct 3 · Pacific Time."
                                )
                            small = page.evaluate(
                                """() => {
                                    for (const details of document.querySelectorAll("details")) details.open = true;
                                    const small = [];
                                    const report = (element, text) => {
                                        const size = parseFloat(getComputedStyle(element).fontSize);
                                        if (size < 12) small.push(`${size}px <${element.localName} class="${element.className}"> ${text}`);
                                    };
                                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                                    while (walker.nextNode()) {
                                        const node = walker.currentNode;
                                        const range = document.createRange();
                                        range.selectNodeContents(node);
                                        if (node.data.trim() && node.parentElement.checkVisibility({visibilityProperty: true})
                                            && [...range.getClientRects()].some(rect => rect.width && rect.height)) {
                                            report(node.parentElement, node.data.trim().slice(0, 40));
                                        }
                                    }
                                    for (const control of document.querySelectorAll("input:not([type=hidden]), select, textarea")) {
                                        if (control.checkVisibility()) report(control, control.name);
                                    }
                                    return small;
                                }"""
                            )
                            self.assertEqual(small, [])
                            self.assertNotRegex(page.evaluate("document.body.innerText"), r"\d{4}-\d{2}-\d{2}")
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_pages_follow_the_system_color_scheme(self):
        palettes = {scheme: colors(tokens) for scheme, tokens in schemes().items()}
        # System colors resolve for the scheme the page uses, as native controls do.
        canvas_text = {"light": "rgb(0, 0, 0)", "dark": "rgb(255, 255, 255)"}
        probe = """() => {
            const probe = document.body.appendChild(document.createElement("i"));
            probe.style.color = "CanvasText";
            const body = getComputedStyle(document.body);
            const colors = [body.backgroundColor, body.color, getComputedStyle(probe).color];
            probe.remove();
            return colors;
        }"""
        directory = Path(__file__).resolve().parents[1] / "test-results"
        directory.mkdir(exist_ok=True)
        with preview() as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for scheme, palette in palettes.items():
                    context = browser.new_context(
                        color_scheme=scheme, viewport={"width": 390, "height": 844},
                        extra_http_headers=fixture.owner,
                    )
                    page = context.new_page()
                    page.goto(fixture.base_url + "/")
                    article = page.locator(".story h3 a").first.get_attribute("href")
                    page.goto(fixture.base_url + "/newsroom")
                    reporter = page.get_by_role("link", name="Open reporter").first.get_attribute("href")
                    for name, path in (("feed", "/"), ("article", article),
                                       ("newsroom", "/newsroom"), ("reporter", reporter)):
                        with self.subTest(scheme=scheme, page=name):
                            page.goto(fixture.base_url + path)
                            self.assertEqual(page.evaluate(probe), [
                                css_rgb(palette["paper"]), css_rgb(palette["ink"]), canvas_text[scheme],
                            ])
                            # Browser placeholder gray is too faint on dark fields; placeholders use muted text.
                            placeholders = page.evaluate("""() => [...document.querySelectorAll("[placeholder]")]
                                .map(field => getComputedStyle(field, "::placeholder").color)""")
                            self.assertEqual(set(placeholders) - {css_rgb(palette["muted"])}, set())
                            page.screenshot(path=str(directory / f"{scheme}-{name}.png"), full_page=True)
                    context.close()
            finally:
                browser.close()

    def test_article_headline_size_and_more_from_the_reporter(self):
        with preview() as fixture, sync_playwright() as playwright:
            titles = []
            for day in (27, 28, 29, 30):
                fixture.at(f"2026-09-{day}T12:00:00-07:00")
                run = fixture.work()[0]["id"]
                claim = fixture.claim(run)
                titles.append(f"Research update for September {day}")
                response = fixture.result(run, fixture.envelope(claim, articles=[
                    fixture.article(title=titles[-1], article_date=f"2026-09-{day}"),
                ]))
                self.assertEqual(response.status_code, 200)
            newest = response.json["article_ids"][0]
            reporter = claim["reporter"]["id"]
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(fixture.base_url + "/articles/" + newest)
                headline = page.get_by_role("heading", level=1)
                section = page.get_by_role("region", name="More from Science desk")
                for width, height, size in ((1440, 900, "44px"), (390, 844, "32px")):
                    with self.subTest(width=width):
                        page.set_viewport_size({"width": width, "height": height})
                        expect(headline).to_have_css("font-size", size)
                        sources = page.locator(".sources").bounding_box()
                        self.assertGreaterEqual(section.bounding_box()["y"], sources["y"] + sources["height"])
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                expect(section.get_by_role("heading")).to_have_text("More from Science desk")
                stories = section.get_by_role("listitem")
                expect(stories.get_by_role("link")).to_have_text(titles[2::-1])
                expect(stories).to_contain_text(["Tue, Sep 29", "Mon, Sep 28", "Sun, Sep 27"])
                stories.get_by_role("link", name=titles[1]).click()
                expect(headline).to_have_text(titles[1])
                expect(stories.get_by_role("link")).to_have_text([titles[3], titles[2], titles[0]])
                page.go_back()
                section.get_by_role("link", name="See all from Science desk").click()
                expect(page).to_have_url(f"{fixture.base_url}/?reporter_id={reporter}")
                expect(page.get_by_role("link", name=titles[3], exact=True)).to_be_visible()
                self.assertEqual(errors, [])
            finally:
                browser.close()

    def test_more_from_wraps_long_reporter_names_on_phones(self):
        with preview() as fixture, sync_playwright() as playwright:
            name = "Correspondent" * 6
            response = fixture.form("/newsroom/reporters", name=name,
                                    prompt="Report useful changes.", cadence="daily")
            reporter = response.headers["Location"].rsplit("/", 1)[-1]
            for day in (27, 28):
                fixture.at(f"2026-09-{day}T12:00:00-07:00")
                run = next(run for run in fixture.work() if run["reporter_id"] == reporter)["id"]
                response = fixture.result(run, fixture.envelope(
                    fixture.claim(run), articles=[fixture.article(title=f"Update for September {day}")]))
                self.assertEqual(response.status_code, 200)
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.goto(fixture.base_url + "/articles/" + response.json["article_ids"][0])
                section = page.get_by_role("region", name="More from " + name)
                expect(section.get_by_role("list")).to_have_attribute("role", "list")
                expect(section.get_by_role("listitem")).to_have_text("Update for September 27 Sat, Sep 26")
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            finally:
                browser.close()

    def test_inactive_schedule_fields_do_not_block_submission(self):
        with preview() as fixture, sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(extra_http_headers=fixture.owner)
                page.goto(fixture.base_url + "/newsroom/reporters/new")
                page.get_by_label("Reporter name").fill("Changed cadence")
                page.get_by_label("Beat & instructions").fill("A daily report.")
                page.get_by_label("How often").select_option("monthly")
                page.get_by_label("Day of the month").fill("32")
                page.get_by_label("How often").select_option("daily")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Changed cadence")
                ).to_be_visible()
                page.get_by_label("How often").select_option("monthly")
                page.get_by_label("Day of the month").fill("32")
                page.get_by_role("button", name="Save changes", exact=True).click()
                self.assertFalse(
                    page.locator("[data-schedule-form]").evaluate(
                        "form => form.checkValidity()"
                    )
                )
                page.get_by_label("Day of the month").fill("15")
                page.get_by_role("button", name="Save changes", exact=True).click()
                expect(page.get_by_label("How often")).to_have_value("monthly")
                expect(page.get_by_label("Day of the month")).to_have_value("15")
            finally:
                browser.close()

    def test_owner_lifecycle_and_public_reading(self):
        with (
            preview() as fixture,
            sync_playwright() as playwright,
            ExitStack() as cleanup,
        ):
            browser = playwright.chromium.launch()
            cleanup.callback(browser.close)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                extra_http_headers=fixture.owner,
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on(
                "console",
                lambda message: (
                    errors.append(message.text) if message.type == "error" else None
                ),
            )
            page.goto(fixture.base_url + "/newsroom")
            expect(page.get_by_role("heading", name="The newsroom.")).to_be_visible()
            page.get_by_role("link", name="+ Add a reporter").click()
            page.get_by_label("Reporter name").fill("Browser contractor")
            page.get_by_label("Beat & instructions").fill(
                "Produce one concise report with useful sources."
            )
            page.get_by_label("How often").select_option("once")
            expect(page.get_by_label("Assignment date 1", exact=True)).to_be_visible()
            expect(page.locator("[data-schedule-preview]")).to_contain_text(
                "Sun, Sep 27"
            )
            page.get_by_role("button", name="Add reporter", exact=True).click()
            expect(
                page.get_by_role("heading", name="Browser contractor", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Pause reporter").click()
            expect(page.get_by_role("button", name="Resume reporter")).to_be_visible()
            page.get_by_role("button", name="Resume reporter").click()
            expect(page.get_by_role("button", name="Pause reporter")).to_be_visible()
            page.on("dialog", lambda dialog: dialog.accept())
            page.get_by_role("button", name="Remove reporter").click()
            page.get_by_role("link", name="Retired & completed").click()
            expect(
                page.get_by_role("heading", name="Browser contractor")
            ).to_be_visible()
            page.get_by_role("link", name="Your reporters", exact=True).click()
            page.locator(".reporter-grid").get_by_role("link", name="Science desk", exact=True).click()
            title = "A little curiosity goes a long way"
            row = page.locator(".history-row").filter(
                has=page.get_by_role("link", name=title)
            )
            row.get_by_role("button", name="Move to Trash").click()
            expect(page.get_by_role("heading", name="Article Trash.")).to_be_visible()
            expect(page.get_by_text(title, exact=True)).to_be_visible()
            page.get_by_role("button", name="Restore article").click()
            expect(page.get_by_text(title, exact=True)).to_have_count(0)
            context.close()
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(fixture.base_url)
            page.get_by_role("link", name=title, exact=True).click()
            expect(page.get_by_role("heading", name=title)).to_be_visible()
            expect(page.locator("table")).to_be_visible()
            self.assertTrue(
                page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            )
            directory = Path(__file__).resolve().parents[1] / "test-results"
            directory.mkdir(exist_ok=True)
            page.screenshot(path=str(directory / "article-mobile.png"), full_page=True)
            response = page.goto(fixture.base_url + "/newsroom")
            self.assertEqual(response.status, 401)
            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
