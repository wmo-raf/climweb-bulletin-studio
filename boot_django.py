"""Minimal Django setup for the management shims (makemigrations.py, migrate.py).

The app has no GIS or Postgres-specific SQL, so sqlite is enough here. The
sandbox is the place to exercise it against a real Wagtail install.
"""
import os

import django
from django.conf import settings

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "bulletin_studio"))

SECRET_KEY = "django-insecure-bulletin-studio-local-only-do-not-use-in-production"

INSTALLED_APPS = [
    "bulletin_studio",

    "wagtail",
    "taggit",

    "django.contrib.auth",
    "django.contrib.contenttypes",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.path.join(os.path.dirname(__file__), "db.sqlite3"),
    }
}


def boot_django():
    settings.configure(
        BASE_DIR=BASE_DIR,
        DEBUG=True,
        INSTALLED_APPS=INSTALLED_APPS,
        TIME_ZONE="UTC",
        USE_TZ=True,
        SECRET_KEY=SECRET_KEY,
        DATABASES=DATABASES,
    )
    django.setup()
