"""Flask REST სერვისი — ცოცხალი მოსვლის პროგნოზებს აწვდის frontend-ს.

თხელი ფენაა: არ შეიცავს ML/feature ლოგიკას (ის predict.py-შია) და იყენებს collector-ის უკვე
არსებულ TTCClient-ს ცოცხალი მონაცემებისთვის (კოდის დუბლირების გარეშე). dev-ში collector-ის
საქაღალდე sys.path-ში ემატება; Docker-ში ორივე სერვისი ერთად დაიკოპირება (მოგვიანებით).

გაშვება:
    cd services/api && API_KEY=... python app.py
"""
import json
import os
import sys
from pathlib import Path

from flask import Flask, jsonify
import requests

from predict import PredictionService

# collector-ის TTCClient-ის ხელახლა გამოყენება (dev-ში path-ით; Docker-ში ერთად დაიკოპირება).
_COLLECTOR = Path(__file__).resolve().parents[1] / "collector"
sys.path.insert(0, str(_COLLECTOR))
from ttc_client import TTCClient  # noqa: E402

MODEL_PATH = Path(os.getenv("MODEL_PATH", Path(__file__).resolve().parents[1] / "ml" / "model.joblib"))
# ქალაქის ყველა გაჩერება (list_all_stops.py) — frontend-ის ძებნა/რუკა/"ჩემთან ახლოს"-ისთვის.
# predict.py-ს stop_id კატეგორიად აღიქვამს და unseen მნიშვნელობებს "missing"-ზე მიაქცევს, ასე რომ
# /predict მუშაობს ნებისმიერი ნამდვილი TTC stop_id-სთვის, არა მხოლოდ tracked ქვესიმრავლისთვის.
ALL_STOPS_FILE = Path(os.getenv("ALL_STOPS_FILE", _COLLECTOR / "all_stops.json"))
# fallback, სანამ list_all_stops.py არ გაშვებულა — tracked ქვესიმრავლე მაინც სჯობს ცარიელს.
TRACKED_STOPS_FILE = Path(os.getenv("TRACKED_STOPS_FILE", _COLLECTOR / "tracked_stops.json"))


def _load_stops():
    """გაჩერებების სია frontend-ისთვის (id, name, lat, lon, routes) — მთელი ქალაქი, თუ არსებობს."""
    stops_file = ALL_STOPS_FILE if ALL_STOPS_FILE.exists() else TRACKED_STOPS_FILE
    with open(stops_file, encoding="utf-8") as f:
        raw = json.load(f).get("stops", [])
    return [{"id": s["id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"],
             "routes": s.get("routes", [])} for s in raw]


app = Flask(__name__)
service = PredictionService(MODEL_PATH)
client = TTCClient.from_env()
STOPS = _load_stops()  # ერთხელ იტვირთება startup-ზე; მცირე და სტატიკურია.


@app.get("/health")
def health():
    return jsonify(status="ok", model=str(MODEL_PATH.name))


@app.get("/stops")
def stops():
    """დაფარული გაჩერებების სია — frontend-ის ძებნისა და რუკისთვის."""
    return jsonify(stops=STOPS)


@app.get("/predict/<stop_id>")
def predict(stop_id: str):
    """ცოცხალი პროგნოზი ერთი გაჩერებისთვის — მოდელი vs ოპერატორის baseline, თითო ავტობუსზე."""
    try:
        payload = client.arrival_times(stop_id)
    except requests.HTTPError as e:
        return jsonify(error="TTC API error", detail=str(e)), 502
    except requests.RequestException as e:
        return jsonify(error="TTC API unreachable", detail=str(e)), 504
    return jsonify(stop_id=stop_id, arrivals=service.predict_stop(stop_id, payload))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
