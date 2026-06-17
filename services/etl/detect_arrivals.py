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

Reading = Tuple[datetime, int, Optional[int]]  # (timestamp, realtime_minutes, scheduled_minutes)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def read_lanes(paths: Iterable[Path]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """ვიღებთ ყველა დაუმუშავებელ ჩანაწერს და ვყრით lane-ებში (stop_id, shortName, patternSuffix) მიხედვით.

    lane არის კონკრეტული გაჩერება + კონკრეტული მარშრუტი + კონკრეტული მარშრუტის მიმართულება (patternSuffix).
    ანუ, x მარშრუტს y მიმართულებით z გაჩერებისთვის lane-ი იქნება (z, x, y). lane-ები ერთმანეთისგან დამოუკიდებელია.
    """
    lanes: Dict[Tuple[str, str, str], Dict[str, Any]] = defaultdict(
        lambda: {"headsign": "", "readings": []}
    )
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                stop_id = rec["stop_id"]
                ts = parse_ts(rec["ts"])
                for a in rec["payload"]:
                    if not a.get("realtime"):
                        continue # მხოლოდ რეალურ დროში მოსვლები გვაინტერესებს, არა მხოლოდ დაგეგმილი
                    key = (stop_id, a["shortName"], a.get("patternSuffix") or "")
                    lane = lanes[key]
                    lane["headsign"] = a.get("headsign", lane["headsign"])
                    lane["readings"].append(
                        (ts, a["realtimeArrivalMinutes"], a.get("scheduledArrivalMinutes"))
                    )
    return lanes


def segment_arrivals(readings: List[Reading]) -> List[Dict[str, Any]]:
    """თითოეული lane-ის უკუთვლების სერიას ვამოწმებთ და ვქმნით მოსვლის (arrival) ჩანაწერებს.
    """
    readings.sort(key=lambda r: r[0])
    arrivals: List[Dict[str, Any]] = []
    approach: List[Reading] = []

    def close(approach: List[Reading]) -> None:
        if not approach:
            return
        last_ts, last_min, last_sched = approach[-1]
        min_remaining = min(r[1] for r in approach)
        if min_remaining > ARRIVAL_MAX_REMAINING_MIN:
            return  # ავტობუსი ვერ მოვიდა 2 წუთში, არ ვქმნით arrival ჩანაწერს.
        arrival_ts = last_ts + timedelta(minutes=last_min)
        arrivals.append({
            "arrival_ts": arrival_ts.isoformat(),
            "delay_min": last_sched,
            "n_readings": len(approach),
            "min_remaining_min": min_remaining,
            "first_seen_min": approach[0][1],
            "first_seen_ts": approach[0][0].isoformat(),
        })

    prev: Optional[Reading] = None
    for r in readings:
        if prev is not None:
            ts, minutes, _ = r
            pts, pmin, _ = prev
            gap = (ts - pts).total_seconds()
            if gap > MAX_GAP_SECONDS or minutes > pmin + RESET_JUMP_MIN:
                close(approach)
                approach = []
        approach.append(r)
        prev = r
    close(approach)
    return arrivals


def detect(paths: List[Path]) -> List[Dict[str, Any]]:
    lanes = read_lanes(paths)
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect bus arrivals from raw arrival-times snapshots.")
    ap.add_argument("inputs", nargs="+", type=Path, help="raw arrival-times .jsonl file(s)")
    ap.add_argument("-o", "--output", type=Path, help="write arrivals JSONL here (default: stdout summary only)")
    args = ap.parse_args()

    arrivals = detect(args.inputs)

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
