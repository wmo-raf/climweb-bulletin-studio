"""The periods of the cadences, and when their drafts are due. Pure: runs on the host too,
`uv run --no-project python -m unittest bulletin_studio.test_periods`."""
import unittest
from datetime import date, datetime, time

from .periods import DAILY, DEKADAL, MONTHLY, due, period


class PeriodTests(unittest.TestCase):
    def test_a_day(self):
        self.assertEqual(period(DAILY, date(2026, 10, 6)), (date(2026, 10, 6),) * 2)
        self.assertEqual(period("", date(2026, 10, 6)), (date(2026, 10, 6),) * 2, "unknown: a day")

    def test_dekads(self):
        for day, expected in [
            (1, (1, 10)), (10, (1, 10)), (11, (11, 20)), (20, (11, 20)), (21, (21, 31)), (31, (21, 31)),
        ]:
            start, end = period(DEKADAL, date(2026, 10, day))
            self.assertEqual((start.day, end.day), expected, day)
        self.assertEqual(period(DEKADAL, date(2026, 2, 25)), (date(2026, 2, 21), date(2026, 2, 28)))
        self.assertEqual(period(DEKADAL, date(2028, 2, 21))[1], date(2028, 2, 29), "leap year")

    def test_months(self):
        self.assertEqual(period(MONTHLY, date(2026, 10, 6)), (date(2026, 10, 1), date(2026, 10, 31)))
        self.assertEqual(period(MONTHLY, date(2026, 12, 31)), (date(2026, 12, 1), date(2026, 12, 31)))


class DueTests(unittest.TestCase):
    at = time(8)

    def test_on_the_first_day_once_its_time_has_come(self):
        self.assertIsNone(due(DEKADAL, self.at, datetime(2026, 10, 11, 7, 45)))
        self.assertEqual(due(DEKADAL, self.at, datetime(2026, 10, 11, 8)), date(2026, 10, 11))
        self.assertIsNone(due(DAILY, self.at, datetime(2026, 10, 6, 7, 59)))
        self.assertEqual(due(DAILY, self.at, datetime(2026, 10, 6, 8)), date(2026, 10, 6))

    def test_late_in_its_period_but_never_one_gone_by(self):
        self.assertEqual(due(DEKADAL, self.at, datetime(2026, 10, 12, 3)), date(2026, 10, 11))
        self.assertEqual(due(MONTHLY, self.at, datetime(2026, 10, 31, 23, 45)), date(2026, 10, 1))
        # the 1st before its time: October's is not due yet, September's is over
        self.assertIsNone(due(MONTHLY, self.at, datetime(2026, 11, 1, 7)))
        self.assertIsNone(due(DAILY, self.at, datetime(2026, 10, 7, 3)), "yesterday's is over")
