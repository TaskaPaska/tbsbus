"""კლიენტი Tbilisi Transport Company (TTC / AzRy)-ის API-სთვის.
endpoint-ები აღებულია სამაგალითო API wrapper-იდან (https://github.com/sunneydev/ttc-api)
"""
import os
from typing import Any, Dict, List, Optional, Tuple

import requests


class TTCClient:
    def __init__(self, api_key: str, base_url: str = "https://transit.ttc.com.ge/pis-gateway/api/v2",
                 locale: str = "ka", timeout: float = 15.0):
        self.base_url = base_url
        self.default_params = {"locale": locale}
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    @classmethod
    def from_env(cls, **kwargs) -> "TTCClient":
        """კლიენტი უნდა დაიბილდოს API_KEY ცვლადისგან"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError("API_KEY არაა დაკონფიგურირებული (დასამატებელია services/collector/.env-ში)")
        return cls(api_key=api_key, **kwargs)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        request_params = {**self.default_params, **(params or {})}
        response = self.session.get(url, params=request_params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # --- endpoints-ები ---------------------------------------------------------

    # ყველა გაჩერება
    def stops(self) -> List[Dict[str, Any]]:
        return self._get("/stops")

    # კონკრეტული გაჩერება ID-ს მიხედვით
    def stop(self, stop_id: str) -> Dict[str, Any]:
        return self._get(f"/stops/1:{stop_id}")

    # ყველა მარშრუტი
    def routes(self, modes: str = "BUS") -> List[Dict[str, Any]]:
        return self._get("/routes", {"modes": modes})

    # მარშრუტები, რომლებიც კონკრეტულ გაჩერებაზე გადიან
    def stop_routes(self, stop_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/stops/1:{stop_id}/routes")

    # როდის მოვა კონკრეტულ გაჩერებაზე ავტობუსი (TTC-ს API-ს მიხედვით).
    def arrival_times(self, stop_id: str, ignore_scheduled: bool = False) -> Any:
        # შენიშვნა: თვითონ სერვერის მხრიდან არასწორადაა დაწერილი "Schedulerd", ასე იღებს API.
        params = {"ignoreSchedulerdArrivalTimes": str(ignore_scheduled).lower()}
        return self._get(f"/stops/1:{stop_id}/arrival-times", params)

    # ავტობუსების მიმდინარე პოზიციები კონკრეტულ მარშრუტზე. forward-ი მარშრუტის მიმართულებას ნიშნავს.
    def positions(self, route_id: str, forward: bool = True) -> Any:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/positions", params)

    # მარშრუტის ფორმა/გეომეტრიული ფორმის მონაცემები.
    def bus_polyline(self, route_id: str, forward: bool = True) -> Any:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/polyline", params)

    # მარშრუტის გაჩერებები.
    def route_stops(self, route_id: str, forward: bool = False) -> List[Dict[str, Any]]:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/stops", params)

    # ორ წერტილს შორის მარშრუტის დაგეგმვა. მხოლოდ ფეხით და ავტობუსით მგზავრობაა გათვალისწინებული.
    def plan(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> Any:
        params = {
            "fromPlace": f"{from_coords[0]},{from_coords[1]}",
            "toPlace": f"{to_coords[0]},{to_coords[1]}",
            "departMode": "leaveNow",
            "modes": "WALK,BUS",
            "optimize": "quick",
        }
        return self._get("/plan", params)