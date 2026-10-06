# CLAUDE.md

## Project Overview

`climweb-bulletin-studio` — a ClimWeb app, shipped as a pip package, that hosts the
Bulletin Studio JS editor inside the ClimWeb admin and publishes what it composes into
ClimWeb's Products section.

ClimWeb ships it like `climweb-dataset-helper`: pinned in `climweb/requirements/base.in`,
listed in ClimWeb's `INSTALLED_APPS`. Until that ClimWeb change is released, sites add it
through `CLIMWEB_ADDITIONAL_APPS`, and the two must never be combined: a duplicate app
label stops Django at startup. `climweb_dev` (ClimWeb main) already lists it, so this dev
stack no longer sets `CLIMWEB_ADDITIONAL_APPS`.

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
items. The template is a point of departure only: an issue records `source_template` (the
draft task needs to know whether the period's exists), but nothing propagates either way.

A template's `cadence` (daily, dekadal, monthly — `periods.py`, pure) sets the period each
issue covers: the one that begins, so the dekadal of the 11th is the outlook of the 11th to
the 20th. No "previous period" mode and no weekly cadence: not needed yet.

Issues are made on the server (`issues.create_issue`, behind "New bulletin" and the draft
task) for the period containing a day: the template's `doc` copied, its forecast and city
forecast blocks frozen from the period's first day (`dayOffset` counts from it), the page
`date` ("Effective from") and `valid_until` ("Effective until", None for a single day) set
to the period, `cadence` copied, and `html` left empty. The title is "{template} —
{period}" from Django's own date formats (a range repeats month and year: "1–10 octobre"
would need rules per language). Only the studio renders html; it does on every publish.
The data of these two blocks and how columns nest blocks are the only parts of the block
schema Python knows.

Dates follow the **admin's** language, not the site's: the title in the views through
Wagtail's `require_admin_access` (the user's preferred language), in the draft task the
preferred language of whoever last saved the template (`author_language`, from the latest
revision's user — hence `save_revision(user=request.user)`). The studio formats its own
dates in the admin's language too: the "issue date" blocks, and the banner's inserted
dates (`{start}`, `{end}`, `{period}`, `{previous}`, `{published}` in the eyebrow, title,
subtitle and badges), which the document keeps as fields and the JS fills at display and
render time — Python never reads them. `{previous}` is the period before the issue's, of
the same cadence: the past dekad an agrometeorological bulletin reviews before its outlook.

Starting points ("New template") live in the JS (`templates.ts`). The dekadal
agrometeorological one is the plan shared by four offices' bulletins (Benin, Burkina
Faso, Chad, Kenya): highlights, rainfall (dekad, season), agrometeorological conditions,
vegetation and crops, outlook, advice (crops, livestock), sources. Its maps are image
blocks for now, captioned with the map each one expects; geomanager map blocks are the
next step.

The drafts: a template's `draft_at` (set in the studio, site time, floored to the quarter
hour) makes the beat task `create_daily_drafts` (`bulletin-studio-daily-drafts`, every 15
minutes, registered on ClimWeb's app through `settings.CELERY_APP`; "daily" in both names
predates the other cadences and stays, beat's DatabaseScheduler keeps renamed rows) prepare
the issue of the current period once that time has passed on its first day — or later in
the period, if the worker was stuck, but never a period gone by. Once a period per
template: `last_draft` keeps a draft deleted by hand from coming back, and an issue of the
period made by hand counts. A human always publishes.

The Python side is deliberately thin: a menu entry, one model, one public template, nine
JSON endpoints. Anything about blocks, layout or rendering belongs in the JS app:

- `doc` — the editor's JSON, stored opaquely (no Python mirror to keep in sync)
- `html` — what the editor rendered from it, and the **only** thing the public page serves

The PDF is the browser printing the studio. Above the bulletin it prints the identity
ClimWeb's navbar shows, from Settings > Organisation (`views._letterhead`): logo,
`logo_append` text (else the organisation's name) and country flag, and so does the
"PDF" preview. Never in `doc` or `html`: the public page has the navbar already, and a
change in the settings reaches every PDF printed after it.

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

Forecast map (`bulletin_studio/forecast/`, in progress — plan in
`../weather-forecast-snapshot/PLAN.md`): the second exception to "thin". A country map of
forecastmanager's city forecasts, drawn on the server (SVG by hand, PNG through
cairosvg) because it is composed without a browser, after each forecast pull. It is not a
second layout engine: it draws one image, which the editor consumes like any other. The
values are the national met office's, displayed as stored — never aggregated or
recomputed. `forecast/render.py` is pure (no Django, no file paths); fixtures and the
design-loop script live in `dev/forecast/`, outside the package, so they never ship.

The trigger: forecastmanager's Wagtail hooks `after_generate_forecast` (yr pulls only —
Open-Meteo, the grid editor and the API fire nothing) and `after_forecast_add_from_form`
queue the Celery task `render_daily_forecast_maps` on commit; it draws the periods set in
Settings > Forecast map (`ForecastMapSettings`, stored as "HH:MM", not as FKs — a
migration depending on forecastmanager would break a ClimWeb without it), today to
`days_ahead`, into `media/forecast_snapshots/`. forecastmanager is optional in ClimWeb
(`IS_METEOROLOGICAL`): import it lazily, never at the top of a module the app loads.

That file is the latest render, rewritten on each pull: a bulletin references a frozen
copy instead. `forecast/library.py` promotes the map into the Wagtail library (collection
"Forecast maps"), once per version. The version is the PNG's sha1, which Wagtail already
stores as `file_hash`, so there is no model of our own. `api/forecast/` lists the maps
drawn (GET) and promotes one (POST); `data-forecast-url` reaches the JS only when
forecastmanager is installed.

City forecasts (the `cities` block): the same forecast as a grid of cities — icon,
max/min, wind arrow, compass point and speed — laid out by the JS as HTML, not drawn by
the server. `forecast/cities.py` reads the slot as stored (`forecast_collection`, the
map's query) and `api/forecast/cities/?date=&period=` serves it; an issue copies the rows
of **every** city into its `doc` (`version`: sha1 of the values, for "Update"), and the
choice and order of cities (`cities`, slugs, null = all) apply when the studio renders,
so Python never filters. Icons are referenced by their unhashed static path
(`/static/forecastmanager/weathericons/<symbol>.svg`): a hashed name would change with
the icon under a published bulletin. Values are rounded for display, never converted:
the wind stays in the office's unit. The arrow is a CSS shape turned by an inline
`style` — the only way to orient something in sanitized html (no svg, no script).

Gotchas worth knowing (mostly learned from the plugin, all still true):
- `apps.ready()` must extend `ProductPage.subpage_types` — ClimWeb hardcodes it
- `base_form_class = WagtailAdminPageForm`: the native `ProductItemPage` form reads
  `parent.product.product_item_types` and crashes without the `products` StreamField
- set `live=False` *before* `add_child`, or Wagtail publishes the page
- an issue made on the server has no html until the studio publishes it: the `publish`
  endpoint, `before_publish_page` and `before_bulk_action` refuse to put it online (its
  public page would be blank)
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
docker compose -f docker-compose.dev.yml exec -T climweb \
  /climweb/web/src/climweb/manage.py shell < dev/forecast/bootstrap.py  # cities, BF boundaries, yr pull on
docker compose -f docker-compose.dev.yml exec climweb \
  /climweb/web/src/climweb/manage.py test bulletin_studio
```

The stack runs ClimWeb's Celery too: `beat` sends the hourly forecast pull
(`download-forecast-every-hour`), `worker` runs it. Neither reloads code: restart `worker`
after editing a task or a hook, and `beat` after adding a periodic one. To pull now,
through the worker as beat would:
`manage.py shell -c "from climweb.base.tasks import download_forecast; download_forecast.delay()"`.
The drafts likewise: `from bulletin_studio.tasks import create_daily_drafts; create_daily_drafts.delay()`.

Needs `climweb_dev:latest` built from `../climweb` (the image only; ClimWeb's own compose
stack on :8000 is independent). The database starts **empty** — `dev-bootstrap.py`
(idempotent) creates the superuser, HomePage, ProductIndexPage and a ProductPage the
studio needs before it has anywhere to put a template. The first `up` runs all ClimWeb
migrations, give it a minute. `bulletin_studio/` is bind-mounted (Python hot-reloads);
packaging changes need `--build`.

The compose file also mounts `../bulletin-studio-js/dist` at `/bulletin-studio-js/dist`,
which is where the `static/bulletin_studio/app` symlink resolves inside the container.

Dev-stack traps:
- The worker has two processes, and ClimWeb's WDQMS statistics (`run_wdqms_stats`, at
  00:00 and 12:00) backfill for hours on a fresh database: the forecast pull, the map
  renders and the drafts queue behind them. `dev-bootstrap.py` disables those
  periodic tasks; if a queue builds up anyway (`redis-cli LLEN celery` on
  `bulletin-redis`), look at `celery inspect active` in the worker.
- ClimWeb forces 2FA on the admin, superusers included: every admin url (the JSON API
  too) 302s to `/admin/2fa/devices/new`. The compose file sets `WAGTAIL_2FA_REQUIRED` and
  `CLIMWEB_2FA_SUPERUSER_REQUIRED` to false.
- ClimWeb dropped `HomePage.hero_type`/`show_banner_video`/… without a migration: the
  NOT NULL columns remain and any `HomePage` insert raises `IntegrityError`.
  `dev-bootstrap.py` sets column defaults; both `BulletinStoreTests` tests (their setUp
  creates a HomePage) fail on it until ClimWeb ships the migration — not a bulletin_studio
  regression.

Frontend iteration: `npm run dev` in `../bulletin-studio-js` (port 5180, strictPort) plus
`BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180` in `.env`. Otherwise `npm run build`
then `manage.py collectstatic --noinput`.

Forecast map iteration, on the host, no stack (icons are read from `../forecastmanager`):

```shell
uv run dev/forecast/render.py --list                     # periods in the fixture
uv run dev/forecast/render.py --all --period Journalière # -> dev/forecast/out/*.png + .svg
uv run --no-project --with shapely python -m unittest bulletin_studio.forecast.tests
```

The host renders with Inter when it is installed; ClimWeb's image only has DejaVu, so a
design also needs checking in the container. From the database (published forecasts only),
into `media/forecast_snapshots/<date>/<HHhMM>-<preset>.png` + `.svg`:

```shell
docker compose -f docker-compose.dev.yml exec climweb \
  /climweb/web/src/climweb/manage.py render_forecast_snapshot --list   # today's periods
docker compose -f docker-compose.dev.yml exec climweb \
  /climweb/web/src/climweb/manage.py render_forecast_snapshot --date 2026-10-05 --period 06:00
```

A pull only returns hours to come: on a fresh database, today's early periods do not
exist; once written by earlier pulls, a past period stays as it was last pulled. To get a
map for today anyway, `manage.py shell < dev/forecast/fill_today.py` copies the nearest
later forecast of each daily period onto today (test data) and redraws.

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
