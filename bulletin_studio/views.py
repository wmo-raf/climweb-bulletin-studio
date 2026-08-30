"""Admin page + JSON store for the Bulletin Studio JS app.

The JS app is the whole UI: `app()` renders the Wagtail admin shell with a mount
point, everything else is the four operations its store needs (list, read,
save, delete). All views sit behind `require_admin_access` and keep Django's
CSRF check - the app sends `X-CSRFToken` from the mount point's data attribute.
"""
import json
import os

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from wagtail.admin.auth import require_admin_access

from .models import Bulletin

MAX_BODY = 5 * 1024 * 1024  # a bulletin is text + image references, not a payload dump

# Point this at a running `npm run dev` (e.g. http://localhost:5173) to serve the
# frontend from Vite with HMR instead of the bundle vendored under static/.
DEV_SERVER = os.environ.get("BULLETIN_STUDIO_DEV_SERVER", "").rstrip("/")


@require_admin_access
def app(request):
    # `asset_base` is where the app's own public files (sample bulletin, icons) live:
    # the Vite dev server in dev, the collected static dir otherwise.
    asset_base = f"{DEV_SERVER}/" if DEV_SERVER else f"{settings.STATIC_URL}bulletin_studio/app/"
    return render(request, "bulletin_studio/app.html",
                  {"dev_server": DEV_SERVER, "asset_base": asset_base})


def _meta(b):
    """Dashboard listing shape - no blocks, the list view never renders them."""
    return {
        "id": str(b.pk),
        "title": b.title,
        "updatedAt": int(b.updated_at.timestamp() * 1000),
        "blockCount": len(b.blocks),
    }


def _full(b):
    return {"id": str(b.pk), "title": b.title, "blocks": b.blocks,
            "updatedAt": int(b.updated_at.timestamp() * 1000)}


def _read_doc(request):
    """Parse and validate a bulletin payload. Returns (title, blocks) or raises ValueError."""
    if len(request.body) > MAX_BODY:
        raise ValueError("payload too large")
    try:
        data = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")

    title = data.get("title", "")
    if not isinstance(title, str) or len(title) > 255:
        raise ValueError("title must be a string of at most 255 characters")

    blocks = data.get("blocks", [])
    if not isinstance(blocks, list):
        raise ValueError("blocks must be a list")

    return title, blocks


@require_admin_access
@require_http_methods(["GET", "POST"])
def bulletins(request):
    if request.method == "POST":
        try:
            title, blocks = _read_doc(request)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        b = Bulletin.objects.create(title=title, doc={"blocks": blocks})
        return JsonResponse(_full(b), status=201)

    return JsonResponse([_meta(b) for b in Bulletin.objects.all()], safe=False)


@require_admin_access
@require_http_methods(["GET", "PUT", "DELETE"])
def bulletin(request, pk):
    if request.method == "PUT":
        # Upsert: the editor owns the id, so a save on a bulletin the server has
        # never seen creates it rather than 404ing.
        try:
            title, blocks = _read_doc(request)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        b, created = Bulletin.objects.update_or_create(
            pk=pk, defaults={"title": title, "doc": {"blocks": blocks}},
        )
        return JsonResponse(_full(b), status=201 if created else 200)

    try:
        b = Bulletin.objects.get(pk=pk)
    except Bulletin.DoesNotExist:
        raise Http404

    if request.method == "DELETE":
        b.delete()
        return HttpResponse(status=204)

    return JsonResponse(_full(b))
