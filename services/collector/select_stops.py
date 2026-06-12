"""Auto-select the ~N busiest bus stops to track, by route density.

"Busiest" = served by the most distinct bus routes. We build the stop->routes mapping
by listing every BUS route and its stops (both directions), then rank stops by how many
routes pass through them. Output (tracked_stops.json) drives the collector: the selected
stops are polled for arrival-times, and the routes serving them are polled for positions.

Run once (re-run to refresh the selection):
    python select_stops.py
"""
import json
import time
from typing import Any, Dict, List

import config
from ttc_client import TTCClient


def bare_id(raw: Any) -> str:
    """Stop/route ids come back as e.g. '1:123'; the path builders re-add the '1:' prefix."""
    s = str(raw)
    return s.split(":", 1)[1] if ":" in s else s


def build_stop_route_density(client: TTCClient):
    """Return (stop_id -> set of route_ids serving it, route_id -> short name)."""
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
            except Exception as e:  # one bad route shouldn't abort the whole scan
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

    # Full stop catalogue, for names/coords. Keep only buses.
    all_stops = client.stops()
    by_id = {bare_id(s.get("id")): s for s in all_stops if s.get("vehicleMode") == "BUS"}
    print(f"{len(by_id)} BUS stops in catalogue.")

    stop_route_ids, route_short = build_stop_route_density(client)

    # Rank known bus stops by route density.
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
