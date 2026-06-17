"""სასწავლო მონაცემების მომზადება — ფაზა 2 (feature engineering).

დაუმუშავებელ snapshot-ებს აქცევს ML-ის სასწავლო სტრიქონებად. იყენებს იმავე lane/approach
ლოგიკას, რასაც detect_arrivals.py — თითო მიახლოებისთვის ვიცით ნამდვილი მოსვლის დრო (arrival_ts),
ამიტომ ამ მიახლოების თითოეული ჩანაწერი ხდება ერთი სასწავლო სტრიქონი:

    features = (realtimeArrivalMinutes, scheduledArrivalMinutes, საათი, კვირის დღე, მარშრუტი, გაჩერება)
    label    = ნამდვილი დარჩენილი წუთები მოსვლამდე = arrival_ts - reading_ts

ასევე ვინახავთ ორ baseline-ს პირდაპირ სვეტებად: `rt_min` (ოპერატორის საკუთარი პროგნოზი) და
`sched_min` (განრიგისეული). მოდელმა MAE-ში ორივეს უნდა აჯობოს (სამიზნე < 3 წთ).

გამოყენება:
    python build_features.py data/raw/arrival-times/*.jsonl -o data/processed/training.csv
"""
import argparse
import csv
import sys
from datetime import timedelta
from pathlib import Path

from detect_arrivals import read_lanes, iter_approaches

# საქართველო მუდმივად UTC+4-ია (DST არ აქვს); საათი/დღე ლოკალურ დროში გვინდა feature-ებისთვის.
TBILISI_UTC_OFFSET_H = 4
# მოსვლამდე ამაზე შორს ჩანაწერებს ვტოვებთ — შორი პროგნოზი ხმაურია და სასწავლოდ ნაკლებად სასარგებლო.
MAX_LABEL_MIN = 60


def build(paths):
    lanes = read_lanes(paths)
    rows = []
    for (stop_id, route, pattern), lane in lanes.items():
        for approach, arrival_ts in iter_approaches(lane["readings"]):
            for ts, rt_min, sched_min in approach:
                label_min = (arrival_ts - ts).total_seconds() / 60.0
                if label_min < 0 or label_min > MAX_LABEL_MIN:
                    continue  # მოსვლის შემდგომი/ძალიან შორი ჩანაწერი
                local = ts + timedelta(hours=TBILISI_UTC_OFFSET_H)
                rows.append({
                    "stop_id": stop_id,
                    "route": route,
                    "pattern": pattern,
                    "ts": ts.isoformat(),       # დროის მიხედვით train/test გაყოფისთვის
                    "hour": local.hour,
                    "dow": local.weekday(),     # 0=ორშაბათი
                    "rt_min": rt_min,           # baseline 1: ოპერატორის პროგნოზი
                    "sched_min": sched_min,     # baseline 2: განრიგი
                    "label_min": round(label_min, 2),
                })
    rows.sort(key=lambda r: r["ts"])
    return rows


def main():
    ap = argparse.ArgumentParser(description="Build ML training rows from raw arrival-times snapshots.")
    ap.add_argument("inputs", nargs="+", type=Path, help="raw arrival-times .jsonl file(s)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="training CSV output path")
    args = ap.parse_args()

    rows = build(args.inputs)
    if not rows:
        sys.exit("No training rows produced.")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # მოკლე შეჯამება + baseline MAE-ები, რომ ბენჩმარკი მაშინვე გვქონდეს.
    n = len(rows)
    mae_rt = sum(abs(r["rt_min"] - r["label_min"]) for r in rows) / n
    sched = [r for r in rows if r["sched_min"] is not None]
    mae_sched = sum(abs(r["sched_min"] - r["label_min"]) for r in sched) / len(sched) if sched else None
    print(f"Wrote {n} training rows -> {args.output}", file=sys.stderr)
    print(f"Baseline MAE (operator realtime): {mae_rt:.2f} min", file=sys.stderr)
    if mae_sched is not None:
        print(f"Baseline MAE (schedule):          {mae_sched:.2f} min", file=sys.stderr)


if __name__ == "__main__":
    main()
