FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system alerts && \
    adduser --system --ingroup alerts alerts && \
    mkdir -p /state && \
    chown -R alerts:alerts /state

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

USER alerts

CMD ["python", "-m", "app.main"]
