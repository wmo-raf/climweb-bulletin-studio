# CLAUDE.md

## Project Overview

`climweb-bulletin-studio` — a ClimWeb app, shipped as a pip package, that hosts the
Bulletin Studio JS editor inside the ClimWeb admin and publishes what it composes into
ClimWeb's Products section.

ClimWeb ships it like `climweb-dataset-helper`: pinned in `climweb/requirements/base.in`,
listed in ClimWeb's `INSTALLED_APPS`. Until that ClimWeb change is released, sites (and
this dev stack) add it through `CLIMWEB_ADDITIONAL_APPS`, and the two must never be
combined: a duplicate app label stops Django at startup.

**It depends on ClimWeb** (`climweb.pages.products`), like geomanager does: there is no
bare-Wagtail mode, and no sandbox — development happens against the real ClimWeb image
(`docker-compose.dev.yml`).

Predecessors, both worth reading before changing anything here:
- `../bulletin-studio-plugin` — the ClimWeb *plugin* attempt (Django-rendered slot
  templates, locked structure, rule-based generation from geomanager, `docs/SPECIFICATION.md`).
  Superseded: the JS editor replaces the slot machinery, and geomanager's REST API replaces
  the Python data extraction. The spec still describes the intended product.
- `../bulletin-studio-js` — the frontend (Vue 3 + Lexical). Source of truth for the UI and
  for the layout; its `dist/` is vendored here by `sync-frontend.sh`.
- `../climweb` — the ClimWeb source, and where `climweb_dev:latest` is built from.

## Architecture

`BulletinPage(ProductItemPage)` under a `ProductPage`. `is_template=True` marks the
starting point an editor duplicates; issues are its siblings, published as real product
items. The template is a point of departure only — nothing stays linked afterwards.

The Python side is deliberately thin: a menu entry, one model, one public template, six
JSON endpoints. Anything about blocks, layout or rendering belongs in the JS app:

- `doc` — the editor's JSON, stored opaquely (no Python mirror to keep in sync)
- `html` — what the editor rendered from it, and the **only** thing the public page serves

The one exception to "thin" is images: they go through `api/images/` into the Wagtail
library rather than living as dataURLs in `doc`, and come back as renditions
(`width-1200`). Renditions are files on disk, so their urls survive in the html snapshot —
but deleting an image from the library will break bulletins that reference it, and nothing
warns about it (the reference lives inside an opaque JSON field).

That choice is deliberate: a Python renderer of the block tree would be a second layout
engine to keep in step with the JS one, which is what sank the plugin. The price is that a
published bulletin is a snapshot.

Maps: the block stores the geomanager layer's tile **path** (relative — a document must
survive a domain change), the frozen timestamp and the legend; the site supplies the
boundary tiles and default bounds through `api/map-config/`. maplibre refuses relative
urls in its sources, so `src/map.ts` makes them absolute at mount time. The basemap is
deliberately light (OSM) where ClimWeb's dashboards are dark: a bulletin gets printed.

Gotchas worth knowing (mostly learned from the plugin, all still true):
- `apps.ready()` must extend `ProductPage.subpage_types` — ClimWeb hardcodes it
- `base_form_class = WagtailAdminPageForm`: the native `ProductItemPage` form reads
  `parent.product.product_item_types` and crashes without the `products` StreamField
- set `live=False` *before* `add_child`, or Wagtail publishes the page
- the slug follows the title only until the first publication, then freezes
- Django's `{# #}` comment is single-line: a multi-line one leaks into the rendered page
- ClimWeb caches public pages (wagtail-cache, 4 h in production, off in dev) and clears
  the cache only from Wagtail editor hooks (`after_edit_page`…). Anything that publishes
  or deletes outside the page editor must call `views._clear_site_cache()`, or the site
  serves stale pages. Invisible on the dev stack.
- geomanager returns absolute urls built from the Wagtail Site (wrong host/port in dev)
  and `new URL()` escapes the `{z}/{x}/{y}` placeholders — `api.samePath()` handles both

## Development

Full walkthrough in README "Development". Short version, from a fresh clone:

```shell
mkdir -p bulletin_studio/static/bulletin_studio          # the bundle symlink is gitignored
ln -s ../../../../bulletin-studio-js/dist bulletin_studio/static/bulletin_studio/app
(cd ../bulletin-studio-js && npm ci && npm run build)    # no host Node: node:22-alpine in docker
cp .env.sample .env                                      # DB_PASSWORD
docker compose -f docker-compose.dev.yml up -d --build   # http://localhost:8010/admin
docker compose -f docker-compose.dev.yml exec -T climweb \
  /climweb/web/src/climweb/manage.py shell < dev-bootstrap.py   # admin/admin + page tree
docker compose -f docker-compose.dev.yml exec climweb \
  /climweb/web/src/climweb/manage.py test bulletin_studio
```

Needs `climweb_dev:latest` built from `../climweb` (the image only; ClimWeb's own compose
stack on :8000 is independent). The database starts **empty** — `dev-bootstrap.py`
(idempotent) creates the superuser, HomePage, ProductIndexPage and a ProductPage the
studio needs before it has anywhere to put a template. The first `up` runs all ClimWeb
migrations, give it a minute. `bulletin_studio/` is bind-mounted (Python hot-reloads);
packaging changes need `--build`.

The compose file also mounts `../bulletin-studio-js/dist` at `/bulletin-studio-js/dist`,
which is where the `static/bulletin_studio/app` symlink resolves inside the container.

Dev-stack traps:
- ClimWeb forces 2FA on the admin, superusers included: every admin url (the JSON API
  too) 302s to `/admin/2fa/devices/new`. The compose file sets `WAGTAIL_2FA_REQUIRED` and
  `CLIMWEB_2FA_SUPERUSER_REQUIRED` to false.
- ClimWeb dropped `HomePage.hero_type`/`show_banner_video`/… without a migration: the
  NOT NULL columns remain and any `HomePage` insert raises `IntegrityError`.
  `dev-bootstrap.py` sets column defaults; `BulletinStoreTests.test_lifecycle` fails on
  it until ClimWeb ships the migration — not a bulletin_studio regression.

Frontend iteration: `npm run dev` in `../bulletin-studio-js` (port 5180, strictPort) plus
`BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180` in `.env`. Otherwise `npm run build`
then `manage.py collectstatic --noinput`.

CSS trap: Tailwind 4 puts its utilities in `@layer utilities`, and any **unlayered** rule
(wagtail's `core.css`) beats a layered one whatever the specificity. The app's
`src/style.css` therefore imports `tailwindcss/utilities.css` outside the layer.

Naming: repo and distribution `climweb-bulletin-studio` (`wmo-raf/`), as
`climweb-dataset-helper`; module and app label `bulletin_studio`, admin url
`/admin/bulletin-studio/`, url namespace `bulletin_studio`, display name "Bulletin Studio".

## Packaging and release

Full procedure in README "Releasing". A release reaches sites only when ClimWeb bumps
its `climweb-bulletin-studio==` pin (`base.in`, then `base.txt`). Things that are easy to
break:
- The bundle is not in git. `frontend.ref` pins the bulletin-studio-js commit a release
  ships, and `publish.yml` builds it. A local build follows the dev symlink instead, so
  it ships whatever `../bulletin-studio-js/dist` holds at that moment.
- `MANIFEST.in` decides what ships from that dist: Vite's `index.html` and its `public/`
  files are excluded. A new top-level file in `public/` would ship unless excluded too.
- `makemigrations` on the dev stack runs against ClimWeb main: a new migration that
  references a ClimWeb model depends on main's latest migration of that app, which no
  release has yet. Re-point it at a released one (`products/0033` for 1.2.2).
- `install_requires` floors stay loose (`django>=4.2`, `wagtail>=6.3`): ClimWeb pins
  both, and a floor above its pin makes pip upgrade them inside ClimWeb's venv.
- Check a release against the released image (`ghcr.io/wmo-raf/climweb:vX`, production
  settings, admin at `/cms-admin/`), not only `climweb_dev`. The HomePage trap above only
  exists on ClimWeb's unreleased main, and the tests pass on 1.2.2.
- ClimWeb's static storage is `ManifestStaticFilesStorage`: `{% static %}` entries get
  hashed names, but the chunks the bundle imports relatively
  (`bulletin-studio-map.js`…) keep unhashed names and are not cache-busted on upgrade.

## i18n

The UI is the JS app's, so the catalogs live there (`../bulletin-studio-js/src/locales/`):
English is the source, plus fr, es, pt, ar. This page passes the admin user's active
language down as `data-locale`, so the studio follows whatever the Wagtail menu is in;
`dir="rtl"` comes from the Wagtail shell for Arabic. ClimWeb also serves am and sw — no
catalog for those yet, they fall back to English.

Python-side strings (the menu entry, the page title) stay Django `gettext`. If they grow
past a handful, add `bulletin_studio/locale/` for the same four languages, English being
the msgid.
