"""პროგნოზის ლოგიკა — ML მოდელი + ცოცხალი TTC მონაცემები -> კორექტირებული მოსვლის წუთები.

ეს მოდული Flask-ისგან დამოუკიდებლად ტესტირებადია: `PredictionService` იღებს ერთ ცოცხალ
arrival-times entry-ს და აბრუნებს მოდელის პროგნოზს. feature-ების აგება ზუსტად იმეორებს
build_features.py-ის ლოგიკას, რომ train და serve დროს features ერთნაირი იყოს (skew-ის თავიდან
აცილება) — იგივე სვეტები, იგივე pattern წესი, იგივე UTC+4 ლოკალური დრო.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import pandas as pd

# train.py-ის feature კონტრაქტი — სვეტების სახელები და რიგი ზუსტად უნდა დაემთხვეს მოდელის ფიტს.
NUMERIC = ["rt_min", "sched_min", "hour", "dow"]
CATEGORICAL = ["route", "stop_id", "pattern"]
# საქართველო მუდმივად UTC+4 (DST არ აქვს) — იგივე კონსტანტა build_features.py-ში.
TBILISI_UTC_OFFSET_H = 4


def _now_local() -> datetime:
    """მიმდინარე დრო თბილისის ლოკალურ დროში — hour/dow feature-ებისთვის."""
    return datetime.now(timezone.utc) + timedelta(hours=TBILISI_UTC_OFFSET_H)


def feature_row(entry: Dict[str, Any], stop_id: str, now_local: datetime) -> Dict[str, Any]:
    """ცოცხალ arrival-times entry-ს აქცევს მოდელის ერთ feature-სტრიქონად.

    `entry` — TTCClient.arrival_times(stop_id) payload-ის ერთი ელემენტი. pattern/route წესი
    ზუსტად ემთხვევა detect_arrivals.read_lanes-ს: route=shortName, pattern=patternSuffix or "".
    """
    return {
        "rt_min": entry["realtimeArrivalMinutes"],
        "sched_min": entry.get("scheduledArrivalMinutes"),
        "hour": now_local.hour,
        "dow": now_local.weekday(),  # 0=ორშაბათი
        "route": entry["shortName"],
        "stop_id": stop_id,
        "pattern": entry.get("patternSuffix") or "",
    }


class PredictionService:
    def __init__(self, model_path: Path):
        self.model_path = Path(model_path)
        self.model = joblib.load(self.model_path)

    def _to_frame(self, rows: List[Dict[str, Any]]) -> pd.DataFrame:
        df = pd.DataFrame(rows, columns=NUMERIC + CATEGORICAL)
        # მოდელი category dtype-ზე დაიტრენა (HistGradientBoosting native categorical);
        # ფიტში არნახული მნიშვნელობებს მოდელი თავად ართმევს თავს (unknown -> missing bin).
        for c in CATEGORICAL:
            df[c] = df[c].astype("category")
        return df

    def predict_rows(self, rows: List[Dict[str, Any]]) -> List[float]:
        if not rows:
            return []
        preds = self.model.predict(self._to_frame(rows))
        return [round(float(p), 2) for p in preds]

    def predict_stop(self, stop_id: str, payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ცოცხალი arrival-times payload-იდან აბრუნებს per-ავტობუს პროგნოზებს.

        მხოლოდ `realtime` entry-ებზე ვმუშაობთ — მოდელიც მხოლოდ realtime ჩანაწერებზე დაიტრენა.
        თითო შედეგი აჩვენებს მოდელის პროგნოზსაც და ოპერატორის baseline-საც, რომ წინ მათი
        შედარება ჩანდეს.
        """
        now_local = _now_local()
        results: List[Dict[str, Any]] = []
        rows = []
        meta = []
        for a in payload:
            if not a.get("realtime"):
                continue
            rows.append(feature_row(a, stop_id, now_local))
            meta.append(a)
        preds = self.predict_rows(rows)
        for a, row, pred in zip(meta, rows, preds):
            results.append({
                "route": a["shortName"],
                "headsign": a.get("headsign", ""),
                "pattern": row["pattern"],
                "operator_min": row["rt_min"],       # baseline: ოპერატორის realtimeArrivalMinutes
                "scheduled_min": row["sched_min"],   # baseline: განრიგი
                "predicted_min": pred,               # ჩვენი მოდელის კორექტირებული პროგნოზი
            })
        results.sort(key=lambda r: r["predicted_min"])
        return results