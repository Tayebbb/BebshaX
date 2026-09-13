FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS build
ENV PIP_NO_CACHE_DIR=1 PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY apps/backend/requirements.lock ./requirements.lock
COPY ml_persona/constraints.txt ./constraints.txt
RUN python -m pip --isolated install --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -c constraints.txt -r requirements.lock
COPY apps/backend/pyproject.toml ./apps/backend/
COPY apps/backend/bebshax ./apps/backend/bebshax
COPY ml_persona/pyproject.toml ./ml_persona/
COPY ml_persona/src ./ml_persona/src
RUN python -m pip --isolated wheel --no-deps --no-build-isolation --no-index --wheel-dir /local-wheels ./ml_persona ./apps/backend
# The reviewed persona ML bundle ships inside the image: cloud hosts have no
# artifact bind mount. Digest-verified against SHA256SUMS and its own manifest.
COPY deploy/unpack_model.py ./unpack_model.py
COPY deploy/models/ml_persona ./model-bundle
RUN python unpack_model.py ./model-bundle /local-model > /local-model.manifest.sha256

FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    PIP_CONFIG_FILE=/dev/null PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 NUMEXPR_NUM_THREADS=2
WORKDIR /app
# The digest-pinned base lags Debian security uploads; the release gate blocks
# any HIGH/CRITICAL CVE that already has a fix.
RUN apt-get update \
    && apt-get -y upgrade --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/python/runtime.lock ./requirements.lock
COPY ml_persona/constraints.txt ./constraints.txt
RUN python -m pip --isolated install --require-hashes --only-binary=:all: --index-url https://pypi.org/simple -c constraints.txt -r requirements.lock
COPY --from=build /local-wheels /local-wheels
RUN python -m pip --isolated install --no-deps --no-index /local-wheels/*.whl \
    && python -m pip --isolated check \
    && rm -rf /local-wheels \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data/uploads /app/data/processed /app/data/metadata /app/artifacts \
    && chown -R 10001:10001 /app/data
COPY apps/backend/alembic.ini ./
COPY apps/backend/alembic ./alembic
COPY providers.toml ./providers.toml
COPY deploy/healthcheck.py ./deploy/healthcheck.py
COPY deploy/runtime_config.py ./deploy/runtime_config.py
COPY deploy/runtime_probe.py ./deploy/runtime_probe.py
# Root-owned and read-only for the app user; a compose bind mount on
# /app/artifacts still overrides it for self-hosted releases.
COPY --from=build --chown=0:0 /local-model /app/artifacts/ml_persona/model
COPY --from=build --chown=0:0 /local-model.manifest.sha256 /app/artifacts/ml_persona/manifest.sha256
ENV FREELLMPOOL_CONFIG=/app/providers.toml \
    BEBSHAX_PROVIDER_CONFIG_PATH=/app/providers.toml \
    BEBSHAX_DATA_DIR=/app/data \
    BEBSHAX_ML_PERSONA_ARTIFACT_DIR=/app/artifacts/ml_persona/model
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "/app/deploy/runtime_config.py"]
CMD ["python", "-m", "uvicorn", "bebshax.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "25"]
