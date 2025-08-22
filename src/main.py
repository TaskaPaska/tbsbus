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

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"

        if params:
            request_params = {**self.default_params, **params}
        else:
            request_params = {**self.default_params}
        response = self.session.get(url, params=request_params)
        response.raise_for_status()
        return response.json()

