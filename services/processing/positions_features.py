"""ავტობუსების GPS პოზიციების join — feature engineering-ისთვის.

collector.py უკვე აგროვებს ავტობუსების ცოცხალ პოზიციებს (poll_positions -> raw/positions/*.jsonl),
მაგრამ build_features.py აქამდე მხოლოდ ერთ scalar-ს იყენებდა (rt_min) — ავტობუსის ნამდვილ
მდებარეობას საერთოდ არ ვხედავდით. აქ ვაბამთ positions-ს stop-ს: თითო position ჩანაწერს აქვს
`nextStopId` — თუ ის ჩვენს target stop_id-ს ემთხვევა, ეს ავტობუსი ზუსტად ამ გაჩერებისკენ მოდის და
შეგვიძლია დავთვალოთ real-world მანძილი (haversine) გაჩერებამდე.

დაკავებულ გაჩერებებზე (ბევრი მარშრუტი ერთსა და იმავე გაჩერებაზე) nextStopId მარტო საკმარისად არ
ავიწროებს კანდიდატებს — ერთდროულად 8-13 სხვადასხვა მარშრუტის ავტობუსმა შეიძლება ერთი და იგივე
გაჩერება დაასახელოს next stop-ად. ამიტომ, თუ route_map გადმოცემულია (route_id -> shortName,
fetch_route_map.py-დან), კანდიდატებს route-ითაც ვფილტრავთ. მიმართულება (`forward`) არ
გამოიყენება ფილტრში — patternSuffix-ის direction-digit-სა და `forward`-ს შორის მიმართება
დადასტურებული არაა, ამიტომ route-level დამთხვევა კმარა კანდიდატების უმეტესობის მოსაშორებლად და
შემდეგ უახლოეს დროში ვამთხვევთ.

გაზომვის შედეგი (2026-09-03, 8 დღე, 7.08M სტრიქონი) — ეს feature ჯერ *არ* მუშაობს ისე, როგორც
ჩაფიქრებული იყო, და ამიტომ სწავლების ნაგულისხმევ კონტრაქტში არ შედის (train.py-ის
EXPERIMENTAL_NUMERIC):

  * corr(veh_dist_m, label_min) = 0.016 — ანუ პრაქტიკულად ნული.
  * veh_dist_m-ის მედიანა ~165მ ყველა rt_min-bucket-ში ერთნაირია: მაშინაც, როცა ავტობუსამდე
    2 წუთია და მაშინაც, როცა 31.
  * აქედან გამომდინარე ნაგულისხმევი სიჩქარე dist/label = 0.93 კმ/სთ (მედიანა) — ფიზიკურად აბსურდი.

მიზეზი სტრუქტურულია: `nextStopId == stop_id` მხოლოდ იმ ავტობუსს ამთხვევს, რომლის *მომდევნო*
გაჩერებაა ჩვენი გაჩერება — ანუ ყოველთვის ერთი გაჩერების მანძილზე მყოფს (~165მ, გაჩერებებს შორის
საშუალო მანძილი). ის ავტობუსი, რომელიც 12 წუთში მოვა, სხვა გაჩერებაზეა "მიმართული", ამიტომ ამ
ინდექსში საერთოდ არ ხვდება. შედეგად veh_dist_m ≈ ამ გაჩერების გაჩერებათაშორისი დაშორება — თითქმის
მუდმივი per-stop მნიშვნელობა, რომელსაც stop_id კატეგორია ისედაც შეიცავს.

რომ ეს feature მართლა გამოდგეს, საჭიროა კონკრეტული ავტობუსის ტრაექტორიის თვალყურის დევნება
(vehicleId-ით) მარშრუტის გეომეტრიაზე და მანძილის *მარშრუტის გასწვრივ* დათვლა, არა სწორხაზოვნად —
ეს ცალკე სამუშაოა, არა ამ მოდულის შესწორება.
"""
import bisect
import json
from collections import defaultdict
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

EARTH_R_M = 6_371_000.0
# positions ჩვეულებრივ ~60წ-ში ერთხელ იკრიბება (POSITIONS_POLL_INTERVAL_SECONDS) — ამაზე
# ძველი დამთხვევა აღარაა სანდო "ახლანდელ" პოზიციად.
MAX_POS_AGE_S = 90


def _bare_id(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return raw.split(":", 1)[1] if ":" in raw else raw


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_M * asin(sqrt(a))


def load_stop_coords(path: Path) -> Dict[str, Tuple[float, float]]:
    """tracked_stops.json (ან all_stops.json) -> {stop_id: (lat, lon)}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for s in data.get("stops", []):
        if s.get("lat") is not None and s.get("lon") is not None:
            out[str(s["id"])] = (s["lat"], s["lon"])
    return out


# stop_id -> ([epoch_seconds, ...] დალაგებული, [(epoch_seconds, lat, lon), ...] იგივე რიგით)
PositionsIndex = Dict[str, Tuple[list, list]]


def load_route_map(path: Path) -> Dict[str, str]:
    """fetch_route_map.py-ის გამოსავალი -> {route_id: shortName}."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_positions_index(paths: Iterable[Path]) -> PositionsIndex:
    raw = defaultdict(list)
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                epoch = datetime.fromisoformat(rec["ts"]).timestamp()
                route_id = rec.get("route_id")  # ერთი poll = ერთი route_id ყველა payload-ვექტორისთვის
                for v in rec.get("payload", []):
                    sid = _bare_id(v.get("nextStopId"))
                    lat, lon = v.get("lat"), v.get("lon")
                    if sid is None or lat is None or lon is None:
                        continue
                    raw[sid].append((epoch, lat, lon, route_id))
    idx: PositionsIndex = {}
    for sid, entries in raw.items():
        entries.sort(key=lambda e: e[0])
        idx[sid] = ([e[0] for e in entries], entries)
    return idx


def vehicle_features(idx: PositionsIndex, stop_coord: Optional[Tuple[float, float]],
                      stop_id: str, ts: datetime, route_short: Optional[str] = None,
                      route_map: Optional[Dict[str, str]] = None
                      ) -> Tuple[Optional[float], Optional[float], int]:
    """(veh_dist_m, veh_pos_age_s, veh_candidates) მოცემულ stop_id-სთვის, დროის მომენტში ts.

    veh_candidates = რამდენი position-ჩანაწერი (route-ფილტრამდე) მოხვდა ±MAX_POS_AGE_S ფანჯარაში —
    ეს ამბივალენტურობის ინდიკატორია: რაც მეტია, მით ნაკლებად სანდოა route_map-ის გარეშე მატჩი.
    """
    hit = idx.get(stop_id)
    if not hit or stop_coord is None:
        return None, None, 0
    times, entries = hit
    epoch = ts.timestamp()
    lo = bisect.bisect_left(times, epoch - MAX_POS_AGE_S)
    hi = bisect.bisect_right(times, epoch + MAX_POS_AGE_S)
    candidates = entries[lo:hi]
    n_candidates = len(candidates)
    if n_candidates == 0:
        return None, None, 0

    pool = candidates
    if route_short and route_map:
        filtered = [e for e in candidates if route_map.get(e[3]) == route_short]
        if filtered:  # თუ ვერაფერი დაემთხვა (route_map არასრულია), მთელ pool-ს ვტოვებთ fallback-ად
            pool = filtered

    best = min(pool, key=lambda e: abs(e[0] - epoch))
    age = abs(best[0] - epoch)
    if age > MAX_POS_AGE_S:
        return None, None, n_candidates

    lat, lon = stop_coord
    dist_m = haversine_m(lat, lon, best[1], best[2])
    return round(dist_m, 1), round(age, 1), n_candidates
