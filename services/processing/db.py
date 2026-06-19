"""PostgreSQL/PostGIS დამხმარე ფენა — ფაზა 2 ETL.

ერთ ადგილას: კავშირი, სქემის ინიციალიზაცია, JSONL→Postgres ჩატვირთვა და წაკითხვა.
detect_arrivals.py და build_features.py იყენებენ `iter_db_arrivals`-ს, რომ იგივე
ნორმალიზებული ჩანაწერები მიიღონ, რასაც JSONL-დან (კოდი ერთი რჩება ორივე წყაროსთვის).

კავშირი env-დან: DATABASE_URL ან ცალკეული POSTGRES_* (default-ები compose-ს ემთხვევა).
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import psycopg2
from psycopg2.extras import execute_values

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
BATCH = 5000  # execute_values-ის batch — RAM/სიჩქარის ბალანსი 8GB კვანძზე.


def dsn() -> str:
    """კავშირის სტრიქონი — DATABASE_URL თუ არის, თორემ POSTGRES_* ცვლადებიდან."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "ttc")
    user = os.getenv("POSTGRES_USER", "ttc")
    pw = os.getenv("POSTGRES_PASSWORD", "ttc")
    return f"host={host} port={port} dbname={db} user={user} password={pw}"


def connect():
    return psycopg2.connect(dsn())


def init_schema(conn) -> None:
    """schema.sql-ის გაშვება (იდემპოTენტურია — IF NOT EXISTS)."""
    with conn.cursor() as cur:
        cur.execute(SCHEMA_FILE.read_text(encoding="utf-8"))
    conn.commit()


# ---------- ჩატვირთვა (JSONL -> Postgres) ----------

def upsert_stops(conn, stops: List[Dict[str, Any]]) -> int:
    """tracked_stops.json-ის გაჩერებები -> stop ცხრილი (geom-ით). იდემპოტენტური (ON CONFLICT)."""
    rows = [(s["id"], s.get("name"), s.get("lat"), s.get("lon"), s.get("routes", []),
             s.get("lon"), s.get("lat")) for s in stops]
    with conn.cursor() as cur:
        execute_values(cur, """
            INSERT INTO stop (id, name, lat, lon, routes, geom)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
              name = EXCLUDED.name, lat = EXCLUDED.lat, lon = EXCLUDED.lon,
              routes = EXCLUDED.routes, geom = EXCLUDED.geom
        """, rows, template="(%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)")
    conn.commit()
    return len(rows)


def _src_date(path: Path) -> str:
    return path.stem  # ფაილი YYYY-MM-DD.jsonl


# ერთი collector-ის ჩანაწერი (JSONL ხაზი ან Kafka message) -> ცხრილის სტრიქონების სია.
# src_date იღება ts-დან (ts[:10]) — collector ფაილებსაც UTC-დღით ჭრის, ამიტომ იდენტურია.
# ამ ფუნქციებს იყენებს batch loader-იც (ქვემოთ) და Kafka consumer-იც (services/ingest).

def arrival_rows_from_record(rec: Dict[str, Any]) -> List[Tuple]:
    ts, stop_id = rec["ts"], rec["stop_id"]
    src = ts[:10]
    return [(
        ts, src, stop_id, a["shortName"], a.get("headsign"),
        a.get("patternSuffix") or "", a.get("vehicleMode"),
        bool(a.get("realtime")), a.get("realtimeArrivalMinutes"),
        a.get("scheduledArrivalMinutes"),
    ) for a in rec["payload"]]


def position_rows_from_record(rec: Dict[str, Any]) -> List[Tuple]:
    ts, route_id, forward = rec["ts"], rec["route_id"], rec.get("forward")
    src = ts[:10]
    out = []
    for v in rec["payload"]:
        lon, lat = v.get("lon"), v.get("lat")
        out.append((ts, src, route_id, forward, v.get("vehicleId"),
                    lat, lon, v.get("heading"), v.get("nextStopId"), lon, lat))
    return out


def load_arrivals_jsonl(conn, path: Path) -> int:
    """ერთი arrival-times JSONL ფაილი -> arrival_snapshot. იდემპოტენტური იმ დღისთვის."""
    import json
    src = _src_date(path)
    rows: List[Tuple] = []
    inserted = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM arrival_snapshot WHERE src_date = %s", (src,))
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rows.extend(arrival_rows_from_record(json.loads(line)))
                if len(rows) >= BATCH:
                    inserted += _flush_arrivals(cur, rows); rows.clear()
        if rows:
            inserted += _flush_arrivals(cur, rows)
    conn.commit()
    return inserted


def _flush_arrivals(cur, rows) -> int:
    execute_values(cur, """
        INSERT INTO arrival_snapshot
          (ts, src_date, stop_id, route, headsign, pattern, vehicle_mode, realtime, rt_min, sched_min)
        VALUES %s
    """, rows)
    return len(rows)


def load_positions_jsonl(conn, path: Path) -> int:
    """ერთი positions JSONL ფაილი -> vehicle_position (geom-ით). იდემპოტენტური იმ დღისთვის."""
    import json
    src = _src_date(path)
    rows: List[Tuple] = []
    inserted = 0
    with conn.cursor() as cur:
        cur.execute("DELETE FROM vehicle_position WHERE src_date = %s", (src,))
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rows.extend(position_rows_from_record(json.loads(line)))
                if len(rows) >= BATCH:
                    inserted += _flush_positions(cur, rows); rows.clear()
        if rows:
            inserted += _flush_positions(cur, rows)
    conn.commit()
    return inserted


def insert_arrival_rows(conn, rows: List[Tuple]) -> int:
    """append-only ჩაწერა (streaming consumer-ისთვის — per-day delete გარეშე)."""
    if not rows:
        return 0
    with conn.cursor() as cur:
        _flush_arrivals(cur, rows)
    conn.commit()
    return len(rows)


def insert_position_rows(conn, rows: List[Tuple]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        _flush_positions(cur, rows)
    conn.commit()
    return len(rows)


def _flush_positions(cur, rows) -> int:
    execute_values(cur, """
        INSERT INTO vehicle_position
          (ts, src_date, route_id, forward, vehicle_id, lat, lon, heading, next_stop_id, geom)
        VALUES %s
    """, rows, template="(%s,%s,%s,%s,%s,%s,%s,%s,%s, ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography)")
    return len(rows)


# ---------- წაკითხვა (Postgres -> ნორმალიზებული ჩანაწერები) ----------

def iter_db_arrivals(conn, only_realtime: bool = True) -> Iterator[Dict[str, Any]]:
    """arrival_snapshot-ს კითხულობს ნორმალიზებულ ჩანაწერებად — იგივე ფორმა, რასაც JSONL-ის
    მკითხველი detect_arrivals.py-ში. server-side cursor — RAM-ს არ ჭამს მილიონ სტრიქონზე.
    """
    sql = ("SELECT ts, stop_id, route, pattern, headsign, rt_min, sched_min "
           "FROM arrival_snapshot")
    if only_realtime:
        sql += " WHERE realtime = true"
    with conn.cursor(name="snap_stream") as cur:  # named = server-side, ნაკადად
        cur.itersize = 50_000
        cur.execute(sql)
        for ts, stop_id, route, pattern, headsign, rt_min, sched_min in cur:
            yield {
                "ts": ts, "stop_id": stop_id, "route": route,
                "pattern": pattern or "", "headsign": headsign or "",
                "rt_min": rt_min, "sched_min": sched_min,
            }


# ---------- ჩაწერა (detect_arrivals-ის შედეგი) ----------

def write_arrival_events(conn, events: Iterable[Dict[str, Any]], replace: bool = True) -> int:
    rows = [(e["stop_id"], e["route"], e["pattern"], e.get("headsign"),
             e["arrival_ts"], e.get("delay_min"), e.get("n_readings"),
             e.get("min_remaining_min"), e.get("first_seen_min"), e.get("first_seen_ts"))
            for e in events]
    with conn.cursor() as cur:
        if replace:
            cur.execute("TRUNCATE arrival_event")
        for i in range(0, len(rows), BATCH):
            execute_values(cur, """
                INSERT INTO arrival_event
                  (stop_id, route, pattern, headsign, arrival_ts, delay_min,
                   n_readings, min_remaining_min, first_seen_min, first_seen_ts)
                VALUES %s
            """, rows[i:i + BATCH])
    conn.commit()
    return len(rows)
