"""One-shot live probe of the TTC API to confirm endpoint shapes before trusting them.

Hits each endpoint we depend on exactly once and prints the top-level structure and the
keys of the first element, so field names in the client/selector can be validated against
reality (CLAUDE.md: confirm endpoints live; do not assume).

    python probe_api.py
"""
import json
from typing import Any

from ttc_client import TTCClient


def describe(label: str, data: Any) -> None:
    print(f"\n=== {label} ===")
    if isinstance(data, list):
        print(f"list of {len(data)}")
        if data:
            first = data[0]
            print("first element keys:", list(first.keys()) if isinstance(first, dict) else type(first).__name__)
            print(json.dumps(first, ensure_ascii=False, indent=2)[:1200])
    elif isinstance(data, dict):
        print("dict keys:", list(data.keys()))
        print(json.dumps(data, ensure_ascii=False, indent=2)[:1200])
    else:
        print(type(data).__name__, repr(data)[:500])


def main() -> None:
    c = TTCClient.from_env()

    stops = c.stops()
    describe("stops()", stops)

    # Pick a sample stop and a sample bus route to probe dependent endpoints.
    sample_stop = next((s for s in stops if s.get("vehicleMode") == "BUS"), stops[0])
    sid = str(sample_stop.get("id", "")).split(":", 1)[-1]
    describe(f"arrival_times(stop={sid})", c.arrival_times(sid))
    describe(f"stop_routes(stop={sid})", c.stop_routes(sid))

    routes = c.routes(modes="BUS")
    describe("routes(BUS)", routes)
    if routes:
        rid = str(routes[0].get("id", "")).split(":", 1)[-1]
        describe(f"route_stops(route={rid})", c.route_stops(rid))
        describe(f"positions(route={rid})", c.positions(rid))


if __name__ == "__main__":
    main()
