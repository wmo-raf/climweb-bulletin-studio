"""From the database to files: the forecast map of one date and period, drawn by
`render` and stored in the media storage.

The values are drawn as forecastmanager stores them - published forecasts only, never
recomputed: they are the national met office's.

Import this module lazily: forecastmanager is only installed on meteorological
ClimWeb sites (IS_METEOROLOGICAL), and bulletin_studio must start without it.
"""
import json
from functools import reduce

import cairosvg
from adminboundarymanager.models import AdminBoundary
from django.contrib.staticfiles import finders
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from forecastmanager.models import CityForecast, Forecast

from . import render

MEDIA_DIR = "forecast_snapshots"


def forecast_collection(date, period_time):
    """The published forecast of one date and period, in `/api/forecasts`' shape, or
    None if there is none.

    Built here rather than with `Forecast.get_geojson()`, which crashes on a city
    without a condition and queries the values city by city."""
    rows = (CityForecast.objects
            .filter(parent__forecast_date=date,
                    parent__effective_period__forecast_effective_time=period_time,
                    parent__status=Forecast.STATUS_PUBLISHED)
            .select_related("parent__effective_period", "city", "condition")
            .prefetch_related("data_values__parameter")
            .order_by("city__name"))
    features = []
    for cf in rows:
        props = {
            "effective_period_label": cf.parent.effective_period.label,
            "city": cf.city.name,
            "city_slug": cf.city.slug,
            "condition": cf.condition.symbol if cf.condition else None,
            "condition_label": cf.condition.label if cf.condition else None,
        }
        for dv in cf.data_values.all():
            try:
                props[dv.parameter.parameter] = dv.parsed_value
            except (TypeError, ValueError):  # an empty or non-numeric "numeric" value
                pass
        features.append({"type": "Feature", "properties": props,
                         "geometry": {"type": "Point", "coordinates": cf.city.coordinates}})
    if not features:
        return None
    return {"type": "FeatureCollection", "date": date.isoformat(), "features": features}


def boundaries(detail_level):
    """The country as `render` wants it (`name_0`, GeoJSON `feature`) and the
    geometries of the admin levels below it, or (None, []) without boundaries.
    A site covering several countries gets them merged into one outline."""
    countries = list(AdminBoundary.objects.filter(level=0))
    if not countries:
        return None, []
    geom = reduce(lambda a, b: a.union(b), (c.geom for c in countries))
    admin0 = {"name_0": " / ".join(c.name_0 for c in countries if c.name_0),
              "feature": json.loads(geom.geojson)}
    levels = [[json.loads(b.geom.geojson) for b in AdminBoundary.objects.filter(level=lvl).only("geom")]
              for lvl in range(1, detail_level + 1)]
    return admin0, levels


def icon_href(condition):
    """forecastmanager's PNG icon for a condition, inlined. Read from the app's
    static files, not from STATIC_ROOT: the worker has no collectstatic."""
    path = condition and finders.find(f"forecastmanager/weathericons/{condition}.png")
    return render.data_uri(path, "image/png") if path else None


def render_snapshot(date, period_time, preset="bulletin", settings=None):
    """(svg, png) of the map, or None when nothing is published for that slot."""
    st = settings or render.Settings()
    fc = forecast_collection(date, period_time)
    if fc is None:
        return None
    admin0, levels = boundaries(st.detail_level)
    if admin0 is None:
        raise ValueError("No country boundary (adminboundarymanager level 0) to draw the map on.")
    svg = render.build_svg(render.filter_cities(fc, st.featured_cities), admin0, levels,
                           render.PRESETS[preset], st, icon=icon_href)
    return svg, cairosvg.svg2png(bytestring=svg.encode())


def snapshot_name(date, period_time, preset, ext):
    return f"{MEDIA_DIR}/{date:%Y-%m-%d}/{period_time:%Hh%M}-{preset}.{ext}"


def write_snapshot(date, period_time, preset="bulletin", settings=None):
    """Render the map and store it, replacing the previous render of that slot.
    Returns the stored PNG's name, or None when nothing is published to draw."""
    out = render_snapshot(date, period_time, preset, settings)
    if out is None:
        return None
    svg, png = out
    for ext, content in (("svg", svg.encode()), ("png", png)):
        name = snapshot_name(date, period_time, preset, ext)
        if default_storage.exists(name):
            default_storage.delete(name)
        default_storage.save(name, ContentFile(content))
    return snapshot_name(date, period_time, preset, "png")
