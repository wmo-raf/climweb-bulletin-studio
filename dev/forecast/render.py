# /// script
# requires-python = ">=3.10"
# dependencies = ["cairosvg", "shapely"]
# ///
"""The forecast map's design loop: frozen JSON -> PNG + SVG, no Django, no database.

    uv run dev/forecast/render.py --list
    uv run dev/forecast/render.py --preset social
    uv run dev/forecast/render.py --all --settings dev/forecast/settings.example.json

The drawing itself is `bulletin_studio.forecast.render`, the module the site runs;
this script only feeds it the fixtures and writes files.

fixtures/: meteoburkina.bf responses of 2026-08-31 - forecasts.json
(`/api/forecasts?format=json`), admin0.json / admin1.json
(`/api/admin-boundary/search?level=N`, geometries simplified to 3-5 thousandths of a
degree, 7.3 MB -> 108 KB).
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
FIX = HERE / "fixtures"
sys.path.insert(0, str(HERE.parents[1]))  # the repo root, for bulletin_studio

from bulletin_studio.forecast.render import (PRESETS, THEMES, Settings,  # noqa: E402
                                             build_svg, data_uri, filter_cities, period_of)

# The icons are read from the sibling forecastmanager checkout rather than copied.
ICONS = HERE.parents[2] / "forecastmanager" / "forecastmanager" / "static" / "forecastmanager" / "weathericons"


def icon_uri(condition):
    # ponytail: 130px PNGs - the MET Norway SVGs are animated and have no root
    # viewBox, cairosvg would draw them badly. Switch if we want vector output.
    return data_uri(ICONS / f"{condition}.png", "image/png")


def load_levels(detail_level):
    """Geometries of levels 1..detail_level found in fixtures/."""
    out = []
    for lvl in range(1, detail_level + 1):
        p = FIX / f"admin{lvl}.json"
        if p.exists():
            out.append([row["feature"] for row in json.loads(p.read_text())])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=list(PRESETS))
    ap.add_argument("--all", action="store_true", help="every preset")
    ap.add_argument("--settings", help="JSON settings file")
    ap.add_argument("--date")
    ap.add_argument("--period")
    ap.add_argument("--theme", choices=list(THEMES), help="overrides the setting")
    ap.add_argument("--outdir", default=str(HERE / "out"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    collections = json.loads((FIX / "forecasts.json").read_text())
    if a.list:
        for c in collections:
            print(f'{c["date"]}  {period_of(c)}  ({len(c["features"])} villes)')
        return

    try:
        st = Settings.load(a.settings)
    except ValueError as exc:
        raise SystemExit(str(exc))
    if a.theme:
        st.theme = a.theme
    presets = list(PRESETS) if a.all else [a.preset] if a.preset else st.presets
    periods = [a.period] if a.period else st.periods

    admin0 = json.loads((FIX / "admin0.json").read_text())[0]
    levels = load_levels(st.detail_level)
    outdir = pathlib.Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    import cairosvg
    for period in periods:
        match = [c for c in collections
                 if (a.date is None or c["date"] == a.date)
                 and (period is None or period_of(c) == period)]
        if not match:
            raise SystemExit(f"Aucun créneau « {period} ». `--list` pour les voir.")
        fc = filter_cities(match[0], st.featured_cities)

        for name in presets:
            svg = build_svg(fc, admin0, levels, PRESETS[name], st, icon=icon_uri)
            stem = outdir / f"{name}-{fc['date']}-{period_of(fc).replace(':', 'h')}"
            stem.with_suffix(".svg").write_text(svg)
            cairosvg.svg2png(bytestring=svg.encode(), write_to=str(stem.with_suffix(".png")))
            print(f'{name:9} {fc["date"]} {period_of(fc):12} '
                  f'{len(fc["features"])} villes -> {stem.name}.png')


if __name__ == "__main__":
    main()
