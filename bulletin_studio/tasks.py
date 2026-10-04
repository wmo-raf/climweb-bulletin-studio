"""Celery tasks, found by ClimWeb's `app.autodiscover_tasks()` and run by its worker."""
from celery import shared_task
from celery_singleton import Singleton


# Singleton: hooks can fire it several times in a row (a pull, then a forecaster's
# form); a render already queued or running covers them, as it redraws everything.
@shared_task(base=Singleton, lock_expiry=600, name="bulletin_studio.render_daily_forecast_maps")
def render_daily_forecast_maps():
    from .forecast.snapshots import render_daily

    return render_daily()
