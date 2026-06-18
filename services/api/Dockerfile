# თხელი image; მოგვიანებით docker-compose/k3s-ისთვის. RAM-ლიმიტირებული კვანძებისთვის slim base.
FROM python:3.12-slim

WORKDIR /app

# გამოყენებული TTCClient collector-იდანაა — ორივე საქაღალდე ერთად კოპირდება.
COPY services/api/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY services/collector/ttc_client.py /app/ttc_client.py
COPY services/api/ /app/
COPY services/ml/model.joblib /model/model.joblib

ENV MODEL_PATH=/model/model.joblib \
    PORT=5000
EXPOSE 5000

# gunicorn — 2 worker საკმარისია thin სერვისისთვის; მოდელი თითო worker-ში ერთხელ იტვირთება.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
