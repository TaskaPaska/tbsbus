# processing — ფაზა 2 ETL & feature engineering

დაუმუშავებელ TTC snapshot-ებს აქცევს ML-ის სასწავლო მონაცემებად. JSONL რჩება
ხელახლა-გაშვებად raw ლოგად; PostgreSQL/PostGIS — *queryable* საცავი.

```
collector → JSONL ──load_to_db──▶ PostgreSQL/PostGIS ──▶ detect_arrivals / build_features ──▶ train
```

## კომპონენტები
- `schema.sql` — PostGIS სქემა: `stop`, `arrival_snapshot`, `vehicle_position`, `arrival_event`.
- `db.py` — კავშირი, სქემის init, JSONL→Postgres ჩატვირთვა, წაკითხვა, arrival_event-ის ჩაწერა.
- `load_to_db.py` — ETL CLI (JSONL → Postgres). იდემპოტენტური თითო დღისთვის.
- `detect_arrivals.py` — მოსვლის დაფიქსირება (ML ლეიბლები). `--source jsonl|db`, `--to-db`.
- `build_features.py` — სასწავლო სტრიქონების აგება. `--source jsonl|db`.

## გაშვება

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Postgres-ის გაშვება (repo root-დან):
#   docker compose up -d postgres

# კავშირი env-დან (default-ები compose-ს ემთხვევა): POSTGRES_HOST/PORT/DB/USER/PASSWORD
# ან: export DATABASE_URL=postgresql://ttc:ttc@localhost:5432/ttc

# 1) ჩატვირთვა JSONL -> Postgres (სქემის init-ით):
python load_to_db.py --init \
  --stops ../collector/tracked_stops.json \
  --arrivals ../../data/raw/arrival-times/*.jsonl \
  --positions ../../data/raw/positions/*.jsonl

# 2) მოსვლების დაფიქსირება Postgres-იდან -> arrival_event ცხრილი:
python detect_arrivals.py --source db --to-db

# 3) სასწავლო მონაცემის აგება Postgres-იდან:
python build_features.py --source db -o ../../data/processed/training.csv
```

JSONL-დან პირდაპირ მუშაობა კვლავ შესაძლებელია (`--source jsonl <files>`) — db არ არის სავალდებულო.
