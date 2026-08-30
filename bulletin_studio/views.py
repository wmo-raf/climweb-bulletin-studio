"""Admin page + JSON store for the Bulletin Studio JS app.

The JS app is the whole UI: `app()` renders the Wagtail admin shell with a mount
point, everything else is what its store needs (pick a product, list, read, save,
publish, delete). All views sit behind `require_admin_access` and keep Django's
CSRF check - the app sends `X-CSRFToken` from the mount point's data attribute.

Saving writes a Wagtail draft revision; publishing is an explicit action, so the
public page keeps serving the last published `html` while an issue is reworked.
"""
import json
import os

import nh3
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods
from wagtail.admin.auth import require_admin_access
from wagtail.images import get_image_model
from wagtail.images.forms import get_image_form

from climweb.pages.products.models import ProductPage

from .models import BulletinPage

MAX_BODY = 5 * 1024 * 1024  # a bulletin is text + image references, not a payload dump

# What goes into a bulletin, and what the picker shows. Renditions are files on
# disk, so the urls stay valid in the published html snapshot.
IMAGE_RENDITION = "width-1200"
IMAGE_THUMB = "fill-160x120"
IMAGE_PAGE = 24

# Point this at a running `npm run dev` (e.g. http://localhost:5180) to serve the
# frontend from Vite with HMR instead of the bundle vendored under static/.
DEV_SERVER = os.environ.get("BULLETIN_STUDIO_DEV_SERVER", "").rstrip("/")

# The rendered html comes from the browser, so it is untrusted input even though
# only staff reach these views: sanitize on write, never on read. The editor emits
# `bs-*` classes and inline styles only - no script, no event handlers, ever.
ALLOWED_TAGS = {
    "div", "p", "span", "a", "br", "hr", "strong", "em", "u", "s",
    "h1", "h2", "h3", "h4", "ul", "ol", "li", "blockquote",
    "img", "figure", "figcaption", "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRS = {
    "*": {"class", "style"},
    "a": {"href", "target"},  # nh3 sets rel="noopener noreferrer" itself
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}


@require_admin_access
def app(request):
    return render(request, "bulletin_studio/app.html", {"dev_server": DEV_SERVER})


def _ms(dt):
    return int(dt.timestamp() * 1000) if dt else None


def _meta(page, parent=None):
    """Dashboard listing shape - no doc, the list view never renders it."""
    parent = parent or page.get_parent()
    return {
        "id": page.pk,
        "title": page.title,
        "isTemplate": page.is_template,
        "parent": parent.pk,
        "parentTitle": parent.title,
        "blockCount": page.block_count,
        "updatedAt": _ms(page.latest_revision_created_at or page.last_published_at),
        "live": page.live,
        "hasUnpublishedChanges": page.has_unpublished_changes,
        "url": page.get_url() if page.live and not page.is_template else None,
    }


def _full(page, parent=None):
    return {**_meta(page, parent), "doc": page.doc}


def _read_body(request):
    """Parse and validate an editor payload. Returns a dict or raises ValueError."""
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

    doc = data.get("doc", {})
    if not isinstance(doc, dict):
        raise ValueError("doc must be an object")

    html = data.get("html", "")
    if not isinstance(html, str):
        raise ValueError("html must be a string")

    return {
        "title": title,
        "doc": doc,
        "html": nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS),
        "is_template": bool(data.get("isTemplate", False)),
        "parent": data.get("parent"),
    }


@require_admin_access
@require_http_methods(["GET"])
def product_pages(request):
    """The products a bulletin can live under - the editor picks one when it
    creates a template, and every issue made from that template inherits it."""
    return JsonResponse(
        [{"id": p.pk, "title": p.title} for p in ProductPage.objects.all()], safe=False)


@require_admin_access
@require_http_methods(["GET", "POST"])
def bulletins(request):
    if request.method == "POST":
        try:
            body = _read_body(request)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        try:
            parent = ProductPage.objects.get(pk=body["parent"])
        except (ProductPage.DoesNotExist, TypeError, ValueError):
            return JsonResponse({"error": "parent must be the id of a product page"}, status=400)

        # live=False must be set *before* add_child, or Wagtail publishes the page.
        page = BulletinPage(doc=body["doc"], html=body["html"],
                            is_template=body["is_template"], live=False)
        page.apply_title(body["title"], parent=parent)
        parent.add_child(instance=page)
        page.save_revision()
        return JsonResponse(_full(page, parent), status=201)

    pages = BulletinPage.objects.all().order_by("-latest_revision_created_at")
    return JsonResponse([_meta(p) for p in pages], safe=False)


@require_admin_access
@require_http_methods(["GET", "PUT", "DELETE"])
def bulletin(request, pk):
    page = get_object_or_404(BulletinPage, pk=pk)

    if request.method == "DELETE":
        page.delete()
        return HttpResponse(status=204)

    if request.method == "PUT":
        try:
            body = _read_body(request)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        page.doc, page.html = body["doc"], body["html"]
        page.apply_title(body["title"])
        # A page that was never published has no public version to protect, so the
        # row follows the draft and the dashboard stays in sync. Once live, only
        # the revision moves until someone publishes.
        if not page.live:
            page.save()
        page.save_revision()
        return JsonResponse(_full(page))

    # The editor opens the draft, not the published version.
    return JsonResponse(_full(page.get_latest_revision_as_object(), page.get_parent()))


@require_admin_access
@require_http_methods(["POST"])
def publish(request, pk):
    page = get_object_or_404(BulletinPage, pk=pk)
    if page.is_template:
        raise Http404
    (page.get_latest_revision() or page.save_revision()).publish()
    page.refresh_from_db()
    return JsonResponse(_meta(page))


def _image(image):
    rendition = image.get_rendition(IMAGE_RENDITION)
    return {
        "id": image.pk,
        "title": image.title,
        "url": rendition.url,
        "width": rendition.width,
        "height": rendition.height,
        "thumb": image.get_rendition(IMAGE_THUMB).url,
        "alt": image.description or "",
    }


@require_admin_access
@require_http_methods(["GET", "POST"])
def images(request):
    """The bulletin's images are ClimWeb images: uploading here puts them in the
    site's own library, and the picker browses what is already there.

    Validation is Wagtail's own image form - it checks the real file format, not
    the extension, and enforces WAGTAILIMAGES_MAX_UPLOAD_SIZE."""
    Image = get_image_model()

    if request.method == "POST":
        if not request.user.has_perm("wagtailimages.add_image"):
            return JsonResponse({"error": "not allowed to add images"}, status=403)
        form = get_image_form(Image)(request.POST, request.FILES,
                                     instance=Image(), user=request.user)
        if not form.is_valid():
            first = next(iter(form.errors.values()))[0]
            return JsonResponse({"error": first}, status=400)
        image = form.save(commit=False)
        image.uploaded_by_user = request.user
        image.save()
        form.save_m2m()
        return JsonResponse(_image(image), status=201)

    q = request.GET.get("q", "").strip()
    qs = Image.objects.all()
    if q:
        qs = qs.filter(title__icontains=q)
    return JsonResponse([_image(i) for i in qs.order_by("-created_at")[:IMAGE_PAGE]], safe=False)
