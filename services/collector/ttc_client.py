"""Thin client for the Tbilisi Transport Company (TTC / AzRy) API.

This is the backend behind the official Tbilisi Transport app. Endpoint shapes were
derived from the reference wrapper (https://github.com/sunneydev/ttc-api) and must be
confirmed against the live API before being trusted.
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
        """Build a client from the API_KEY environment variable (loads .env if present)."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        api_key = os.getenv("API_KEY")
        if not api_key:
            raise RuntimeError("API_KEY is not set (put it in services/collector/.env)")
        return cls(api_key=api_key, **kwargs)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        request_params = {**self.default_params, **(params or {})}
        response = self.session.get(url, params=request_params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # --- endpoints ---------------------------------------------------------

    def stops(self) -> List[Dict[str, Any]]:
        return self._get("/stops")

    def stop(self, stop_id: str) -> Dict[str, Any]:
        return self._get(f"/stops/1:{stop_id}")

    def routes(self, modes: str = "BUS") -> List[Dict[str, Any]]:
        return self._get("/routes", {"modes": modes})

    def stop_routes(self, stop_id: str) -> List[Dict[str, Any]]:
        return self._get(f"/stops/1:{stop_id}/routes")

    def arrival_times(self, stop_id: str, ignore_scheduled: bool = False) -> Any:
        # NOTE: the query key is misspelled server-side ("Schedulerd"); kept as-is to match the API.
        params = {"ignoreSchedulerdArrivalTimes": str(ignore_scheduled).lower()}
        return self._get(f"/stops/1:{stop_id}/arrival-times", params)

    def positions(self, route_id: str, forward: bool = True) -> Any:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/positions", params)

    def bus_polyline(self, route_id: str, forward: bool = True) -> Any:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/polyline", params)

    def route_stops(self, route_id: str, forward: bool = False) -> List[Dict[str, Any]]:
        params = {"forward": str(forward).lower()}
        return self._get(f"/routes/1:{route_id}/stops", params)

    def plan(self, from_coords: Tuple[float, float], to_coords: Tuple[float, float]) -> Any:
        params = {
            "fromPlace": f"{from_coords[0]},{from_coords[1]}",
            "toPlace": f"{to_coords[0]},{to_coords[1]}",
            "departMode": "leaveNow",
            "modes": "WALK,BUS",
            "optimize": "quick",
        }
        return self._get("/plan", params)