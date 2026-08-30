# ClimWeb Bulletin Studio

Block-based bulletin editor for [ClimWeb](https://github.com/wmo-raf/nmhs-cms): a Wagtail
admin entry that hosts the [Bulletin Studio](https://github.com/fgg-consultant/bulletin-studio-js)
JS app (Vue 3 + Lexical) and stores its documents server-side.

An ordinary pip-installable Django/Wagtail app, packaged the same way as
[climweb-dataset-helper](https://github.com/wmo-raf/climweb-dataset-helper) — not a
ClimWeb *plugin*.

## Installation

```shell
pip install climweb-bulletin-studio
```

Then add the app to ClimWeb via its environment:

```shell
CLIMWEB_ADDITIONAL_APPS=bulletin_studio
```

For any other Wagtail project, add `"bulletin_studio"` to `INSTALLED_APPS` yourself.
Then run migrations:

```shell
python manage.py migrate bulletin_studio
```

The admin menu gains a **Bulletin Studio** entry pointing at `/admin/bulletin-studio/`.

## Layout

```
bulletin_studio/          the Django app
  wagtail_hooks.py        admin menu entry + admin urls
  views.py                the admin page + the JSON store the JS app talks to
  models.py               Bulletin (uuid pk, title, doc JSONField)
  templates/…/app.html    Wagtail admin shell + mount point for the JS app
  static/…/app/           built JS bundle (see sync-frontend.sh)
sandbox/                  minimal Wagtail project to run the app standalone
```

## Frontend

The UI lives in its own repo ([bulletin-studio-js](https://github.com/fgg-consultant/bulletin-studio-js))
and the admin page can load it two ways.

**Dev — Vite dev server, HMR, no build step.** Point the app at a running dev server:

```shell
cd ../bulletin-studio-js && npm run dev          # port fixe 5180 (strictPort)
BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180 python manage.py runserver
```

The template then loads `/@vite/client` and `/src/main.ts` from that origin instead of the
bundle, and styles arrive through Vite's module graph.

**Built bundle.** `./sync-frontend.sh ../bulletin-studio-js` builds and copies `dist/` into
`bulletin_studio/static/bulletin_studio/app/`. In this checkout that path is a **symlink**
to `../bulletin-studio-js/dist`, so a plain `npm run build` in the JS repo is enough
(the script detects the symlink and skips the copy).

Either way the page hands the app its API url, CSRF token and asset base through data
attributes on `#bulletin-studio-app`, and the bundle keeps unhashed names
(`bulletin-studio.js` / `bulletin-studio.css`) so `{% static %}` can find it.

## Store API

All under `/admin/bulletin-studio/`, staff-only, CSRF-protected (send `X-CSRFToken`):

| Method | Path | Purpose |
|---|---|---|
| `GET` | `api/bulletins/` | dashboard listing (metadata only) |
| `POST` | `api/bulletins/` | create |
| `GET` | `api/bulletins/<uuid>/` | read one, with blocks |
| `PUT` | `api/bulletins/<uuid>/` | save (upsert — the editor owns the id) |
| `DELETE` | `api/bulletins/<uuid>/` | delete |

## Development

```shell
docker compose -f sandbox/docker-compose.yml up --build   # http://localhost:8000/admin (admin/admin)
```

Or without Docker:

```shell
python -m venv .venv && . .venv/bin/activate
cd sandbox && pip install -r requirements.txt   # `-e ..` needs this cwd
python manage.py migrate && python manage.py createsuperuser
python manage.py runserver
```

`makemigrations.py` / `migrate.py` at the repo root are shims that boot Django against
sqlite for schema work outside the sandbox.
