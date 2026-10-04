"""The drawing engine against frozen meteoburkina responses: what would break
silently - the projection, the derived tolerance, the density steps, the city filter.

Plain unittest, no database: `manage.py test bulletin_studio` runs it, and so does
`uv run --no-project --with shapely python -m unittest bulletin_studio.forecast.tests` on the host.
"""
import json
import pathlib
import tempfile
import unittest

from .render import PRESETS, Settings, build_svg, filter_cities, make_projector, merc_y

# The fixtures live outside the package (dev/forecast/), so they never ship.
FIX = pathlib.Path(__file__).resolve().parents[2] / "dev" / "forecast" / "fixtures"
BBOX = (-5.5, 9.4, 2.4, 15.1)


def load_levels(detail_level):
    return [[row["feature"] for row in json.loads((FIX / f"admin{lvl}.json").read_text())]
            for lvl in range(1, detail_level + 1)]


@unittest.skipUnless(FIX.is_dir(), "dev/forecast/fixtures not available")
class ForecastRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin0 = json.loads((FIX / "admin0.json").read_text())[0]
        cls.fc = next(
            c for c in json.loads((FIX / "forecasts.json").read_text())
            if c["features"] and c["features"][0]["properties"]["effective_period_label"] == "Journalière")

    def test_projection_contained_and_centered(self):
        box = (100, 50, 800, 400)  # wider than the country's aspect -> height-bound
        proj, ppd = make_projector(BBOX, box)
        x0, y0 = proj(BBOX[0], BBOX[3])  # top-left corner
        x1, y1 = proj(BBOX[2], BBOX[1])  # bottom-right corner
        self.assertAlmostEqual(y0, 50, msg="must fill the height")
        self.assertAlmostEqual(y1, 450, msg="must fill the height")
        self.assertTrue(x0 > 100 and x1 < 900, "must be contained in the width")
        self.assertAlmostEqual(x0 - 100, 900 - x1, msg="must be centered")
        self.assertAlmostEqual(ppd * (BBOX[2] - BBOX[0]), x1 - x0)

    def test_tolerance_follows_resolution(self):
        """The bigger the canvas, the finer the simplification."""
        tol = {}
        for name in ("social", "bulletin"):
            p = PRESETS[name]
            w = p["width"] - 80
            h = (w / ((BBOX[2] - BBOX[0]) / (merc_y(BBOX[3]) - merc_y(BBOX[1])))
                 if p["height"] is None else p["height"] - 200)
            tol[name] = 1.2 / make_projector(BBOX, (0, 0, w, h))[1]
        self.assertLess(tol["bulletin"], tol["social"])
        # The fixture must stay finer than the most demanding preset needs, or it is
        # what caps the print quality.
        self.assertGreater(tol["bulletin"], 0.001, "fixture too coarse for the bulletin preset")

    def test_density_steps(self):
        levels = load_levels(1)
        seen = {}
        for density in ("icon", "temp", "normal", "full"):
            svg = build_svg(self.fc, self.admin0, levels, PRESETS["web"], Settings(density=density),
                            icon=lambda condition: "data:image/png;base64,")
            seen[density] = (svg.count("<image"), "Ouagadougou" in svg, svg.count("° / "))
        self.assertEqual(seen["icon"], (11, False, 0))
        self.assertEqual(seen["temp"], (11, False, 0))
        self.assertEqual(seen["normal"][1:], (True, 0))
        self.assertEqual(seen["full"][2], 11)

    def test_no_icon_without_a_resolver(self):
        svg = build_svg(self.fc, self.admin0, [], PRESETS["web"], Settings())
        self.assertEqual(svg.count("<image"), 0)

    def test_detail_level_changes_the_number_of_paths(self):
        n = {lvl: build_svg(self.fc, self.admin0, load_levels(lvl), PRESETS["web"], Settings()).count("<path")
             for lvl in (0, 1)}
        self.assertEqual(n[0], 2)  # the country's fill + outline
        self.assertEqual(n[1], 2 + 13)  # + the 13 regions

    def test_city_filter(self):
        out = filter_cities(self.fc, ["OUAGADOUGOU", "bobo-dioulasso", "Inconnue"])
        self.assertEqual([f["properties"]["city"] for f in out["features"]],
                         ["Bobo Dioulasso", "Ouagadougou"])
        self.assertEqual(len(filter_cities(self.fc, None)["features"]), 11)


class SettingsTests(unittest.TestCase):
    def test_unknown_setting_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write('{"couleur": "rouge"}')
        path = pathlib.Path(f.name)
        try:
            with self.assertRaisesRegex(ValueError, "couleur"):
                Settings.load(path)
        finally:
            path.unlink()
