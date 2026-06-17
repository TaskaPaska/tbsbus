"""ირჩევს რომელ გაჩერებებს უნდა დავაკვირდეთ.

ეშვება ერთჯერადად, თავიდან, სანამ მონაცემების შეგროვება დაიწყება. ამოირჩევა რომელი დაახლ. 30 გაჩერების შესახებ
უნდა შევაგროვოთ მონაცემები.
გაჩერება ამოირჩევა იმის მიხედვით, თუ რამდენად დაკავებული ("Busiest") არის იგი. რაც უფრო მეტი მარშრუტი/ავტობუსი გადის
გაჩერებაზე, მით უფრო მაღალია მისი პრიორიტეტი. ამოირჩევა მხოლოდ ავტობუსის გაჩერებები.
"""
import json
import time
from typing import Any, Dict, List

import config
from ttc_client import TTCClient


def bare_id(raw: Any) -> str:
    """გაჩერების id მოდის მოც. ფორმატში '1:123'. ეს ფუნქცია ამატებს სწორედ ამ '1:' პრეფიქსს."""
    s = str(raw)
    return s.split(":", 1)[1] if ":" in s else s


def build_stop_route_density(client: TTCClient):
    """აბრუნებს (stop_id -> route_ids-ები, რომლებიც მოც. გაჩერებაზე გადის, route_id -> მოკლე დასახელება)."""
    routes = client.routes(modes="BUS")
    print(f"Found {len(routes)} bus routes; listing stops per route...")

    stop_route_ids: Dict[str, set] = {}
    route_short: Dict[str, str] = {}
    for i, route in enumerate(routes, 1):
        route_id = bare_id(route.get("id"))
        short = route.get("shortName") or route.get("name") or route_id
        route_short[route_id] = short
        for forward in (True, False):
            try:
                stops = client.route_stops(route_id, forward=forward)
            except Exception as e:  # ერთმა არამართებულმა მარშრუტმა არ უნდა ჩაშალოს მთელი პროცესი, უბრალოდ გამოვტოვოთ
                print(f"  ! route {short} forward={forward}: {e}")
                continue
            for stop in stops or []:
                sid = bare_id(stop.get("id"))
                stop_route_ids.setdefault(sid, set()).add(route_id)
            time.sleep(config.INTER_REQUEST_DELAY)
        if i % 25 == 0:
            print(f"  ...{i}/{len(routes)} routes scanned")
    return stop_route_ids, route_short


def main() -> None:
    client = TTCClient.from_env()

    # მთლიანი გაჩერებების ჩამონათვალი, ჩვენთვის რელევანტურია მხოლოდ ავტობუსის გაჩერებები.
    all_stops = client.stops()
    by_id = {bare_id(s.get("id")): s for s in all_stops if s.get("vehicleMode") == "BUS"}
    print(f"{len(by_id)} BUS stops in catalogue.")

    stop_route_ids, route_short = build_stop_route_density(client)

    # ჩვენთვის ნაცნობი ავტობუსის გაჩერებების დალაგება მათი "დაკავებულობის" მიხედვით.
    ranked = sorted(
        ((sid, rids) for sid, rids in stop_route_ids.items() if sid in by_id),
        key=lambda kv: len(kv[1]),
        reverse=True,
    )
    selected = ranked[: config.TARGET_STOP_COUNT]

    tracked_stops: List[Dict[str, Any]] = []
    route_ids_union: set = set()
    for sid, rids in selected:
        s = by_id[sid]
        tracked_stops.append({
            "id": sid,
            "name": s.get("name"),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
            "route_count": len(rids),
            "routes": sorted(route_short.get(r, r) for r in rids),
        })
        route_ids_union |= rids

    out = {
        "stops": tracked_stops,
        "route_ids": sorted(route_ids_union),
        "routes": sorted(route_short.get(r, r) for r in route_ids_union),
        "target_stop_count": config.TARGET_STOP_COUNT,
    }
    config.TRACKED_STOPS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {len(tracked_stops)} stops, {len(route_ids_union)} routes -> {config.TRACKED_STOPS_FILE}")
    for st in tracked_stops[:10]:
        print(f"  {st['route_count']:2d} routes  {st['id']:>8}  {st['name']}")


if __name__ == "__main__":
    main()
