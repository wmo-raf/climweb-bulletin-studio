# No GDAL, no Postgres: Bulletin Studio stores one JSONField, so plain Python is enough.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=sandbox.settings.dev

EXPOSE 8000

WORKDIR /app

# The package lives one level up from the sandbox, so the build context is the repo
# root (see docker-compose.yml) and `-e ..` in requirements.txt resolves.
COPY setup.cfg pyproject.toml README.md LICENSE MANIFEST.in /app/
COPY bulletin_studio /app/bulletin_studio
COPY sandbox/requirements.txt /app/sandbox/requirements.txt

# `-e ..` in requirements.txt is resolved relative to the cwd, hence sandbox/.
WORKDIR /app/sandbox
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

COPY sandbox /app/sandbox

CMD ["bash", "./entrypoint.sh"]
