"""Which forecast the daily map draws - a per-site setting, chosen by the met office.

The periods are stored as their effective time ("06:00"), not as foreign keys to
forecastmanager's ForecastPeriod: a migration depending on forecastmanager would stop
a ClimWeb without it (IS_METEOROLOGICAL=false) from migrating. The effective time is
unique, and survives a period being relabelled ("Journalière", "Morning"...), which
the label would not.
"""
from django import forms
from django.apps import apps
from django.core.validators import MaxValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.admin.panels import FieldPanel
from wagtail.contrib.settings.models import BaseSiteSetting, register_setting


def period_choices():
    """The site's forecast periods, as forecastmanager defines them."""
    if not apps.is_installed("forecastmanager"):
        return []
    from forecastmanager.forecast_settings import ForecastPeriod

    return [(f"{p.forecast_effective_time:%H:%M}", f"{p.label} ({p.forecast_effective_time:%H:%M})")
            for p in ForecastPeriod.objects.order_by("forecast_effective_time")]


class ForecastMapSettingsForm(WagtailAdminModelForm):
    periods = forms.MultipleChoiceField(
        label=_("Daily forecast periods"), required=False, widget=forms.CheckboxSelectMultiple,
        help_text=_("The periods your service publishes as the forecast of the day. "
                    "One map is drawn per period, after each forecast update."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["periods"].choices = period_choices()


@register_setting(icon="globe")
class ForecastMapSettings(BaseSiteSetting):
    base_form_class = ForecastMapSettingsForm

    periods = models.JSONField(default=list, blank=True)  # ["06:00", ...]
    days_ahead = models.PositiveSmallIntegerField(
        default=1, validators=[MaxValueValidator(6)], verbose_name=_("Days ahead"),
        help_text=_("Draw today's maps and those of the following days: 0 for today only, "
                    "6 at most (a forecast pull covers a week)."))

    panels = [FieldPanel("periods"), FieldPanel("days_ahead")]

    class Meta:
        verbose_name = _("Forecast map")
