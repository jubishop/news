"""One real-browser owner journey, plus mobile reading and layout checks."""

from contextlib import ExitStack
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect
from preview import preview


class BrowserJourney(unittest.TestCase):
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
