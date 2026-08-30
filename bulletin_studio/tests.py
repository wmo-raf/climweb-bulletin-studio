"""One pass over the store API: a template, an issue made from it, a draft save,
a publication, and the public page serving the rendered html."""
import base64
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse as _reverse
from django.urls import reverse
from wagtail.models import Page, Site

from climweb.base.models.snippets import Product, ServiceCategory
from climweb.pages.home.models import HomePage
from climweb.pages.products.models import ProductIndexPage, ProductPage

from .models import BulletinPage


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

        url = reverse("bulletin_studio:bulletin", args=[issue["id"]])
        # Saving is a draft, and the html is sanitized on the way in.
        saved = self.client.put(url, data=json.dumps({
            "title": "Decadal bulletin no 12", "doc": {"blocks": []},
            "html": "<p>rain</p><script>alert(1)</script>",
            "isTemplate": False}), content_type="application/json").json()
        self.assertFalse(saved["live"])
        self.assertEqual(BulletinPage.objects.get(pk=issue["id"]).html, "<p>rain</p>")

        published = self.client.post(
            reverse("bulletin_studio:publish", args=[issue["id"]])).json()
        self.assertTrue(published["live"])
        self.assertTrue(published["url"])

        page = BulletinPage.objects.get(pk=issue["id"])
        self.assertContains(self.client.get(page.url), "rain")
        # The template has no public page even if it somehow went live.
        BulletinPage.objects.filter(pk=tpl["id"]).update(live=True)
        self.assertEqual(self.client.get(BulletinPage.objects.get(pk=tpl["id"]).url).status_code, 404)

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(BulletinPage.objects.filter(pk=issue["id"]).exists())


# smallest valid PNG: the image form checks the real format, not the extension
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


class ImageStoreTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "a@example.com", "pw"))

    def test_upload_then_browse(self):
        url = _reverse("bulletin_studio:images")
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
