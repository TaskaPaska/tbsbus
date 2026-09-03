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
- `build_features.py` — სასწავლო სტრიქონების აგება. `--source jsonl|db`, სურვილისამებრ
  `--positions raw/positions/*.jsonl --stops ../collector/tracked_stops.json
  [--route-map ../collector/route_map.json]` GPS-მანძილის (veh_dist_m/veh_pos_age_s/veh_candidates)
  feature-ებისთვის — იხ. `positions_features.py`. route_map.json-ს `fetch_route_map.py`
  (`services/collector/`) აგენერირებს. **ეს GPS-სვეტები კვლევითია** — გაზომვით ჯერ არ მუშაობს
  (corr(veh_dist_m, label_min) = 0.016), ამიტომ `train.py` მათ ნაგულისხმევად არ იყენებს;
  მიზეზი დაწვრილებით `positions_features.py`-ის docstring-შია.

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

## Spark (ფაზა 3) — განაწილებული feature engineering

`spark_features.py` იგივეს აკეთებდა, რასაც `build_features.py`, ოღონდ Spark-ით განაწილებულად:
Postgres-იდან JDBC-ით კითხულობს (partition-ებად), lane-ებს worker-ებზე ანაწილებს და თითო
lane-ზე *იმავე* `iter_approaches` ლოგიკას უშვებდა (`applyInPandas`).

**შენიშვნა (2026-08):** `build_features.py`-ს დაემატა ტრენდი (rt_delta_min/rt_rate/stall_s) და
GPS-join (veh_dist_m/...) — `spark_features.py` ჯერ არ არის განახლებული ამ ლოგიკით, ასე რომ
შედეგი აღარაა იდენტური. CLAUDE.md-ის მიხედვით Spark ისედაც გამარტივების კანდიდატია
(personal-use მასშტაბზე DuckDB/Polars/pandas საკმარისია) — არ ღირს პარალელური ლოგიკის
შენარჩუნება, სანამ Spark-ის საჭიროება საბოლოოდ არ გადაწყდება.

Spark cluster batch/on-demand-ია — compose-ის `spark` profile-ში:

```bash
# 1) cluster (master + 1 worker) ატანა:
docker compose --profile spark up -d spark-master spark-worker   # master UI: http://localhost:8080

# 2) feature-job-ის გაშვება (Postgres-იდან -> /out/training_spark CSV):
docker compose --profile spark run --rm spark-submit

# 3) cluster-ის გაჩერება (RAM-ის გასათავისუფლებლად):
docker compose --profile spark stop spark-master spark-worker
```

დემოზე დამატებითი worker (forge/laptop) იგივე `ttc-spark` image-ით უერთდება:
`/opt/spark/bin/spark-class org.apache.spark.deploy.worker.Worker spark://<atlas>:7077` —
კოდის ცვლილების გარეშე. pyspark/pandas/pyarrow + postgres JDBC driver `Dockerfile.spark`-შია
(ჰოსტზე java/pyspark არ სჭირდება).
