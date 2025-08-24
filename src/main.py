import os
import requests
from dotenv import load_dotenv
import requests
from typing import Any, Dict, List, Optional, Tuple
load_dotenv()

API_KEY = os.getenv("API_KEY")


class TTCClient:
    def __init__(self):
        self.base_url = "https://transit.ttc.com.ge/pis-gateway/api/v2"
        self.headers = {"X-Api-Key": API_KEY}
        self.default_params = {"locale": "ka"}
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        url = f"{self.base_url}{endpoint}"

        if params:
            request_params = {**self.default_params, **params}
        else:
            request_params = {**self.default_params}
        try:
            response = self.session.get(url, params=request_params)
        except requests.exceptions.HTTPError as e:
            raise Exception(f"Request failed with status code {e.response.status_code}: {e.response.text}")

        response.raise_for_status()
        return response.json()

    def stops(self) -> List[Dict[str, Any]]:
        return self._get("/stops")

    def stop(self, stop_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/stops/1:{stop_id}")

    def routes(self) -> List[Dict[str, Any]]:
        return self._get("/routes", {"modes": "BUS"})

    def plan(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> List[Dict[str, Any]]:
        params = {
            **self.default_params,
            "fromPlace": f"{from_coords[0]},{from_coords[1]}",
            "toPlace": f"{to_coords[0]},{to_coords[1]}",
            "departMode": "leaveNow",
            "modes": "WALK,BUS",
            "optimize": "quick"
        }
        return self._get("/plan", params)

    def bus_polyline(self, bus_id: str, forward: bool = True) -> List[Dict[str, Any]]:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{bus_id}/polyline", params)

    def locations(self, bus_id: str, forward: bool = True) -> List[Dict[str, Any]]:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{bus_id}/positions", params)

    def stop_routes(self, stop_id: str) -> List[Dict[str, Any]]:
        params = self.default_params
        return self._get(f"/stops/1:{stop_id}/routes", params)

    def bus_routes(self, bus_id: str, forward: Optional[bool] = None) -> List[Dict[str, Any]]:
        params = {
            **self.default_params,
            "forward": str(forward if forward is not None else False).lower()
        }
        return self._get(f"/routes/1:{bus_id}/stops", params)

    def arrival_times(self, stop_id: str, ignore_scheduled_arrival_times: bool = False) -> List[Dict[str, Any]]:
        params = {
            **self.default_params,
            "ignoreSchedulerdArrivalTimes": str(ignore_scheduled_arrival_times).lower()
        }
        return self._get(f"/stops/1:{stop_id}/arrival-times", params)


if __name__ == "__main__":
    # Just exploring the data
    client = TTCClient()
    stops = client.stops()
    st = set()
    for stop in stops:
        st.add(stop.get('vehicleMode'))
        if stop.get('vehicleMode') != "BUS":
            print(stop)
    print(st)
