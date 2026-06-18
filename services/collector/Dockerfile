# მსუბუქი collector image — TTC API-ს ეკითხება და JSONL-ს /data volume-ში წერს.
# RAM-ლიმიტირებული კვანძებისთვის slim base.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# self-contained საქაღალდეა (config, ttc_client, tracked_stops.json ერთადაა).
COPY . /app/

# JSONL ცალკე volume-ში, რომ container-ის რესტარტს მონაცემები გადაურჩეს.
ENV DATA_DIR=/data
VOLUME ["/data"]

CMD ["python", "collector.py"]
