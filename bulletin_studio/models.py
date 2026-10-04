"""The bulletin as a ClimWeb product item.

A bulletin is a page under a `ProductPage`: `is_template=True` marks the starting
point an editor duplicates, the others are the issues, which ClimWeb's products
machinery lists and filters natively (year/month filters read `date`).

`doc` is the JS editor's own JSON, kept opaque - the block schema belongs to the
frontend. `html` is what that editor rendered from it, and the only thing the
public page serves, so there is no Python renderer to keep in sync with the JS.
"""
from django.db import models
from django.http import Http404
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminPageForm

from climweb.pages.products.models import ProductItemPage


def unique_child_slug(parent, base, exclude_pk=None):
    """A slug unique among `parent`'s children - Wagtail enforces sibling unicity."""
    base = base or "bulletin"
    slug, n = base, 1
    siblings = parent.get_children()
    if exclude_pk:
        siblings = siblings.exclude(pk=exclude_pk)
    while siblings.filter(slug=slug).exists():
        n += 1
        slug = f"{base}-{n}"
    return slug


class BulletinPage(ProductItemPage):
    # The native ProductItemPage form reads `parent.product.product_item_types` to
    # rebuild the `products` StreamField, which we don't use - the plain page form
    # skips it. Editing happens in the JS studio anyway, not in the page editor.
    base_form_class = WagtailAdminPageForm
    template = "bulletin_studio/bulletin_page.html"
    parent_page_types = ["products.ProductPage"]
    subpage_types = []

    doc = models.JSONField(default=dict, blank=True)
    html = models.TextField(blank=True, default="")
    is_template = models.BooleanField(default=False, verbose_name=_("Template"))

    class Meta:
        verbose_name = _("Bulletin")
        verbose_name_plural = _("Bulletins")

    @property
    def block_count(self):
        blocks = self.doc.get("blocks") if isinstance(self.doc, dict) else None
        return len(blocks) if isinstance(blocks, list) else 0

    def apply_title(self, title, parent=None):
        """The title comes from the editor. The slug follows it until the first
        publication, then freezes so public URLs stay stable."""
        self.title = title.strip() or str(_("Untitled bulletin"))
        if not self.live:
            parent = parent or self.get_parent()
            self.slug = unique_child_slug(parent, slugify(self.title), exclude_pk=self.pk)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        # Maps hydrate client-side: the document carries the layer, the frozen date
        # and the legend, the site supplies the admin boundaries around them.
        context["has_map"] = "bs-map" in self.html
        if context["has_map"]:
            from .views import map_settings
            context["map"] = map_settings(request)
        return context

    def serve(self, request, *args, **kwargs):
        # A template is a starting point, not an issue: it has no public page even
        # if someone publishes it by hand from the Wagtail explorer.
        if self.is_template:
            raise Http404
        return super().serve(request, *args, **kwargs)


# Per-site setting of the forecast map; lives with the rest of the forecast code.
from .forecast.models import ForecastMapSettings  # noqa: E402, F401
