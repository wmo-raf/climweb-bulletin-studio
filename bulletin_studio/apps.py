from django.apps import AppConfig


class BulletinStudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bulletin_studio"
    verbose_name = "Bulletin Studio"

    def ready(self):
        # ClimWeb hardcodes ProductPage.subpage_types to ProductItemPage, so our
        # subclass is not creatable underneath it until we add it here.
        from climweb.pages.products.models import ProductPage

        if "bulletin_studio.BulletinPage" not in ProductPage.subpage_types:
            ProductPage.subpage_types = list(ProductPage.subpage_types) + ["bulletin_studio.BulletinPage"]
