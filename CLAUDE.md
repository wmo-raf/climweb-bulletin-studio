# CLAUDE.md

## Project Overview

`climweb-bulletin-studio` — pip-installable Django/Wagtail app that hosts the Bulletin
Studio JS editor inside the ClimWeb admin. Structure copied from
`../dataset-helper-plugin`'s packaged form, i.e.
https://github.com/wmo-raf/climweb-dataset-helper (setup.cfg + `sandbox/` + root
`boot_django.py`/`makemigrations.py`/`migrate.py`).

Predecessors, both worth reading before changing anything here:
- `../bulletin-studio-plugin` — the ClimWeb *plugin* attempt (Django-rendered slot
  templates, `docs/SPECIFICATION.md`). Superseded by this package; the specification
  still describes the intended product.
- `../bulletin-studio-js` — the frontend (Vue 3 + Lexical). Source of truth for the UI;
  its `dist/` is vendored here by `sync-frontend.sh`.
- `../climweb` — the ClimWeb source. `wagtail-webstories-editor` (in its requirements) is
  the reference for "a JS app as a Wagtail admin page".

## Architecture

The Python side is deliberately thin: a menu entry, one template, one model, four JSON
endpoints. Anything about blocks, layout or rendering belongs in the JS app —
`Bulletin.doc` is stored opaquely so the two can move independently.

## Development

```shell
# frontend en mode dev (HMR) - le chemin le plus court pour itérer sur l'UI
cd ../bulletin-studio-js && npm run dev                    # port 5180, strictPort
cd sandbox && BULLETIN_STUDIO_DEV_SERVER=http://localhost:5180 ../.venv/bin/python manage.py runserver 8010

# ou bundle buildé (static/bulletin_studio/app est un lien vers ../bulletin-studio-js/dist)
./sync-frontend.sh ../bulletin-studio-js
docker compose -f sandbox/docker-compose.yml up --build    # http://localhost:8000/admin (admin/admin)
```

Le venv de la sandbox est `.venv` (python3.11 **système** : le pyenv 3.11.13 est compilé
sans `_sqlite3`). Sur cette machine 8000 et 5173 sont déjà pris, d'où 8010 / 5180.

Piège CSS : Tailwind 4 pose ses utilitaires dans `@layer utilities`, et toute règle CSS
**non layerisée** (le `core.css` de wagtail) gagne contre une règle layerisée quelle que
soit la spécificité. `src/style.css` de l'app importe donc `tailwindcss/utilities.css`
hors couche.

Naming: distribution `climweb-bulletin-studio`, module and app label `bulletin_studio`,
admin url `/admin/bulletin-studio/`, url namespace `bulletin_studio`, display name
"Bulletin Studio".

## i18n

English is the source language. When the app grows user-facing strings, mirror the
`../bulletin-studio-plugin` setup: catalogs under `bulletin_studio/locale/` for fr, es,
pt, ar (no English `.po`).
