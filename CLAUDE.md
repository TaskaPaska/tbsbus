# CLAUDE.md

## Project
Real-time bus arrival prediction and nearest-stop lookup for Tbilisi, Georgia — a
personal navigation tool, live at **https://tbsbus.com**. The system ingests live data
from the Tbilisi Transport Company (TTC / AzRy) API, trains ML models to predict bus
arrival times, and serves predictions via a web app. AI coding tools were used during
development; the system design, engineering decisions, and analysis are the author's
own.

**Origin:** this repo continues from a bachelor's thesis proof-of-concept
(`tbilisi-bus-stats`, Caucasus University, now archived), which demonstrated a
distributed Big Data pipeline (Kafka, Spark, k3s) for the same underlying problem. This
repo inherited that codebase and is a standalone, actively developed successor — scope
has narrowed from "thesis demonstration" to "personal-use app," and the architecture is
being simplified accordingly rather than kept at thesis scale out of inertia. See
`NEXT_APP_PLAN.md` (gitignored, local-only living doc) for the current working plan and
sequencing; treat it as the source of truth for "what's next" over this file's older
framing where they conflict.

**Current scope, concretely:** one job — accurate live arrival info for whichever stop
the user is near, anywhere in the city. Not a multi-user product (yet). Two planned but
not-yet-started features: route-change/disruption detection, and a personal
stats/health view (collector uptime, data freshness, model-vs-operator accuracy).

## Hardware / nodes
- `atlas` — Lenovo ThinkCentre M720q, i3-8100T, 8GB RAM. Ubuntu Server, headless, always
  on. Runs the lightweight always-on services: collector, Kafka, PostgreSQL, and later
  the k3s control plane + Flask/Angular.
- `forge` — desktop PC, 32GB RAM, Windows. The workhorse, on only when working. Runs
  Spark workers and ML training (via WSL2 or Docker).
- Two laptops (8GB each) — join as extra cluster nodes near the end, via small Linux VMs,
  for the multi-node demo only.

**Resource reality:** nodes are RAM-constrained (8GB). Keep every component small. Always
prefer lightweight implementations over "production" defaults.

## Stack
- Language: Python 3.11+
- Storage: PostgreSQL 16 + PostGIS, single instance. Not going anywhere.
- ML: scikit-learn (Linear Regression, Random Forest, Gradient Boosting) first;
  Keras/TensorFlow LSTM last, only if time allows. Best so far: 1.83 min MAE vs. the
  operator's own 3.33 min MAE.
- API: Flask (thin REST service).
- Frontend: Angular (minimal — do not gold-plate).
- Containers: Docker / Docker Compose for dev orchestration.

**Inherited from the thesis, now considered simplification candidates rather than fixed
decisions** — kept only where there's a real reason (reliability, or genuine interest in
keeping the skill sharp), not by default:
- Apache Kafka (single broker, KRaft mode) — likely to be dropped; collector → Postgres
  directly is enough at personal-use scale. No real multi-consumer/replay need yet.
- Apache Spark (small standalone cluster) — very likely unnecessary; single city, single
  box, this is DuckDB/Polars/pandas-sized data indefinitely at personal-use volume.
- k3s — fewer moving parts favors plain systemd/docker-compose on a solo-maintained
  always-on box (`atlas`).

Do not silently re-introduce or expand these without checking `NEXT_APP_PLAN.md` first —
the direction is to shrink this list, not grow it.

## Data source
Tbilisi Transport Company (TTC / AzRy) API — the backend behind the official Tbilisi
Transport app. Reference wrapper: https://github.com/sunneydev/ttc-api (TypeScript).

**Before writing the collector:** read that wrapper's source to extract the real HTTP base
URL and request shapes for `stops`, `arrivalTimes`, and `locations`, then verify they
respond live with a quick `curl` / `requests` test. Confirm endpoints against the live
API first — do not assume them.

Key response fields (from the wrapper):
- `stops`: `id, code, name, lat, lon, vehicleMode (BUS/GONDOLA/SUBWAY)`
- `arrivalTimes(stopId)`: per upcoming arrival -> `shortName (route), headsign,
  realtime (bool), realtimeArrivalMinutes, scheduledArrivalMinutes`
- `locations(route/busId)`: real-time vehicle positions on a route

Respect rate limits: cache, poll politely, start with a small set of stops. The optimal
poll interval is itself a finding to determine experimentally.

## Data collection design (determines whether the ML works)
The API is a polling source; it does NOT return "actual arrival time." Labels are
reconstructed:
1. Track a fixed, modest set of stops (~20-40 on a few busy routes).
2. Every ~30-60s, poll `arrivalTimes` for each tracked stop and store **every snapshot**:
   timestamp, stop_id, route, direction/headsign, realtime flag, realtimeArrivalMinutes,
   scheduledArrivalMinutes. Also poll `locations` for those routes and store vehicle traces.
3. **Arrival detection:** for a (stop, route, direction), the predicted-minutes series
   decreases toward 0 then disappears — that timestamp approximates actual arrival. Use
   vehicle positions (and a vehicle id if available) to confirm/disambiguate.
4. **Training row** = a snapshot taken k minutes before arrival (features:
   realtimeArrivalMinutes, scheduledArrivalMinutes, time-of-day, day-of-week, route, stop,
   recent headway, distance-to-stop) -> **label** = actual minutes to arrival.
5. **Baselines for evaluation:** the operator's own `realtimeArrivalMinutes` and the
   `scheduledArrivalMinutes`. The model should beat both on MAE (target < 3 min).

## Storage path
- Phase 1: collector appends newline-delimited JSON (JSONL) to `data/raw/`, one file per
  day. Zero setup — nothing should block data collection from starting.
- Phase 2: ETL JSONL -> PostgreSQL; Spark reads from there.

## Repo structure (actual, current)
```
/
  CLAUDE.md
  README.md
  NEXT_APP_PLAN.md            # gitignored, local-only — living plan, check first
  docker-compose.yml          # kafka + collector + ingest + api + postgres
  .env.example                # documents required env vars; never commit real secrets
  services/
    collector/                # polls TTC API -> JSONL (+ Kafka)
    ingest/                   # Kafka -> PostgreSQL consumer
    processing/               # ETL, arrival detection, feature engineering (Python + Spark)
    ml/                       # training + evaluation (sklearn)
    api/                      # Flask REST API (tracked-stops list + predictions)
    frontend/                 # Angular app
  data/
    raw/                      # JSONL snapshots (gitignored)
  k8s/                        # k3s manifests (inherited from thesis; simplification candidate)
  docs/                       # documentation, figures
```

## Current focus
Per `NEXT_APP_PLAN.md`'s sequencing: nearest-stop lookup using the **full city stop
list** (all TTC stops, via the `stops` endpoint) is the app's core not-yet-built
feature — today `/stops` in `services/api/app.py` only serves the curated ~20-40 stop
training subset (`services/collector/tracked_stops.json`). Distinguish two different
problems: loading/showing all stops (cheap, one call) vs. continuously polling
`arrivalTimes` for all of them (expensive, rate-limited, and `atlas` is RAM-constrained
— do not naively scale the tracked-subset poll loop to every stop). Current plan:
on-demand live fetch for "the stop the user is at right now," keeping the curated
subset for historical/ML/disruption-baseline data.

## Conventions
- One virtualenv per Python service (`.venv`), pinned `requirements.txt`.
- Config via environment variables / `.env`. Never commit secrets; keep `.env.example` current.
- Each service has its own Dockerfile and a short README.
- Keep services small and independently runnable. Favor clarity over cleverness.

## Commands
- Dev stack: `cp .env.example services/collector/.env` (fill in `API_KEY`), then
  `docker compose up --build` — kafka + collector + ingest + api + postgres.
- Run collector alone: `cd services/collector && python collector.py`
- Train model: `cd services/ml && python train.py ../../data/processed/training.csv`
- Frontend dev: `cd services/frontend && npm install && npm start`
- API endpoints: `GET /health`, `GET /stops`, `GET /predict/<stop_id>`.

## Public demo exposure (atlas → Cloudflare Tunnel)
Frontend + API are exposed at **https://tbsbus.com** via a Cloudflare Tunnel running on
`atlas` (native systemd, no Docker). Rationale + design: see `docs/decisions.md` §7.
- **cloudflared config:** `/etc/cloudflared/config.yml` (tunnel `ttc-demo`; ingress
  `tbsbus.com → http://127.0.0.1:8080`, catch-all `404`). Credentials:
  `/etc/cloudflared/<tunnel-uuid>.json` + `~atlas/.cloudflared/cert.pem` — **never commit**.
- **systemd units on atlas:** `cloudflared`, `caddy` (reverse proxy, `127.0.0.1:8080`, static
  bundle in `/var/www/ttc` + proxies `/predict`,`/stops`,`/health`), `ttc-api`
  (gunicorn `127.0.0.1:5000`). All enabled (survive reboot). Caddyfile: `/etc/caddy/Caddyfile`.
- Postgres/Kafka/Spark are NOT exposed (not run on atlas; API/Caddy bind loopback only).
