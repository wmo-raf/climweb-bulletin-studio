# Dev stack only: gives today a forecast for the daily periods a pull left empty.
#
# A pull only returns hours to come, so on a database started after 06:00 today has no
# 06:00 forecast, and today's map cannot be drawn. For each period set in Settings >
# Forecast map, this copies the nearest later published forecast of that period onto
# today - tomorrow's values under today's date, test data, never for a real site - then
# redraws the maps. Idempotent: a period today already has is left alone. The nightly
# clear_old_forecasts removes the copy with the rest of the day.
#
#   docker compose -f docker-compose.dev.yml exec -T climweb \
#     /climweb/web/src/climweb/manage.py shell < dev/forecast/fill_today.py
from datetime import datetime

from bulletin_studio.forecast.models import ForecastMapSettings
from bulletin_studio.forecast.snapshots import render_daily
from django.db import transaction
from django.utils import timezone
from forecastmanager.models import CityForecast, DataValue, Forecast
from wagtail.models import Site

today = timezone.localdate(timezone=timezone.get_default_timezone())
periods = ForecastMapSettings.for_site(Site.objects.get(is_default_site=True)).periods
if not periods:
    print("No daily period set (Settings > Forecast map): run dev/forecast/bootstrap.py first.")

for period in periods:
    at = datetime.strptime(period, "%H:%M").time()
    published = Forecast.objects.filter(effective_period__forecast_effective_time=at,
                                        status=Forecast.STATUS_PUBLISHED)
    if published.filter(forecast_date=today).exists():
        print(f"{today} {period}: already there")
        continue
    source = published.filter(forecast_date__gt=today).order_by("forecast_date").first()
    if source is None:
        print(f"{today} {period}: no later forecast to copy, pull first")
        continue
    with transaction.atomic():
        copy = Forecast.objects.create(forecast_date=today, effective_period=source.effective_period,
                                       source=source.source, status=source.status)
        for cf in source.city_forecasts.prefetch_related("data_values"):
            new = CityForecast.objects.create(parent=copy, city=cf.city, condition=cf.condition,
                                              data_source=cf.data_source)
            DataValue.objects.bulk_create(DataValue(parent=new, parameter=dv.parameter, value=dv.value)
                                          for dv in cf.data_values.all())
    print(f"{today} {period}: copied from {source.forecast_date} ({source.city_forecasts.count()} cities)")

print("maps:", ", ".join(render_daily()) or "none")
