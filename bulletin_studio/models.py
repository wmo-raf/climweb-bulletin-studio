import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class Bulletin(models.Model):
    """A bulletin document, as produced by the Bulletin Studio JS editor.

    `doc` stores the editor's own JSON verbatim ({"blocks": [...]}). The block
    schema belongs to the frontend, so the server keeps it opaque - no Python
    mirror of it to keep in sync.

    The pk is a UUID because the editor mints ids client-side
    (crypto.randomUUID) and PUTs them, so saving is an upsert with no
    round-trip to allocate an id.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, blank=True, default="")
    doc = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("Bulletin")
        verbose_name_plural = _("Bulletins")

    def __str__(self):
        return self.title or str(self.pk)

    @property
    def blocks(self):
        blocks = self.doc.get("blocks") if isinstance(self.doc, dict) else None
        return blocks if isinstance(blocks, list) else []
