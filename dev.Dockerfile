# The package installed into the ClimWeb dev image. Built FROM climweb_dev:latest,
# which comes from a local ClimWeb checkout (see ../climweb).
FROM climweb_dev:latest

USER root

# Installed editable at the same path the compose file bind-mounts, so edits to
# bulletin_studio/ on the host take effect without a rebuild.
COPY . /app
RUN . /climweb/venv/bin/activate && pip3 install -e /app

USER $DOCKER_USER

ENV PATH="/climweb/venv/bin:$PATH"
ENV DJANGO_SETTINGS_MODULE='climweb.config.settings.dev'
CMD ["django-dev"]
