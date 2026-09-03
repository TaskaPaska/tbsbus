"""მოდელის სწავლება და შეფასება — ფაზა (ML).

ვსწავლობთ ავტობუსის მოსვლამდე დარჩენილი წუთების პროგნოზს build_features.py-ის სასწავლო
მონაცემებზე და ვადარებთ ორ baseline-ს: ოპერატორის საკუთარ `rt_min`-ს და განრიგისეულ `sched_min`-ს.
სამიზნე — MAE < 3 წუთი და ორივე baseline-ის ჯობნა.

მნიშვნელოვანი: train/test დროის მიხედვით იყოფა (ადრინდელ დღეებზე ვსწავლობთ, ბოლო დღეზე ვამოწმებთ),
შემთხვევით კი არა — ერთი ავტობუსის მიახლოების ჩანაწერები ძლიერ კორელირებულია, შემთხვევითი გაყოფა
leakage-ს მისცემდა და ხელოვნურად ასწევდა შედეგს.

feature-კონტრაქტი (SERVING_NUMERIC) განზრახ ემთხვევა იმას, რისი გამოთვლაც predict.py-ს
*ცოცხლად* შეუძლია. build_features.py უფრო მეტ სვეტს აწარმოებს (ტრენდი + GPS-მანძილი), მაგრამ
ისინი ნაგულისხმევად სწავლებაში არ მონაწილეობს — გაზომილი მიზეზით, იხ. EXPERIMENTAL_NUMERIC.

გამოყენება:
    python train.py ../../data/processed/training.csv
    python train.py training.csv --test-day 2026-09-02      # default: მონაცემების ბოლო დღე
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import joblib

# საწარმოო feature-კონტრაქტი — ზუსტად ის სვეტები, რომელთა გამოთვლაც predict.py-ს ერთი ცოცხალი
# arrival_times() call-იდან შეუძლია. predict.py-ის NUMERIC-ს ზუსტად უნდა დაემთხვეს.
SERVING_NUMERIC = ["rt_min", "sched_min", "hour", "dow"]

# build_features.py-ის დამატებითი სვეტები, რომლებიც /predict-ს ცოცხლად *არ* აქვს (ტრენდს readings
# history სჭირდება, GPS-ს — positions poll-ები). მხოლოდ კვლევისთვის, --with-experimental-ით.
#
# 2026-09-03-ის გაზომვა (8 დღე, 7.08M სტრიქონი, test day 2026-09-02): ამ სვეტების დამატება
# offline MAE-ს მხოლოდ 2.008 -> 1.996 წუთით აუმჯობესებს (0.012 წთ ≈ ხმაური), ხოლო *საწარმოოში*,
# სადაც ისინი NaN-ია, შედეგს აუარესებს: 2.008 -> 2.078. ანუ ამ სვეტებზე დატრენილი მოდელი
# ცოცხლად baseline-ს უფრო უახლოვდება, ვიდრე base-ზე დატრენილი. ამიტომ ნაგულისხმევად გამორთულია.
# veh_* კონკრეტულად არაა სანდო: nextStopId მხოლოდ *მომდევნო* გაჩერებაზე მიმავალ ავტობუსს ამთხვევს,
# ამიტომ veh_dist_m ≈ გაჩერებებს შორის მანძილი (მედიანა ~165მ), label_min-თან კორელაცია 0.016.
EXPERIMENTAL_NUMERIC = ["dt_since_prev_s", "rt_delta_min", "rt_rate", "stall_s",
                        "veh_dist_m", "veh_pos_age_s", "veh_candidates"]

CATEGORICAL = ["route", "stop_id", "pattern"]
# bucket-ების მიხედვით MAE-ის ჩვენებისთვის — რომ დავინახოთ სად სჯობს/ჩამორჩება მოდელი ოპერატორს.
RT_BUCKETS = [(-1, 2), (2, 5), (5, 10), (10, 20), (20, 999)]
# RandomForest-ი მთელ მონაცემზე მეხსიერებას სჭამს (8GB კვანძები); ვსწავლობთ ნიმუშზე.
RF_SAMPLE = 400_000

# HGB-ის კონფიგურაცია ერთ ადგილას — retrain.py-იც ამასვე იძახებს, რომ განრიგით ავტომატურად
# გადამზადებული მოდელი ხელით ნატრენინგისგან არ განსხვავდებოდეს.
HGB_PARAMS = dict(max_iter=300, learning_rate=0.1, max_depth=None, random_state=0)


def make_hgb():
    """საწარმოო მოდელი — ერთადერთი ადგილი, სადაც მისი პარამეტრები განისაზღვრება."""
    return HistGradientBoostingRegressor(categorical_features=CATEGORICAL, **HGB_PARAMS)


def load(path: Path, test_day: str | None):
    df = pd.read_csv(path, dtype={"stop_id": str, "route": str, "pattern": str})
    df["day"] = df["ts"].str.slice(0, 10)
    # ნაგულისხმევად ბოლო დღეს ვამოწმებთ — ასე ახალი მონაცემებით გაშვება კოდის შეცვლას არ ითხოვს.
    day = test_day or df["day"].max()
    return df[df["day"] < day].copy(), df[df["day"] == day].copy(), day


def evaluate(name, y_true, y_pred, results, is_model=True):
    mae = mean_absolute_error(y_true, y_pred)
    results.append((name, mae, is_model))
    print(f"  {name:<28} MAE = {mae:.3f} min", file=sys.stderr)
    return mae


def evaluate_by_bucket(name, rt_min, y_true, y_pred):
    """MAE-ი rt_min-ის დიაპაზონების მიხედვით — რომ დავინახოთ მოდელი ოპერატორს
    შორ თუ ახლო პროგნოზებზე სჯობნის (ახლოს ოპერატორის GPS-ზე დაფუძნებული პროგნოზი
    თავისთავად ზუსტდება — იქ ჯობნის საზღვარი ბუნებრივად ვიწროა).
    """
    print(f"  {name}:", file=sys.stderr)
    for lo, hi in RT_BUCKETS:
        mask = (rt_min > lo) & (rt_min <= hi)
        if mask.sum() == 0:
            continue
        mae = mean_absolute_error(y_true[mask], y_pred[mask])
        label = f"rt_min in ({lo},{hi}]"
        print(f"    {label:<18} n={mask.sum():>7,}  MAE = {mae:.3f} min", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Train & evaluate arrival-time prediction models.")
    ap.add_argument("input", type=Path, help="training CSV from build_features.py")
    ap.add_argument("--model-out", type=Path, default=Path("model.joblib"), help="where to save the best model")
    ap.add_argument("--test-day", help="YYYY-MM-DD held-out day (default: last day present in the data)")
    ap.add_argument("--with-experimental", action="store_true",
                    help="დაამატე ტრენდის/GPS სვეტები (იხ. EXPERIMENTAL_NUMERIC). მხოლოდ კვლევისთვის — "
                         "ასეთი მოდელი predict.py-ს არ შეესაბამება და საწარმოოში უარეს შედეგს იძლევა")
    args = ap.parse_args()

    numeric = SERVING_NUMERIC + (EXPERIMENTAL_NUMERIC if args.with_experimental else [])
    features = numeric + CATEGORICAL

    train, test, test_day = load(args.input, args.test_day)
    print(f"Train rows: {len(train):,} ({train['day'].min()}..{train['day'].max()})", file=sys.stderr)
    print(f"Test rows:  {len(test):,} ({test_day})", file=sys.stderr)
    if test.empty or train.empty:
        sys.exit(f"Empty train or test split — check --test-day ({test_day}) against the data's date range.")
    missing = [c for c in features if c not in train.columns]
    if missing:
        sys.exit(f"training CSV is missing required columns: {missing}")
    if args.with_experimental:
        print("  WARNING: --with-experimental features are NOT available to predict.py at serve time; "
              "the saved model would be served degraded. Research only.", file=sys.stderr)

    y_train, y_test = train["label_min"].values, test["label_min"].values
    rt_test = test["rt_min"].values
    results = []

    print("\n=== Baselines (no learning) ===", file=sys.stderr)
    evaluate("operator realtime (rt_min)", y_test, rt_test, results, is_model=False)
    sched_mask = test["sched_min"].notna()
    evaluate("schedule (sched_min)", y_test[sched_mask], test.loc[sched_mask, "sched_min"].values,
             results, is_model=False)

    print("\n=== Models (target: label_min) ===", file=sys.stderr)

    # 1) Linear Regression — one-hot კატეგორიები + sched_min-ის იმპუტაცია.
    pre = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), numeric),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    lin = Pipeline([("pre", pre), ("lr", LinearRegression())])
    lin.fit(train[features], y_train)
    evaluate("LinearRegression", y_test, lin.predict(test[features]), results)

    # 2) Random Forest — ნიმუშზე, კატეგორიები კოდებად.
    for c in CATEGORICAL:
        codes = pd.Categorical(train[c]).categories
        train[c + "_code"] = pd.Categorical(train[c], categories=codes).codes
        test[c + "_code"] = pd.Categorical(test[c], categories=codes).codes
    rf_cols = numeric + [c + "_code" for c in CATEGORICAL]
    rf_train = train.sample(min(RF_SAMPLE, len(train)), random_state=0)
    rf = Pipeline([("imp", SimpleImputer(strategy="median")),
                   ("rf", RandomForestRegressor(n_estimators=60, max_depth=18,
                                                n_jobs=-1, random_state=0))])
    rf.fit(rf_train[rf_cols], rf_train["label_min"].values)
    evaluate(f"RandomForest (n={len(rf_train):,})", y_test, rf.predict(test[rf_cols]), results)

    # 3) Hist Gradient Boosting — მთელ მონაცემზე, კატეგორიების ნატიური მხარდაჭერა, NaN-ს თავად ართმევს თავს.
    # კატეგორიების სია სწავლებისას ფიქსირდება; test-ს *იმავე* კატეგორიებზე ვამაგრებთ, თორემ
    # ორ მხარეს სხვადასხვა კოდირება მიიღება.
    cats = {}
    for c in CATEGORICAL:
        train[c] = train[c].astype("category")
        cats[c] = train[c].cat.categories
        test[c] = pd.Categorical(test[c], categories=cats[c])
    hgb = make_hgb()
    hgb.fit(train[features], y_train)
    hgb_pred = hgb.predict(test[features])
    evaluate("HistGradientBoosting", y_test, hgb_pred, results)

    print("\n=== MAE by rt_min bucket (operator baseline vs. saved HGB model) ===", file=sys.stderr)
    evaluate_by_bucket("operator realtime (rt_min)", rt_test, y_test, rt_test)
    evaluate_by_bucket("HistGradientBoosting", rt_test, y_test, hgb_pred)

    # შეჯამება — "საუკეთესო" მხოლოდ ნასწავლ მოდელებს შორის ვეძებთ, baseline-ები აქ არ ერევა.
    base = next(m for n, m, _ in results if n.startswith("operator"))
    best_name, best_mae, _ = min((r for r in results if r[2]), key=lambda x: x[1])
    print("\n=== Summary ===", file=sys.stderr)
    print(f"  operator baseline: {base:.3f} min", file=sys.stderr)
    print(f"  best model:        {best_name} @ {best_mae:.3f} min", file=sys.stderr)
    delta = base - best_mae
    print(f"  improvement vs operator: {delta:+.3f} min ({100*delta/base:+.1f}%)", file=sys.stderr)
    print(f"  target (<3 min): {'MET' if best_mae < 3 else 'not yet'}", file=sys.stderr)

    joblib.dump(hgb, args.model_out)
    print(f"\nSaved HistGradientBoosting -> {args.model_out}", file=sys.stderr)
    print(f"  feature contract: {features}", file=sys.stderr)
    print("  predicts label_min directly (minutes to arrival) — callers use model.predict(...) as-is.",
          file=sys.stderr)


if __name__ == "__main__":
    main()
