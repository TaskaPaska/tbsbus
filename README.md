# რეალურ დროში ავტობუსის მოსვლის პროგნოზირების სისტემა

რეალურ დროში ავტობუსის მოძრაობის პროგნოზირების სისტემა ისტორიულ მონაცემებზე
დაფუძნებული დისტრიბუციული Big Data და მანქანური სწავლების ტექნოლოგიებით.

საბაკალავრო ნაშრომი — კავკასიის უნივერსიტეტი. სისტემა იღებს ცოცხალ მონაცემებს
თბილისის სატრანსპორტო კომპანიის (TTC / AZRY) საჯარო API-დან, ამუშავებს მათ მცირე
დისტრიბუციულ pipeline-ში, წვრთნის ML მოდელს ავტობუსის მოსვლის დროის
პროგნოზირებისთვის და აწვდის პროგნოზებს ვებ-აპლიკაციით.

---

## მიმოხილვა

API არ აბრუნებს ფაქტობრივ მოსვლის დროს — ის მხოლოდ დარჩენილ წუთებს გასცემს. ამიტომ
სისტემის ბირთვი არის **მოსვლის რეკონსტრუქცია**: გაჩერებაზე თითო (მარშრუტი,
მიმართულება) წყვილისთვის ETA-ს კლებადი სერია ფიქსირდება და მისი 0-მდე მიახლოების
მომენტი ითვლება ფაქტობრივ მოსვლად. ამ ლეიბლებზე იწვრთნება მოდელი, რომელიც აჯობებს
ოპერატორის საკუთარ პროგნოზსაც და განრიგსაც.

დეტალური დასაბუთება თითო ინჟინრულ გადაწყვეტილებაზე იხ.
[`docs/decisions.md`](docs/decisions.md).

---

## არქიტექტურა

```
TTC / AZRY API
     │  (poller, ზრდილობიანი — 30/60 წმ)
     ▼
collector ──► JSONL (durable raw log, data/raw/)
     │
     └──────► Kafka topic (ttc.arrivals / ttc.positions)   ← Apache Kafka, single broker, KRaft
                   │
                   ▼
              ingest consumer ──► PostgreSQL 16 + PostGIS   ← queryable საცავი
                                       │
                                       ▼
                              Apache Spark (standalone cluster)
                              მოსვლის დაფიქსირება + feature engineering
                                       │
                                       ▼
                              ML წვრთნა (scikit-learn) ──► model.joblib
                                       │
                                       ▼
                              Flask REST API  ──►  Angular ვებ-ინტერფეისი
```

მთელი სტეკი კონტეინერიზებულია Docker-ით; დისტრიბუციული გაშვება ხდება **k3s**
კლასტერზე ოთხ კვანძზე (იხ. [„დისტრიბუციული გაშვება“](#დისტრიბუციული-გაშვება-k3s)).

---

## ტექნოლოგიური სტეკი

| ფენა | ტექნოლოგია | დანიშნულება |
|------|------------|-------------|
| ინგესტირება | Apache Kafka (single broker, KRaft) | მონაცემთა ნაკადის ბროკერი |
| საცავი | PostgreSQL 16 + PostGIS | ტიპიზებული, geo-მოთხოვნადი საცავი |
| დამუშავება | Apache Spark (standalone) | დისტრიბუციული feature engineering |
| ML | scikit-learn | Linear Regression, Random Forest, HistGradientBoosting |
| API | Flask + gunicorn | REST პროგნოზის სერვისი |
| Frontend | Angular + TypeScript | ვებ-ინტერფეისი რუკით |
| ორკესტრაცია | Docker Compose (dev), k3s (კლასტერი) | კონტეინერების მართვა |

---

## რეპოზიტორიის სტრუქტურა

```
services/
  collector/    # TTC API-ს poller → JSONL (+ Kafka)
  ingest/       # Kafka → PostgreSQL consumer
  processing/   # ETL, მოსვლის დაფიქსირება, feature engineering (Python + Spark)
  ml/           # მოდელის წვრთნა და შეფასება
  api/          # Flask REST API
  frontend/     # Angular აპლიკაცია
data/raw/       # JSONL snapshot-ები (gitignored)
k8s/            # k3s მანიფესტები (4-კვანძიანი კლასტერი)
docs/           # decisions.md (დასაბუთებები), ai-usage-log.md
```

თითო სერვისს აქვს საკუთარი `README.md` დეტალური ინსტრუქციით.

---

## მონაცემთა ნაკადი

1. **შეგროვება** — `collector` ყოველ ~30 წმ-ში პოლავს ~30 თვალყურის ქვეშ მყოფ
   გაჩერებას, ინახავს თითო snapshot-ს JSONL-ში და პარალელურად აქვეყნებს Kafka-ში.
2. **ჩატვირთვა** — `ingest` consumer კითხულობს Kafka-დან და წერს PostgreSQL-ში
   (idempotent, at-least-once).
3. **დამუშავება** — Spark კითხულობს snapshot-ებს Postgres-იდან JDBC-ით, აჯგუფებს
   lane-ებად (გაჩერება × მარშრუტი × მიმართულება) და თითო lane-ზე უშვებს მოსვლის
   დაფიქსირების ალგორითმს → სასწავლო სტრიქონები.
4. **წვრთნა** — `ml/train.py` წვრთნის სამ მოდელს დროის მიხედვით გაყოფით
   (train = ადრინდელი დღეები, test = ბოლო დღე — leakage-ის თავიდან ასაცილებლად).
5. **მიწოდება** — Flask API ტვირთავს მოდელს და გასცემს ცოცხალ პროგნოზებს.

---

## ML მოდელი და შედეგები

სამი მოდელი მზარდი სირთულით: **LinearRegression → RandomForest → HistGradientBoosting**.
შეფასების baseline-ებია ოპერატორის საკუთარი რეალურ-დროითი პროგნოზი და განრიგი —
მოდელმა ორივეს უნდა აჯობოს.

| მაჩვენებელი | MAE (წუთი) |
|-------------|-----------|
| ოპერატორის baseline (`rt_min`) | ≈ 3.33 |
| **საუკეთესო მოდელი (HistGradientBoosting)** | **≈ 1.83** |

სამიზნე (MAE < 3 წთ) მიღწეულია; მოდელი აჯობებს ოპერატორის პროგნოზს ~45%-ით.
დასაბუთება — [`docs/decisions.md` §4](docs/decisions.md).

---

## გაშვება

### dev სტეკი (Docker Compose)

```bash
cp .env.example services/collector/.env   # შეავსე API_KEY
docker compose up --build                 # kafka + collector + ingest + api + postgres
```

Spark-ის feature-job (on-demand):

```bash
docker compose --profile spark up -d spark-master spark-worker
docker compose --profile spark run --rm spark-submit
```

მოდელის წვრთნა:

```bash
cd services/ml && python train.py ../../data/processed/training.csv
```

Frontend (dev):

```bash
cd services/frontend && npm install && npm start
```

### სერვისები და პორტები

| სერვისი | პორტი |
|---------|-------|
| Flask API | `5000` (`/predict/<stop_id>`, `/stops`, `/health`) |
| PostgreSQL | `5432` |
| Kafka (ჰოსტიდან) | `29092` |
| Spark master UI | `8080` |

---

## დისტრიბუციული გაშვება (k3s)

სისტემა იშლება **ოთხ ფიზიკურ კვანძზე** k3s კლასტერით (მანიფესტები `k8s/`-ში):

| კვანძი | როლი |
|--------|------|
| `atlas` | k3s server + stateful (PostgreSQL, Kafka) |
| `forge` | compute (collector, ingest, api, spark-master) |
| `laptop-1`, `laptop-2` | Spark worker-ები |

Spark worker გაშვებულია **DaemonSet**-ად `ttc/spark=true` კვანძებზე, ასე რომ
feature-job ნამდვილად ნაწილდება worker-ებზე. კვანძის დამატება ხდება კოდის
ცვლილების გარეშე (ლეიბლი + `K3S_URL` token). runbook — [`k8s/README.md`](k8s/README.md).

---

## საჯარო დემო

frontend + API ხელმისაწვდომია **https://tbsbus.com**-ზე (Cloudflare Tunnel `atlas`-დან).
მონაცემთა ბაზა, Kafka და Spark არ ქვეყნდება — მხოლოდ ვებ-ინტერფეისი და პროგნოზის API.

---

## დოკუმენტაცია

- [`docs/decisions.md`](docs/decisions.md) — დასაბუთება თითო ინჟინრულ გადაწყვეტილებაზე.
- [`docs/ai-usage-log.md`](docs/ai-usage-log.md) — AI-ს გამოყენების ჟურნალი.
- `services/*/README.md` — თითო სერვისის დეტალური ინსტრუქცია.
</content>
