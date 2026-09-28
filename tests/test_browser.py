"""One real-browser owner journey, plus mobile reading and layout checks."""

from contextlib import ExitStack
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect
from preview import preview


class BrowserJourney(unittest.TestCase):
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
                page.get_by_label("Assignment dates", exact=True).fill("2026-10-05\n2026-10-01\n2026-10-03")
                page.get_by_label("Reporter name").click()
                expect(page.locator("[data-schedule-preview]")).to_contain_text("2026-10-01")
                page.get_by_role("button", name="Add reporter", exact=True).click()
                expect(page.get_by_role("heading", name="A finite assignment")).to_be_visible()
                reporter = page.url.rsplit("/", 1)[-1]
                expect(page.get_by_label("Assignment dates", exact=True)).to_have_value("2026-10-01\n2026-10-03\n2026-10-05")
                fixture.at("2026-10-04T06:00:00-07:00")
                page.reload()
                expect(page.get_by_text("Original dates already due", exact=True)).to_be_visible()
                expect(page.get_by_label("Future assignment dates")).to_have_value("2026-10-05")
                page.get_by_label("Future assignment dates").fill("2026-10-06\n2026-10-08")
                page.get_by_role("button", name="Save changes", exact=True).click()
                expect(page.get_by_label("Future assignment dates")).to_have_value("2026-10-06\n2026-10-08")
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
                page.locator(".run-row").filter(has_text="2026-10-03").locator("summary").first.click()
                expect(page.get_by_text("Assignment dates: 2026-10-01, 2026-10-03", exact=True)).to_be_visible()
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
                            for selector in ("h2", "p"):
                                styles = stories.locator(selector).evaluate_all(
                                    """elements => elements.map(element => {
                                        const style = getComputedStyle(element);
                                        return [style.fontSize, style.fontFamily,
                                                style.fontWeight, style.lineHeight];
                                    })"""
                                )
                                self.assertTrue(
                                    all(style == styles[0] for style in styles),
                                    f"Unequal {selector} typography: {styles}",
                                )
                            self.assertTrue(
                                page.evaluate(
                                    "document.documentElement.scrollWidth <= innerWidth"
                                )
                            )
                page.get_by_role("link", name="Older stories →").click()
                expect(page.get_by_role("article")).to_have_count(2)
                expect(page.get_by_label("Search stories")).to_have_value("Bulletin")
                expect(page.get_by_label("From the desk of")).to_have_value(reporter)
                story = page.get_by_role("article").first
                title = story.get_by_role("heading").inner_text()
                story.get_by_role("link", name="Read the story").click()
                expect(page.get_by_role("heading", name=title)).to_be_visible()
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
            expect(page.get_by_label("Assignment date")).to_be_visible()
            expect(page.locator("[data-schedule-preview]")).to_contain_text(
                "2026-09-27"
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
            page.get_by_role("link", name="Science desk", exact=True).click()
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
