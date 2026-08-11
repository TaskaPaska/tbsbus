"""ქალაქის ყველა ავტობუსის გაჩერების ჩამონათვალი -> all_stops.json.

განსხვავებით select_stops.py-სგან (რომელიც ირჩევს ~30 ყველაზე დაკავებულ გაჩერებას
ტრენინგისთვის), აქ საჭირო არაა route-density scan — `stops()` ერთი გამოძახებით
აბრუნებს მთელი ქალაქის სიას. ეს ფაილი frontend-ის "ჩემთან ახლოს" ძებნას ჭირდება
(nearest-stop lookup მთელ ქალაქზე), არა მხოლოდ tracked_stops.json-ის ქვესიმრავლეს.

გაშვება ერთჯერადია, სასურველია პერიოდულად თავიდან (გაჩერებები იშვიათად იცვლება).
"""
import json
from typing import Any, Dict

import config
from ttc_client import TTCClient


def bare_id(raw: Any) -> str:
    """გაჩერების id მოდის '1:123' ფორმატში — ვშლით '1:' პრეფიქსს."""
    s = str(raw)
    return s.split(":", 1)[1] if ":" in s else s


def main() -> None:
    client = TTCClient.from_env()

    all_stops = client.stops()
    bus_stops: list[Dict[str, Any]] = [
        {
            "id": bare_id(s.get("id")),
            "name": s.get("name"),
            "lat": s.get("lat"),
            "lon": s.get("lon"),
        }
        for s in all_stops
        if s.get("vehicleMode") == "BUS"
    ]

    out = {"stops": bus_stops}
    config.ALL_STOPS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {len(bus_stops)} BUS stops -> {config.ALL_STOPS_FILE}")


if __name__ == "__main__":
    main()
