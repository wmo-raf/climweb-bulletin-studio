"""`{% studio_static %}`: `{% static %}` for the bundle's entry files, with their version.

The entries keep stable names (`bulletin-studio.js`, `.css`…), the templates load them.
In production ManifestStaticFilesStorage hashes them, but the dev storage does not, and
Django serves static files with no Cache-Control: a browser then keeps what it has for
10 % of the file's age (heuristic freshness), hours for a file collected days earlier,
without asking. It runs a new script with an old stylesheet, or the reverse. The file's
modification time in the query string makes every build a new url.
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.templatetags.static import static

register = template.Library()


def _mtime(path):
    """The served copy (STATIC_ROOT, once collected), else the app's own."""
    try:
        collected = staticfiles_storage.path(path)
        if os.path.exists(collected):
            return int(os.path.getmtime(collected))
    except NotImplementedError:  # a remote storage: no local file to look at
        pass
    found = finders.find(path)
    return int(os.path.getmtime(found)) if found else None


@register.simple_tag
def studio_static(path):
    url = static(path)
    # a hashed name already changes with its content
    if os.path.basename(url.split("?")[0]) != os.path.basename(path):
        return url
    version = _mtime(path)
    return f"{url}?v={version}" if version else url
