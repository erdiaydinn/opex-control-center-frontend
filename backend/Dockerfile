FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/migrations ./migrations
COPY src/modules/workforce/staffingNorms.js ./app/modules/recruitment/data/staffingNorms.js

RUN mkdir -p /var/lib/dockos /var/backups/dockos /var/lib/dockos/recruitment-evidence

EXPOSE 8000

CMD ["sh", "-c", "python -m app.prestart && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${DOCKOS_WORKERS:-2}"]
