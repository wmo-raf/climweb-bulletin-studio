"""The promotion of a stored map into the Wagtail library, once per version, and the API
the forecast block reads it through."""
import hashlib
import io
import json
import tempfile
from datetime import date, time
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image as PILImage
from wagtail.images import get_image_model
from wagtail.models import Site

DAY = date(2026, 10, 5)


def png(color):
    out = io.BytesIO()
    PILImage.new("RGB", (40, 30), color).save(out, "PNG")
    return out.getvalue()


@skipUnless(apps.is_installed("forecastmanager"), "forecastmanager is not installed")
class ForecastLibraryTests(TestCase):
    def setUp(self):
        from forecastmanager.forecast_settings import ForecastPeriod, ForecastSetting

        from bulletin_studio.forecast.models import ForecastMapSettings

        site = Site.objects.get(is_default_site=True)
        ForecastPeriod.objects.create(parent=ForecastSetting.for_site(site),
                                      forecast_effective_time=time(6), label="Journalière")
        settings = ForecastMapSettings.for_site(site)
        settings.periods, settings.days_ahead = ["06:00"], 1
        settings.save()

        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_root = override_settings(MEDIA_ROOT=media.name)
        media_root.enable()
        self.addCleanup(media_root.disable)

        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))
        self.url = reverse("bulletin_studio:forecast")

    def draw(self, content, day=DAY):
        """What a forecast pull leaves behind: the slot's file, replaced."""
        from bulletin_studio.forecast.snapshots import snapshot_name

        name = snapshot_name(day, time(6), "bulletin", "png")
        if default_storage.exists(name):
            default_storage.delete(name)
        default_storage.save(name, ContentFile(content))

    def post(self, body):
        return self.client.post(self.url, json.dumps(body), content_type="application/json")

    def test_a_version_is_promoted_once_and_stays_frozen(self):
        from bulletin_studio.forecast.library import promote

        self.assertIsNone(promote(DAY, time(6), "bulletin"), "nothing drawn, nothing to promote")
        self.draw(png("red")[:60])
        self.assertIsNone(promote(DAY, time(6), "bulletin"), "a render caught halfway is not frozen")
        self.draw(png("red"))
        image, details = promote(DAY, time(6), "bulletin")
        self.assertEqual(image.title, "Forecast map — 2026-10-05 — Journalière")
        self.assertEqual(image.collection.name, "Forecast maps")
        self.assertEqual((image.width, image.height), (40, 30))
        self.assertEqual(image.file_hash, hashlib.sha1(png("red")).hexdigest())
        self.assertEqual(details, {"date": "2026-10-05", "period": "06:00", "periodLabel": "Journalière",
                                   "preset": "bulletin", "version": image.file_hash})
        self.assertEqual(promote(DAY, time(6), "bulletin")[0], image, "same render, same image")

        self.draw(png("blue"))  # the next pull changed the forecast
        newer, _ = promote(DAY, time(6), "bulletin")
        self.assertNotEqual(newer, image)
        with image.open_file() as f:
            self.assertEqual(f.read(), png("red"), "the image an issue froze is untouched")
        self.assertEqual(get_image_model().objects.count(), 2)

    def test_lists_the_maps_drawn(self):
        self.draw(png("red"))
        body = self.client.get(self.url, {"date": "2026-10-05"}).json()
        self.assertEqual(body["periods"], [{"time": "06:00", "label": "Journalière"}])
        self.assertEqual((body["daysAhead"], body["presets"]), (1, ["bulletin"]))
        [drawn] = body["maps"]  # nothing yet for the 6th
        self.assertEqual((drawn["date"], drawn["period"], drawn["preset"]), ("2026-10-05", "06:00", "bulletin"))
        self.assertEqual(drawn["version"], hashlib.sha1(png("red")).hexdigest())
        self.assertEqual(drawn["url"], f"/media/forecast_snapshots/2026-10-05/06h00-bulletin.png?v={drawn['version'][:12]}")
        self.assertEqual(self.client.get(self.url, {"date": "05/10/2026"}).status_code, 400)

    def test_promotes_through_the_api(self):
        self.assertEqual(self.post({"date": "2026-10-05", "period": "06:00"}).status_code, 404)
        self.draw(png("red"))
        response = self.post({"date": "2026-10-05", "period": "06:00"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["periodLabel"], body["version"]),
                         ("Journalière", hashlib.sha1(png("red")).hexdigest()))
        self.assertTrue(body["url"].startswith("/media/images/"),
                        "a rendition of the library image, not the file the pulls rewrite")
        for bad in ({"date": "tomorrow", "period": "06:00"}, {"date": "2026-10-05"},
                    {"date": "2026-10-05", "period": "06:00", "preset": "../../secrets"}):
            self.assertEqual(self.post(bad).status_code, 400, bad)

    def test_image_picker_leaves_the_maps_to_a_search(self):
        self.draw(png("red"))
        self.post({"date": "2026-10-05", "period": "06:00"})
        get_image_model().objects.create(title="Logo", file=ImageFile(io.BytesIO(png("green")), name="logo.png"))
        images = reverse("bulletin_studio:images")
        self.assertEqual([i["title"] for i in self.client.get(images).json()], ["Logo"])
        self.assertEqual([i["title"] for i in self.client.get(images, {"q": "forecast"}).json()],
                         ["Forecast map — 2026-10-05 — Journalière"])

    def test_no_forecast_block_without_forecastmanager(self):
        app = reverse("bulletin_studio:app")
        self.assertContains(self.client.get(app), f'data-forecast-url="{self.url}"')
        installed = apps.is_installed
        with mock.patch.object(apps, "is_installed", lambda name: name != "forecastmanager" and installed(name)):
            self.assertNotContains(self.client.get(app), "data-forecast-url")
            self.assertEqual(self.client.get(self.url).status_code, 404)
