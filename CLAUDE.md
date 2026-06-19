# CLAUDE.md

## Project
Real-time bus arrival prediction for Tbilisi public transport (bachelor's thesis,
Caucasus University). The system ingests live data from the Tbilisi Transport Company
(TTC / AzRy) API, processes it through a small distributed pipeline, trains ML models to
predict bus arrival times, and serves predictions via a web app. AI coding tools were
used during development; the system design, engineering decisions, and analysis are the
author's own.

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

## Stack (decided — do NOT substitute heavier alternatives)
- Language: Python 3.11+
- Ingestion: Apache Kafka, **single broker, KRaft mode** (no ZooKeeper). Not multi-broker.
- Processing: Apache Spark, **small standalone cluster** (1 master + 1-2 workers), small executors.
- Storage: PostgreSQL 16 + PostGIS, single instance.
- ML: scikit-learn (Linear Regression, Random Forest, Gradient Boosting) first;
  Keras/TensorFlow LSTM last, only if time allows.
- API: Flask (thin REST service).
- Frontend: Angular (minimal — 1-3 components; do not gold-plate).
- Orchestration: **k3s** (lightweight Kubernetes), added AFTER the pipeline works. Not kubeadm.
- Dev orchestration: **Docker Compose first**; port to k3s later.
- Containers: Docker.

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

## Repo structure
```
/
  CLAUDE.md
  README.md
  docker-compose.yml          # dev orchestration (added once services exist)
  .env.example                # documents required env vars; never commit real secrets
  services/
    collector/                # polls TTC API -> JSONL (then -> Kafka)
    processing/               # Spark jobs: clean, feature engineering
    ml/                       # training + evaluation (sklearn, keras)
    api/                      # Flask REST API
    frontend/                 # Angular app
  data/
    raw/                      # JSONL snapshots (gitignored)
  k8s/                        # k3s manifests (added later)
  notebooks/                  # exploratory analysis
  docs/                       # documentation
```

## Conventions
- One virtualenv per Python service (`.venv`), pinned `requirements.txt`.
- Config via environment variables / `.env`. Never commit secrets; keep `.env.example` current.
- Each service has its own Dockerfile and a short README.
- Keep services small and independently runnable. Favor clarity over cleverness.

## Commands
(Fill in as components are built, e.g.:)
- Run collector: `cd services/collector && python collector.py`
- Dev stack: `docker compose up`

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
