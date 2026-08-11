# tbsbus

Real-time Tbilisi bus arrival predictions and a nearest-stop lookup. A personal
navigation tool: accurate live arrival info for whichever stop I'm near, anywhere in
the city.

Live: **https://tbsbus.com**

> **Status:** actively developed, personal-use scope. This repo continues from a
> bachelor's thesis proof-of-concept —
> [`tbilisi-bus-stats`](https://github.com/TaskaPaska/tbilisi-bus-stats) (Caucasus
> University), now archived — which demonstrated a distributed Big Data pipeline
> (Kafka, Spark, k3s) for the same underlying problem. This repo inherits that
> codebase as a starting point and is narrowing scope and architecture toward what a
> single-user app actually needs; expect the stack described below to simplify over
> time rather than match the thesis's distributed design.

---

## What it does

- Live arrival predictions vs. the TTC operator's own real-time predictions and
  schedule — the ML model beats both baselines (best so far: **1.83 min MAE** vs. the
  operator's **3.33 min MAE**).
- Nearest-stop lookup across every stop in the city (not just the tracked training
  subset) — geolocate and get predictions for whichever stop you're near.
- Planned next: route-change/disruption detection and a personal quality/health view.

## Origin

The API doesn't return an actual arrival time — only minutes remaining. So the core
of the system is **arrival reconstruction**: for a (stop, route, direction), the
predicted-minutes series is tracked as it decreases toward zero, and that point is
taken as the actual arrival. Models are trained on labels built this way.

## Architecture (inherited, being simplified)

```
TTC / AZRY API
     │  (polite poller — 30/60s)
     ▼
collector ──► JSONL (durable raw log, data/raw/)
     │
     └──────► Kafka topic (ttc.arrivals / ttc.positions)   ← Apache Kafka, single broker, KRaft
                   │
                   ▼
              ingest consumer ──► PostgreSQL 16 + PostGIS
                                       │
                                       ▼
                              Apache Spark (standalone cluster)
                              arrival detection + feature engineering
                                       │
                                       ▼
                              scikit-learn training ──► model.joblib
                                       │
                                       ▼
                              Flask REST API  ──►  Angular frontend
```

This is the thesis's distributed setup, sized to demonstrate Kafka/Spark/k3s for an
academic defense. A single-user app serving one city on one small always-on box
doesn't need that — default going forward is to simplify (Kafka and Spark are the
most likely to go) rather than keep it out of inertia.

## Repo structure

```
services/
  collector/    # TTC API poller → JSONL (+ Kafka)
  ingest/       # Kafka → PostgreSQL consumer
  processing/   # ETL, arrival detection, feature engineering (Python + Spark)
  ml/           # model training and evaluation
  api/          # Flask REST API
  frontend/     # Angular app
data/raw/       # JSONL snapshots (gitignored)
k8s/            # k3s manifests (inherited, likely to shrink or go)
```

Each service has its own `README.md`.

## Running it

```bash
cp .env.example services/collector/.env   # fill in API_KEY
cd services/collector && python list_all_stops.py   # once, generates all_stops.json
cd ../.. && docker compose up --build                # kafka + collector + ingest + api + postgres
```

Model training:

```bash
cd services/ml && python train.py ../../data/processed/training.csv
```

Frontend (dev):

```bash
cd services/frontend && npm install && npm start
```

| Service | Port |
|---------|------|
| Flask API | `5000` (`/predict/<stop_id>`, `/stops`, `/health`) |
| PostgreSQL | `5432` |
| Kafka (from host) | `29092` |
| Spark master UI | `8080` |

## Public demo

**https://tbsbus.com** is served from this repo (Flask API + frontend), via a
Cloudflare Tunnel. Postgres, Kafka, and Spark are not exposed.
