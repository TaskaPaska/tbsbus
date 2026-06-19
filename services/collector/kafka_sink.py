"""არასავალდებულო Kafka producer collector-ისთვის.

დიზაინი: JSONL რჩება collector-ის *durable* raw ლოგად; Kafka არის სტრიმინგ-ტრანსპორტი,
რომელსაც consumer (services/ingest) Postgres-ში ჩაწერს. თუ KAFKA_BOOTSTRAP ცარიელია,
`KafkaSink` no-op-ია — collector ზუსტად ისე იქცევა, როგორც აქამდე (atlas-ზე production-ი
არ ირღვევა, სანამ env ცვლადს არ დააყენებ).

kafka-python იმპორტდება მხოლოდ enabled რეჟიმში — disabled-ში ბიბლიოთეკა საჭირო არ არის.
"""
import json
from typing import Any, Dict, Optional


class KafkaSink:
    def __init__(self, bootstrap: str, acks: int = 1, linger_ms: int = 200):
        self.enabled = bool(bootstrap)
        self.producer = None
        if not self.enabled:
            return
        from kafka import KafkaProducer  # lazy — საჭიროა მხოლოდ enabled-ში
        self.producer = KafkaProducer(
            bootstrap_servers=[b.strip() for b in bootstrap.split(",")],
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
            acks=acks,            # 1 = leader-ის დადასტურება (single broker-ზე საკმარისი)
            linger_ms=linger_ms,  # მცირე batching — gondola/poll ციკლი ისედაც იშვიათია
            retries=3,
        )

    def send(self, topic: str, record: Dict[str, Any], key: Optional[str] = None) -> None:
        """JSONL-ში ჩაწერილი იგივე record-ი ქვეყნდება topic-ში. key → partition affinity
        (იგივე stop/route ერთ partition-ში, lane-ის რიგი დაცული რჩება single broker-ზეც)."""
        if self.producer is not None:
            self.producer.send(topic, value=record, key=key)

    def close(self) -> None:
        if self.producer is not None:
            self.producer.flush()
            self.producer.close()
