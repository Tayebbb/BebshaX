# Production image for the BebshaX API (docs/DEMO.md §7).
# Build context: apps/backend — `docker compose --profile full up --build`.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# alembic.ini + alembic/ stay in the workdir so migrations can be run
# manually: docker compose exec app python -m alembic upgrade head
COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY bebshax ./bebshax
RUN pip install .

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "bebshax.main:app", "--host", "0.0.0.0", "--port", "8000"]
