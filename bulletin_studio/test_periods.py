"""The periods of the cadences, and when their drafts are due. Pure: runs on the host too,
`uv run --no-project python -m unittest bulletin_studio.test_periods`."""
import unittest
from datetime import date, datetime, time

from .periods import DAILY, DEKADAL, MONTHLY, due, next_draft, period


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


class NextDraftTests(unittest.TestCase):
    """When the studio says the next draft comes, and of which period."""
    at = time(8)

    @staticmethod
    def draft(cadence, at, now, current_done):
        """`next_draft` with the periods done up to the current one, or none of them."""
        current = period(cadence, now.date())[0]
        return next_draft(cadence, at, now, lambda start: current_done and start <= current)

    def test_the_first_day_before_its_time(self):
        self.assertEqual(self.draft(DAILY, self.at, datetime(2026, 10, 6, 7), False),
                         (datetime(2026, 10, 6, 8), date(2026, 10, 6), date(2026, 10, 6)))
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 10, 11, 7, 59), False),
                         (datetime(2026, 10, 11, 8), date(2026, 10, 11), date(2026, 10, 20)))
        self.assertEqual(self.draft(MONTHLY, self.at, datetime(2026, 10, 1), False),
                         (datetime(2026, 10, 1, 8), date(2026, 10, 1), date(2026, 10, 31)))

    def test_due_and_not_done_at_the_next_run(self):
        # its time has come, or the worker missed it: the next quarter of an hour
        self.assertEqual(self.draft(DAILY, self.at, datetime(2026, 10, 6, 8), False)[0],
                         datetime(2026, 10, 6, 8, 15), "the run of 8:00 is under way")
        self.assertEqual(self.draft(DAILY, self.at, datetime(2026, 10, 6, 8, 7, 30), False)[0],
                         datetime(2026, 10, 6, 8, 15))
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 10, 15, 23, 50), False),
                         (datetime(2026, 10, 16), date(2026, 10, 11), date(2026, 10, 20)), "mid-period")

    def test_done_the_next_period(self):
        self.assertEqual(self.draft(DAILY, self.at, datetime(2026, 10, 6, 9), True),
                         (datetime(2026, 10, 7, 8), date(2026, 10, 7), date(2026, 10, 7)))
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 10, 11, 7), True)[1:],
                         (date(2026, 10, 21), date(2026, 10, 31)), "done before its time: made by hand")
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 10, 25, 12), True),
                         (datetime(2026, 11, 1, 8), date(2026, 11, 1), date(2026, 11, 10)))
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 2, 25, 12), True)[1:],
                         (date(2026, 3, 1), date(2026, 3, 10)))

    def test_month_and_year_ends(self):
        self.assertEqual(self.draft(MONTHLY, self.at, datetime(2026, 12, 9), True),
                         (datetime(2027, 1, 1, 8), date(2027, 1, 1), date(2027, 1, 31)))
        self.assertEqual(self.draft(DAILY, self.at, datetime(2026, 12, 31, 12), True)[0],
                         datetime(2027, 1, 1, 8))
        self.assertEqual(self.draft(DEKADAL, self.at, datetime(2026, 12, 31, 12), True)[1:],
                         (date(2027, 1, 1), date(2027, 1, 10)))

    def test_a_period_gone_by_before_the_next_run(self):
        # the next run falls on the next period's first day, which never prepares the past
        late = time(23, 45)
        self.assertEqual(self.draft(DAILY, late, datetime(2026, 10, 6, 23, 50), False),
                         (datetime(2026, 10, 7, 23, 45), date(2026, 10, 7), date(2026, 10, 7)))
        self.assertEqual(self.draft(MONTHLY, self.at, datetime(2026, 12, 31, 23, 55), False),
                         (datetime(2027, 1, 1, 8), date(2027, 1, 1), date(2027, 1, 31)))

    def test_periods_made_ahead_of_time(self):
        # the issues of the next two dekads made by hand: the task skips them
        made = {date(2026, 10, 11), date(2026, 10, 21), date(2026, 11, 1)}
        self.assertEqual(next_draft(DEKADAL, self.at, datetime(2026, 10, 12), made.__contains__),
                         (datetime(2026, 11, 11, 8), date(2026, 11, 11), date(2026, 11, 20)))
        self.assertIsNone(next_draft(DAILY, self.at, datetime(2026, 10, 6), lambda start: True),
                          "a year of issues made ahead: nothing to announce")
