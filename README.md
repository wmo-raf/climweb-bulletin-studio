# ClimWeb Bulletin Studio

Block-based bulletin editor for [ClimWeb](https://github.com/wmo-raf/climweb): a Wagtail
admin entry that hosts the [Bulletin Studio](https://github.com/fgg-consultant/bulletin-studio-js)
JS app (Vue 3 + Lexical) and publishes what it composes into ClimWeb's Products section.

A ClimWeb app, shipped like [climweb-dataset-helper](https://github.com/wmo-raf/climweb-dataset-helper):
an ordinary pip-installable Django app that ClimWeb pins in its requirements and lists in
`INSTALLED_APPS`. It **depends on ClimWeb** (it subclasses `products.ProductItemPage`) and
will not boot in a bare Wagtail project.

## How it fits into ClimWeb

```
HomePage → ProductIndexPage → ProductPage ("Agromet bulletin")
                                   ├── template  (draft, is_template=True, never public)
                                   ├── issue n°12  (live ProductItemPage)
                                   └── issue n°13
```

- A **template** is just a bulletin flagged as one, living as a draft under the
  ProductPage an editor picks when creating it. It is a starting point, nothing stays
  linked afterwards — an issue may freely diverge from it.
- An **issue** is a copy of the template's document, published as a real
  `ProductItemPage`: it shows up in the native product listing with its year/month
  filters, at a stable URL.
- The page serves the **HTML the JS app rendered**. There is no Python renderer of the
  block document, so the editor stays the single source of layout truth; the document
  itself (`doc`) is stored opaquely next to it.

## Status

**Alpha.** Usable end to end (templates, issues, publication, images, maps), but not yet
run on a production site. See [Known limitations](#known-limitations) before putting it in
front of editors.

## Requirements

- **ClimWeb 1.1.7 or later.** The migration builds on `products/0033`, so an older
  ClimWeb refuses to migrate. Developed and tested against ClimWeb 1.2.2 (Python 3.10,
  Django 5.2, Wagtail 7.3).
- Nothing else to install: geomanager and adminboundarymanager, which the map block
  relies on, ship with every ClimWeb. The only new dependency is `nh3` (html sanitizer).

The package bundles the built frontend: there is no Node step on the ClimWeb side.

## Installation

### On ClimWeb

Bulletin Studio ships with ClimWeb the way the dataset helper does: ClimWeb pins
`climweb-bulletin-studio` in `climweb/requirements/base.in` and lists `bulletin_studio` in
`INSTALLED_APPS`. On a ClimWeb image that includes it there is nothing to install: its
migrations and static files run with ClimWeb's own at startup.

Do **not** also set `CLIMWEB_ADDITIONAL_APPS=bulletin_studio` there. The app would be
registered twice and Django refuses to start:

```
ImproperlyConfigured: Application labels aren't unique, duplicates: bulletin_studio
```

No ClimWeb release ships it yet (1.2.2 is the latest). Until one does, install it as an
additional app, as below.

### Before ClimWeb ships it

ClimWeb runs from Docker images (`ghcr.io/wmo-raf/climweb`, deployed with
[climweb-docker](https://github.com/wmo-raf/climweb-docker)). A `pip install` run inside a
running container is lost the next time the container is recreated, so build the package
into an image derived from the one you run:

```dockerfile
# Dockerfile
FROM ghcr.io/wmo-raf/climweb:v1.2.2
RUN /climweb/venv/bin/pip install --no-cache-dir climweb-bulletin-studio==0.1.0a1
```

Pre-releases need that exact pin (or `pip install --pre`): pip skips them otherwise.
To try a wheel that is not on PyPI yet, `COPY` it into the image and `pip install` the
file instead.

Then, in climweb-docker:

1. Build the image (`docker build -t climweb-with-studio .`) and point **all three**
   ClimWeb services at it in `docker-compose.yml`: `climweb`, `climweb_celery_worker` and
   `climweb_celery_beat`. They share the same environment, so a service still on the
   stock image fails at startup with `No module named 'bulletin_studio'`.
2. Enable the app in `.env`, next to any app already listed there (comma-separated):

   ```shell
   CLIMWEB_ADDITIONAL_APPS=bulletin_studio
   ```

3. `docker compose up -d`. The ClimWeb entrypoint migrates and collects static files on
   startup (`MIGRATE_ON_STARTUP` and `COLLECT_STATICFILES_ON_STARTUP`, both on by
   default). If your deployment disables them, run them by hand:

   ```shell
   docker compose exec climweb climweb migrate
   docker compose exec climweb climweb collectstatic --noinput
   ```

To upgrade, bump the pin and rebuild the image. When you move to a ClimWeb release that
ships the studio, go back to the stock image **and** remove `bulletin_studio` from
`CLIMWEB_ADDITIONAL_APPS`. The bulletins carry over: same app label, same tables.

### First use

The admin menu shows a **Bulletin Studio** entry (`/<admin path>/bulletin-studio/`,
`/cms-admin/` by default). The studio stores bulletins under ClimWeb **Product pages**, so
at least one must exist before the first template can be created. The studio never
creates product pages itself.

## Known limitations

- **Permissions.** Any user with access to the Wagtail admin can create, publish and
  delete bulletins, whatever their page permissions on the Products section. For now,
  keep the studio to trusted editors.
- **A published bulletin is a snapshot.** The page serves the html the editor rendered.
  A ClimWeb theme change does not restyle past issues, and a newer frontend only renders
  a bulletin again once someone opens and saves it.
- **Images are not reference-tracked.** Bulletins point at renditions of library images.
  Deleting an image from the library breaks every bulletin using it, without any warning.
- **Languages.** The studio UI exists in English, French, Spanish, Portuguese and
  Arabic. Other ClimWeb languages (Amharic, Swahili) fall back to English.
- **Uninstalling.** Delete the bulletin pages first. Wagtail cannot display pages whose
  model is no longer installed.

## Layout

```
bulletin_studio/          the Django app
  wagtail_hooks.py        admin menu entry + admin urls
  apps.py                 ready(): lets BulletinPage live under a ProductPage
  models.py               BulletinPage(ProductItemPage): doc, html, is_template
  views.py                the admin page + the JSON store the JS app talks to
  templates/…/app.html    Wagtail admin shell + mount point for the JS app
  templates/…/bulletin_page.html   the public page: the rendered html, nothing else
  static/…/app/           built JS bundle (see sync-frontend.sh)
```

## Frontend

The UI lives in its own repo ([bulletin-studio-js](https://github.com/fgg-consultant/bulletin-studio-js))
and the admin page can load it two ways.

**Dev — Vite dev server, HMR, no build step.** Point the app at a running dev server:

```shell
cd ../bulletin-studio-js && npm run dev          # fixed port 5180 (strictPort)
# then BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180 in .env
```

The template then loads `/@vite/client` and `/src/main.ts` from that origin instead of the
bundle, and styles arrive through Vite's module graph.

**Built bundle.** `./sync-frontend.sh ../bulletin-studio-js` builds and copies `dist/` into
`bulletin_studio/static/bulletin_studio/app/`. In this checkout that path is a **symlink**
to `../bulletin-studio-js/dist`, so a plain `npm run build` in the JS repo is enough
(the script detects the symlink and skips the copy).

The build emits two stylesheets: `bulletin-studio.css` for the editor, and
`bulletin-studio-content.css` — the bulletin's own content styles, which the *public*
page loads. Both come from the same source, so what the author composes is what the site
shows.

Either way the page hands the app its API urls, CSRF token and the admin user's active
language through data attributes on `#bulletin-studio-app` — the studio translates itself
into whatever language the Wagtail admin is set to (English, French, Spanish, Portuguese,
Arabic; other ClimWeb languages fall back to English).

## Store API

All under `/<admin path>/bulletin-studio/`, staff-only, CSRF-protected (send `X-CSRFToken`):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `api/product-pages/` | the products a bulletin can live under |
| `GET` | `api/images/` | browse the ClimWeb image library (`?q=` filters on title) |
| `GET` | `api/map-config/` | where geomanager serves its layers, admin boundary tiles, country bounds |
| `POST` | `api/images/` | upload an image into that library |
| `GET` | `api/forecast/` | the forecast maps drawn from `?date=` (today by default), and the periods they cover |
| `POST` | `api/forecast/` | promote one (`{date, period}`) into the image library, frozen |
| `GET` | `api/bulletins/` | dashboard listing (templates and issues, metadata only) |
| `POST` | `api/bulletins/` | create under a product page |
| `GET` | `api/bulletins/<id>/` | read one, with its document (latest draft) |
| `PUT` | `api/bulletins/<id>/` | save — a Wagtail draft revision |
| `POST` | `api/bulletins/<id>/issues/` | a new issue of this template (`{date}`, today by default), made on the server |
| `POST` | `api/bulletins/<id>/publish/` | publish the draft |
| `DELETE` | `api/bulletins/<id>/` | delete |

Saving never publishes: a live issue keeps serving its published html until someone hits
publish. "New bulletin" asks the server for the issue: a draft dated for the day, titled
"{template} — {date}" in the site's language, its forecast maps frozen. Its html is
rendered by the studio when it is published — until then, neither the studio nor Wagtail's
own publish actions will put it online. The `html` payload is sanitized on write (`nh3`) — it comes from a browser.
Publishing and deleting clear ClimWeb's page cache, as Wagtail's own editor does: in
production, ClimWeb caches public pages for hours.

Images are ClimWeb images: the studio uploads through Wagtail's own image form (which
validates the real file format, not the extension) and hands back a **rendition** url, so
a 4000px photo never reaches the page. The document keeps that url plus the image id; the
library endpoint lets an editor reuse an image that is already on the site — the agency
logo, typically.

Forecast maps (meteorological sites only, with forecastmanager) are redrawn after each
forecast pull, so a bulletin never points at them: `POST api/forecast/` copies the current
map into the library, in a "Forecast maps" collection, and hands back its rendition like
any image. Promoting the same map twice returns the same image; the library picker leaves
that collection to searches.

Maps come from geomanager's own layer catalogue (`api/datasets/`), no `DashboardMap`
snippet to configure first. Picking a layer freezes its tile path, **its date** and its
legend into the document — a published issue keeps showing the data of its own decade,
and geomanager's raster tiles require a `time` parameter anyway. On the public page each
map is a declarative `<div class="bs-map" data-tiles data-time data-bounds>` that
`bulletin-studio-embed.js` hydrates with ClimWeb's own maplibre; the legend is plain html,
so it prints.

## Development

The dev stack is the package installed (editable) into the ClimWeb dev image, next to
its own PostGIS and Redis. Expected layout — three sibling checkouts:

```
wmo/
  climweb/                    ClimWeb, builds climweb_dev:latest
  bulletin-studio-js/         the frontend
  climweb-bulletin-studio/    this repo
```

**1. The ClimWeb image.** Build `climweb_dev:latest` from `../climweb` (see its
`docs/_docs/technical/development/running-dev-environment.md`). It only has to exist;
this stack does not need ClimWeb's own compose to be running.

**2. The frontend bundle.** `bulletin_studio/static/bulletin_studio/app` is a symlink to
`../bulletin-studio-js/dist`. It is gitignored, so create it once after cloning, then
build the JS app:

```shell
mkdir -p bulletin_studio/static/bulletin_studio
ln -s ../../../../bulletin-studio-js/dist bulletin_studio/static/bulletin_studio/app

cd ../bulletin-studio-js && npm ci && npm run build
# no Node on the host:
docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/src -w /src \
  node:22-alpine sh -c 'npm ci && npm run build'
```

The compose file mounts `../bulletin-studio-js/dist` at `/bulletin-studio-js/dist`,
which is where the symlink resolves inside the container.

**3. The stack.**

```shell
cp .env.sample .env          # set DB_PASSWORD (anything, it is a local database)
docker compose -f docker-compose.dev.yml up -d --build   # http://localhost:8010/admin
```

The first start runs every ClimWeb migration (`MIGRATE_ON_STARTUP`), which takes a
minute; `docker compose -f docker-compose.dev.yml logs -f climweb` until daphne listens.
2FA, which ClimWeb forces on the admin, is switched off in the compose file.

**4. Seed the database.** It starts empty; `dev-bootstrap.py` creates an `admin`/`admin`
superuser, a HomePage as the site root, a ProductIndexPage and an "Agromet bulletin"
ProductPage for templates to live under. It is idempotent, and dev-only: it is not part of
the package, and a real ClimWeb already has its page tree.

```shell
docker compose -f docker-compose.dev.yml exec -T climweb \
  /climweb/web/src/climweb/manage.py shell < dev-bootstrap.py
```

The studio is then at <http://localhost:8010/admin/bulletin-studio/>.

**Day to day.** `bulletin_studio/` is bind-mounted, so Python changes hot-reload;
packaging changes (`setup.cfg`, new dependencies) need `--build`. For the frontend,
either rebuild (`npm run build`, then `manage.py collectstatic --noinput` in the container
— the entrypoint only collects at startup) or run `npm run dev` in
`../bulletin-studio-js` and set `BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180` in
`.env` (then `up -d` again). `docker compose -f docker-compose.dev.yml down -v` wipes the
database.

```shell
docker compose -f docker-compose.dev.yml exec climweb /climweb/web/src/climweb/manage.py test bulletin_studio
docker compose -f docker-compose.dev.yml exec climweb /climweb/web/src/climweb/manage.py makemigrations bulletin_studio
```

Check the `dependencies` of a new migration before committing it. When a change
references a ClimWeb model, Django pins the latest migration of that app *in the ClimWeb
it runs against*. `climweb_dev` is ClimWeb's main, ahead of every release: a dependency
on an unreleased migration (`products/0034` and later, today) makes `migrate` fail on
released ClimWeb with `NodeNotFoundError`. Point it back at a released migration
(`0001_initial` depends on `products/0033`).

Known ClimWeb issue: ClimWeb's main branch (after 1.2.2) removed four `HomePage` fields
(`hero_type`, `show_banner_video`, …) without a migration, so their NOT NULL columns
survive and creating a HomePage fails with an `IntegrityError`. `dev-bootstrap.py` works
around it with column defaults. `BulletinStoreTests`, whose test database comes straight
from the migrations, fails on `climweb_dev` until ClimWeb ships `home/0040`. It passes on
the released image, the one to check a release against: install the wheel into
`ghcr.io/wmo-raf/climweb:v1.2.2` and run `manage.py test bulletin_studio` there with
`DJANGO_SETTINGS_MODULE=climweb.config.settings.test`.

## Releasing

The frontend bundle is not in git. `frontend.ref` pins the bulletin-studio-js commit a
release ships, and the publish workflow builds that commit into the package.

1. Bump `version` in `setup.cfg` (PEP 440: `0.1.0a2`, `0.1.0b1`, `0.1.0`), point
   `frontend.ref` at the frontend commit to ship, and move the `CHANGELOG.md` entry out
   of "unreleased".
2. Check the package locally. In a dev checkout the bundle symlink is followed, so build
   the frontend at that commit first:

   ```shell
   (cd ../bulletin-studio-js && git checkout "$(cat ../climweb-bulletin-studio/frontend.ref)" && npm ci && npm run build)
   uv build            # or: python -m build
   unzip -l dist/*.whl # bulletin_studio/static/bulletin_studio/app/bulletin-studio*.{js,css}
   ```

3. Tag `<version>` (`0.1.0a1`, no `v`, as climweb-dataset-helper does) and publish a
   GitHub release from it, ticking "pre-release" for an alpha or beta.
   `.github/workflows/publish.yml` builds the frontend, checks that the bundle is in the
   wheel and uploads to PyPI through trusted publishing. On PyPI, the `climweb-bulletin-studio`
   project's trusted publisher is repository `wmo-raf/climweb-bulletin-studio`, workflow
   `publish.yml`, environment `pypi`. Before the very first upload, declare it as a
   "pending publisher".
4. Bump the pin in ClimWeb (`climweb/requirements/base.in`, then regenerate `base.txt`).
   Sites get the new version with the next ClimWeb release.

## License

MIT
