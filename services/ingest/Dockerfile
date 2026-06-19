# Kafka -> Postgres consumer. db.py services/processing-იდანაა — ორივე საქაღალდე ერთად კოპირდება
# (context = repo root, api-ს მსგავსად). RAM-ლიმიტირებული კვანძებისთვის slim base.
FROM python:3.12-slim

WORKDIR /app

COPY services/ingest/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# db.py + schema.sql processing-იდან /app-ში (consumer-ის გვერდით); dev-ის ../processing
# sys.path fallback container-ში უვნებელია — `import db` /app-დან მაინც მოიძებნება.
COPY services/processing/db.py services/processing/schema.sql /app/
COPY services/ingest/ /app/

CMD ["python", "consumer.py"]
