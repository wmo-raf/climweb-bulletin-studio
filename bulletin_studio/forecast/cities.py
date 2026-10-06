"""The city forecasts of one date and period as rows, for the studio's city forecast
block: a grid of cities with their icon, temperatures and wind, which the editor lays
out as HTML - text on the page, where the forecast map is an image.

An issue copies the rows into its document, as the map block freezes its image: the
forecast of 5 October stays that of 5 October, once forecastmanager has purged it or a
later pull has changed it. The values are forecastmanager's as stored, never
recomputed; a parameter the office does not publish is left empty, and the block
leaves out what no city has.

Import this module lazily, like `snapshots`: it needs forecastmanager.
"""
import hashlib
import json
import math
from urllib.parse import urljoin

from django.conf import settings
from forecastmanager.constants import WEATHER_PARAMETERS_AS_DICT
from forecastmanager.forecast_settings import ForecastDataParameters
from forecastmanager.models import City

from .snapshots import forecast_collection

# a row's values, from forecastmanager's parameters
FIELDS = {
    "tmax": "air_temperature_max",
    "tmin": "air_temperature_min",
    # the only temperature of a site that publishes no min/max
    "temp": "air_temperature",
    "wind": "wind_speed",
    "windDir": "wind_from_direction",  # where the wind comes from, in degrees
}


def icon_url(symbol):
    """forecastmanager's icon for a condition, by its plain static path. Not `static()`:
    under ClimWeb's ManifestStaticFilesStorage that is a hashed name, which changes with
    the icon, while a published bulletin keeps its url for good. collectstatic keeps the
    unhashed copy too."""
    return urljoin(settings.STATIC_URL, f"forecastmanager/weathericons/{symbol}.svg") if symbol else None


def units():
    """The units of the temperatures and of the wind speed, as the site has them: the
    office's own, else forecastmanager's defaults for these parameters."""
    found = {p.parameter: p.units for p in ForecastDataParameters.objects.all()}

    def unit(*parameters):
        for parameter in parameters:
            if found.get(parameter):
                return found[parameter]
        return WEATHER_PARAMETERS_AS_DICT.get(parameters[0], {}).get("unit")

    return {"temperature": unit("air_temperature_max", "air_temperature_min", "air_temperature"),
            "wind": unit("wind_speed")}


def _number(value):
    # a "text" parameter, or a NaN JSON would not carry
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def table(day, period_time):
    """The published forecast of that slot as the block freezes it, or None when
    nothing is published for it. `version` changes with any value: the studio offers
    to update an issue whose rows differ from the forecast's current ones."""
    fc = forecast_collection(day, period_time)
    if fc is None:
        return None
    rows = [{
        "slug": f["properties"]["city_slug"],
        "name": f["properties"]["city"],
        "icon": icon_url(f["properties"]["condition"]),
        "condition": f["properties"]["condition_label"] or "",
        **{key: _number(f["properties"].get(parameter)) for key, parameter in FIELDS.items()},
    } for f in fc["features"]]
    data = {
        "date": day.isoformat(),
        "period": f"{period_time:%H:%M}",
        "periodLabel": fc["features"][0]["properties"]["effective_period_label"],
        "units": units(),
        "rows": rows,
    }
    return {**data, "version": hashlib.sha1(json.dumps(data, sort_keys=True).encode()).hexdigest()}


def all_cities():
    """Every city, for the block's choice of cities - including those with nothing
    published for the slot at hand."""
    return [{"slug": slug, "name": name} for slug, name in City.objects.values_list("slug", "name")]
