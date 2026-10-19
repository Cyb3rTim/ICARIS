# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Run as an unprivileged user; uploads live on a mounted volume.
RUN useradd --system --uid 10001 --home /app icaris \
    && mkdir -p /app/staticfiles /var/lib/icaris/media \
    && chown -R icaris:icaris /app/staticfiles /var/lib/icaris
USER icaris

ENV DJANGO_MEDIA_ROOT=/var/lib/icaris/media

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "grc_project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
