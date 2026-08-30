"""Smallest check that the store round-trips and stays staff-only.

Run from the sandbox:  python manage.py test bulletin_studio
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Bulletin

DOC = {"title": "Bulletin agromet", "blocks": [{"id": "1", "type": "text"}]}


class StoreTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="x", is_staff=True,
                                              is_superuser=True)

    def test_requires_admin_access(self):
        for url in (reverse("bulletin_studio:app"), reverse("bulletin_studio:bulletins")):
            self.assertEqual(self.client.get(url).status_code, 302, url)

    def test_page_mounts_the_app(self):
        self.client.force_login(self.staff)
        html = self.client.get(reverse("bulletin_studio:app")).content.decode()
        self.assertIn('id="bulletin-studio-app"', html)
        self.assertIn(reverse("bulletin_studio:bulletins"), html)

    def test_create_list_read_save_delete(self):
        self.client.force_login(self.staff)
        listing = reverse("bulletin_studio:bulletins")

        created = self.client.post(listing, DOC, content_type="application/json")
        self.assertEqual(created.status_code, 201)
        pk = created.json()["id"]

        self.assertEqual(self.client.get(listing).json(),
                         [{"id": pk, "title": DOC["title"], "blockCount": 1,
                           "updatedAt": created.json()["updatedAt"]}])

        detail = reverse("bulletin_studio:bulletin", args=[pk])
        self.assertEqual(self.client.get(detail).json()["blocks"], DOC["blocks"])

        saved = self.client.put(detail, {"title": "v2", "blocks": []},
                                content_type="application/json")
        self.assertEqual((saved.status_code, saved.json()["title"]), (200, "v2"))

        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertEqual(Bulletin.objects.count(), 0)

    def test_put_on_unknown_id_creates_it(self):
        """The editor mints ids client-side, so a first save is a create."""
        self.client.force_login(self.staff)
        url = reverse("bulletin_studio:bulletin", args=["0f0e4b1e-0000-4000-8000-000000000001"])
        self.assertEqual(self.client.put(url, DOC, content_type="application/json").status_code, 201)
        self.assertEqual(Bulletin.objects.count(), 1)

    def test_rejects_bad_payloads(self):
        self.client.force_login(self.staff)
        listing = reverse("bulletin_studio:bulletins")
        for body in (b"not json", json.dumps([1]).encode(),
                     json.dumps({"blocks": "nope"}).encode(),
                     json.dumps({"title": "x" * 256}).encode()):
            self.assertEqual(self.client.post(listing, body,
                                              content_type="application/json").status_code,
                             400, body[:20])
        self.assertEqual(Bulletin.objects.count(), 0)
