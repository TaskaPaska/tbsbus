"""განრიგით ავტომატური გადამზადება — build_features -> train -> შემოწმება -> გაშვება.

რატომ: 2026-09-03-ის გაზომვამ აჩვენა, რომ ყველაზე დიდი მოგება მოდელის გაუმჯობესება კი არა,
*სიახლე* იყო — ივნისში დატრენილი მოდელი 2.287 წთ MAE-ს იძლეოდა, იმავე კოდით ახალ მონაცემებზე
გადამზადებული კი 1.999-ს. ეს დრეიფი დროთა განმავლობაში ისევ დაგროვდება, ამიტომ გადამზადება
განრიგზეა და არა ხელით.

უსაფრთხოება — ახალი მოდელი საწარმოოში *მხოლოდ მაშინ* ხვდება, თუ იმავე held-out დღეზე:
  1. ოპერატორის baseline-ს ჯობნის, და
  2. ამჟამად გაშვებულ მოდელს ჯობნის (ცუდი გადამზადება ჩუმად ვერ ჩაანაცვლებს კარგს).
წინააღმდეგ შემთხვევაში ძველი მოდელი რჩება და exit code 0-ია (ეს ნორმალური შედეგია, არა ავარია).

გამოყენება:
    python retrain.py                 # ბოლო 8 სრული დღე, შემოწმება + გაშვება
    python retrain.py --days 14
    python retrain.py --dry-run       # ითვლის და აჯამებს, მოდელს არ ცვლის
"""
import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train import CATEGORICAL, RT_BUCKETS, SERVING_NUMERIC, make_hgb  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
ARRIVALS_DIR = Path(os.getenv("ARRIVALS_DIR", REPO / "data" / "raw" / "arrival-times"))
MODEL_PATH = Path(os.getenv("MODEL_PATH", Path(__file__).resolve().parent / "model.joblib"))
BUILD_FEATURES = REPO / "services" / "processing" / "build_features.py"
HISTORY = Path(os.getenv("RETRAIN_HISTORY", REPO / "data" / "retrain-history.jsonl"))
LOCK = Path(os.getenv("RETRAIN_LOCK", "/tmp/tbsbus-retrain.lock"))
API_UNIT = os.getenv("API_UNIT", "ttc-api")

# მხოლოდ ეს სვეტები იკითხება CSV-დან — atlas-ს 8GB აქვს და training.csv-ს ტრენდის სვეტებიც
# მოჰყვება, რომლებსაც საწარმოო კონტრაქტი არ იყენებს (იხ. train.py-ის EXPERIMENTAL_NUMERIC).
USECOLS = ["ts"] + SERVING_NUMERIC + CATEGORICAL + ["label_min"]
DTYPES = {"stop_id": "string", "route": "string", "pattern": "string",
          "hour": "int8", "dow": "int8",
          "rt_min": "float32", "sched_min": "float32", "label_min": "float32"}


def log(msg):
    print(f"[retrain] {msg}", file=sys.stderr, flush=True)


def recent_days(n):
    """ბოლო n *სრული* დღის ფაილი — დღევანდელი გამოტოვებულია, ის ჯერ ივსება."""
    today = date.today()
    out = []
    for i in range(1, n + 60):           # ხარვეზებზე ვიყურებით, არა მხოლოდ ბოლო n კალენდარულ დღეს
        f = ARRIVALS_DIR / f"{today - timedelta(days=i)}.jsonl"
        if f.exists() and f.stat().st_size > 0:
            out.append(f)
        if len(out) == n:
            break
    return sorted(out)


def build_features(files, out_csv, workdir):
    """თითო დღე ცალკე ითვლება და შედეგები ერთ CSV-ში ეწებება.

    ერთ გაშვებაში ყველა დღის გადაცემა უფრო მარტივი იქნებოდა, მაგრამ build_features.py
    *ყველა* lane-ის ყველა reading-ს მეხსიერებაში იკავებს: 8 დღეზე ეს ~5.6GB პიკია, atlas-ს კი
    სულ 8GB აქვს და collector-იც იმავე მანქანაზე ზის. დღეობით დაყოფისას პიკი ~0.7GB-მდე ეცემა.
    ერთადერთი დანაკარგი შუაღამეზე გადამდები მიახლოებებია — iter_approaches ისედაც წყვეტს
    სერიას 180წმ-ზე დიდ პაუზაზე, ღამით კი რეისები თითქმის არაა (გაზომვით სხვაობა <0.1%).
    """
    log(f"building features from {len(files)} day(s): {files[0].stem}..{files[-1].stem}")
    parts = []
    for i, f in enumerate(files, 1):
        part = workdir / f"part-{f.stem}.csv"
        r = subprocess.run([sys.executable, str(BUILD_FEATURES), str(f), "-o", str(part)],
                           cwd=str(BUILD_FEATURES.parent), capture_output=True, text=True)
        if r.returncode != 0:
            log((r.stdout + r.stderr)[-2000:])
            sys.exit(f"build_features failed on {f.name} (exit {r.returncode})")
        parts.append(part)
        log(f"  [{i}/{len(files)}] {f.stem}: {sum(1 for _ in part.open()) - 1:,} rows")

    with out_csv.open("w", encoding="utf-8") as out:
        for i, part in enumerate(parts):
            with part.open(encoding="utf-8") as fh:
                header = fh.readline()
                if i == 0:
                    out.write(header)
                for line in fh:
                    out.write(line)
            part.unlink()


def buckets(y, pred, rt):
    return "  ".join(f"({lo},{hi}]:{mean_absolute_error(y[m], pred[m]):.2f}"
                     for lo, hi in RT_BUCKETS if (m := (rt > lo) & (rt <= hi)).sum())


def score_current(test, features, y_test):
    """ამჟამად გაშვებული მოდელის MAE იმავე test-დღეზე. None — თუ არ არსებობს/არ ჯდება."""
    if not MODEL_PATH.exists():
        return None
    try:
        cur = joblib.load(MODEL_PATH)
        return float(mean_absolute_error(y_test, cur.predict(test[features])))
    except Exception as e:                                  # noqa: BLE001 — ნებისმიერი შეუთავსებლობა
        log(f"current model could not be scored ({type(e).__name__}: {e}); treating as no baseline")
        return None


def reload_api():
    """gunicorn worker-ების გადატვირთვა SIGHUP-ით — root არ სჭირდება (unit atlas-ით გადის)."""
    try:
        pid = int(subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", API_UNIT],
                                 capture_output=True, text=True).stdout.strip())
    except ValueError:
        pid = 0
    if pid <= 0:
        log(f"{API_UNIT} not running — skipping reload (it will load the new model when it next starts)")
        return False
    cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace") if Path(f"/proc/{pid}").exists() else ""
    if "gunicorn" not in cmdline:
        log(f"PID {pid} does not look like gunicorn — refusing to signal it")
        return False
    os.kill(pid, signal.SIGHUP)
    log(f"sent SIGHUP to {API_UNIT} (pid {pid}) — workers reload with the new model")
    return True


def record(entry):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Rebuild features, retrain, and promote the model if it is better.")
    ap.add_argument("--days", type=int, default=8, help="how many complete days to use (default: 8)")
    ap.add_argument("--dry-run", action="store_true", help="evaluate but never replace the live model")
    ap.add_argument("--keep-csv", type=Path, help="keep the generated training CSV here instead of a temp file")
    args = ap.parse_args()

    LOCK.touch(exist_ok=True)
    lock_fh = LOCK.open("r+")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit("another retrain is already running — exiting")

    started = time.time()
    features = SERVING_NUMERIC + CATEGORICAL
    files = recent_days(args.days)
    if len(files) < 2:
        sys.exit(f"need at least 2 days of data in {ARRIVALS_DIR}, found {len(files)}")

    tmpdir = tempfile.TemporaryDirectory(prefix="tbsbus-retrain-")
    csv_path = args.keep_csv or Path(tmpdir.name) / "training.csv"
    build_features(files, csv_path, Path(tmpdir.name))

    log("loading training rows")
    df = pd.read_csv(csv_path, usecols=USECOLS, dtype=DTYPES)
    df["day"] = df["ts"].str.slice(0, 10)
    df.drop(columns=["ts"], inplace=True)
    test_day = df["day"].max()
    train, test = df[df["day"] < test_day], df[df["day"] == test_day]
    log(f"{len(df):,} rows total | train {len(train):,} | test {len(test):,} (held out {test_day})")
    if train.empty or test.empty:
        sys.exit("empty train or test split")

    y_train, y_test = train["label_min"].values, test["label_min"].values
    rt_test = test["rt_min"].values
    operator = float(mean_absolute_error(y_test, rt_test))

    # კატეგორიები სწავლების მიხედვით ფიქსირდება; test-ს იმავეზე ვამაგრებთ.
    Xtr, Xte = train[features].copy(), test[features].copy()
    for c in CATEGORICAL:
        Xtr[c] = Xtr[c].astype("category")
        Xte[c] = pd.Categorical(Xte[c], categories=Xtr[c].cat.categories)

    current = score_current(test, features, y_test)

    log("fitting")
    model = make_hgb()
    model.fit(Xtr, y_train)
    pred = model.predict(Xte)
    candidate = float(mean_absolute_error(y_test, pred))

    log(f"operator baseline : {operator:.3f} min")
    log(f"current live model: {current:.3f} min" if current is not None else "current live model: (none)")
    log(f"new candidate     : {candidate:.3f} min")
    log(f"  by bucket -> operator  {buckets(y_test, rt_test, rt_test)}")
    log(f"  by bucket -> candidate {buckets(y_test, pred, rt_test)}")

    beats_operator = candidate < operator
    beats_current = current is None or candidate < current
    promote = beats_operator and beats_current and not args.dry_run

    reason = ("dry-run" if args.dry_run else
              "worse than operator baseline" if not beats_operator else
              "worse than the model already live" if not beats_current else "promoted")

    if promote:
        backup = MODEL_PATH.with_name(f"model.joblib.prev")
        if MODEL_PATH.exists():
            backup.write_bytes(MODEL_PATH.read_bytes())
        tmp_model = MODEL_PATH.with_suffix(".joblib.new")
        joblib.dump(model, tmp_model)
        os.replace(tmp_model, MODEL_PATH)     # ატომური — API-მ ნახევრად ჩაწერილი ფაილი ვერ დაინახავს
        log(f"promoted -> {MODEL_PATH} (previous kept at {backup.name})")
        reload_api()
    else:
        log(f"NOT promoting: {reason}. Live model left untouched.")

    record({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "days": len(files),
        "train_rows": int(len(train)), "test_rows": int(len(test)), "test_day": test_day,
        "operator_mae": round(operator, 4),
        "current_mae": round(current, 4) if current is not None else None,
        "candidate_mae": round(candidate, 4),
        "promoted": bool(promote), "reason": reason,
        "seconds": round(time.time() - started, 1),
    })
    log(f"done in {time.time() - started:.0f}s — {reason}")
    tmpdir.cleanup()


if __name__ == "__main__":
    main()
