"""მოსვლის დაფიქსირება, ფაზა 2, ETL-ი.

collector-ს მოაქვს თითოეული გაჩერებისთვის ჩასვლის დროები ყოველ 30 წამში.
თითოეყლუი snapshot-ი მომავალ ავტობუსებს აჩვენებს მოსვლის დროის *მინიმალურ* დარჩენილი წუთებს,
ანუ უკანთვლა/countdown-ი ხდება ``realtimeArrivalMinutes``-ის საშუალებით. როდესაც ავტობუსი მიაღწევს გაჩერებას,
countdown-ი 0-მდე მიდის და შემდეგ ავტობუსი აღარ ჩანს snapshot-ებში.

    09:00  route 305  pat 0:01  rt=4
    09:01  route 305  pat 0:01  rt=3
    09:02  route 305  pat 0:01  rt=1
    09:03  route 305  pat 0:01  rt=0
    09:04  (აღარაა)                        <- ავტობუსი მივიდა დაახლ. 09:03-09:04 დროის დიაპაზონში.

ვაკვირდებით თითოეულ უკუთვლას, როდესაც ავტობუსი მიაღწევს გაჩერებას, ანუ 0-მდე დავა მაჩვენებელი,
ვინახავთ "მოსვლის" (arrival) ჩანაწერს.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# თუ უკუთვლა გაიზარდა 3+ წუთით, მაშინ ვთვლით, რომ უკვე სხვა ავტობუსზეა საუბარი და თვლა უკვე სხვა ავტობუსისაა.
RESET_JUMP_MIN = 3
# თუ ერთი მარშრუტის უკუთვლებს შორის 3+ წუთი გავიდა, მაშინ ვთვლით, რომ ავტობუსი უკვე გაჩერებიდან წავიდა და თვლა უკვე სხვა ავტობუსისაა.
MAX_GAP_SECONDS = 180
# თუ ავტობუსი არ მივიდა 2 წუთში, მაშინ ვთვლით, რომ ეს ავტობუსი ვერ მოვიდა და არ ვქმნით arrival ჩანაწერს.
ARRIVAL_MAX_REMAINING_MIN = 2
# თუ უკუთვლა იკლებს იმაზე უფრო სწრაფად, ვიდრე გასული დრო უშვებს (ფიზიკურად შეუძლებელია, მაგ. 24→0
# ერთ ნაბიჯში), ესეც სხვა ავტობუსია ან API-ის ხარვეზი — ვწყვეტთ მიმდინარე მიახლოებას.
MAX_DROP_TOLERANCE_MIN = 2
# ნამდვილ მოსვლას მინიმუმ ორი ჩანაწერი სჭირდება; ცალკეული 0 ხშირად API-ის ხარვეზია.
MIN_READINGS_FOR_ARRIVAL = 2

Reading = Tuple[datetime, int, Optional[int]]  # (timestamp, realtime_minutes, scheduled_minutes)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def iter_jsonl_arrivals(paths: Iterable[Path]) -> Iterable[Dict[str, Any]]:
    """დაუმუშავებელ JSONL-ს ნაკადად აქცევს ნორმალიზებულ realtime ჩანაწერებად.

    ერთი ჩანაწერი = ერთი მოსალოდნელი ავტობუსი ერთ poll-ში. იგივე ფორმას აბრუნებს, რასაც
    db.iter_db_arrivals — ასე lane-ების აგების ლოგიკა ერთი რჩება ორივე წყაროსთვის.
    """
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                stop_id = rec["stop_id"]
                ts = parse_ts(rec["ts"])
                for a in rec["payload"]:
                    if not a.get("realtime"):
                        continue  # მხოლოდ რეალურ დროში მოსვლები, არა მხოლოდ დაგეგმილი
                    yield {
                        "ts": ts, "stop_id": stop_id, "route": a["shortName"],
                        "pattern": a.get("patternSuffix") or "", "headsign": a.get("headsign", ""),
                        "rt_min": a["realtimeArrivalMinutes"],
                        "sched_min": a.get("scheduledArrivalMinutes"),
                    }


def lanes_from_arrivals(records: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """ნორმალიზებულ ჩანაწერებს ვყრით lane-ებში (stop_id, route, pattern) მიხედვით.

    lane არის კონკრეტული გაჩერება + მარშრუტი + მიმართულება (patternSuffix). ანუ x მარშრუტს
    y მიმართულებით z გაჩერებისთვის lane-ი (z, x, y). lane-ები ერთმანეთისგან დამოუკიდებელია.
    წყარო (JSONL თუ DB) აქ მნიშვნელობა აღარ აქვს — iter_approaches თავად დაალაგებს დროით.
    """
    lanes: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(
        lambda: {"headsign": "", "readings": []}
    )
    for r in records:
        key = (r["stop_id"], r["route"], r["pattern"])
        lane = lanes[key]
        if r["headsign"]:
            lane["headsign"] = r["headsign"]
        lane["readings"].append((r["ts"], r["rt_min"], r["sched_min"]))
    return lanes


def read_lanes(paths: Iterable[Path]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """JSONL-დან lane-ების აგება (backward-compatible wrapper)."""
    return lanes_from_arrivals(iter_jsonl_arrivals(paths))


def iter_approaches(readings: List[Reading]):
    """თითო lane-ის უკუთვლებს ჭრის ცალკეულ მიახლოებებად და აბრუნებს მხოლოდ ვალიდურ
    მოსვლებს, წყვილად (approach_readings, arrival_ts). საერთო ლოგიკაა arrival detection-ისა
    და feature engineering-ისთვის, რომ ორივემ ერთნაირად დაჭრას მონაცემები.
    """
    readings.sort(key=lambda r: r[0])

    def arrival_of(approach: List[Reading]) -> Optional[datetime]:
        if len(approach) < MIN_READINGS_FOR_ARRIVAL:
            return None  # ერთჯერადი ჩანაწერი — სავარაუდოდ ხარვეზი.
        if min(r[1] for r in approach) > ARRIVAL_MAX_REMAINING_MIN:
            return None  # ვერ მიუახლოვდა 0-ს — მოსვლად არ ჩაითვლება.
        last_ts, last_min, _ = approach[-1]
        return last_ts + timedelta(minutes=last_min)

    approach: List[Reading] = []
    prev: Optional[Reading] = None
    for r in readings:
        if prev is not None:
            ts, minutes, _ = r
            pts, pmin, _ = prev
            gap = (ts - pts).total_seconds()
            # ფიზიკურად შეუძლებელი ვარდნა: უკუთვლა გასულ დროზე მეტად დაიკლებს.
            impossible_drop = (pmin - minutes) > gap / 60.0 + MAX_DROP_TOLERANCE_MIN
            if gap > MAX_GAP_SECONDS or minutes > pmin + RESET_JUMP_MIN or impossible_drop:
                arr = arrival_of(approach)
                if arr is not None:
                    yield approach, arr
                approach = []
        approach.append(r)
        prev = r
    arr = arrival_of(approach)
    if arr is not None:
        yield approach, arr


def segment_arrivals(readings: List[Reading]) -> List[Dict[str, Any]]:
    """თითოეული lane-ის უკუთვლების სერიას ვამოწმებთ და ვქმნით მოსვლის (arrival) ჩანაწერებს."""
    arrivals: List[Dict[str, Any]] = []
    for approach, arrival_ts in iter_approaches(readings):
        _, _, last_sched = approach[-1]
        arrivals.append({
            "arrival_ts": arrival_ts.isoformat(),
            "delay_min": last_sched,
            "n_readings": len(approach),
            "min_remaining_min": min(r[1] for r in approach),
            "first_seen_min": approach[0][1],
            "first_seen_ts": approach[0][0].isoformat(),
        })
    return arrivals


def detect_from_lanes(lanes: Dict[Tuple[str, str, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for (stop_id, short_name, pattern), lane in lanes.items():
        for ev in segment_arrivals(lane["readings"]):
            out.append({
                "stop_id": stop_id,
                "route": short_name,
                "pattern": pattern,
                "headsign": lane["headsign"],
                **ev,
            })
    out.sort(key=lambda e: (e["arrival_ts"], e["stop_id"]))
    return out


def detect(paths: List[Path]) -> List[Dict[str, Any]]:
    """JSONL-დან მოსვლების დაფიქსირება (backward-compatible wrapper)."""
    return detect_from_lanes(read_lanes(paths))


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect bus arrivals from raw arrival-times snapshots.")
    ap.add_argument("inputs", nargs="*", type=Path, help="raw arrival-times .jsonl file(s) (--source jsonl)")
    ap.add_argument("--source", choices=["jsonl", "db"], default="jsonl",
                    help="საიდან წავიკითხოთ snapshot-ები (default: jsonl)")
    ap.add_argument("-o", "--output", type=Path, help="write arrivals JSONL here (default: stdout summary only)")
    ap.add_argument("--to-db", action="store_true", help="შედეგი ჩაიწეროს arrival_event ცხრილში")
    args = ap.parse_args()

    if args.source == "db":
        import db
        conn = db.connect()
        arrivals = detect_from_lanes(lanes_from_arrivals(db.iter_db_arrivals(conn)))
    else:
        if not args.inputs:
            ap.error("--source jsonl მოითხოვს მინიმუმ ერთ შემავალ ფაილს")
        arrivals = detect(args.inputs)

    if args.to_db:
        import db
        conn = db.connect() if args.source == "jsonl" else conn
        n = db.write_arrival_events(conn, arrivals)
        print(f"Wrote {n} arrival_event rows -> Postgres", file=sys.stderr)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as fh:
            for ev in arrivals:
                fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        print(f"Wrote {len(arrivals)} arrivals -> {args.output}", file=sys.stderr)

    by_route: Dict[str, int] = defaultdict(int)
    late = on_time = 0
    for ev in arrivals:
        by_route[ev["route"]] += 1
        d = ev["delay_min"]
        if d is not None:
            if d < -2:
                late += 1
            else:
                on_time += 1
    print(f"\nTotal arrivals detected: {len(arrivals)}", file=sys.stderr)
    print(f"Distinct routes: {len(by_route)}", file=sys.stderr)
    print(f"Late (>2min behind schedule): {late}   On-time/early: {on_time}", file=sys.stderr)
    top = sorted(by_route.items(), key=lambda kv: -kv[1])[:10]
    print("Busiest routes:", ", ".join(f"{r}({n})" for r, n in top), file=sys.stderr)

    if not args.output:
        for ev in arrivals[:20]:
            print(json.dumps(ev, ensure_ascii=False))


if __name__ == "__main__":
    main()
