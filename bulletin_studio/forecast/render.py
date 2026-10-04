"""Forecast FeatureCollection -> SVG map of the country, one marker per city.

Pure functions: the caller loads the forecast, the boundaries and the icons, and
rasterizes the SVG (cairosvg) if it needs a PNG. Three levels, not to be confused:

  DERIVED   never configurable - simplification tolerance, map aspect, and every
            graphic size, all multiples of `scale`.
  PRESET    PRESETS: canvas, chrome, density. One entry = one output format.
  SETTING   Settings: what a met service wants to change. These fields map one to
            one onto a Wagtail BaseSiteSetting.

Inputs are the shapes of forecastmanager's `/api/forecasts` (one FeatureCollection
per date and period) and adminboundarymanager's boundary search (`feature` holds
the GeoJSON geometry).
"""
import base64
import dataclasses
import html
import json
import math
import pathlib

FONT = "Inter, Noto Sans, DejaVu Sans, sans-serif"
FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]

# --- PRESETS ----------------------------------------------------------------
# height=None: free height, the frame follows the country's aspect (no dead space).
# Fixed height: imposed by the destination platform; the map is *contained* and the
# leftover space becomes the chrome area.
PRESETS = {
    "web": dict(width=1600, height=None, chrome="full", density="full"),
    "bulletin": dict(width=2480, height=None, chrome="min", density="full"),  # ≈210 mm @300 dpi
    "social": dict(width=1200, height=900, chrome="full", density="normal"),  # 4:3
    "square": dict(width=1080, height=1080, chrome="full", density="normal"),
}

THEMES = {
    "light": {
        "bg": "#ffffff", "land": "#eef3f7", "land_edge": "#5b7d99", "prov": "#c3d2de",
        "title": "#0f2233", "sub": "#64798c", "city": "#33475b", "temp": "#0f2233",
        "minmax": "#8496a6", "accent": "#e8710a",
    },
    "dark": {
        "bg": "#0d1622", "land": "#1b2b3d", "land_edge": "#4a7295", "prov": "#33495f",
        "title": "#ffffff", "sub": "#7d96ad", "city": "#b9cbdb", "temp": "#ffffff",
        "minmax": "#7d96ad", "accent": "#f5a623",
    },
}

# How much information per city. The real lever against overlaps is
# Settings.featured_cities; this only degrades gracefully on a small canvas.
DENSITY = {"icon": 0, "temp": 1, "normal": 2, "full": 3}


@dataclasses.dataclass
class Settings:
    """The SETTINGS. They map one to one onto a Wagtail BaseSiteSetting."""
    # Identity - available tokens: {pays} {date} {creneau}
    title_template: str = "Prévisions météo"
    source_text: str = "Source : ClimWeb / forecastmanager · icônes MET Norway"
    logo: str | None = None
    # Appearance
    theme: str = "light"
    colors: dict = dataclasses.field(default_factory=dict)  # one-off overrides of the theme
    detail_level: int = 1  # 0 = country only, 1 = + regions, 2 = + provinces
    # Content
    featured_cities: list | None = None  # None = all
    density: str | None = None  # None = the preset's
    temp_unit: str = "°"
    # Production
    periods: list = dataclasses.field(default_factory=lambda: ["Journalière"])
    presets: list = dataclasses.field(default_factory=lambda: ["web"])

    @classmethod
    def load(cls, path):
        """Settings from a JSON file, defaults for what it leaves out. Unknown keys
        raise ValueError: a typo must not be silently ignored."""
        if not path:
            return cls()
        known = {f.name for f in dataclasses.fields(cls)}
        data = json.loads(pathlib.Path(path).read_text())
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Réglages inconnus : {', '.join(sorted(unknown))}")
        return cls(**data)


# --- geometry ---------------------------------------------------------------

def merc_y(lat):
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def bbox_of(geom):
    xs, ys = [], []

    def walk(o):
        if isinstance(o[0], (int, float)):
            xs.append(o[0]), ys.append(o[1])
        else:
            for c in o:
                walk(c)

    walk(geom["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


def make_projector(bbox, box):
    """lon/lat -> px (Web Mercator), contained and centered in box = (x, y, w, h).

    Also returns the px per degree of longitude: that is what sets the
    simplification tolerance, so it is never tuned by hand.
    """
    minlon, minlat, maxlon, maxlat = bbox
    y0, y1 = merc_y(minlat), merc_y(maxlat)
    bx, by, bw, bh = box
    ppd = min(bw / (maxlon - minlon), bh / (y1 - y0))
    ox = bx + (bw - ppd * (maxlon - minlon)) / 2
    oy = by + (bh - ppd * (y1 - y0)) / 2
    return lambda lon, lat: (ox + (lon - minlon) * ppd, oy + (y1 - merc_y(lat)) * ppd), ppd


def simplified_path(geom, tol, proj):
    """GeoJSON (Multi)Polygon -> one SVG 'd', simplified to ~1 px (holes: evenodd)."""
    from shapely.geometry import mapping, shape
    g = mapping(shape(geom).simplify(tol, preserve_topology=True))
    polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
    parts = []
    for poly in polys:
        for ring in poly:
            pts = (proj(x, y) for x, y in ring)
            parts.append("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")
    return "".join(parts)


# --- helpers ----------------------------------------------------------------

def data_uri(path, mime):
    """A file inlined as a data: URI, so the SVG is self-contained. None if missing."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def period_of(fc):
    return fc["features"][0]["properties"]["effective_period_label"] if fc["features"] else "?"


def fr_date(iso):
    y, m, d = (int(v) for v in iso.split("-"))
    return f"{d} {FR_MONTHS[m - 1]} {y}"


def esc(s):
    return html.escape(str(s), quote=False)


# --- rendering --------------------------------------------------------------

def build_svg(fc, admin0, levels, preset, st, icon=None):
    """The map as an SVG string.

    fc       one forecast FeatureCollection (one date, one period)
    admin0   the country's boundary row (`feature`, `name_0`)
    levels   per admin level below the country, a list of GeoJSON geometries
    preset   an entry of PRESETS
    st       Settings
    icon     condition symbol -> image href (a data: URI for a self-contained SVG),
             or None to draw no icon
    """
    C = {**THEMES[st.theme], **st.colors}
    W, Hfix = preset["width"], preset["height"]
    chrome, density = preset["chrome"], DENSITY[st.density or preset["density"]]

    # DERIVED - a single scale variable. Free height: the width rules.
    # Fixed canvas: the short side, so nothing overflows on a square.
    s = W / 1500 if Hfix is None else min(W, Hfix) / 1000
    margin = 40 * s          # ≈2.7 % of the width when free, ≈4 % of the short side when fixed
    head = (150 if chrome == "full" else 76) * s
    foot = (64 if chrome == "full" else 52) * s

    country = admin0["feature"]
    bbox = bbox_of(country)
    aspect = (bbox[2] - bbox[0]) / (merc_y(bbox[3]) - merc_y(bbox[1]))

    map_w = W - 2 * margin
    map_h = (map_w / aspect) if Hfix is None else (Hfix - head - foot)
    H = head + map_h + foot
    inset = 0.03 * min(map_w, map_h)  # breathing room: the country does not touch the frame
    proj, ppd = make_projector(bbox, (margin + inset, head + inset,
                                      map_w - 2 * inset, map_h - 2 * inset))
    tol = 1.2 / ppd  # ~1 px: finer would be invisible, coarser would show

    tokens = dict(pays=admin0["name_0"], date=fr_date(fc["date"]), creneau=period_of(fc))
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
         f'width="{W:.0f}" height="{H:.0f}" viewBox="0 0 {W:.0f} {H:.0f}">',
         f'<rect width="100%" height="100%" fill="{C["bg"]}"/>']

    def text(x, y, txt, size, color, weight=400, anchor="start", ls=0):
        o.append(f'<text x="{x:.0f}" y="{y:.0f}" fill="{color}" font-family="{FONT}" '
                 f'font-size="{size * s:.1f}" font-weight="{weight}" text-anchor="{anchor}" '
                 f'letter-spacing="{ls * s:.2f}">{esc(txt)}</text>')

    # --- header
    if chrome == "full":
        text(margin, 72 * s, st.title_template.format(**tokens), 46, C["title"], 700, ls=-1)
        text(margin, 108 * s, tokens["pays"].upper(), 21, C["accent"], 600, ls=3)
        text(W - margin, 72 * s, tokens["date"], 30, C["title"], 600, "end")
        text(W - margin, 106 * s, tokens["creneau"], 20, C["sub"], 400, "end")
    else:
        text(margin, 46 * s, f'{tokens["pays"]} — {tokens["date"]}', 26, C["title"], 700)
        text(W - margin, 46 * s, tokens["creneau"], 22, C["sub"], 400, "end")

    # --- country and admin levels
    o.append(f'<path d="{simplified_path(country, tol, proj)}" fill="{C["land"]}" fill-rule="evenodd"/>')
    for lvl_geoms in levels:
        for geom in lvl_geoms:
            o.append(f'<path d="{simplified_path(geom, tol, proj)}" fill="none" '
                     f'stroke="{C["prov"]}" stroke-width="{1.2 * s:.2f}"/>')
    o.append(f'<path d="{simplified_path(country, tol, proj)}" fill="none" fill-rule="evenodd" '
             f'stroke="{C["land_edge"]}" stroke-width="{2.2 * s:.2f}" stroke-linejoin="round"/>')

    # --- cities
    for feat in fc["features"]:
        pr = feat["properties"]
        x, y = proj(*feat["geometry"]["coordinates"])
        o.append(f'<g transform="translate({x:.1f} {y:.1f})">')
        o.append(f'<circle r="{3.5 * s:.1f}" fill="{C["accent"]}"/>')
        href = icon(pr["condition"]) if icon else None
        if href:
            o.append(f'<image x="{-34 * s:.1f}" y="{-76 * s:.1f}" width="{68 * s:.1f}" '
                     f'height="{68 * s:.1f}" xlink:href="{href}"/>')
        t = pr.get("air_temperature")
        if density >= 1 and t is not None:
            text(0, 30 * s, f"{round(t)}{st.temp_unit}", 30, C["temp"], 700, "middle")
        if density >= 2:
            text(0, 54 * s, pr["city"], 17, C["city"], 600, "middle", ls=0.5)
        lo, hi = pr.get("air_temperature_min"), pr.get("air_temperature_max")
        if density >= 3 and lo is not None and hi is not None:
            text(0, 76 * s, f"{round(lo)}{st.temp_unit} / {round(hi)}{st.temp_unit}",
                 15, C["minmax"], 400, "middle")
        o.append("</g>")

    # --- footer
    text(margin, H - 24 * s, st.source_text.format(**tokens), 15, C["sub"])
    logo = data_uri(st.logo, "image/png") if st.logo else None
    if logo:
        o.append(f'<image x="{W - margin - 120 * s:.1f}" y="{H - 52 * s:.1f}" '
                 f'width="{120 * s:.1f}" height="{40 * s:.1f}" '
                 f'preserveAspectRatio="xMaxYMid meet" xlink:href="{logo}"/>')

    o.append("</svg>")
    return "\n".join(o)


def filter_cities(fc, featured):
    """Keep only the featured cities (name or slug, case-insensitive)."""
    if not featured:
        return fc
    keep = {c.casefold() for c in featured}
    out = dict(fc)
    out["features"] = [f for f in fc["features"]
                       if f["properties"]["city"].casefold() in keep
                       or f["properties"]["city_slug"] in keep]
    return out
