from django.urls import include, path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem

from . import urls as bulletin_studio_urls


@hooks.register("register_admin_urls")
def register_bulletin_studio_urls():
    return [
        path("bulletin-studio/", include((bulletin_studio_urls, "bulletin_studio"))),
    ]


@hooks.register("register_admin_menu_item")
def register_bulletin_studio_menu_item():
    # Single entry -> the JS app, which does its own routing (dashboard, editor)
    # behind the hash. Nothing else to hang off the Wagtail menu.
    return MenuItem(_("Bulletin Studio"), reverse("bulletin_studio:app"),
                    icon_name="doc-full", order=200)
