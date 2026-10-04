# Seeds the dev database with what a forecast pull needs, from the meteoburkina
# fixtures: the 11 cities, the Burkina Faso boundaries (country + 13 regions), the
# country in the boundary settings, the yr pull switched on, and 06:00 as the day's
# forecast for the map. Idempotent. Run it
# through the Django shell, after dev-bootstrap.py:
#
#   docker compose -f docker-compose.dev.yml exec -T climweb \
#     /climweb/web/src/climweb/manage.py shell < dev/forecast/bootstrap.py
#
# Then pull for real (met.no, a few seconds for 11 cities):
#
#   docker compose -f docker-compose.dev.yml exec climweb \
#     /climweb/web/src/climweb/manage.py generate_auto_forecast
import json
import pathlib

from adminboundarymanager.models import AdminBoundary, AdminBoundarySettings, Country
from bulletin_studio.forecast.models import ForecastMapSettings
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point
from forecastmanager.forecast_settings import ForecastSetting
from forecastmanager.models import City
from wagtail.models import Site

# The compose file mounts ./dev here; the shell reads this script from stdin, so it
# has no __file__ to resolve the fixtures from.
FIX = pathlib.Path("/app/dev/forecast/fixtures")
site = Site.objects.get(is_default_site=True)

# Cities: name and location of the first forecast's features.
collections = json.loads((FIX / "forecasts.json").read_text())
created = 0
for feature in collections[0]["features"]:
    lon, lat = feature["geometry"]["coordinates"]
    _, was_created = City.objects.get_or_create(
        name=feature["properties"]["city"], defaults={"location": Point(lon, lat, srid=4326)})
    created += was_created
print(f"cities: {City.objects.count()} ({created} created)")

# Boundaries: level 0 and 1 as the boundary search returns them, geometry in `feature`.
if not AdminBoundary.objects.filter(gid_0="BF").exists():
    fields = ["level", "gid_0", "gid_1", "gid_2", "gid_3", "name_0", "name_1", "name_2", "name_3"]
    for level in (0, 1):
        for row in json.loads((FIX / f"admin{level}.json").read_text()):
            geom = GEOSGeometry(json.dumps(row["feature"]), srid=4326)
            if geom.geom_type == "Polygon":
                geom = MultiPolygon(geom, srid=4326)
            AdminBoundary.objects.create(geom=geom, **{f: row.get(f) for f in fields})
print("boundaries:", {lvl: AdminBoundary.objects.filter(gid_0="BF", level=lvl).count() for lvl in (0, 1)})

boundary_settings = AdminBoundarySettings.for_site(site)
if not boundary_settings.countries.exists():
    Country.objects.create(parent=boundary_settings, country="BF")
print("boundary countries:", [c["code"] for c in boundary_settings.countries_list])

# The pull: yr, published straight away, as on meteoburkina.
forecast_setting = ForecastSetting.for_site(site)
forecast_setting.enable_auto_forecast = True
forecast_setting.forecast_provider = "yr"
forecast_setting.auto_publish_forecasts = True
forecast_setting.save()
print(f"auto forecast: {forecast_setting.forecast_provider}, published")

# The forecast map: the 06:00 period is the day's forecast, as on meteoburkina,
# drawn for today and tomorrow after each pull.
map_settings = ForecastMapSettings.for_site(site)
if not map_settings.periods:
    map_settings.periods, map_settings.days_ahead = ["06:00"], 1
    map_settings.save()
print(f"forecast map: periods {map_settings.periods}, {map_settings.days_ahead} day(s) ahead")
