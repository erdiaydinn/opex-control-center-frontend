# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EAY_AI_DB_PATH=/var/lib/eay-ai/eay_ai.db

WORKDIR /app

RUN addgroup --system eay && \
    adduser --system --ingroup eay eay && \
    mkdir -p /var/lib/eay-ai && \
    chown -R eay:eay /var/lib/eay-ai

COPY pyproject.toml ./
COPY app ./app
COPY config ./config
COPY models ./models
RUN pip install --upgrade pip && pip install .

USER eay

EXPOSE 8015

# This image packages the repository-governed AI Core only. Production company/
# operational retrieval remains fail-closed until canonical Core tenant context
# is propagated and verified; building this image is not production acceptance.
CMD ["uvicorn", "app.entrypoint:app", "--host", "0.0.0.0", "--port", "8015", "--no-proxy-headers"]
