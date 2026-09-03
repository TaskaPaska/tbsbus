# services/ml — მოდელის სწავლება და გადამზადება

`build_features.py`-ის `training.csv`-ზე ვსწავლობთ მოსვლამდე დარჩენილ წუთებს და ვინახავთ
`model.joblib`-ს, რომელსაც `services/api` იყენებს.

## ვერსიები — მნიშვნელოვანი

მოდელი უნდა დაიტრენოს *იმავე* ვერსიებით, რაც API-ს ჰოსტზეა (`requirements.txt`:
`scikit-learn==1.5.2`, `pandas==2.2.3`). უფრო ახალი sklearn-ით დამარილებული `model.joblib`
atlas-ზე **არ ჩაიტვირთება** (`AttributeError: Can't get attribute '_RemainderColsList'`).

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
```

## ხელით სწავლება

```bash
./.venv/bin/python train.py ../../data/processed/training.csv --model-out model.joblib
```

ბეჭდავს ორ baseline-ს (ოპერატორის `rt_min`, განრიგი), სამ მოდელს და MAE-ს `rt_min`-ის
დიაპაზონების მიხედვით. held-out დღე ნაგულისხმევად მონაცემების ბოლო დღეა (`--test-day`-ით იცვლება).

**feature-კონტრაქტი** (`SERVING_NUMERIC`) განზრახ ემთხვევა იმას, რისი გამოთვლაც `predict.py`-ს
ცოცხლად შეუძლია. `build_features.py` მეტ სვეტსაც აწარმოებს (ტრენდი, GPS-მანძილი) — ისინი
`--with-experimental`-ითაა ხელმისაწვდომი, მაგრამ საწარმოოში შედეგს *აუარესებს*, რადგან
`/predict`-ს ცოცხლად არ აქვს (გაზომვა: 1.999 -> 2.029 წთ MAE). იხ. `train.py`-ის კომენტარები.

## ავტომატური გადამზადება (atlas)

`retrain.py` აკეთებს სრულ ციკლს: ბოლო N სრული დღის feature-ების აგება -> სწავლება ->
შედარება -> გაშვება.

```bash
./.venv/bin/python retrain.py --days 8          # სრული ციკლი
./.venv/bin/python retrain.py --dry-run         # ითვლის, მოდელს არ ცვლის
```

- **დაცვა:** ახალი მოდელი ცოცხლდება მხოლოდ თუ იმავე held-out დღეზე *ორივეს* ჯობნის —
  ოპერატორის baseline-სა და ამჟამად გაშვებულ მოდელს. სხვა შემთხვევაში ძველი რჩება.
- **ატომური ჩანაცვლება:** `os.replace`, ძველი ვერსია `model.joblib.prev`-ად რჩება.
- **გადატვირთვა:** `SIGHUP` gunicorn-ის master-ს (root არ სჭირდება).
- **ისტორია:** `data/retrain-history.jsonl` — თითო გაშვების MAE-ები და გადაწყვეტილება.
- **მეხსიერება:** feature-ები დღეობით ითვლება; პიკი ~2.5GB (8GB-იან atlas-ზე უსაფრთხოა).
  unit-ს `MemoryMax=4G` აქვს, რომ გაუთვალისწინებელმა ზრდამ collector არ დააგდოს.

განრიგი — `ttc-retrain.timer` (კვირაში ერთხელ, კვირას 03:00 UTC):

```bash
sudo cp ttc-retrain.service ttc-retrain.timer /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now ttc-retrain.timer
systemctl list-timers ttc-retrain.timer
journalctl -u ttc-retrain -n 50
```

## რატომ განრიგით

2026-09-03-ის გაზომვით ყველაზე დიდი მოგება მოდელის გაუმჯობესება კი არ იყო, არამედ **სიახლე**:
ივნისში დატრენილი, საწარმოოში მყოფი მოდელი 2.287 წთ MAE-ს იძლეოდა, იმავე კოდით ახალ
მონაცემებზე გადამზადებული — 1.999-ს (ოპერატორის baseline 3.860). ეს დრეიფი ისევ დაგროვდება.
