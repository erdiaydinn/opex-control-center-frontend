FROM python:3.12-slim

WORKDIR /app

RUN addgroup --system platform && \
    adduser --system --ingroup platform platform

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

USER platform

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
