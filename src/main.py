import os
import requests
from dotenv import load_dotenv
import requests
from typing import Any, Dict, List, Optional
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
        response = self.session.get(url, params=request_params)
        response.raise_for_status()
        return response.json()

    def stops(self) -> List[Dict[str, Any]]:
        return self._get("/stops")

    def stop(self, stop_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/stops/1:{stop_id}")

    def routes(self) -> List[Dict[str, Any]]:
        return self._get("/routes", {"modes": "BUS"})


if __name__ == "__main__":
    # Just exploring the data
    client = TTCClient()
    stops = client.stops()
    st = set()
    for stop in stops:
        st.add(stop.get('vehicleMode'))
    print(st)
