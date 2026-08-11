# Collector

Phase 1 of the pipeline: poll the TTC API and append raw snapshots to daily JSONL files.
Nothing downstream exists until data does, so this runs first and always-on (on `atlas`).

## Files
- `ttc_client.py` — thin TTC API client.
- `probe_api.py` — one-shot live check of endpoint shapes (run first, after setting the key).
- `select_stops.py` — auto-selects the ~30 busiest stops by route density → `tracked_stops.json`
  (training/collection subset — this is what `collector.py` polls continuously).
- `list_all_stops.py` — dumps every BUS stop citywide (one cheap `stops()` call, no route
  scan) → `all_stops.json`. Used by the API's `/stops` for nearest-stop lookup — not polled
  continuously, just refreshed occasionally (stops rarely change).
- `collector.py` — the polling loop: arrival-times per stop + positions per route → JSONL.
- `config.py` — all tunables (env-overridable).

## What it stores
Two streams under `data/raw/` (repo root), one file per UTC day:
- `arrival-times/YYYY-MM-DD.jsonl` — per stop, per poll (the primary signal for arrival detection).
- `positions/YYYY-MM-DD.jsonl` — per route/direction, per poll (auxiliary, to confirm arrivals).

Each line is `{"ts", "endpoint", "stop_id"|"route_id", "payload": <full raw response>}`.
We keep the **full raw payload** on purpose: collection is irreversible, so we lose nothing
now and normalize later in the Phase 2 ETL.

## Setup & run (local)
```bash
cd services/collector
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then put your API_KEY in it

python probe_api.py           # 1. confirm endpoint shapes live
python select_stops.py        # 2. pick training stops -> tracked_stops.json
python list_all_stops.py      # 3. full city stop list -> all_stops.json (for nearest-stop lookup)
python collector.py           # 4. start collecting (Ctrl-C to stop)
```

Re-run `list_all_stops.py` occasionally (e.g. monthly, or after a known TTC route change) to
pick up new/removed stops — it's not part of the continuous collection loop.

## Tunables (env / `.env`)
| var | default | meaning |
|-----|---------|---------|
| `POLL_INTERVAL_SECONDS` | 30 | arrival-times cadence |
| `POSITIONS_POLL_INTERVAL_SECONDS` | 60 | positions cadence (auxiliary, slower) |
| `POSITIONS_BOTH_DIRECTIONS` | true | poll both route directions for positions |
| `INTER_REQUEST_DELAY` | 0.25 | polite pause between HTTP calls |
| `TARGET_STOP_COUNT` | 30 | how many stops the selector picks |

## Deploy on atlas
See `collector.service` for a systemd unit template. Once data is flowing it survives
reboots and restarts on failure.
