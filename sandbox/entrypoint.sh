#!/bin/bash
set -euo pipefail

python manage.py migrate --noinput

if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" ]]; then
  python manage.py createsuperuser --noinput 2>/dev/null \
    && echo "Created superuser $DJANGO_SUPERUSER_USERNAME." \
    || echo "Superuser $DJANGO_SUPERUSER_USERNAME already exists."
fi

echo "Bulletin Studio sandbox: http://localhost:8000/admin/bulletin-studio/"
exec python manage.py runserver 0.0.0.0:8000
