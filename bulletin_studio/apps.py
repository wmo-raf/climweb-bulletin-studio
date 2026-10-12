from django.apps import AppConfig


class BulletinStudioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bulletin_studio"
    verbose_name = "Bulletin Studio"

    def ready(self):
        # ClimWeb hardcodes ProductPage.subpage_types to ProductItemPage, so Wagtail
        # would not let a bulletin sit under a product page (moving one in the explorer)
        # until we add it here. `is_creatable = False` keeps it out of "Add child page".
        from climweb.pages.products.models import ProductPage

        if "bulletin_studio.BulletinPage" not in ProductPage.subpage_types:
            ProductPage.subpage_types = list(ProductPage.subpage_types) + ["bulletin_studio.BulletinPage"]
