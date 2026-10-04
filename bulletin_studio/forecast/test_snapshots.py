"""The forecast map from the database: published forecasts only, tolerant of what the
office may leave empty, stored in the media storage and replaced on each render."""
import tempfile
from datetime import date, time
from unittest import skipUnless

from django.apps import apps
from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from wagtail.models import Site

DAY = date(2026, 10, 5)


@skipUnless(apps.is_installed("forecastmanager"), "forecastmanager is not installed")
class ForecastSnapshotTests(TestCase):
    def setUp(self):
        from adminboundarymanager.models import AdminBoundary
        from forecastmanager.forecast_settings import (ForecastDataParameters, ForecastPeriod,
                                                       ForecastSetting, WeatherCondition)
        from forecastmanager.models import City, CityForecast, DataValue, Forecast

        settings = ForecastSetting.for_site(Site.objects.get(is_default_site=True))
        daily = ForecastPeriod.objects.create(parent=settings, forecast_effective_time=time(6),
                                              label="Journalière")
        noon = ForecastPeriod.objects.create(parent=settings, forecast_effective_time=time(12),
                                             label="12:00")
        sunny = WeatherCondition.objects.create(parent=settings, symbol="clearsky_day", label="Clear sky")
        temp = ForecastDataParameters.objects.create(parent=settings, parameter="air_temperature",
                                                     name="Temp", parameter_type="numeric")
        ouaga = City.objects.create(name="Ouagadougou", location=Point(-1.5, 12.4))
        bobo = City.objects.create(name="Bobo Dioulasso", location=Point(-4.3, 11.2))

        published = Forecast.objects.create(forecast_date=DAY, effective_period=daily,
                                            status=Forecast.STATUS_PUBLISHED)
        cf = CityForecast.objects.create(parent=published, city=ouaga, condition=sunny)
        DataValue.objects.create(parent=cf, parameter=temp, value="24.4")
        # What an office can leave behind: no condition, an empty numeric value.
        cf = CityForecast.objects.create(parent=published, city=bobo, condition=None)
        DataValue.objects.create(parent=cf, parameter=temp, value="")

        draft = Forecast.objects.create(forecast_date=DAY, effective_period=noon,
                                        status=Forecast.STATUS_DRAFT)
        CityForecast.objects.create(parent=draft, city=ouaga, condition=sunny)

        square = MultiPolygon(Polygon(((-6, 9), (3, 9), (3, 15), (-6, 15), (-6, 9))), srid=4326)
        AdminBoundary.objects.create(level=0, gid_0="BF", name_0="Burkina Faso", geom=square)

    def test_collection_is_the_published_forecast_as_stored(self):
        from bulletin_studio.forecast.snapshots import forecast_collection

        fc = forecast_collection(DAY, time(6))
        props = {f["properties"]["city"]: f["properties"] for f in fc["features"]}
        self.assertEqual(list(props), ["Bobo Dioulasso", "Ouagadougou"])
        self.assertEqual(props["Ouagadougou"]["air_temperature"], 24.4)
        self.assertEqual(props["Ouagadougou"]["effective_period_label"], "Journalière")
        self.assertIsNone(props["Bobo Dioulasso"]["condition"])
        self.assertNotIn("air_temperature", props["Bobo Dioulasso"])
        self.assertIsNone(forecast_collection(DAY, time(12)), "a draft is not drawn")
        self.assertIsNone(forecast_collection(DAY, time(18)))

    def test_snapshot_is_stored_and_replaced(self):
        from bulletin_studio.forecast.snapshots import write_snapshot

        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            name = write_snapshot(DAY, time(6))
            self.assertEqual(name, "forecast_snapshots/2026-10-05/06h00-bulletin.png")
            first = default_storage.open(name).read()
            self.assertTrue(first.startswith(b"\x89PNG"))
            svg = default_storage.open(name.replace(".png", ".svg")).read().decode()
            self.assertEqual(svg.count("<image"), 1, "one icon: Bobo Dioulasso has no condition")

            self.assertEqual(write_snapshot(DAY, time(6)), name)
            _, files = default_storage.listdir("forecast_snapshots/2026-10-05")
            self.assertEqual(sorted(files), ["06h00-bulletin.png", "06h00-bulletin.svg"],
                             "a new render replaces the file, no suffixed copies")
            self.assertIsNone(write_snapshot(DAY, time(12)))
