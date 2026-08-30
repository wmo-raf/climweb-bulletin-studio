# CLAUDE.md

## Project Overview

`climweb-bulletin-studio` — pip-installable Django/Wagtail app that hosts the Bulletin
Studio JS editor inside the ClimWeb admin and publishes what it composes into ClimWeb's
Products section.

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

Gotchas worth knowing (all learned from the plugin, all still true):
- `apps.ready()` must extend `ProductPage.subpage_types` — ClimWeb hardcodes it
- `base_form_class = WagtailAdminPageForm`: the native `ProductItemPage` form reads
  `parent.product.product_item_types` and crashes without the `products` StreamField
- set `live=False` *before* `add_child`, or Wagtail publishes the page
- the slug follows the title only until the first publication, then freezes
- Django's `{# #}` comment is single-line: a multi-line one leaks into the rendered page

## Development

```shell
cp .env.sample .env                                  # DB_PASSWORD
docker compose -f docker-compose.dev.yml up -d       # http://localhost:8010/admin
docker compose -f docker-compose.dev.yml exec climweb \
  /climweb/web/src/climweb/manage.py test bulletin_studio
```

Needs `climweb_dev:latest` built from `../climweb`. The stack starts on an **empty**
database: create a superuser, a HomePage and a ProductPage before the studio has anywhere
to put a template. `bulletin_studio/` is bind-mounted (Python hot-reloads); packaging
changes need `build climweb`.

The compose file also mounts `../bulletin-studio-js/dist` at `/bulletin-studio-js/dist`,
which is where the `static/bulletin_studio/app` symlink resolves inside the container.

Frontend iteration: `npm run dev` in `../bulletin-studio-js` (port 5180, strictPort) plus
`BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180` in `.env`. Otherwise `npm run build`
then `manage.py collectstatic --noinput`.

CSS trap: Tailwind 4 puts its utilities in `@layer utilities`, and any **unlayered** rule
(wagtail's `core.css`) beats a layered one whatever the specificity. The app's
`src/style.css` therefore imports `tailwindcss/utilities.css` outside the layer.

Naming: distribution `climweb-bulletin-studio`, module and app label `bulletin_studio`,
admin url `/admin/bulletin-studio/`, url namespace `bulletin_studio`, display name
"Bulletin Studio".

## i18n

The UI is the JS app's, so the catalogs live there (`../bulletin-studio-js/src/locales/`):
English is the source, plus fr, es, pt, ar. This page passes the admin user's active
language down as `data-locale`, so the studio follows whatever the Wagtail menu is in;
`dir="rtl"` comes from the Wagtail shell for Arabic. ClimWeb also serves am and sw — no
catalog for those yet, they fall back to English.

Python-side strings (the menu entry, the page title) stay Django `gettext`. If they grow
past a handful, add `bulletin_studio/locale/` for the same four languages, English being
the msgid.
