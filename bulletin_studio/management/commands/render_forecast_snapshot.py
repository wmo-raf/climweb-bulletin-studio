"""Draw the forecast map of one date and period into the media storage.

    manage.py render_forecast_snapshot --list                 # published periods of today
    manage.py render_forecast_snapshot --period 06:00         # today, bulletin preset
    manage.py render_forecast_snapshot --date 2026-10-05 --period 06:00 --preset social
"""
from datetime import date, datetime

from django.apps import apps
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from bulletin_studio.forecast.render import PRESETS


def parse_date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"--date: expected YYYY-MM-DD, got {value!r}") from exc


class Command(BaseCommand):
    help = "Render the forecast map of one date and period (published forecasts only)."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=parse_date, help="YYYY-MM-DD, default today (site time zone)")
        parser.add_argument("--period", help="effective time of the period, HH:MM")
        parser.add_argument("--preset", choices=list(PRESETS), default="bulletin")
        parser.add_argument("--list", action="store_true", help="list the published periods of the date")

    def handle(self, *args, **options):
        if not apps.is_installed("forecastmanager"):
            raise CommandError("forecastmanager is not installed on this site.")
        from forecastmanager.models import Forecast

        from bulletin_studio.forecast.snapshots import write_snapshot

        day = options["date"] or timezone.localdate()
        if options["list"] or not options["period"]:
            forecasts = (Forecast.objects
                         .filter(forecast_date=day, status=Forecast.STATUS_PUBLISHED)
                         .select_related("effective_period").order_by("effective_period__forecast_effective_time"))
            if not forecasts:
                raise CommandError(f"No published forecast on {day}.")
            for f in forecasts:
                p = f.effective_period
                self.stdout.write(f"{day}  {p.forecast_effective_time:%H:%M}  {p.label}")
            if not options["list"]:
                raise CommandError("Pick one with --period HH:MM.")
            return

        try:
            period = datetime.strptime(options["period"], "%H:%M").time()
        except ValueError as exc:
            raise CommandError(f"--period: expected HH:MM, got {options['period']!r}") from exc

        name = write_snapshot(day, period, options["preset"])
        if name is None:
            raise CommandError(f"No published forecast on {day} at {period:%H:%M}.")
        self.stdout.write(self.style.SUCCESS(f"{name}  ({default_storage.url(name)})"))
