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

from detect_arrivals import read_lanes, iter_approaches, lanes_from_arrivals
from positions_features import load_positions_index, load_route_map, load_stop_coords, vehicle_features

# საქართველო მუდმივად UTC+4-ია (DST არ აქვს); საათი/დღე ლოკალურ დროში გვინდა feature-ებისთვის.
TBILISI_UTC_OFFSET_H = 4
# მოსვლამდე ამაზე შორს ჩანაწერებს ვტოვებთ — შორი პროგნოზი ხმაურია და სასწავლოდ ნაკლებად სასარგებლო.
MAX_LABEL_MIN = 60
# rt_min მთელ წუთებშია, poll კი 30წ-ში ერთხელაა — მეზობელ ჩანაწერებს შორის სხვაობა თითქმის ყოველთვის
# 0-ია (კვანტიზაციის ხმაური). ტრენდისთვის ~2წთ-იან ფანჯარაში შედარებას ვიყენებთ, რომ რეალური
# აჩქარება/შენელება/საცობი დავიჭიროთ და არა API-ის დამრგვალება.
TREND_WINDOW_S = 120


def build_from_lanes(lanes, positions_idx=None, stop_coords=None, route_map=None):
    """positions_idx/stop_coords არასავალდებულოა (Phase-1 zero-setup) — თუ ორივე არაა გადმოცემული,
    veh_* სვეტები ცარიელი (NaN) გამოვა და მოდელი მათზე უბრალოდ იმპუტაციით/NaN-ის მხარდაჭერით იმუშავებს.
    route_map (route_id -> shortName) არასავალდებულოა კიდევ უფრო — გარეშე candidate-ების
    route-ით ფილტრვა არ ხდება (იხ. positions_features.py-ის შენიშვნა).
    """
    rows = []
    for (stop_id, route, pattern), lane in lanes.items():
        stop_coord = stop_coords.get(stop_id) if stop_coords else None
        for approach, arrival_ts in iter_approaches(lane["readings"]):
            # ტრენდი ითვლება უკუთვლის სრულ მიმდევრობაზე, მიუხედავად იმისა, ბოლოს ჩანაწერი filter-ს
            # გაივლის თუ არა — თორემ ტრენდი "ხტება" გამოტოვებულ წერტილებზე.
            prev_ts, prev_rt = None, None
            history = []          # [(ts, rt_min), ...] მიმდინარე approach-ის ამ წამამდე
            last_change_ts = None  # ბოლო ჯერზე rt_min როდის შეიცვალა
            for ts, rt_min, sched_min in approach:
                dt_since_prev_s = None
                rt_delta_min = None
                if prev_ts is not None:
                    dt_since_prev_s = (ts - prev_ts).total_seconds()
                    rt_delta_min = rt_min - prev_rt
                    if rt_min != prev_rt:
                        last_change_ts = ts
                if last_change_ts is None:
                    last_change_ts = ts
                stall_s = (ts - last_change_ts).total_seconds()

                # ~2წთ-ის წინანდელი ყველაზე ახლო ჩანაწერი (windowed rate რეალურ აჩქარებას/საცობს
                # ასახავს, ცალკეულ 30წ-იან ნაბიჯებს შორის კვანტიზაციის ხმაურის მაგივრად).
                rt_rate = None
                ref = None
                for h_ts, h_rt in history:
                    if (ts - h_ts).total_seconds() >= TREND_WINDOW_S:
                        ref = (h_ts, h_rt)
                    else:
                        break
                if ref is not None:
                    ref_ts, ref_rt = ref
                    span_s = (ts - ref_ts).total_seconds()
                    if span_s > 0:
                        # >1 = countdown ეცემა რეალურ დროზე სწრაფად (ჩქარობს), <1 = ნელა/ჩერდება (საცობი).
                        rt_rate = (ref_rt - rt_min) / (span_s / 60.0)
                history.append((ts, rt_min))
                prev_ts, prev_rt = ts, rt_min

                label_min = (arrival_ts - ts).total_seconds() / 60.0
                if label_min < 0 or label_min > MAX_LABEL_MIN:
                    continue  # მოსვლის შემდგომი/ძალიან შორი ჩანაწერი
                local = ts + timedelta(hours=TBILISI_UTC_OFFSET_H)
                veh_dist_m = veh_pos_age_s = None
                veh_candidates = 0
                if positions_idx is not None:
                    veh_dist_m, veh_pos_age_s, veh_candidates = vehicle_features(
                        positions_idx, stop_coord, stop_id, ts, route, route_map)
                rows.append({
                    "stop_id": stop_id,
                    "route": route,
                    "pattern": pattern,
                    "ts": ts.isoformat(),       # დროის მიხედვით train/test გაყოფისთვის
                    "hour": local.hour,
                    "dow": local.weekday(),     # 0=ორშაბათი
                    "rt_min": rt_min,           # baseline 1: ოპერატორის პროგნოზი
                    "sched_min": sched_min,     # baseline 2: განრიგი
                    "dt_since_prev_s": dt_since_prev_s,
                    "rt_delta_min": rt_delta_min,
                    "rt_rate": rt_rate,
                    "stall_s": stall_s,
                    "veh_dist_m": veh_dist_m,
                    "veh_pos_age_s": veh_pos_age_s,
                    "veh_candidates": veh_candidates,
                    "label_min": round(label_min, 2),
                })
    rows.sort(key=lambda r: r["ts"])
    return rows


def build(paths, positions_idx=None, stop_coords=None, route_map=None):
    """JSONL-დან სასწავლო სტრიქონები (backward-compatible wrapper)."""
    return build_from_lanes(read_lanes(paths), positions_idx, stop_coords, route_map)


def main():
    ap = argparse.ArgumentParser(description="Build ML training rows from raw arrival-times snapshots.")
    ap.add_argument("inputs", nargs="*", type=Path, help="raw arrival-times .jsonl file(s) (--source jsonl)")
    ap.add_argument("--source", choices=["jsonl", "db"], default="jsonl",
                    help="საიდან წავიკითხოთ snapshot-ები (default: jsonl)")
    ap.add_argument("-o", "--output", type=Path, required=True, help="training CSV output path")
    ap.add_argument("--positions", nargs="*", type=Path, default=[],
                    help="raw/positions/*.jsonl — თუ გადმოცემულია, veh_dist_m/veh_pos_age_s/veh_candidates "
                         "დაემატება (მოითხოვს --stops-საც)")
    ap.add_argument("--stops", type=Path,
                    help="tracked_stops.json (ან all_stops.json) — გაჩერებების lat/lon --positions-join-სთვის")
    ap.add_argument("--route-map", type=Path,
                    help="route_map.json (fetch_route_map.py-დან) — route_id -> shortName, "
                         "positions candidate-ების route-ით გასაფილტრად (არასავალდებულო)")
    args = ap.parse_args()

    if bool(args.positions) != bool(args.stops):
        ap.error("--positions და --stops ერთად გამოიყენება (ორივე ან არცერთი)")
    positions_idx = load_positions_index(args.positions) if args.positions else None
    stop_coords = load_stop_coords(args.stops) if args.stops else None
    route_map = load_route_map(args.route_map) if args.route_map else None

    if args.source == "db":
        import db
        rows = build_from_lanes(lanes_from_arrivals(db.iter_db_arrivals(db.connect())),
                                 positions_idx, stop_coords, route_map)
    else:
        if not args.inputs:
            ap.error("--source jsonl მოითხოვს მინიმუმ ერთ შემავალ ფაილს")
        rows = build(args.inputs, positions_idx, stop_coords, route_map)
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
