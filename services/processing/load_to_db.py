"""ETL: დაუმუშავებელი JSONL -> PostgreSQL/PostGIS — ფაზა 2.

JSONL რჩება ხელახლა-გაშვებად raw ლოგად; ეს სკრიპტი მას ანაწილებს ბაზის ტიპიზებულ
ცხრილებში. ჩატვირთვა იდემპოტენტურია თითო დღისთვის (ხელახლა გაშვებისას იმ დღის სტრიქონები
ჯერ იშლება). გაჩერებები იტვირთება collector/tracked_stops.json-დან.

გამოყენება:
    python load_to_db.py --init \\
        --stops ../collector/tracked_stops.json \\
        --arrivals ../../data/raw/arrival-times/*.jsonl \\
        --positions ../../data/raw/positions/*.jsonl
"""
import argparse
import json
import sys
from pathlib import Path

import db


def main():
    ap = argparse.ArgumentParser(description="Load raw TTC JSONL into PostgreSQL/PostGIS.")
    ap.add_argument("--init", action="store_true", help="ჯერ გაუშვას schema.sql")
    ap.add_argument("--stops", type=Path, help="tracked_stops.json — stop ცხრილისთვის")
    ap.add_argument("--arrivals", nargs="*", type=Path, default=[], help="arrival-times JSONL ფაილები")
    ap.add_argument("--positions", nargs="*", type=Path, default=[], help="positions JSONL ფაილები")
    args = ap.parse_args()

    conn = db.connect()
    if args.init:
        db.init_schema(conn)
        print("schema.sql applied.", file=sys.stderr)

    if args.stops:
        stops = json.loads(args.stops.read_text(encoding="utf-8")).get("stops", [])
        n = db.upsert_stops(conn, stops)
        print(f"Upserted {n} stops.", file=sys.stderr)

    for p in args.arrivals:
        n = db.load_arrivals_jsonl(conn, p)
        print(f"arrival_snapshot += {n:,}  <- {p.name}", file=sys.stderr)

    for p in args.positions:
        n = db.load_positions_jsonl(conn, p)
        print(f"vehicle_position += {n:,}  <- {p.name}", file=sys.stderr)

    if not (args.stops or args.arrivals or args.positions):
        print("Nothing to load (pass --stops/--arrivals/--positions).", file=sys.stderr)


if __name__ == "__main__":
    main()
