"""One pass over the store API: a template, an issue made from it, a draft save,
a publication, and the public page serving the rendered html."""
import base64
import json
import os
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from wagtail.images import get_image_model
from wagtail.models import Collection, Page, Site

from climweb.base.models import OrganisationSetting
from climweb.base.models.snippets import Product, ServiceCategory
from climweb.pages.home.models import HomePage
from climweb.pages.products.models import ProductIndexPage, ProductItemPage, ProductPage

from .models import BulletinPage
from .templatetags.bulletin_studio_tags import studio_static
from .wagtail_hooks import menu_label


class BulletinStoreTests(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        home = HomePage(title="ClimWeb", slug="climweb", hero_title="ClimWeb")
        root.add_child(instance=home)
        Site.objects.update_or_create(
            is_default_site=True,
            defaults={"hostname": "localhost", "port": 80, "root_page": home})
        index = ProductIndexPage(title="Products", slug="products")
        home.add_child(instance=index)
        self.product = ProductPage(
            title="Agromet", slug="agromet",
            service=ServiceCategory.objects.create(name="Bulletins", icon=""),
            product=Product.objects.create(name="Agromet"),
            introduction_title="Agromet", introduction_text="<p>Agromet</p>")
        index.add_child(instance=self.product)

        self.client = Client()
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))

    def post(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_lifecycle(self):
        products = self.client.get(reverse("bulletin_studio:product_pages")).json()
        self.assertEqual([p["id"] for p in products], [self.product.pk])

        # A template: a draft under the product, never served publicly.
        tpl = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Decadal template", "doc": {"blocks": [{"id": "a", "type": "divider"}]},
            "html": "<div class='bs-doc'><hr></div>", "isTemplate": True,
            "parent": self.product.pk}).json()
        self.assertTrue(tpl["isTemplate"])
        self.assertFalse(BulletinPage.objects.get(pk=tpl["id"]).live)

        # An issue starts as a copy of the template's doc, under the same product.
        issue = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Decadal bulletin no 12", "doc": tpl["doc"],
            "html": "<p>draft</p>", "isTemplate": False, "parent": tpl["parent"]}).json()
        self.assertEqual(issue["parent"], self.product.pk)
        # its date is ClimWeb's "effective from", the day it was created by default
        self.assertEqual(issue["date"], timezone.localdate().isoformat())

        url = reverse("bulletin_studio:bulletin", args=[issue["id"]])
        # Saving is a draft, and the html is sanitized on the way in.
        saved = self.client.put(url, data=json.dumps({
            "title": "Decadal bulletin no 12", "doc": {"blocks": []},
            "html": "<p>rain</p><script>alert(1)</script>",
            "isTemplate": False}), content_type="application/json").json()
        self.assertFalse(saved["live"])
        self.assertEqual(saved["date"], issue["date"], "read back from the database, still a date")
        self.assertEqual(BulletinPage.objects.get(pk=issue["id"]).html, "<p>rain</p>")

        published = self.client.post(
            reverse("bulletin_studio:publish", args=[issue["id"]])).json()
        self.assertTrue(published["live"])
        self.assertTrue(published["url"])

        page = BulletinPage.objects.get(pk=issue["id"])
        public = self.client.get(page.url)
        self.assertContains(public, "rain")
        # ClimWeb's share buttons, under the document
        self.assertContains(public, f"sharer.php?u={page.get_full_url()}")
        # The template has no public page even if it somehow went live.
        BulletinPage.objects.filter(pk=tpl["id"]).update(live=True)
        self.assertEqual(self.client.get(BulletinPage.objects.get(pk=tpl["id"]).url).status_code, 404)

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(BulletinPage.objects.filter(pk=issue["id"]).exists())

    def test_publish_and_delete_clear_the_site_cache(self):
        # ClimWeb clears its page cache from Wagtail editor hooks the studio
        # never goes through: without this, a republished issue keeps serving
        # its old html for hours in production.
        issue = self.post(reverse("bulletin_studio:bulletins"), {
            "title": "Issue", "doc": {}, "html": "<p>v1</p>", "isTemplate": False,
            "parent": self.product.pk}).json()
        url = reverse("bulletin_studio:bulletin", args=[issue["id"]])
        with mock.patch("bulletin_studio.views._clear_site_cache") as clear:
            self.client.put(url, data=json.dumps({"title": "Issue", "doc": {}, "html": "<p>v2</p>"}),
                            content_type="application/json")
            clear.assert_not_called()  # a draft changes nothing public
            self.client.post(reverse("bulletin_studio:publish", args=[issue["id"]]))
            clear.assert_called_once()
            self.client.delete(url)
            self.assertEqual(clear.call_count, 2)


class PageTreeTests(SimpleTestCase):
    def test_bulletins_are_made_in_the_studio_not_in_the_page_tree(self):
        # "Add child page" under a product page offers the product item only...
        self.assertEqual(ProductPage.creatable_subpage_models(), [ProductItemPage])
        # ...but a bulletin may still be moved to another product page.
        self.assertIn(BulletinPage, ProductPage.allowed_subpage_models())


class MenuTests(SimpleTestCase):
    def test_a_pre_release_says_so_in_the_menu(self):
        self.assertEqual(str(menu_label("0.1.0a2")), "Bulletin Studio (alpha 2)")
        self.assertEqual(str(menu_label("0.2.0b1")), "Bulletin Studio (beta 1)")
        self.assertEqual(str(menu_label("1.0.0")), "Bulletin Studio")
        self.assertEqual(str(menu_label(None)), "Bulletin Studio", "not installed as a package")


# smallest valid PNG: the image form checks the real format, not the extension
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class ImageStoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))

    def test_upload_then_browse(self):
        url = reverse("bulletin_studio:images")
        self.assertEqual(self.client.get(url).json(), [])

        created = self.client.post(url, {
            "title": "Rainfall map",
            "file": SimpleUploadedFile("map.png", PNG, content_type="image/png"),
        })
        self.assertEqual(created.status_code, 201)
        payload = created.json()
        # a rendition, not the original: a 4000px photo must not reach the page
        self.assertTrue(payload["url"].endswith(".png"))
        self.assertTrue(payload["thumb"])
        self.assertEqual(payload["title"], "Rainfall map")

        self.assertEqual([i["id"] for i in self.client.get(url).json()], [payload["id"]])
        self.assertEqual(self.client.get(url, {"q": "rain"}).json()[0]["id"], payload["id"])
        self.assertEqual(self.client.get(url, {"q": "snow"}).json(), [])

        refused = self.client.post(url, {
            "title": "Not an image",
            "file": SimpleUploadedFile("x.png", b"not a png", content_type="image/png"),
        })
        self.assertEqual(refused.status_code, 400)

    def test_with_several_collections(self):
        # the forecast maps make a second collection: Wagtail's form then asks for one
        Collection.get_first_root_node().add_child(name="Forecast maps")
        url = reverse("bulletin_studio:images")

        def upload(title, **extra):
            response = self.client.post(url, {
                "title": title, "file": SimpleUploadedFile("x.png", PNG, content_type="image/png"), **extra})
            self.assertEqual(response.status_code, 201, response.content)
            return get_image_model().objects.get(pk=response.json()["id"])

        photo = upload("Photo")
        self.assertEqual(photo.collection, Collection.get_first_root_node())
        flash = upload("Heavy rain", purpose="flash")
        self.assertEqual(flash.collection.name, "Media flashes")
        self.assertEqual(upload("Second flash", purpose="flash").collection, flash.collection)

        # the flashes' captures stay out of the picker, unless searched for
        self.assertEqual([i["id"] for i in self.client.get(url).json()], [photo.pk])
        self.assertEqual([i["id"] for i in self.client.get(url, {"q": "rain"}).json()], [flash.pk])


class LetterheadTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))

    def test_the_organisation_identity_reaches_the_studio(self):
        url = reverse("bulletin_studio:app")
        self.assertNotContains(self.client.get(url), "data-letterhead")

        organisation = OrganisationSetting.for_site(Site.objects.get(is_default_site=True))
        organisation.logo, organisation.country_flag = (
            get_image_model().objects.create(
                title=name, file=SimpleUploadedFile(f"{name}.png", PNG, content_type="image/png"))
            for name in ("logo", "flag"))
        organisation.name = "Météo Test"
        organisation.save()
        page = self.client.get(url).content.decode()
        # renditions, as for the bulletin's own images
        self.assertRegex(page, r'data-letterhead-logo="/media/images/logo[^"]*\.height-240\.png"')
        self.assertRegex(page, r'data-letterhead-flag="/media/images/flag[^"]*\.height-240\.png"')
        self.assertIn('data-letterhead-text="Météo Test"', page)

        # the navbar's text beside the logo comes first
        organisation.logo_append = "Agence nationale de la météorologie"
        organisation.save()
        self.assertContains(self.client.get(url), 'data-letterhead-text="Agence nationale de la météorologie"')


class StudioStaticTests(SimpleTestCase):
    """The bundle's entries keep their names, and Django serves static files with no
    Cache-Control: a browser kept an old stylesheet under a new script for hours. Their
    urls carry the file's version instead."""

    ENTRY = "bulletin_studio/test-only/entry.css"  # not a file of the real bundle

    def setUp(self):
        self.source = tempfile.TemporaryDirectory()
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.source.cleanup)
        self.addCleanup(self.root.cleanup)
        storages = {**settings.STORAGES,
                    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
        overridden = override_settings(STATICFILES_DIRS=[self.source.name], STATIC_ROOT=self.root.name,
                                       STATIC_URL="/static/", STORAGES=storages)
        overridden.enable()
        self.addCleanup(overridden.disable)

    def write(self, base, mtime):
        path = os.path.join(base, self.ENTRY)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "w").close()
        os.utime(path, (mtime, mtime))

    def test_the_source_until_collected(self):
        self.write(self.source.name, 1_800_000_000)
        self.assertEqual(studio_static(self.ENTRY), f"/static/{self.ENTRY}?v=1800000000")

    def test_the_collected_copy_is_the_one_served(self):
        self.write(self.source.name, 1_800_000_000)
        self.write(self.root.name, 1_800_000_500)
        self.assertEqual(studio_static(self.ENTRY), f"/static/{self.ENTRY}?v=1800000500")

    def test_no_file_no_version(self):
        self.assertEqual(studio_static(self.ENTRY), f"/static/{self.ENTRY}")

    def test_a_hashed_name_is_left_alone(self):
        hashed = "/static/bulletin_studio/test-only/entry.0123abcd.css"
        with mock.patch("bulletin_studio.templatetags.bulletin_studio_tags.static", return_value=hashed):
            self.assertEqual(studio_static(self.ENTRY), hashed)
