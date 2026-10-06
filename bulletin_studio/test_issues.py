"""An issue made on the server from a template: a draft of one period of the
template's cadence, its forecast maps frozen, kept offline until the studio has
rendered it."""
import hashlib
import json
import tempfile
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest import skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from wagtail import hooks
from wagtail.models import Page, Site
from wagtail.users.models import UserProfile

from climweb.base.models.snippets import Product, ServiceCategory
from climweb.pages.products.models import ProductIndexPage, ProductPage

from .issues import create_drafts, issue_title
from .models import BulletinPage

DAY = date(2026, 10, 5)


class IssueTestCase(TestCase):
    blocks = []

    def setUp(self):
        # Straight under the root: ClimWeb main cannot create a HomePage in a test
        # database (CLAUDE.md), and the studio does not need one.
        index = ProductIndexPage(title="Products", slug="products-issues")
        Page.objects.get(depth=1).add_child(instance=index)
        product = ProductPage(
            title="Daily", slug="daily", service=ServiceCategory.objects.create(name="Bulletins", icon=""),
            product=Product.objects.create(name="Daily"),
            introduction_title="Daily", introduction_text="<p>Daily</p>")
        index.add_child(instance=product)

        self.admin = get_user_model().objects.create_superuser("admin", "a@example.com", "pw")
        self.client.force_login(self.admin)
        self.template = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Daily weather", "doc": {"blocks": self.blocks}, "html": "", "isTemplate": True,
            "parent": product.pk}).json()

    def post(self, url, body):
        return self.client.post(url, json.dumps(body), content_type="application/json")

    def new_issue(self, body=None, template=None):
        return self.post(reverse("bulletin_studio:new_issue", args=[template or self.template["id"]]), body or {})


class IssueTests(IssueTestCase):
    blocks = [{"id": "d", "type": "date", "date": "2026-01-01", "issueDate": True, "align": "left"},
              {"id": "t", "type": "text", "preset": "text", "state": None}]

    def test_an_issue_is_a_dated_draft_of_the_template(self):
        response = self.new_issue({"date": "2026-10-05"})
        self.assertEqual(response.status_code, 201)
        issue = response.json()
        self.assertEqual((issue["isTemplate"], issue["live"], issue["date"], issue["validUntil"]),
                         (False, False, "2026-10-05", None))
        self.assertEqual(issue["title"], issue_title("Daily weather", "daily", DAY))
        self.assertEqual(issue["parent"], self.template["parent"])
        self.assertEqual(issue["doc"]["blocks"], self.blocks, "the date block shows the page's date itself")

        page = BulletinPage.objects.get(pk=issue["id"])
        self.assertEqual(page.source_template_id, self.template["id"])
        self.assertEqual(page.html, "", "only the studio renders html")
        self.assertTrue(page.slug.startswith("daily-weather-"), page.slug)

        today = self.new_issue().json()
        self.assertEqual(today["date"], timezone.localdate().isoformat())
        self.assertEqual(self.new_issue(template=issue["id"]).status_code, 404, "an issue is no template")
        self.assertEqual(self.new_issue({"date": "05/10/2026"}).status_code, 400)

    def test_title_in_the_admin_language(self):
        # an English site, an admin working in French (ClimWeb capitalises French months)
        profile = UserProfile.get_for_user(self.admin)
        profile.preferred_language = "fr"
        profile.save()
        with override_settings(LANGUAGE_CODE="en"):
            self.assertRegex(self.new_issue({"date": "2026-10-05"}).json()["title"],
                             r"^Daily weather — 5 [oO]ctobre 2026$")

    def test_the_issue_covers_a_period_of_the_cadence(self):
        template = BulletinPage.objects.get(pk=self.template["id"])
        for cadence, day, period, title in [
            ("dekadal", "2026-10-14", ("2026-10-11", "2026-10-20"), "Oct. 11, 2026 – Oct. 20, 2026"),
            ("dekadal", "2026-02-25", ("2026-02-21", "2026-02-28"), "Feb. 21, 2026 – Feb. 28, 2026"),
            ("monthly", "2026-10-14", ("2026-10-01", "2026-10-31"), "October 2026"),
        ]:
            BulletinPage.objects.filter(pk=template.pk).update(cadence=cadence)
            with override_settings(LANGUAGE_CODE="en"):
                issue = self.new_issue({"date": day}).json()
            self.assertEqual((issue["date"], issue["validUntil"]), period)
            self.assertEqual(issue["title"], f"Daily weather — {title}")

    def test_an_unrendered_issue_stays_offline(self):
        issue = self.new_issue({"date": "2026-10-05"}).json()
        publish = reverse("bulletin_studio:publish", args=[issue["id"]])
        self.assertEqual(self.client.post(publish).status_code, 400)

        request = RequestFactory().post("/")
        request.session = {}
        request._messages = FallbackStorage(request)
        page = Page.objects.get(pk=issue["id"])  # a plain Page, as the explorer lists them
        bulk = SimpleNamespace(next_url="/admin/pages/")
        [refused] = [r for fn in hooks.get_hooks("before_bulk_action")
                     if (r := fn(request, "publish", [page], bulk))]
        self.assertEqual(refused.url, "/admin/pages/")
        [refused] = [r for fn in hooks.get_hooks("before_publish_page") if (r := fn(request, page.specific))]
        self.assertEqual(refused.status_code, 302)

        # the studio renders it, then it can go online
        self.client.put(reverse("bulletin_studio:bulletin", args=[issue["id"]]), json.dumps({
            "title": issue["title"], "doc": issue["doc"], "html": "<p>Sunny</p>", "isTemplate": False,
        }), content_type="application/json")
        page = Page.objects.get(pk=issue["id"])
        self.assertFalse([r for fn in hooks.get_hooks("before_publish_page") if (r := fn(request, page.specific))])
        self.assertEqual(self.client.post(publish).status_code, 200)
        self.assertTrue(BulletinPage.objects.get(pk=issue["id"]).live)


class DraftTests(IssueTestCase):
    def put(self, pk, **extra):
        page = self.client.get(reverse("bulletin_studio:bulletin", args=[pk])).json()
        return self.client.put(reverse("bulletin_studio:bulletin", args=[pk]), json.dumps({
            "title": page["title"], "doc": page["doc"], "html": "", "isTemplate": page["isTemplate"],
            **extra}), content_type="application/json")

    def test_a_template_sets_its_cadence_and_its_time_by_the_quarter_hour(self):
        pk = self.template["id"]
        self.assertEqual((self.template["cadence"], self.template["draftAt"]), ("daily", None))
        self.assertEqual(self.put(pk, draftAt="06:10").json()["draftAt"], "06:00")
        self.assertEqual(BulletinPage.objects.get(pk=pk).draft_at, time(6))
        self.assertEqual(self.put(pk, cadence="dekadal").json()["draftAt"], "06:00", "absent: unchanged")
        self.assertEqual(BulletinPage.objects.get(pk=pk).cadence, "dekadal")
        self.assertIsNone(self.put(pk, draftAt="").json()["draftAt"])
        self.assertEqual(self.put(pk, draftAt="25:00").status_code, 400)
        self.assertEqual(self.put(pk, cadence="weekly").status_code, 400)

        issue = self.new_issue().json()
        self.assertEqual(issue["cadence"], "dekadal", "the template's")
        self.assertEqual(self.put(issue["id"], draftAt="06:00", cadence="monthly").json()["cadence"], "dekadal",
                         "only templates have settings")

    def test_one_draft_a_day_once_its_time_has_come(self):
        at = lambda d, h, m=0: timezone.make_aware(datetime(2026, 10, d, h, m))  # noqa: E731
        BulletinPage.objects.filter(pk=self.template["id"]).update(draft_at=time(6))

        self.assertEqual(create_drafts(at(5, 5, 59)), [])
        [draft] = create_drafts(at(5, 6))
        self.assertEqual((draft.date, draft.valid_until, draft.source_template_id, draft.live, draft.html),
                         (DAY, None, self.template["id"], False, ""))
        self.assertEqual(create_drafts(at(5, 6, 15)), [], "once a day")
        draft.delete()
        self.assertEqual(create_drafts(at(5, 6, 30)), [], "a draft deleted by hand stays deleted")

        [tomorrow] = create_drafts(at(6, 6))
        self.assertEqual(tomorrow.date, date(2026, 10, 6))

        # an issue of the day made by hand beforehand: no second one
        BulletinPage.objects.filter(pk=self.template["id"]).update(draft_at=time(7))
        self.new_issue({"date": "2026-10-07"})
        self.assertEqual(create_drafts(at(7, 7)), [])
        self.assertEqual(BulletinPage.objects.filter(source_template_id=self.template["id"]).count(), 2)

    def test_a_dekad_on_the_1st_the_11th_and_the_21st(self):
        at = lambda m, d, h: timezone.make_aware(datetime(2026, m, d, h))  # noqa: E731
        BulletinPage.objects.filter(pk=self.template["id"]).update(cadence="dekadal", draft_at=time(8))

        self.assertEqual(create_drafts(at(10, 11, 7)), [])
        [draft] = create_drafts(at(10, 11, 8))
        self.assertEqual((draft.date, draft.valid_until), (date(2026, 10, 11), date(2026, 10, 20)))
        self.assertEqual(create_drafts(at(10, 15, 8)), [], "once a dekad")
        # the worker was down on the 21st: the next morning still gets its dekad
        [late] = create_drafts(at(10, 22, 3))
        self.assertEqual((late.date, late.valid_until), (date(2026, 10, 21), date(2026, 10, 31)))
        self.assertEqual(create_drafts(at(11, 1, 7)), [])
        self.assertEqual(create_drafts(at(11, 1, 8))[0].date, date(2026, 11, 1))

    def test_a_draft_in_the_language_of_the_template_author(self):
        profile = UserProfile.get_for_user(self.admin)
        profile.preferred_language = "fr"
        profile.save()
        BulletinPage.objects.filter(pk=self.template["id"]).update(cadence="monthly", draft_at=time(8))
        with override_settings(LANGUAGE_CODE="en"):
            [draft] = create_drafts(timezone.make_aware(datetime(2026, 10, 1, 8)))
        self.assertRegex(draft.title, r"^Daily weather — [oO]ctobre 2026$")


@skipUnless(apps.is_installed("forecastmanager"), "forecastmanager is not installed")
class ForecastIssueTests(IssueTestCase):
    def forecast(self, **recipe):
        return {"id": "f", "type": "forecast", "period": "06:00", "preset": "bulletin", "dayOffset": 0,
                "date": None, "src": None, "imageId": None, "version": None, "periodLabel": "",
                "alt": "", "caption": "", **recipe}

    def setUp(self):
        from forecastmanager.forecast_settings import ForecastPeriod, ForecastSetting

        from .forecast.models import ForecastMapSettings
        from .forecast.snapshots import snapshot_name
        from .forecast.test_library import png

        self.blocks = [
            {"id": "c", "type": "columns", "ratios": [1], "columns": [[self.forecast()]]},
            self.forecast(dayOffset=1, period=None),  # nothing drawn for the 6th yet
            self.forecast(preset="../../secrets"),
            self.forecast(src="/media/stale.png", imageId=99, version="old"),
        ]
        site = Site.objects.get(is_default_site=True)
        ForecastPeriod.objects.create(parent=ForecastSetting.for_site(site),
                                      forecast_effective_time=time(6), label="Journalière")
        settings = ForecastMapSettings.for_site(site)
        settings.periods = ["06:00"]
        settings.save()

        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        media_root = override_settings(MEDIA_ROOT=media.name)
        media_root.enable()
        self.addCleanup(media_root.disable)
        self.png = png("red")
        default_storage.save(snapshot_name(DAY, time(6), "bulletin", "png"), ContentFile(self.png))
        super().setUp()

    def test_the_issue_freezes_the_maps_of_its_date(self):
        blocks = self.new_issue({"date": "2026-10-05"}).json()["doc"]["blocks"]
        in_column, next_day, bad_preset, stale = blocks[0]["columns"][0][0], blocks[1], blocks[2], blocks[3]

        self.assertEqual((in_column["date"], in_column["period"], in_column["periodLabel"]),
                         ("2026-10-05", "06:00", "Journalière"))
        self.assertEqual(in_column["version"], hashlib.sha1(self.png).hexdigest())
        self.assertTrue(in_column["src"].startswith("/media/images/"), "a rendition of the library image")
        self.assertTrue(in_column["imageId"])

        for empty in (next_day, bad_preset):
            self.assertIsNone(empty["src"])
        self.assertEqual(next_day["period"], "06:00", "the office's first period, made explicit")
        self.assertEqual(stale["src"], in_column["src"], "never what the template carried")
        self.assertEqual(stale["imageId"], in_column["imageId"], "the same version, the same image")

        template = BulletinPage.objects.get(pk=self.template["id"])
        self.assertEqual(template.doc["blocks"][3]["src"], "/media/stale.png", "the template is untouched")


@skipUnless(apps.is_installed("forecastmanager"), "forecastmanager is not installed")
class CityForecastIssueTests(IssueTestCase):
    def cities(self, **recipe):
        return {"id": "g", "type": "cities", "period": "06:00", "dayOffset": 0,
                "cities": ["ouagadougou"], "columns": 2, "date": None, "periodLabel": "",
                "units": None, "rows": None, "version": None, **recipe}

    def setUp(self):
        from .forecast.test_cities import publish_city_forecasts

        publish_city_forecasts()
        self.blocks = [
            {"id": "c", "type": "columns", "ratios": [1], "columns": [[self.cities()]]},
            self.cities(dayOffset=1, period=None),  # nothing published for the 6th yet
            self.cities(rows=[{"slug": "ouagadougou", "name": "Ouagadougou"}], version="old"),
        ]
        super().setUp()

    def test_the_issue_freezes_the_forecast_of_its_date(self):
        from .forecast.cities import table

        blocks = self.new_issue({"date": "2026-10-05"}).json()["doc"]["blocks"]
        in_column, next_day, stale = blocks[0]["columns"][0][0], blocks[1], blocks[2]

        expected = table(DAY, time(6))
        self.assertEqual((in_column["date"], in_column["periodLabel"], in_column["version"]),
                         ("2026-10-05", "Journalière", expected["version"]))
        self.assertEqual(in_column["rows"], expected["rows"], "every city's row: the studio picks")
        self.assertEqual(in_column["cities"], ["ouagadougou"], "the template's choice, untouched")
        self.assertEqual(stale["rows"], expected["rows"], "never what the template carried")

        self.assertIsNone(next_day["rows"])
        self.assertEqual(next_day["period"], "06:00", "the office's first period, made explicit")
