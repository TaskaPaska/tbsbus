"""Arrival detection — Phase 2 ETL.

Turns the raw arrival-times snapshot stream into discrete *arrival events*: the moment a
specific bus actually reached a stop. This is the research core — every downstream metric
(headways, frequency, schedule adherence) is derived from these events.

How it works
------------
The collector polls every stop ~every 30s. Each snapshot lists the upcoming buses with a
live countdown ``realtimeArrivalMinutes``. A single bus shows up across many consecutive
snapshots with a *monotonically decreasing* countdown:

    09:00  route 305  pat 0:01  rt=4
    09:01  route 305  pat 0:01  rt=3
    09:02  route 305  pat 0:01  rt=1
    09:03  route 305  pat 0:01  rt=0
    09:04  (gone)                        <- the bus arrived around 09:03-09:04

We group readings by a "lane" = (stop_id, shortName, patternSuffix), order them by time, and
segment them into individual vehicle approaches. A segment ends — and is recorded as an
arrival — when the countdown reaches ~0 and then disappears, or when it jumps back UP
(the next vehicle of the same route/direction has appeared). The arrival timestamp is
extrapolated: last_seen_ts + last_remaining_minutes.

Only ``realtime`` readings are used: a scheduled-only entry is a timetable guess, not a
tracked vehicle, so it can't anchor an arrival time.

Usage
-----
    python detect_arrivals.py data/raw/arrival-times/2026-06-13.jsonl
    python detect_arrivals.py data/raw/arrival-times/*.jsonl -o data/processed/arrivals.jsonl
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --- tuning knobs ----------------------------------------------------------------------
# A countdown that jumps UP by more than this (minutes) means a new vehicle, not the one
# we were tracking — close the current approach and start a fresh one.
RESET_JUMP_MIN = 3
# A time gap larger than this (seconds) between two readings of the same lane breaks the
# approach: we lost sight of the bus, so we don't stitch across the hole.
MAX_GAP_SECONDS = 180
# An approach only counts as a real arrival if the countdown got at least this low. A bus
# we only ever saw at 15+ min away and then lost is not a confirmed arrival.
ARRIVAL_MAX_REMAINING_MIN = 2

Reading = Tuple[datetime, int, Optional[int]]  # (timestamp, realtime_minutes, scheduled_minutes)


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def read_lanes(paths: Iterable[Path]) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """Load every raw record and bucket realtime readings into lanes.

    Returns: lane_key -> {"headsign": str, "readings": List[Reading]} where lane_key is
    (stop_id, shortName, patternSuffix). Readings are appended in file order (chronological).
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
                        continue  # scheduled-only guess — can't anchor an arrival
                    key = (stop_id, a["shortName"], a.get("patternSuffix") or "")
                    lane = lanes[key]
                    lane["headsign"] = a.get("headsign", lane["headsign"])
                    lane["readings"].append(
                        (ts, a["realtimeArrivalMinutes"], a.get("scheduledArrivalMinutes"))
                    )
    return lanes


def segment_arrivals(readings: List[Reading]) -> List[Dict[str, Any]]:
    """Split one lane's time-ordered readings into individual arrivals.

    An approach is a run of non-increasing countdowns. It closes (and may emit an arrival)
    when the countdown jumps up past RESET_JUMP_MIN, when a gap exceeds MAX_GAP_SECONDS, or
    at end-of-stream.
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
            return  # never got close enough to call it an arrival
        # Extrapolate the final countdown to zero for the arrival instant.
        arrival_ts = last_ts + timedelta(minutes=last_min)
        arrivals.append({
            "arrival_ts": arrival_ts.isoformat(),
            "delay_min": last_sched,          # scheduled minutes at last sighting: <0 = late
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

    # Summary to stderr so stdout can be piped cleanly when -o is omitted.
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
