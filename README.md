# ClimWeb Bulletin Studio

Block-based bulletin editor for [ClimWeb](https://github.com/wmo-raf/nmhs-cms): a Wagtail
admin entry that hosts the [Bulletin Studio](https://github.com/fgg-consultant/bulletin-studio-js)
JS app (Vue 3 + Lexical) and publishes what it composes into ClimWeb's Products section.

A ClimWeb app, packaged like [geomanager](https://github.com/wmo-raf/geomanager): an
ordinary pip-installable Django app, but one that **depends on ClimWeb** (it subclasses
`products.ProductItemPage`) — it will not boot in a bare Wagtail project.

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

## Installation

```shell
pip install climweb-bulletin-studio
```

Then add the app to ClimWeb via its environment:

```shell
CLIMWEB_ADDITIONAL_APPS=bulletin_studio
```

```shell
climweb migrate bulletin_studio
climweb collectstatic --noinput
```

The admin menu gains a **Bulletin Studio** entry pointing at `/admin/bulletin-studio/`.
Creating a template needs at least one ClimWeb **Product page** to host it.

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

All under `/admin/bulletin-studio/`, staff-only, CSRF-protected (send `X-CSRFToken`):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `api/product-pages/` | the products a bulletin can live under |
| `GET` | `api/images/` | browse the ClimWeb image library (`?q=` filters on title) |
| `GET` | `api/map-config/` | where geomanager serves its layers, admin boundary tiles, country bounds |
| `POST` | `api/images/` | upload an image into that library |
| `GET` | `api/bulletins/` | dashboard listing (templates and issues, metadata only) |
| `POST` | `api/bulletins/` | create under a product page |
| `GET` | `api/bulletins/<id>/` | read one, with its document (latest draft) |
| `PUT` | `api/bulletins/<id>/` | save — a Wagtail draft revision |
| `POST` | `api/bulletins/<id>/publish/` | publish the draft |
| `DELETE` | `api/bulletins/<id>/` | delete |

Saving never publishes: a live issue keeps serving its published html until someone hits
publish. The `html` payload is sanitized on write (`nh3`) — it comes from a browser.

Images are ClimWeb images: the studio uploads through Wagtail's own image form (which
validates the real file format, not the extension) and hands back a **rendition** url, so
a 4000px photo never reaches the page. The document keeps that url plus the image id; the
library endpoint lets an editor reuse an image that is already on the site — the agency
logo, typically.

Maps come from geomanager's own layer catalogue (`api/datasets/`), no `DashboardMap`
snippet to configure first. Picking a layer freezes its tile path, **its date** and its
legend into the document — a published issue keeps showing the data of its own decade,
and geomanager's raster tiles require a `time` parameter anyway. On the public page each
map is a declarative `<div class="bs-map" data-tiles data-time data-bounds>` that
`bulletin-studio-embed.js` hydrates with ClimWeb's own maplibre; the legend is plain html,
so it prints.

## Development

Needs a local `climweb_dev:latest` image, built from a ClimWeb checkout (`../climweb`).

```shell
cp .env.sample .env          # set DB_PASSWORD
docker compose -f docker-compose.dev.yml up -d      # http://localhost:8010/admin
docker compose -f docker-compose.dev.yml exec climweb /climweb/web/src/climweb/manage.py test bulletin_studio
```

`bulletin_studio/` is bind-mounted, so Python changes hot-reload; packaging changes need
`docker compose -f docker-compose.dev.yml build climweb`. The stack starts on an empty
database: create a superuser, a Home page and a Product page before the studio has
anywhere to put a template.

## License

MIT
