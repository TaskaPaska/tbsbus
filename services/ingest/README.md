# ingest — Kafka → PostgreSQL consumer (ფაზა 2)

collector აქვეყნებს snapshot-ებს Kafka topic-ებში (`ttc.arrivals`, `ttc.positions`)
JSONL-ის *პარალელურად*. ეს consumer კითხულობს მათ და Postgres-ში წერს (append-only),
`services/processing/db.py`-ის იგივე unroll-ლოგიკით, რასაც batch loader.

```
collector ──┬─▶ JSONL (durable raw log)
            └─▶ Kafka topic ──▶ ingest consumer ──▶ PostgreSQL
```

## დიზაინის არჩევანები
- **JSONL რჩება durable წყაროდ**; Kafka — სტრიმინგ-ტრანსპორტი. ბაზის თავიდან აგება
  ნებისმიერ დროს JSONL-დან (batch `load_to_db.py`) შესაძლებელია.
- **At-least-once**: ჯერ DB-batch ჩაიწერება, მერე offset commit-დება. ავარიაზე ბოლო batch
  გამეორდება — append-only ანალიტიკურ ცხრილზე ეს მისაღებია.
- **opt-in**: collector Kafka-ში წერს მხოლოდ `KAFKA_BOOTSTRAP`-ის დაყენებისას. atlas-ის
  systemd collector ამ ცვლადის გარეშე მუშაობს → JSONL-only, წინანდებურად.
- **batch/time flush**: `INGEST_BATCH` (def. 500) ან `INGEST_FLUSH_SECONDS` (def. 5).

## გაშვება

```bash
# compose-ით (რეკომენდებული) — kafka + collector + ingest + postgres ერთად:
docker compose up --build

# ან ცალკე, ჰოსტიდან (Kafka compose-ში, წვდომა localhost:29092):
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
KAFKA_BOOTSTRAP=localhost:29092 POSTGRES_HOST=localhost python consumer.py
```

env: `KAFKA_BOOTSTRAP`, `KAFKA_TOPIC_ARRIVALS`, `KAFKA_TOPIC_POSITIONS`, `KAFKA_GROUP`,
`POSTGRES_*` / `DATABASE_URL`, `INGEST_BATCH`, `INGEST_FLUSH_SECONDS`.
