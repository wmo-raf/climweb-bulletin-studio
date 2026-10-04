"""A new issue of a template, made on the server: by "New bulletin" in the studio, and
by the daily draft task.

The issue is a draft whose `doc` is the template's, with its forecast blocks frozen
for the issue's date, and whose `html` is empty: only the studio renders html, and it
does when someone publishes (the publish guard in `wagtail_hooks` keeps an unrendered
issue offline). So the only part of the block schema Python knows is the forecast
block, and how columns nest blocks - nothing about layout.
"""
import copy
from datetime import datetime, timedelta

from django.apps import apps
from django.conf import settings
from django.utils import timezone, translation
from django.utils.formats import date_format

from .models import BulletinPage


def walk(blocks):
    """Every block of a document, those inside columns included."""
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        yield block
        if block.get("type") == "columns":
            for column in block.get("columns") or []:
                yield from walk(column)


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

    from wagtail.models import Site

    from .forecast import library
    from .forecast.models import ForecastMapSettings
    from .views import IMAGE_RENDITION

    periods = ForecastMapSettings.for_site(Site.objects.get(is_default_site=True)).periods
    for block in forecast_blocks:
        period = block.get("period") or (periods[0] if periods else None)
        preset = block.get("preset") or library.DAILY_PRESETS[0]
        try:
            period_time = datetime.strptime(period, "%H:%M").time()
            target = day + timedelta(days=int(block.get("dayOffset") or 0))
        except (TypeError, ValueError):
            continue
        if preset not in library.DAILY_PRESETS:  # also keeps it out of the file path
            continue
        block["period"] = period  # explicit, even while its map is missing
        promoted = library.promote(target, period_time, preset, user=user)
        if promoted is None:
            continue
        image, details = promoted
        block.update(period=details["period"], date=details["date"], version=details["version"],
                     periodLabel=details["periodLabel"], imageId=image.pk,
                     src=image.get_rendition(IMAGE_RENDITION).url)


def issue_title(template, day):
    """"Daily weather — 5 October 2026": the date in the site's language, the same
    whoever creates the issue, so a title (and its slug) never depends on the admin
    language of the person who clicked."""
    with translation.override(settings.LANGUAGE_CODE):
        return f"{template.title} — {date_format(day, 'DATE_FORMAT')}"


def create_issue(template, day=None, user=None):
    """The issue of `template` for `day` (today, for the site), as a draft under the
    same product page."""
    template = template.get_latest_revision_as_object()
    day = day or timezone.localdate()
    doc = copy.deepcopy(template.doc) if isinstance(template.doc, dict) else {}
    freeze_forecasts(doc.get("blocks"), day, user=user)

    parent = template.get_parent()
    # live=False must be set *before* add_child, or Wagtail publishes the page.
    issue = BulletinPage(doc=doc, html="", is_template=False, live=False,
                         date=day, source_template_id=template.pk)
    issue.apply_title(issue_title(template, day), parent=parent)
    parent.add_child(instance=issue)
    issue.save_revision(user=user)
    return issue
