FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system identity && \
    adduser --system --ingroup identity identity

COPY pyproject.toml ./
COPY app ./app

RUN pip install --upgrade pip && \
    pip install .

USER identity

EXPOSE 8020

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8020", "--no-proxy-headers"]
