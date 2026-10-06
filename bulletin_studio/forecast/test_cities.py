"""The city forecasts the city forecast block freezes: published forecasts only, every
value as stored, and the API the block reads them through."""
from datetime import date, time
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.urls import reverse
from wagtail.models import Site

DAY = date(2026, 10, 5)


def publish_city_forecasts():
    """Burkina Faso at 06:00 on DAY: two cities published, one the office left half
    empty, a third city with no forecast at all, and a draft at noon."""
    from forecastmanager.forecast_settings import (ForecastDataParameters, ForecastPeriod,
                                                   ForecastSetting, WeatherCondition)
    from forecastmanager.models import City, CityForecast, DataValue, Forecast

    from bulletin_studio.forecast.models import ForecastMapSettings

    site = Site.objects.get(is_default_site=True)
    fs = ForecastSetting.for_site(site)
    daily = ForecastPeriod.objects.create(parent=fs, forecast_effective_time=time(6), label="Journalière")
    noon = ForecastPeriod.objects.create(parent=fs, forecast_effective_time=time(12), label="12:00")
    settings = ForecastMapSettings.for_site(site)
    settings.periods = ["06:00"]
    settings.save()

    sunny = WeatherCondition.objects.create(parent=fs, symbol="clearsky_day", label="Clear sky")
    params = {name: ForecastDataParameters.objects.create(parent=fs, parameter=name, name=name,
                                                          parameter_type="numeric", parameter_unit=unit)
              for name, unit in (("air_temperature_min", None), ("air_temperature_max", None),
                                 ("wind_speed", "km/h"), ("wind_from_direction", None))}
    ouaga = City.objects.create(name="Ouagadougou", location=Point(-1.5, 12.4))
    bobo = City.objects.create(name="Bobo Dioulasso", location=Point(-4.3, 11.2))
    City.objects.create(name="Pô", location=Point(-1.1, 11.2))

    published = Forecast.objects.create(forecast_date=DAY, effective_period=daily,
                                        status=Forecast.STATUS_PUBLISHED)
    cf = CityForecast.objects.create(parent=published, city=ouaga, condition=sunny)
    for name, value in (("air_temperature_min", "24.4"), ("air_temperature_max", "35.6"),
                        ("wind_speed", "20"), ("wind_from_direction", "225")):
        DataValue.objects.create(parent=cf, parameter=params[name], value=value)
    # What an office can leave behind: no condition, an empty numeric value.
    cf = CityForecast.objects.create(parent=published, city=bobo, condition=None)
    DataValue.objects.create(parent=cf, parameter=params["air_temperature_max"], value="33")
    DataValue.objects.create(parent=cf, parameter=params["wind_speed"], value="")

    draft = Forecast.objects.create(forecast_date=DAY, effective_period=noon, status=Forecast.STATUS_DRAFT)
    CityForecast.objects.create(parent=draft, city=ouaga, condition=sunny)
    return params


@skipUnless(apps.is_installed("forecastmanager"), "forecastmanager is not installed")
class CityForecastTests(TestCase):
    def setUp(self):
        self.params = publish_city_forecasts()
        self.client.force_login(get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))
        self.url = reverse("bulletin_studio:forecast_cities")

    def test_rows_are_the_published_forecast_as_stored(self):
        from bulletin_studio.forecast.cities import table

        found = table(DAY, time(6))
        self.assertEqual((found["date"], found["period"], found["periodLabel"]),
                         ("2026-10-05", "06:00", "Journalière"))
        self.assertEqual(found["units"], {"temperature": "°C", "wind": "km/h"},
                         "the office's unit, else forecastmanager's default")
        bobo, ouaga = found["rows"]
        self.assertEqual(ouaga, {
            "slug": "ouagadougou", "name": "Ouagadougou",
            "icon": "/static/forecastmanager/weathericons/clearsky_day.svg", "condition": "Clear sky",
            "tmax": 35.6, "tmin": 24.4, "temp": None, "wind": 20.0, "windDir": 225.0,
        })
        self.assertEqual((bobo["icon"], bobo["tmax"], bobo["tmin"], bobo["wind"]), (None, 33.0, None, None))
        self.assertIsNone(table(DAY, time(12)), "a draft is not shown")
        self.assertIsNone(table(date(2026, 10, 6), time(6)))

    def test_the_version_follows_the_values(self):
        from forecastmanager.models import DataValue

        from bulletin_studio.forecast.cities import table

        version = table(DAY, time(6))["version"]
        self.assertEqual(table(DAY, time(6))["version"], version)
        DataValue.objects.filter(parameter=self.params["air_temperature_max"], value="33").update(value="34")
        self.assertNotEqual(table(DAY, time(6))["version"], version)

    def test_api(self):
        body = self.client.get(self.url, {"date": "2026-10-05", "period": "06:00"}).json()
        self.assertEqual([c["name"] for c in body["cities"]], ["Bobo Dioulasso", "Ouagadougou", "Pô"],
                         "every city, those with no forecast too")
        self.assertEqual([r["slug"] for r in body["table"]["rows"]], ["bobo-dioulasso", "ouagadougou"])
        self.assertIsNone(self.client.get(self.url, {"date": "2026-10-06", "period": "06:00"}).json()["table"])
        for bad in ({}, {"date": "2026-10-05"}, {"date": "05/10/2026", "period": "06:00"},
                    {"date": "2026-10-05", "period": "6h"}):
            self.assertEqual(self.client.get(self.url, bad).status_code, 400, bad)

    def test_no_city_forecast_block_without_forecastmanager(self):
        app = reverse("bulletin_studio:app")
        self.assertContains(self.client.get(app), f'data-forecast-cities-url="{self.url}"')
        installed = apps.is_installed
        with mock.patch.object(apps, "is_installed", lambda name: name != "forecastmanager" and installed(name)):
            self.assertNotContains(self.client.get(app), "data-forecast-cities-url")
            self.assertEqual(self.client.get(self.url, {"date": "2026-10-05", "period": "06:00"}).status_code, 404)
