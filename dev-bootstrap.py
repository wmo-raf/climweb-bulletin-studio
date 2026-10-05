# Seeds an empty dev database with the minimum the studio needs: an admin user,
# a HomePage as the site root, a ProductIndexPage and one ProductPage to host
# templates. Idempotent. Run it through the Django shell:
#
#   docker compose -f docker-compose.dev.yml exec -T climweb \
#     /climweb/web/src/climweb/manage.py shell < dev-bootstrap.py
#
# Login: admin / admin (dev only).
from django.contrib.auth import get_user_model
from django.db import connection
from wagtail.models import Page, Site

from climweb.base.models.snippets import Product, ServiceCategory
from climweb.pages.home.models import HomePage
from climweb.pages.products.models import ProductIndexPage, ProductPage

User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser("admin", "admin@example.com", "admin")
    print("superuser admin / admin")

home = HomePage.objects.first()
if home is None:
    # ClimWeb dropped these HomePage fields without a migration: the columns are
    # still NOT NULL in the database but the model no longer fills them.
    with connection.cursor() as cursor:
        cursor.execute("""
            DO $$ BEGIN
              ALTER TABLE home_homepage ALTER COLUMN hero_type SET DEFAULT 'card';
              ALTER TABLE home_homepage ALTER COLUMN show_banner_video SET DEFAULT false;
            EXCEPTION WHEN undefined_column THEN NULL;
            END $$;
        """)
    root = Page.get_first_root_node()
    # Wagtail's "Welcome" placeholder holds the "home" slug and the default Site.
    placeholder = root.get_children().exact_type(Page).first()
    if placeholder is not None:
        placeholder.slug = "wagtail-welcome"
        placeholder.save_revision().publish()
    home = root.add_child(instance=HomePage(title="Home", slug="home", hero_title="ClimWeb"))
    site = Site.objects.filter(is_default_site=True).first() or Site(hostname="localhost", is_default_site=True)
    site.root_page = home
    site.port = 80
    site.save()
    if placeholder is not None:
        placeholder.delete()
    print("HomePage created")

index = ProductIndexPage.objects.first()
if index is None:
    index = home.add_child(instance=ProductIndexPage(title="Products", slug="products"))
    print("ProductIndexPage created")

if not ProductPage.objects.exists():
    service, _ = ServiceCategory.objects.get_or_create(name="Agriculture", defaults={"icon": "leaf"})
    product, _ = Product.objects.get_or_create(name="Agromet bulletin")
    index.add_child(instance=ProductPage(
        title="Agromet bulletin",
        slug="agromet-bulletin",
        introduction_title="Agromet bulletin",
        introduction_text="<p>Decadal agrometeorological bulletin.</p>",
        service=service,
        product=product,
    ))
    print("ProductPage created")

# ClimWeb's WDQMS statistics (run_wdqms_stats, 00:00 and 12:00) backfill months of data on
# a fresh database: for hours, they hold both processes of the dev worker, and the
# forecast pull and the daily drafts wait behind them. Beat keeps `enabled` when it
# restarts, so switching them off holds. Nothing in the studio needs them.
from django_celery_beat.models import PeriodicTask

wdqms = PeriodicTask.objects.filter(task="climweb.base.tasks.run_wdqms_stats", enabled=True)
if wdqms.exists():
    print(f"WDQMS periodic tasks disabled: {wdqms.update(enabled=False)}")
