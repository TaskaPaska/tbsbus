# API სერვისი

თხელი Flask REST სერვისი, რომელიც ცოცხალ TTC მონაცემებზე ატარებს ნატრენ ML მოდელს და
აბრუნებს კორექტირებულ მოსვლის პროგნოზს გაჩერებისთვის (მოდელი vs ოპერატორის baseline).

## არქიტექტურა
- `predict.py` — feature-ების აგება + მოდელის გამოძახება (Flask-ისგან დამოუკიდებლად ტესტირებადი).
  feature კონტრაქტი ზუსტად იმეორებს `services/processing/build_features.py`-ს (train/serve skew-ის გარეშე).
- `app.py` — HTTP ფენა; იყენებს `services/collector`-ის `TTCClient`-ს ცოცხალი მონაცემებისთვის.

## endpoints
- `GET /health` — სტატუსი + ჩატვირთული მოდელის ფაილი.
- `GET /stops` — გაჩერებების სია (id, name, lat, lon, routes) frontend-ის ძებნა/რუკა/"ჩემთან
  ახლოს"-ისთვის. კითხულობს `services/collector/all_stops.json`-ს (ქალაქის ყველა BUS გაჩერება,
  `list_all_stops.py`-ით გენერირებული); თუ ის არ არსებობს, უკან ვარდება `tracked_stops.json`-ზე.
- `GET /predict/<stop_id>` — per-ავტობუს პროგნოზი ერთი გაჩერებისთვის:
  `predicted_min` (მოდელი), `operator_min` და `scheduled_min` (baseline-ები), `route`, `headsign`.
  მუშაობს ნებისმიერი ნამდვილი TTC stop_id-სთვის, არა მხოლოდ tracked ქვესიმრავლისთვის — მოდელს
  stop_id კატეგორიული feature-ია და unseen მნიშვნელობებს "missing"-ზე მიაქცევს.

## გაშვება (dev)
```bash
cd services/api
../../.venv/bin/python -m virtualenv .venv      # python3 -m venv ამ მანქანაზე არ მუშაობს
.venv/bin/pip install -r requirements.txt
API_KEY=... .venv/bin/python app.py             # default port 5000
```
მოდელის გზა: `MODEL_PATH` (default `services/ml/model.joblib`). `API_KEY` იკითხება გარემოდან/`.env`-დან.

## მაგალითი
```bash
curl localhost:5000/health
curl localhost:5000/predict/<stop_id>
```
