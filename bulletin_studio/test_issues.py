"""An issue made on the server from a template: a draft of one period of the
template's cadence, its forecast maps frozen, kept offline until the studio has
rendered it."""
import hashlib
import json
import tempfile
from datetime import date, datetime, time
from types import SimpleNamespace
from unittest import mock, skipUnless

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from wagtail import hooks
from wagtail.images import get_image_model
from wagtail.models import Page, Site
from wagtail.users.models import UserProfile

from climweb.base.models.snippets import Product, ServiceCategory
from climweb.pages.products.models import ProductIndexPage, ProductPage

from .issues import create_drafts, issue_title
from .models import BulletinPage
from .tests import PNG

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


class FlashTests(IssueTestCase):
    """A media flash is a bulletin of another kind: one square image and its post text,
    made from a template and published the same way."""

    def put(self, pk, **body):
        page = self.client.get(reverse("bulletin_studio:bulletin", args=[pk])).json()
        return self.client.put(reverse("bulletin_studio:bulletin", args=[pk]), json.dumps({
            "title": page["title"], "doc": page["doc"], "html": "<p>Rain</p>",
            "isTemplate": page["isTemplate"], **body}), content_type="application/json")

    def test_a_flash_template_makes_flashes(self):
        self.assertEqual(self.template["kind"], "bulletin", "a bulletin unless said otherwise")
        flash = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Heavy rain", "kind": "flash", "doc": {"blocks": []}, "html": "",
            "isTemplate": True, "parent": self.template["parent"]}).json()
        self.assertEqual(flash["kind"], "flash")
        issue = self.new_issue({"date": "2026-10-05"}, template=flash["id"]).json()
        self.assertEqual(issue["kind"], "flash")
        self.assertEqual(issue["title"], issue_title("Heavy rain", "daily", DAY))

        self.assertEqual(self.put(issue["id"], kind="bulletin").json()["kind"], "flash", "fixed once made")
        self.assertEqual(self.post(reverse("bulletin_studio:bulletins"), {
            "title": "x", "kind": "poster", "doc": {}, "html": "", "isTemplate": True,
            "parent": self.template["parent"]}).status_code, 400)

    def test_the_studio_picks_the_image_of_a_shared_link(self):
        first, second = (get_image_model().objects.create(
            title=name, file=SimpleUploadedFile(f"{name}.png", PNG, content_type="image/png"))
            for name in ("first", "second"))
        pk = self.new_issue({"date": "2026-10-05"}).json()["id"]

        self.assertEqual(self.put(pk, shareImage=first.pk).status_code, 200)
        self.client.post(reverse("bulletin_studio:publish", args=[pk]))
        # ClimWeb's og:image: the page's own search image before its product's
        self.assertEqual(BulletinPage.objects.get(pk=pk).get_meta_image(), first)

        # once online, a draft changes the preview of the link only when it is published
        self.put(pk, shareImage=second.pk)
        self.assertEqual(BulletinPage.objects.get(pk=pk).search_image, first)
        self.client.post(reverse("bulletin_studio:publish", args=[pk]))
        self.assertEqual(BulletinPage.objects.get(pk=pk).search_image, second)

        self.put(pk)  # absent: left as it is
        self.assertEqual(BulletinPage.objects.get(pk=pk).latest_revision.as_object().search_image, second)
        for wrong in (10 ** 6, True, "1"):
            self.assertEqual(self.put(pk, shareImage=wrong).status_code, 400, wrong)
        self.put(pk, shareImage=None)
        self.client.post(reverse("bulletin_studio:publish", args=[pk]))
        self.assertIsNone(BulletinPage.objects.get(pk=pk).search_image)


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


def ms(dt):
    return int(dt.timestamp() * 1000)


class NavigationTests(IssueTestCase):
    """What the studio's navigation shows of each page: the template an issue was made
    from, a template's issues and its next draft, when an issue was prepared and when
    it was published."""

    def put(self, pk, **extra):
        page = self.client.get(reverse("bulletin_studio:bulletin", args=[pk])).json()
        return self.client.put(reverse("bulletin_studio:bulletin", args=[pk]), json.dumps({
            "title": page["title"], "doc": page["doc"], "html": "<p>Sunny</p>",
            "isTemplate": page["isTemplate"], **extra}), content_type="application/json")

    def read(self, pk):
        return self.client.get(reverse("bulletin_studio:bulletin", args=[pk])).json()

    def listed(self):
        return {p["id"]: p for p in self.client.get(reverse("bulletin_studio:bulletins")).json()}

    def one_off(self, **extra):
        return self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Heat wave", "doc": {}, "html": "<p>Hot</p>", "isTemplate": False,
            "parent": self.template["parent"], **extra})

    def test_an_issue_names_its_template_and_a_template_counts_its_issues(self):
        pk = self.template["id"]
        self.assertEqual((self.template["template"], self.template["issueCount"]), (None, 0))
        issue = self.new_issue({"date": "2026-10-05"}).json()
        self.assertEqual(issue["template"], {"id": pk, "title": "Daily weather"})
        self.assertEqual(issue["issueCount"], 0, "only a template has issues")
        self.new_issue({"date": "2026-10-06"})
        one_off = self.one_off().json()
        self.assertEqual(one_off["template"], None, "made without template")

        self.assertEqual(self.read(pk)["issueCount"], 2)
        listed = self.listed()
        self.assertEqual(listed[pk]["issueCount"], 2)
        self.assertEqual(listed[issue["id"]]["template"], {"id": pk, "title": "Daily weather"})
        self.assertEqual(listed[one_off["id"]]["template"], None)

        # the template renamed: its issues say so, their own titles stay
        self.put(pk, title="Daily forecast")
        self.assertEqual(self.read(issue["id"])["template"]["title"], "Daily forecast")
        # deleted: its issues stay, without it
        self.client.delete(reverse("bulletin_studio:bulletin", args=[pk]))
        self.assertIsNone(self.read(issue["id"])["template"])
        self.assertIsNone(self.listed()[issue["id"]]["template"])

    def test_when_an_issue_was_prepared_and_published(self):
        BulletinPage.objects.filter(pk=self.template["id"]).update(draft_at=time(6))
        [draft] = create_drafts(timezone.make_aware(datetime(2026, 10, 5, 6)))
        self.assertEqual(self.read(draft.pk)["preparedAt"], ms(draft.prepared_at))
        by_hand = self.new_issue({"date": "2026-10-06"}).json()
        self.assertIsNone(by_hand["preparedAt"], "made by hand")
        self.assertIsNone(self.one_off().json()["preparedAt"])

        self.assertIsNone(self.listed()[draft.pk]["publishedAt"])
        self.put(draft.pk)  # the studio renders it
        published = self.client.post(reverse("bulletin_studio:publish", args=[draft.pk])).json()
        page = BulletinPage.objects.get(pk=draft.pk)
        self.assertEqual(published["publishedAt"], ms(page.last_published_at))
        self.assertEqual(published["preparedAt"], ms(draft.prepared_at), "still prepared by the task")
        # a draft saved since: the read opens the revision, the dates are the page's
        self.put(draft.pk, title="Reworked")
        self.assertEqual(self.read(draft.pk)["publishedAt"], ms(page.last_published_at))
        self.assertEqual(self.listed()[draft.pk]["publishedAt"], ms(page.last_published_at))

    def test_the_next_draft_of_a_template(self):
        pk = self.template["id"]
        now = lambda m, d, h, mi=0: mock.patch(  # noqa: E731
            "bulletin_studio.views._site_now", return_value=datetime(2026, m, d, h, mi))
        self.assertIsNone(self.template["nextDraft"], "no time set: no draft")
        self.put(pk, draftAt="06:00")

        with now(10, 5, 5):
            self.assertEqual(self.read(pk)["nextDraft"],
                             {"at": "2026-10-05T06:00", "start": "2026-10-05", "end": "2026-10-05"})
        with now(10, 5, 7, 5):  # its time has passed, the worker is behind
            self.assertEqual(self.listed()[pk]["nextDraft"]["at"], "2026-10-05T07:15")
        create_drafts(timezone.make_aware(datetime(2026, 10, 5, 7, 5)))
        with now(10, 5, 7, 10):
            self.assertEqual(self.read(pk)["nextDraft"],
                             {"at": "2026-10-06T06:00", "start": "2026-10-06", "end": "2026-10-06"})
            # deleted by hand, it stays deleted: the task is done with the day
            BulletinPage.objects.get(source_template_id=pk).delete()
            self.assertEqual(self.read(pk)["nextDraft"]["start"], "2026-10-06", "the row's last draft")
            self.assertEqual(self.listed()[pk]["nextDraft"]["start"], "2026-10-06")

        # a dekad made by hand before its time counts
        self.put(pk, cadence="dekadal")
        with now(10, 11, 5):
            self.assertEqual(self.listed()[pk]["nextDraft"],
                             {"at": "2026-10-11T06:00", "start": "2026-10-11", "end": "2026-10-20"})
            issue = self.new_issue({"date": "2026-10-11"}).json()
            self.assertEqual(self.listed()[pk]["nextDraft"],
                             {"at": "2026-10-21T06:00", "start": "2026-10-21", "end": "2026-10-31"})
            self.assertIsNone(self.listed()[issue["id"]]["nextDraft"], "an issue prepares nothing")
            # and so does the next one, made ahead of time: the task will skip it too
            self.new_issue({"date": "2026-10-21"})
            self.assertEqual(self.read(pk)["nextDraft"]["start"], "2026-11-01")

    def test_the_list_queries_do_not_grow_with_the_bulletins(self):
        url = reverse("bulletin_studio:bulletins")

        def queries():
            self.client.get(url)  # the caches a publication clears, filled again
            with CaptureQueriesContext(connection) as captured:
                self.assertEqual(self.client.get(url).status_code, 200)
            return len(captured)

        BulletinPage.objects.filter(pk=self.template["id"]).update(draft_at=time(6))
        first = self.new_issue({"date": "2026-10-05"}).json()["id"]
        self.put(first)
        self.client.post(reverse("bulletin_studio:publish", args=[first]))
        few = queries()

        second = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Monthly", "doc": {}, "html": "", "isTemplate": True, "cadence": "monthly",
            "draftAt": "08:00", "parent": self.template["parent"]}).json()["id"]
        for day in ("2026-10-06", "2026-10-07"):
            self.new_issue({"date": day})
        self.new_issue({"date": "2026-10-01"}, template=second)
        published = self.one_off().json()["id"]
        self.client.post(reverse("bulletin_studio:publish", args=[published]))
        self.one_off()
        self.assertEqual(BulletinPage.objects.count(), 8)
        self.assertEqual(queries(), few)


class OneOffTests(IssueTestCase):
    """A bulletin made without template: its date ("Effective from") is its own, where an
    issue's is the period its template's cadence sets."""

    def create(self, **extra):
        return self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Heat wave", "doc": {}, "html": "<p>Hot</p>", "isTemplate": False,
            "parent": self.template["parent"], **extra})

    def put(self, pk, **extra):
        page = self.client.get(reverse("bulletin_studio:bulletin", args=[pk])).json()
        return self.client.put(reverse("bulletin_studio:bulletin", args=[pk]), json.dumps({
            "title": page["title"], "doc": page["doc"], "html": "<p>Hot</p>",
            "isTemplate": page["isTemplate"], **extra}), content_type="application/json")

    def test_a_date_of_its_own(self):
        made = self.create(date="2026-10-05")
        self.assertEqual(made.status_code, 201)
        bulletin = made.json()
        self.assertEqual((bulletin["date"], bulletin["validUntil"]), ("2026-10-05", None))
        self.assertEqual(self.create().json()["date"], timezone.localdate().isoformat(), "today by default")

        pk = bulletin["id"]
        self.assertEqual(self.put(pk, date="2026-10-07").json()["date"], "2026-10-07")
        self.assertEqual(BulletinPage.objects.get(pk=pk).date, date(2026, 10, 7))
        self.assertEqual(self.put(pk).json()["date"], "2026-10-07", "absent: unchanged")

        for wrong in ("07/10/2026", "2026-10-32", "", None, 20261007):
            response = self.put(pk, date=wrong)
            self.assertEqual(response.status_code, 400, wrong)
            self.assertIn("date must be YYYY-MM-DD", response.json()["error"])
            self.assertEqual(self.create(date=wrong).status_code, 400, wrong)
        self.assertEqual(BulletinPage.objects.get(pk=pk).date, date(2026, 10, 7))

    def test_online_the_date_waits_for_the_publication(self):
        pk = self.create(date="2026-10-05").json()["id"]
        self.client.post(reverse("bulletin_studio:publish", args=[pk]))
        self.assertEqual(self.put(pk, date="2026-10-07").json()["date"], "2026-10-07")
        page = BulletinPage.objects.get(pk=pk)
        self.assertEqual(page.date, date(2026, 10, 5), "the public page keeps its date")
        self.assertEqual(page.latest_revision.as_object().date, date(2026, 10, 7))
        self.client.post(reverse("bulletin_studio:publish", args=[pk]))
        self.assertEqual(BulletinPage.objects.get(pk=pk).date, date(2026, 10, 7))

    def test_an_issue_and_a_template_keep_their_period(self):
        template = self.template["id"]
        BulletinPage.objects.filter(pk=template).update(cadence="dekadal")
        issue = self.new_issue({"date": "2026-10-14"}).json()["id"]
        for pk in (issue, template):
            response = self.put(pk, date="2026-10-15")
            self.assertEqual(response.status_code, 400)
            self.assertIn("cadence", response.json()["error"])
        self.assertEqual(BulletinPage.objects.get(pk=issue).date, date(2026, 10, 11))
        self.assertEqual(self.create(date="2026-10-15", isTemplate=True).status_code, 400)

        # its template deleted, an issue still covers its dekad
        self.client.delete(reverse("bulletin_studio:bulletin", args=[template]))
        self.assertEqual(self.put(issue, date="2026-10-15").status_code, 400)


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
