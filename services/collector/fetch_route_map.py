"""route_id -> shortName მეპინგის გენერაცია (route_map.json).

positions.jsonl-ში ვხედავთ route_id-ს (მაგ. "R101593"), მაგრამ არა route-ის ნომერს (shortName,
მაგ. "388"), რომელსაც build_features.py იყენებს lane-ის გასაღებად. tracked_stops.json ამ
წყვილს არ ინახავს (მხოლოდ ორ ცალკე დალაგებულ სიას — route_ids და routes — თანმიმდევრობის
გარანტიის გარეშე). ეს სკრიპტი მსუბუქია: მხოლოდ ერთხელ /routes-ს ეხმაურება (არა route_stops-ს
ყველა route/მიმართულებაზე, როგორც select_stops.py), ასე რომ tracked_stops.json-ის თავიდან
გენერირება/არჩეული გაჩერებების შეცვლა არ სჭირდება.

გამოყენება:
    cd services/collector && python fetch_route_map.py
"""
import json

import config
from select_stops import bare_id
from ttc_client import TTCClient

ROUTE_MAP_FILE = config.COLLECTOR_DIR / "route_map.json"


def main() -> None:
    client = TTCClient.from_env()
    routes = client.routes(modes="BUS")
    route_map = {bare_id(r.get("id")): r.get("shortName") or r.get("name") for r in routes}
    ROUTE_MAP_FILE.write_text(json.dumps(route_map, ensure_ascii=False, indent=2))
    print(f"Wrote {len(route_map)} route_id -> shortName pairs -> {ROUTE_MAP_FILE}")


if __name__ == "__main__":
    main()
