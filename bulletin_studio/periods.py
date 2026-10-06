"""The period an issue covers, from its template's cadence: a day, a dekad (the 1st to
the 10th, the 11th to the 20th, the 21st to the end of the month) or a month.

An issue covers the period that begins: the dekadal bulletin prepared on the 11th is
the outlook of the 11th to the 20th. Pure: no Django, no database.
"""
import calendar
from datetime import timedelta

DAILY, DEKADAL, MONTHLY = "daily", "dekadal", "monthly"
CADENCES = (DAILY, DEKADAL, MONTHLY)


def last_of_month(day):
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def period(cadence, day):
    """(first day, last day) of the period of `cadence` that contains `day` - the day
    itself for a daily template, or an unknown cadence."""
    if cadence == DEKADAL:
        start = day.replace(day=min((day.day - 1) // 10, 2) * 10 + 1)
        return start, (start + timedelta(days=9) if start.day < 21 else last_of_month(day))
    if cadence == MONTHLY:
        return day.replace(day=1), last_of_month(day)
    return day, day


def due(cadence, draft_at, now):
    """The first day of the period whose draft is due at `now` (a naive local datetime):
    the current period's, once `draft_at` has passed on its first day. Never an older
    one - a draft prepared late in its period still serves (a worker stuck on the 11th
    prepares the dekad's on the 12th), one of a period gone by would not."""
    start, _ = period(cadence, now.date())
    if start == now.date() and now.time() < draft_at:
        return None
    return start
