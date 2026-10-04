import logging

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import include, path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.models import Page

from . import urls as bulletin_studio_urls
from .models import BulletinPage

logger = logging.getLogger(__name__)


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


def _unrendered(page):
    """An issue whose html the studio never rendered - one the server prepared. Its
    public page would be blank: it goes online from the studio, which renders it."""
    if not (isinstance(page, Page) and issubclass(page.specific_class or Page, BulletinPage)):
        return False  # every page publication passes here: no query for the others
    page = page.specific
    return not page.is_template and not page.get_latest_revision_as_object().html.strip()


UNRENDERED = _("This bulletin has not been composed yet: open it in Bulletin Studio to "
               "review and publish it.")


@hooks.register("before_publish_page")
def keep_unrendered_bulletin_offline(request, page):
    if _unrendered(page):
        messages.error(request, UNRENDERED)
        return redirect("wagtailadmin_pages:edit", page.pk)


@hooks.register("before_bulk_action")
def keep_unrendered_bulletins_offline(request, action_type, objects, action_class_instance):
    if action_type == "publish" and any(_unrendered(obj) for obj in objects):
        messages.error(request, UNRENDERED)
        return redirect(getattr(action_class_instance, "next_url", None) or "wagtailadmin_explore_root")


# forecastmanager fires these after writing forecasts: the yr pull (not Open-Meteo's)
# and the admin form. Nothing fires them on a site without forecastmanager.
@hooks.register("after_generate_forecast")
def render_forecast_maps_after_pull(forecast_pks):
    _queue_forecast_maps()


@hooks.register("after_forecast_add_from_form")
def render_forecast_maps_after_form():
    _queue_forecast_maps()


def _queue_forecast_maps():
    """Queue the render, never run it here: the pull hook runs inside ClimWeb's
    forecast task, under its 30-minute lock. And never fail it: the forecast is
    already committed, a broker hiccup only costs this round of maps."""
    from .tasks import render_daily_forecast_maps

    def send():
        try:
            render_daily_forecast_maps.delay()
        except Exception:
            logger.exception("Forecast map: could not queue the render")

    transaction.on_commit(send)
