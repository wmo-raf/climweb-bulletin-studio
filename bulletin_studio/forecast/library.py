"""The stored maps as the editor sees them: which are available, and the promotion of
one into the Wagtail library - the frozen copy a bulletin references.

The file under `forecast_snapshots/` is the latest render, rewritten after each pull: a
bulletin pointing at it would change under its readers. Promoting copies it into an
Image, once per version. The version is the PNG's sha1, which Wagtail itself stores as
`file_hash` to spot duplicates: promoting the same render twice returns the same image,
a new render gets a new image, and the old one stays with the bulletins using it.

Import this module lazily, like `snapshots`: it needs forecastmanager.
"""
import io
import logging
from datetime import datetime, timedelta

from django.core.files.images import ImageFile
from django.core.files.storage import default_storage
from django.utils import timezone
from PIL import Image as PILImage
from wagtail.images import get_image_model
from wagtail.models import Collection, Site
from wagtail.utils.file import hash_filelike

from . import MAPS_COLLECTION
from .models import ForecastMapSettings, period_labels
from .snapshots import DAILY_PRESETS, snapshot_name

logger = logging.getLogger(__name__)


def _ms(dt):
    return int(dt.timestamp() * 1000)


def stored_map(day, period_time, preset):
    """The map currently stored for that slot - url, version, render time - or None."""
    name = snapshot_name(day, period_time, preset, "png")
    try:
        with default_storage.open(name) as f:
            version = hash_filelike(f)
        rendered_at = default_storage.get_modified_time(name)
    except FileNotFoundError:  # never drawn, or being redrawn right now
        return None
    return {
        "date": day.isoformat(),
        "period": f"{period_time:%H:%M}",
        "preset": preset,
        # same url for every render of the slot: the version keeps browsers from
        # showing the previous one from their cache
        "url": f"{default_storage.url(name)}?v={version[:12]}",
        "version": version,
        "renderedAt": _ms(rendered_at),
    }


def available(day=None):
    """What the forecast block can offer, from `day` (today by default) to `days_ahead`
    days later: the periods the office set as the forecast of the day, and the maps
    drawn so far. "Today" is the site's, as forecastmanager has it, not the browser's."""
    settings = ForecastMapSettings.for_site(Site.objects.get(is_default_site=True))
    today = timezone.localdate()
    day = day or today
    labels = period_labels()
    maps = []
    for offset in range(settings.days_ahead + 1):
        for period in settings.periods:
            for preset in DAILY_PRESETS:
                found = stored_map(day + timedelta(days=offset),
                                   datetime.strptime(period, "%H:%M").time(), preset)
                if found:
                    maps.append(found)
    return {
        "today": today.isoformat(),
        "daysAhead": settings.days_ahead,
        "periods": [{"time": p, "label": labels.get(p, p)} for p in settings.periods],
        "presets": list(DAILY_PRESETS),
        "maps": maps,
    }


def collection():
    """The library collection of the promoted maps, created on first use."""
    root = Collection.get_first_root_node()
    return root.get_children().filter(name=MAPS_COLLECTION).first() or root.add_child(name=MAPS_COLLECTION)


def promote(day, period_time, preset, user=None):
    """(image, details) for the map currently stored for that slot, or None when there
    is none. The image is created on the first promotion of this version only."""
    name = snapshot_name(day, period_time, preset, "png")
    try:
        with default_storage.open(name) as f:
            content = f.read()
        # The storage writes a render in place: caught halfway, the PNG is cut short,
        # and an issue would freeze it as is. Better no map for a moment.
        PILImage.open(io.BytesIO(content)).verify()
    except FileNotFoundError:
        return None
    except Exception:
        logger.warning("Forecast map: %s is incomplete, probably being redrawn", name)
        return None
    version = hash_filelike(io.BytesIO(content))
    period = f"{period_time:%H:%M}"
    label = period_labels().get(period, period)

    Image = get_image_model()
    maps = collection()
    image = Image.objects.filter(collection=maps, file_hash=version).first()
    if image is None:
        image = Image(
            title=f"Forecast map — {day:%Y-%m-%d} — {label}", collection=maps,
            file=ImageFile(io.BytesIO(content), name=f"forecast-{day:%Y-%m-%d}-{period_time:%Hh%M}-{preset}.png"),
            # what Wagtail's upload form would compute, from the bytes already read
            file_size=len(content), file_hash=version, uploaded_by_user=user)
        image.save()
    return image, {"date": day.isoformat(), "period": period, "periodLabel": label,
                   "preset": preset, "version": version}
