"""Worker date repair preserves explicit instants and rejects ambiguous input."""

from copy import deepcopy
import unittest

from news.errors import Problem
from news.worker_claude import validate_result
from test_worker import RESULT


class WorkerDateTests(unittest.TestCase):
    def test_explicit_timestamps_use_pacific_dates_without_changing_input(self):
        cases = (
            ("2026-10-01T07:17:31-07:00", "2026-10-01"),
            ("2026-10-01T06:00:06.749342-07:00", "2026-10-01"),
            ("2026-10-01T01:00:00Z", "2026-09-30"),
            ("2026-01-01T07:30:00+00:00", "2025-12-31"),
            ("2026-07-01T07:30:00+00:00", "2026-07-01"),
            ("2026-11-01T01:30:00-07:00", "2026-11-01"),
            ("2026-11-01T01:30:00-08:00", "2026-11-01"),
            ("2026-10-01", "2026-10-01"),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                result = deepcopy(RESULT)
                for name in ("article_date", "coverage_start", "coverage_end"):
                    result["articles"][0][name] = value
                original = deepcopy(result)
                article, = validate_result(result)["articles"]
                for name in ("article_date", "coverage_start", "coverage_end"):
                    self.assertEqual(article[name], expected)
                self.assertEqual(result, original)

    def test_invalid_or_ambiguous_dates_still_reject_the_complete_result(self):
        for value in (
            "2026-10-01T06:00:00", "October 1, 2026", "2026-02-30T06:00:00-08:00",
            "2026-10-01T25:00:00-07:00", "2026-10-01T06:00:00+07:99",
            "2026-10-01T06:00:00-00:00", "2026-10-01T06:00:00-07:00 extra",
            "0001-01-01T00:00:00Z", None, 20261001,
        ):
            with self.subTest(value=value):
                result = deepcopy(RESULT)
                result["articles"].append(dict(result["articles"][0], coverage_end=value))
                with self.assertRaisesRegex(Problem, "coverage_end must be a YYYY-MM-DD date"):
                    validate_result(result)

    def test_reversed_coverage_is_not_repaired(self):
        result = deepcopy(RESULT)
        result["articles"][0].update(coverage_start="2026-09-28T06:00:00-07:00",
                                      coverage_end="2026-09-28T01:00:00Z")
        with self.assertRaisesRegex(Problem, "Coverage end must be on or after coverage start"):
            validate_result(result)
