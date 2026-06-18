"""მოდელის სწავლება და შეფასება — ფაზა (ML).

ვსწავლობთ ავტობუსის მოსვლამდე დარჩენილი წუთების პროგნოზს build_features.py-ის სასწავლო
მონაცემებზე და ვადარებთ ორ baseline-ს: ოპერატორის საკუთარ `rt_min`-ს და განრიგისეულ `sched_min`-ს.
სამიზნე — MAE < 3 წუთი და ორივე baseline-ის ჯობნა.

მნიშვნელოვანი: train/test დროის მიხედვით იყოფა (ადრინდელ დღეებზე ვსწავლობთ, ბოლო დღეზე ვამოწმებთ),
შემთხვევით კი არა — ერთი ავტობუსის მიახლოების ჩანაწერები ძლიერ კორელირებულია, შემთხვევითი გაყოფა
leakage-ს მისცემდა და ხელოვნურად ასწევდა შედეგს.

გამოყენება:
    python train.py ../../data/processed/training.csv
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import joblib

NUMERIC = ["rt_min", "sched_min", "hour", "dow"]
CATEGORICAL = ["route", "stop_id", "pattern"]
# ბოლო დღე ცალკე ვამოწმოთ; დანარჩენი — სასწავლო.
TEST_DAY = "2026-06-17"
# RandomForest-ი მთელ 5.4M-ზე მეხსიერებას სჭამს (8GB კვანძები); ვსწავლობთ ნიმუშზე.
RF_SAMPLE = 400_000


def load(path: Path):
    df = pd.read_csv(path, dtype={"stop_id": str, "route": str, "pattern": str})
    df["day"] = df["ts"].str.slice(0, 10)
    train = df[df["day"] < TEST_DAY].copy()
    test = df[df["day"] == TEST_DAY].copy()
    return train, test


def evaluate(name, y_true, y_pred, results):
    mae = mean_absolute_error(y_true, y_pred)
    results.append((name, mae))
    print(f"  {name:<28} MAE = {mae:.3f} min", file=sys.stderr)
    return mae


def main():
    ap = argparse.ArgumentParser(description="Train & evaluate arrival-time prediction models.")
    ap.add_argument("input", type=Path, help="training CSV from build_features.py")
    ap.add_argument("--model-out", type=Path, default=Path("model.joblib"), help="where to save the best model")
    args = ap.parse_args()

    train, test = load(args.input)
    print(f"Train rows: {len(train):,} ({train['day'].min()}..{train['day'].max()})", file=sys.stderr)
    print(f"Test rows:  {len(test):,} ({TEST_DAY})", file=sys.stderr)
    if test.empty or train.empty:
        sys.exit("Empty train or test split — check TEST_DAY against the data's date range.")

    y_train, y_test = train["label_min"].values, test["label_min"].values
    results = []

    print("\n=== Baselines (no learning) ===", file=sys.stderr)
    evaluate("operator realtime (rt_min)", y_test, test["rt_min"].values, results)
    sched_mask = test["sched_min"].notna()
    evaluate("schedule (sched_min)", y_test[sched_mask], test.loc[sched_mask, "sched_min"].values, results)

    print("\n=== Models ===", file=sys.stderr)

    # 1) Linear Regression — one-hot კატეგორიები + sched_min-ის იმპუტაცია.
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    lin = Pipeline([("pre", pre), ("lr", LinearRegression())])
    lin.fit(train[NUMERIC + CATEGORICAL], y_train)
    evaluate("LinearRegression", y_test, lin.predict(test[NUMERIC + CATEGORICAL]), results)

    # 2) Random Forest — ნიმუშზე, კატეგორიები კოდებად.
    for c in CATEGORICAL:
        codes = pd.Categorical(train[c]).categories
        train[c + "_code"] = pd.Categorical(train[c], categories=codes).codes
        test[c + "_code"] = pd.Categorical(test[c], categories=codes).codes
    code_cols = [c + "_code" for c in CATEGORICAL]
    rf_cols = NUMERIC + code_cols
    rf_train = train.sample(min(RF_SAMPLE, len(train)), random_state=0)
    rf = Pipeline([("imp", SimpleImputer(strategy="median")),
                   ("rf", RandomForestRegressor(n_estimators=60, max_depth=18,
                                                n_jobs=-1, random_state=0))])
    rf.fit(rf_train[rf_cols], rf_train["label_min"].values)
    evaluate(f"RandomForest (n={len(rf_train):,})", y_test, rf.predict(test[rf_cols]), results)

    # 3) Hist Gradient Boosting — მთელ მონაცემზე, კატეგორიების ნატიური მხარდაჭერა, NaN-ს თავად ართმევს თავს.
    for c in CATEGORICAL:
        train[c] = train[c].astype("category")
        test[c] = test[c].astype("category")
    hgb = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.1, max_depth=None,
        categorical_features=CATEGORICAL, random_state=0)
    hgb.fit(train[NUMERIC + CATEGORICAL], y_train)
    hgb_mae = evaluate("HistGradientBoosting", y_test, hgb.predict(test[NUMERIC + CATEGORICAL]), results)

    # შეჯამება
    base = next(m for n, m in results if n.startswith("operator"))
    best_name, best_mae = min(results, key=lambda x: x[1])
    print("\n=== Summary ===", file=sys.stderr)
    print(f"  operator baseline: {base:.3f} min", file=sys.stderr)
    print(f"  best model:        {best_name} @ {best_mae:.3f} min", file=sys.stderr)
    delta = base - best_mae
    print(f"  improvement vs operator: {delta:+.3f} min ({100*delta/base:+.1f}%)", file=sys.stderr)
    print(f"  target (<3 min): {'MET' if best_mae < 3 else 'not yet'}", file=sys.stderr)

    joblib.dump(hgb, args.model_out)
    print(f"\nSaved HistGradientBoosting -> {args.model_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
