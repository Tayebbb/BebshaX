# Production image for the BebshaX API (docs/DEMO.md §7).
# Build context: REPO ROOT — `docker compose --profile full up --build`
# (root context lets the image ship the repo-level providers.toml).
# python:3.12-slim = minor pin; the patch floats so security releases land.
# No digest pin: obtaining one needs the registry (docker manifest inspect),
# which the offline venue box lacks — see deploy/web.Dockerfile for the recipe.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# alembic.ini + alembic/ land in /app (the WORKDIR): alembic.ini resolves
# script_location via %(here)s, so `python -m alembic upgrade head` works from
# /app. docker-compose.yml runs exactly that before uvicorn; the bare image
# CMD below stays serve-only so other deployments can migrate out-of-band.
COPY apps/backend/pyproject.toml apps/backend/alembic.ini ./
COPY apps/backend/alembic ./alembic
COPY apps/backend/bebshax ./bebshax
COPY ml_persona/pyproject.toml ./ml_persona/
COPY ml_persona/constraints.txt ./ml_persona/
COPY ml_persona/src ./ml_persona/src
# freellmpool provider catalog — without it the container silently falls back
# to the library's built-in providers (see bebshax/main.py warning).
COPY providers.toml ./providers.toml
RUN pip install --constraint ./ml_persona/constraints.txt ./ml_persona .

# Writable dataset root for the non-root runtime user; compose mounts a named
# volume here so uploads survive rebuilds. data/ is excluded from the build
# context (.dockerignore) — compose bind-mounts ./data/processed and
# ./data/metadata read-only over these empty directories.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads /app/data/processed /app/data/metadata \
    && chown -R appuser:appuser /app/data
USER appuser

ENV FREELLMPOOL_CONFIG=/app/providers.toml \
    BEBSHAX_DATA_DIR=/app/data

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "bebshax.main:app", "--host", "0.0.0.0", "--port", "8000"]
