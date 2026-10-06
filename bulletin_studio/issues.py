"""A new issue of a template, made on the server: by "New bulletin" in the studio, and
by the draft task (`create_drafts`, every quarter of an hour).

The issue is a draft covering one period of the template's cadence (`periods`): its
`date` and `valid_until` are that period's, its title names it, its `doc` is the
template's with the forecast and city forecast blocks frozen from the period's first
day, and its `html` is empty: only the studio
renders html, and it does when someone publishes (the publish guard in `wagtail_hooks`
keeps an unrendered issue offline). So the only parts of the block schema Python knows
are these two blocks' data, and how columns nest blocks - nothing about layout.
"""
import copy
import logging
from datetime import datetime, timedelta

from django.apps import apps
from django.conf import settings
from django.utils import timezone, translation
from django.utils.formats import date_format

from . import periods
from .models import BulletinPage

logger = logging.getLogger(__name__)


def walk(blocks):
    """Every block of a document, those inside columns included."""
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        yield block
        if block.get("type") == "columns":
            for column in block.get("columns") or []:
                yield from walk(column)


def daily_periods():
    """The periods the office set as the forecast of the day ("06:00"...)."""
    from wagtail.models import Site

    from .forecast.models import ForecastMapSettings

    return ForecastMapSettings.for_site(Site.objects.get(is_default_site=True)).periods


def recipe(block, day, periods):
    """(period time, target date) of a forecast or city forecast block: its period,
    the office's first by default, on `day + dayOffset`. None if unreadable.
    The period becomes explicit in the block, even while its forecast is missing."""
    period = block.get("period") or (periods[0] if periods else None)
    try:
        period_time = datetime.strptime(period, "%H:%M").time()
        target = day + timedelta(days=int(block.get("dayOffset") or 0))
    except (TypeError, ValueError):
        return None
    block["period"] = period
    return period_time, target


def freeze_forecasts(blocks, day, user=None):
    """Fill each forecast block with the map of `day + dayOffset`, promoted into the
    library. A block whose map is not drawn yet stays empty: the studio fills it when
    the issue is opened, if the map has come since."""
    forecast_blocks = [b for b in walk(blocks) if b.get("type") == "forecast"]
    for block in forecast_blocks:
        # whatever a template carries, an issue only shows the map of its own date
        block.update(date=None, src=None, imageId=None, version=None, periodLabel="")
    if not forecast_blocks or not apps.is_installed("forecastmanager"):
        return

    from .forecast import library
    from .views import IMAGE_RENDITION

    periods = daily_periods()
    for block in forecast_blocks:
        preset = block.get("preset") or library.DAILY_PRESETS[0]
        if preset not in library.DAILY_PRESETS:  # also keeps it out of the file path
            continue
        slot = recipe(block, day, periods)
        if slot is None:
            continue
        period_time, target = slot
        promoted = library.promote(target, period_time, preset, user=user)
        if promoted is None:
            continue
        image, details = promoted
        block.update(period=details["period"], date=details["date"], version=details["version"],
                     periodLabel=details["periodLabel"], imageId=image.pk,
                     src=image.get_rendition(IMAGE_RENDITION).url)


# what a city forecast block holds of the forecast it shows
CITY_TABLE = ("date", "periodLabel", "units", "rows", "version")


def freeze_city_forecasts(blocks, day):
    """Fill each city forecast block with the forecast of `day + dayOffset`, its rows
    copied into the document. Nothing published for that slot yet: the block stays
    empty, and the studio fills it when the issue is opened, if it has come since. The
    choice of cities and their order stay as the template has them: the rows are
    every city's, the studio picks among them when it renders."""
    city_blocks = [b for b in walk(blocks) if b.get("type") == "cities"]
    for block in city_blocks:
        block.update(date=None, periodLabel="", units=None, rows=None, version=None)
    if not city_blocks or not apps.is_installed("forecastmanager"):
        return

    from .forecast import cities

    periods = daily_periods()
    for block in city_blocks:
        slot = recipe(block, day, periods)
        found = slot and cities.table(slot[1], slot[0])
        if found:
            block.update({key: found[key] for key in CITY_TABLE})


def issue_title(title, cadence, start, end=None):
    """"Météo journalière — 5 octobre 2026", "Bulletin mensuel — octobre 2026",
    "Bulletin décadaire — 1 octobre 2026 – 10 octobre 2026": the period in the active
    language, the admin's (Wagtail activates it in the views, `create_drafts` the
    template author's). Django's own formats only, so no catalog of ours: a range
    repeats the month and year, as "1–10 octobre" would need rules for each language."""
    end = end or start
    if cadence == periods.MONTHLY:
        label = date_format(start, "YEAR_MONTH_FORMAT")
    elif end != start:
        label = f"{date_format(start, 'DATE_FORMAT')} – {date_format(end, 'DATE_FORMAT')}"
    else:
        label = date_format(start, "DATE_FORMAT")
    return f"{title} — {label}"


def create_issue(template, day=None, user=None):
    """The issue of `template` for the period containing `day` (today, for the site), as
    a draft under the same product page."""
    # the settings from the row, which the draft task reads too; the document from the
    # latest revision, which the studio saves
    start, end = periods.period(
        template.cadence, day or timezone.localdate(timezone=timezone.get_default_timezone()))
    cadence, template = template.cadence, template.get_latest_revision_as_object()
    doc = copy.deepcopy(template.doc) if isinstance(template.doc, dict) else {}
    freeze_forecasts(doc.get("blocks"), start, user=user)
    freeze_city_forecasts(doc.get("blocks"), start)

    parent = template.get_parent()
    # live=False must be set *before* add_child, or Wagtail publishes the page.
    issue = BulletinPage(doc=doc, html="", is_template=False, live=False, date=start,
                         valid_until=end if end != start else None, cadence=cadence,
                         source_template_id=template.pk)
    issue.apply_title(issue_title(template.title, cadence, start, end), parent=parent)
    parent.add_child(instance=issue)
    issue.save_revision(user=user)
    return issue


def author_language(template):
    """The admin language of whoever last saved the template: a draft the task prepares
    has no admin of its own to follow."""
    revision = template.latest_revision
    if revision is None or revision.user is None:
        return settings.LANGUAGE_CODE
    from wagtail.users.models import UserProfile

    return UserProfile.get_for_user(revision.user).get_preferred_language()


def create_drafts(now=None):
    """The issue of the current period of each template set to prepare one, once its time
    has come on the period's first day (site time). Once a period per template: not when
    an issue of it exists already (made by hand, say), nor again after its draft was
    deleted."""
    now = timezone.localtime(now, timezone.get_default_timezone())
    made = []
    for template in BulletinPage.objects.filter(is_template=True, draft_at__isnull=False):
        start = periods.due(template.cadence, template.draft_at, now.replace(tzinfo=None))
        if start is None or (template.last_draft and template.last_draft >= start):
            continue
        try:
            if not template.issues.filter(date=start).exists():
                with translation.override(author_language(template)):
                    made.append(create_issue(template, start))
        except Exception:  # the next run tries again; the other templates go on
            logger.exception("Draft: could not prepare the issue of %s of %r", start, template.title)
            continue
        BulletinPage.objects.filter(pk=template.pk).update(last_draft=start)
    if made:
        logger.info("Draft: %s", ", ".join(issue.title for issue in made))
    return made
