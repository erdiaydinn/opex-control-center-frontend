FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EAY_AI_DB_PATH=/data/eay_ai.db

RUN groupadd --gid 10001 eay \
    && useradd --uid 10001 --gid eay --create-home --shell /usr/sbin/nologin eay

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --upgrade pip \
    && python -m pip install . \
    && mkdir -p /data \
    && chown -R 10001:10001 /app /data

USER 10001:10001

EXPOSE 8030

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8030"]
