"""Kafka -> PostgreSQL consumer — ფაზა 2.

ttc.arrivals / ttc.positions topic-ებიდან კითხულობს collector-ის ჩანაწერებს და Postgres-ში
წერს (append-only). იყენებს services/processing/db.py-ის row-builder-ებს — იგივე unroll-ლოგიკა,
რასაც batch loader (კოდის დუბლირების გარეშე).

At-least-once: ჯერ DB-ში ჩაიწერება batch, მერე commit-დება offset-ები. ავარიაზე ბოლო batch
შეიძლება გამეორდეს — append-only ანალიტიკურ ცხრილზე ეს მისაღებია (იშვიათი დუბლიკატი).

გაშვება:  KAFKA_BOOTSTRAP=localhost:9092 POSTGRES_HOST=localhost python consumer.py
"""
import json
import os
import signal
import sys
import time
from pathlib import Path

# services/processing/db.py-ის ხელახლა გამოყენება (dev-ში path-ით; Docker-ში ერთად კოპირდება).
_PROCESSING = Path(__file__).resolve().parents[1] / "processing"
sys.path.insert(0, str(_PROCESSING))
import db  # noqa: E402

from kafka import KafkaConsumer  # noqa: E402
from kafka.errors import NoBrokersAvailable  # noqa: E402

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_ARRIVALS = os.getenv("KAFKA_TOPIC_ARRIVALS", "ttc.arrivals")
TOPIC_POSITIONS = os.getenv("KAFKA_TOPIC_POSITIONS", "ttc.positions")
GROUP = os.getenv("KAFKA_GROUP", "ttc-ingest")
BATCH = int(os.getenv("INGEST_BATCH", "500"))           # flush ამდენი message-ის შემდეგ
FLUSH_SECONDS = float(os.getenv("INGEST_FLUSH_SECONDS", "5"))  # ან ამდენი წამის შემდეგ

_running = True


def _stop(*_):
    global _running
    print("\nconsumer ჩერდება...", flush=True)
    _running = False


def connect_consumer() -> KafkaConsumer:
    """broker-ის მოლოდინი — compose-ში consumer collector-ზე ადრე შეიძლება აიწყოს."""
    for attempt in range(1, 31):
        try:
            return KafkaConsumer(
                TOPIC_ARRIVALS, TOPIC_POSITIONS,
                bootstrap_servers=[b.strip() for b in BOOTSTRAP.split(",")],
                group_id=GROUP,
                enable_auto_commit=False,             # offset-ს ხელით ვაკომიტებთ DB-ჩაწერის შემდეგ
                auto_offset_reset="earliest",
                value_deserializer=lambda b: json.loads(b.decode("utf-8")),
            )
        except NoBrokersAvailable:
            print(f"  broker ჯერ მიუწვდომელია ({attempt}/30), ვცდი...", flush=True)
            time.sleep(2)
    sys.exit(f"Kafka broker {BOOTSTRAP} მიუწვდომელია.")


def main():
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    conn = db.connect()
    db.init_schema(conn)  # იდემპოტენტური
    consumer = connect_consumer()
    print(f"ingest started: {BOOTSTRAP} topics=[{TOPIC_ARRIVALS}, {TOPIC_POSITIONS}] group={GROUP}", flush=True)

    arr_buf, pos_buf = [], []
    last_flush = time.monotonic()
    total_arr = total_pos = 0

    def flush():
        nonlocal total_arr, total_pos, last_flush
        if arr_buf:
            total_arr += db.insert_arrival_rows(conn, arr_buf); arr_buf.clear()
        if pos_buf:
            total_pos += db.insert_position_rows(conn, pos_buf); pos_buf.clear()
        consumer.commit()  # offset commit მხოლოდ წარმატებული DB-ჩაწერის შემდეგ
        last_flush = time.monotonic()

    while _running:
        batches = consumer.poll(timeout_ms=1000, max_records=BATCH)
        for tp, records in batches.items():
            for msg in records:
                if tp.topic == TOPIC_ARRIVALS:
                    arr_buf.extend(db.arrival_rows_from_record(msg.value))
                else:
                    pos_buf.extend(db.position_rows_from_record(msg.value))
        pending = len(arr_buf) + len(pos_buf)
        if pending and (pending >= BATCH or time.monotonic() - last_flush >= FLUSH_SECONDS):
            flush()
            print(f"  flushed -> snapshots={total_arr:,} positions={total_pos:,}", flush=True)

    flush()  # ბოლო ნაშთი
    consumer.close()
    print(f"Stopped. snapshots={total_arr:,} positions={total_pos:,}", flush=True)


if __name__ == "__main__":
    main()
