"""Celery tasks, found by ClimWeb's `app.autodiscover_tasks()` and run by its worker."""
import importlib
import logging

from celery import shared_task
from celery.schedules import crontab
from celery_singleton import Singleton
from django.conf import settings

logger = logging.getLogger(__name__)


# Singleton: hooks can fire it several times in a row (a pull, then a forecaster's
# form); a render already queued or running covers them, as it redraws everything.
@shared_task(base=Singleton, lock_expiry=600, name="bulletin_studio.render_daily_forecast_maps")
def render_daily_forecast_maps():
    from .forecast.snapshots import render_daily

    return render_daily()


@shared_task(base=Singleton, lock_expiry=600, name="bulletin_studio.create_daily_drafts")
def create_daily_drafts():
    from .issues import create_daily_drafts as create

    return [issue.pk for issue in create()]


def _celery_app():
    """ClimWeb's Celery app, named in its settings (cap-composer finds it the same way):
    beat only runs the periodic tasks registered on it."""
    if not getattr(settings, "CELERY_APP", None):
        return None
    module, name = settings.CELERY_APP.split(":")
    return getattr(importlib.import_module(module), name)


app = _celery_app()
if app is None:
    logger.warning("No CELERY_APP setting: daily drafts are not scheduled.")
else:
    @app.on_after_finalize.connect
    def schedule_daily_drafts(sender, **kwargs):
        # Every quarter of an hour, the step the templates' times are rounded to. The
        # name is final: beat's DatabaseScheduler keeps the rows of renamed tasks.
        sender.add_periodic_task(crontab(minute="*/15"), create_daily_drafts.s(),
                                 name="bulletin-studio-daily-drafts")
