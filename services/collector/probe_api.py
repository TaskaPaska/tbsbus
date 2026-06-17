"""ერთჯერადი "დიაგნოსტიკა", რომ დავრწმუნდეთ, რომ API-თ ჯერ კიდევ მოგვაქვს მონაცემები სწორედ იმ ფორმატში, რასაც ველოდით.
ეს არის ე.წ. sanity check, რომ არ დავიწყოთ/გავაგრძელოთ მონაცემების შეგროვება, თუ API შეიცვალა.
"""
import json
from typing import Any

from ttc_client import TTCClient


def describe(label: str, data: Any) -> None:
    """პრინტავს მონაცემების ტიპს, ზომას და პირველ ელემენტს (თუ არის list ან dict)."""
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

    # თუ გვაქვს ავტობუსის გაჩერებები, ვამოწმებთ arrival_times და stop_routes-ის სტრუქტურას კონკრეტულ გაჩერებაზე.
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
