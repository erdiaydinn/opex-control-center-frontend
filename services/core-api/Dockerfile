# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPEX_PLANOGRAM_ENGINE_ROOT=/opt/eay/planai

WORKDIR /app

RUN addgroup --system opex && adduser --system --ingroup opex opex

COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --upgrade pip && pip install .

# Named build context points to apps/planai/backend. The repository keeps one
# canonical engine source; the immutable Core API image receives that exact
# reviewed library rather than a reimplemented copy.
COPY --from=planai . /opt/eay/planai

USER opex

EXPOSE 8000

CMD ["uvicorn", "app.budget_main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
