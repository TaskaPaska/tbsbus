# The prediction pipeline, explained for a data engineer

This doc assumes you know pipelines, ETL, joins, and SQL — but nothing about this
project specifically, and nothing about ML. It explains what the system does, what
"the model" actually is, and what changed recently and why.

## 1. What this project does, in one paragraph

Tbilisi's transit app tells you "bus arrives in 4 minutes." That number comes from the
transit company's own backend (call it **the operator's estimate**, or `rt_min` in the
code). This project pulls that same number, plus some extra context, and tries to
output a *better* number. To know if "better" is even true, we need a ground-truth
label to compare against — which doesn't exist directly (the API never says "the bus
actually arrived at 14:32:10"), so step one of this whole project is *manufacturing*
that label from raw polling data. Everything else follows from that.

## 2. The pipeline, as an ETL diagram

```
┌─────────────┐   poll every    ┌──────────────┐   batch ETL    ┌───────────────┐
│  TTC API     │   30-60s        │  raw JSONL   │   (offline)    │  training.csv │
│ (operator's  │ ──────────────▶ │  (append-    │ ─────────────▶ │  (features +  │
│  own system) │                 │   only log)  │                │   label)      │
└─────────────┘                 └──────────────┘                └───────────────┘
                                        │                               │
                                        │ (optional)                    │ train.py
                                        ▼                                ▼
                                 ┌──────────────┐                ┌───────────────┐
                                 │  PostgreSQL  │                │ model.joblib  │
                                 │  (queryable) │                │ (fitted model)│
                                 └──────────────┘                └───────────────┘
                                                                         │
                                                                         ▼
                                                                 ┌───────────────┐
   user's phone  ◀── frontend ◀── Flask API (/predict) ◀────────│  loaded at    │
                                  (one live request                startup     │
                                   at a time)                    └───────────────┘
```

Two completely different code paths consume the same trained model:

- **Batch / training path** (`services/collector` → `services/processing` →
  `services/ml`): runs occasionally, offline, has the luxury of looking at minutes of
  history per bus and joining multiple data sources together.
- **Serving path** (`services/api`): runs on every page load, has to answer in under a
  second, and — this matters a lot later — only has *one snapshot in time*, no history.

Keep that asymmetry in mind. A lot of the recent work exists because of the gap between
these two paths.

## 3. Where the label comes from (the part that isn't obvious)

The API is a polling countdown, not an arrival log. Polling `arrivalTimes` for one bus
repeatedly looks like this:

```
09:00  route 305  rt_min=4
09:01  route 305  rt_min=3
09:02  route 305  rt_min=1
09:03  route 305  rt_min=0
09:04  (bus no longer appears in the response)
```

`detect_arrivals.py` watches this countdown per (stop, route, direction) "lane" and says:
once the countdown hits ~0 and then the bus disappears, that timestamp *is* the arrival.
That reconstructed timestamp becomes the label. This is inherently a bit fuzzy — it's an
inference, not a direct measurement — and the code has guardrails for API glitches
(countdown jumping backwards, resetting, gaps in polling, etc.) baked into
`iter_approaches()`.

Every poll of a bus *before* it arrives becomes one training row:

| column | meaning |
|---|---|
| `rt_min` | operator's own countdown at that moment — **baseline #1** |
| `sched_min` | scheduled-timetable countdown — **baseline #2**, usually much worse |
| `label_min` | minutes between this poll and the reconstructed arrival — **the answer key** |

The whole point of "the model" is: can we build something that's closer to `label_min`
than `rt_min` is, using `rt_min` plus more context as input?

## 4. ML vocabulary, translated to SQL/pipeline terms

| ML term | What it actually is here |
|---|---|
| **feature** | an input column (`rt_min`, `hour`, `route`, ...) — literally just a column in `training.csv` |
| **label / target** | the output column we're trying to predict (`label_min`) |
| **model** | a function fitted to historical (features → label) pairs, so it can guess the label for a *new* row of features it hasn't seen. Think of it as a generalized, fuzzy lookup table — not a hardcoded rule, but not magic either. |
| **training** | the fitting process: feed it `training.csv`, it adjusts internal parameters to minimize error |
| **inference / predict()** | running the *already-fitted* function on one new row, at serving time |
| **baseline** | the "dumb" number you're trying to beat — here, `rt_min` and `sched_min` |
| **MAE** (mean absolute error) | "on average, how many minutes off are we" — a plain, business-readable metric. MAE of 1.83 means "off by 1.83 minutes on average." |
| **train/test split** | holding out some data the model never saw during fitting, to check it's not just memorizing |
| **overfitting / leakage** | the model cheating — e.g. if you split train/test *randomly*, readings from the same bus approach end up on both sides, and the model partly "memorizes" that specific approach instead of learning general patterns. That's why `train.py` splits **by day** (train on earlier days, test on the last day) instead of randomly — same reason you backtest time-series forecasts on a held-out future window, not a random sample of days. |

`train.py` currently trains three different model types (linear regression, random
forest, gradient boosting) on the same `training.csv` and just picks whichever gets the
lowest MAE. You don't need to understand how each algorithm works internally to follow
any of this — they're interchangeable "fit function to data" boxes for this purpose.

## 5. The question that started this, and its answer

> The closer the bus gets, the closer `rt_min` (operator) already is to the truth — so
> my model's improvement over `rt_min` shrinks near the stop.

**Half right.** The operator's estimate does get much better near the stop, and the
model's *edge* does shrink. But the edge never disappears — the model beats the operator
in every bucket, including 0–2 minutes out. Measured on a held-out day:

| bucket (`rt_min`) | operator MAE | model MAE | model's edge |
|---|---|---|---|
| 0–2 min | 1.95 | **1.56** | −20% |
| 2–5 min | 2.99 | **1.69** | −43% |
| 5–10 min | 4.18 | **1.97** | −53% |
| 10–20 min | 5.37 | **2.40** | −55% |
| 20+ min | 6.29 | **2.95** | −53% |

So there is no hard ceiling at short range — just diminishing returns. The interesting
part is how *flat* the model's error is (1.56 → 2.95) compared to how fast the
operator's degrades (1.95 → 6.29). The operator's estimate falls apart with distance;
the model's barely moves.

## 6. What was tried, and what the data said

Four changes were drafted. All four have now been run against real data — 8 days pulled
from `atlas` (2026-08-26 → 2026-09-02), **7,081,038 training rows**, trained on the
first 7 days and evaluated on the held-out last day (901,724 rows).

Before this, none of it had ever been executed — it was written and reasoned about, but
not measured. Two of the four ideas did not survive contact with the data.

### 6.1 — Bucket diagnostic — **kept**

MAE grouped by `rt_min` range instead of one blended number. In SQL terms, `GROUP BY
rt_min_bucket`. This is what produced the table in §5, and it's the thing that actually
answered the original question. Cheap, diagnostic, no downside. Kept in `train.py`.

### 6.2 — Trend features — **built, measured, not shipped**

The reasoning was sound. `rt_min` moves in whole-minute steps but polls happen every 30
seconds, so ~96% of adjacent-poll deltas are exactly zero — quantization noise, not
signal. The fix was to compare each reading against one from ~2 minutes earlier (a
windowed lag), yielding `rt_rate` (is the countdown falling faster or slower than real
time?) and `stall_s` (how long has it been stuck on the same number?).

The features compute correctly and populate well (`rt_rate` on 86.6% of rows, `stall_s`
on 100%). They just don't help:

| feature set (offline, all features available) | MAE |
|---|---|
| base | 2.008 |
| base + trend | 2.003 |
| base + GPS | 2.006 |
| base + trend + GPS | 1.996 |

A 0.012-minute gain — under one second — across 7M rows. That's noise, not signal.

The likely reason: `rt_min` is *already* the operator's GPS-derived estimate, and it
already encodes whatever the bus is currently doing. Re-deriving "is it slowing down"
from the countdown's own history mostly recovers information the countdown already
carried. Combined with `route`, `stop_id`, and `hour`, the model has essentially
saturated what this data can tell it.

### 6.3 — Residual modeling — **measured, reverted**

Instead of predicting `label_min` directly, train on `label_min − rt_min` (the
operator's error) and add `rt_min` back at serving time. The argument — don't waste
model capacity re-deriving an estimate you already have for free — is a real and
commonly useful technique.

It made no difference here, and slightly hurt:

| target | MAE |
|---|---|
| direct `label_min` | **1.999** |
| residual `label_min − rt_min` | 2.011 |

Gradient boosting already has `rt_min` as an input feature and can learn to use it as an
anchor on its own; hand-coding that structure bought nothing.

Since it was a tie on accuracy, the tiebreak was **failure modes**, and residual
modeling has a nasty one: the model's output stops being "minutes" and becomes "minutes
of correction." Any caller that forgets to add `rt_min` back returns numbers like `-0.3`
instead of `4` — no crash, no error, just silently wrong output on a live page. Reverted
to predicting `label_min` directly, which makes that class of bug impossible.

### 6.4 — GPS join — **built, measured, does not work as designed**

This one is worth reading carefully, because it looked right and wasn't.

Each GPS ping carries `nextStopId`. The idea: match each arrival reading to the
nearest-in-time GPS ping for the same stop (an as-of join), then compute straight-line
distance to the stop. Busy stops have 8–13 different buses all reporting the same next
stop, so the join was made more selective by also matching on route — which required
building `route_map.json` (route ID → route number), since that mapping existed nowhere.

The join works. The number it produces is meaningless:

- `corr(veh_dist_m, label_min)` = **0.016** — essentially zero
- median `veh_dist_m` is **~165 m in every bucket** — the same whether the bus is 2
  minutes away or 31
- implied bus speed (`dist / label`) = **0.93 km/h** median, which is physically absurd

**Root cause is structural, not a tuning problem.** `nextStopId == stop_id` only ever
matches a bus whose *immediate next stop* is your stop — i.e. a bus that is always
roughly one stop away. The bus that will arrive in 12 minutes is several stops out, and
its `nextStopId` points at some *other* stop, so it never enters the index for your stop
at all. What gets matched instead is whichever bus happens to be arriving imminently.

So `veh_dist_m` is, in effect, a noisy measurement of *the distance between this stop and
the one before it* — a near-constant per stop, and information the `stop_id` categorical
already contains.

The earlier synthetic test (without the route filter the join picked a bus 11.4 km away;
with it, 69 m) verified that the route filter picks a *closer* bus. It could not have
caught this, because closer was never the same thing as *correct*.

Making this feature real requires tracking a specific vehicle by `vehicleId` along the
route's geometry and measuring distance *along the route* — a different piece of work,
not a fix to this join. The code is kept and documented; it is simply not wired into the
model.

## 7. The trap that this avoided: train/serve skew

The **batch path** (`build_features.py`) can look at minutes of polling history per bus
plus a whole separate GPS feed. The **serving path** (`services/api/predict.py`) answers
one live HTTP request with exactly one call to the operator's API — no history buffer,
no GPS lookup. It structurally *cannot* compute trend or GPS features.

The original patch handled this by filling those columns with neutral placeholders at
serving time, and documenting the model as running "degraded" in production. That works
in the sense that nothing crashes. But it's worth measuring what "degraded" costs:

| model | MAE in production |
|---|---|
| base features only (nothing to lose) | **1.999** |
| base + trend + GPS, served with those columns empty | 2.029 |

Training on features that won't exist at serving time makes production **worse** than
not using them at all — the model learns to lean on signals it then never receives.

Since those features bought ~nothing even offline (§6.2, §6.4), there was nothing to
trade off. The model's feature contract is now exactly what the serving path can
compute, and train/serve skew for the deployed model is **zero** rather than merely
documented.

`build_features.py` still emits the trend and GPS columns — they cost little and are
useful for research — but `train.py` excludes them unless explicitly asked via
`--with-experimental`, which prints a warning explaining why the resulting model should
not be deployed.

## 8. What actually shipped

Retrained on the 8 days above, with the serving-matched feature contract:

| model | MAE | vs. operator |
|---|---|---|
| operator's own estimate (baseline) | 3.860 | — |
| schedule | 25.48 | — |
| **previous model, live on atlas** (June-trained) | 2.287 | −41% |
| **new model** (base features, direct label) | **1.999** | **−48%** |

Two separate wins are bundled here, worth keeping distinct:

- **Retraining on fresh data**: 2.287 → 1.999 (−12.6%). The live model was trained in
  June and had drifted; most of this gain is just recency, and it argues for retraining
  on a schedule rather than once.
- **Not shipping the skewed feature set**: 2.029 → 1.999, i.e. the change that was
  *avoided* was worth more than any of the features that were added.

One more serving fix: the regressor produces negative predictions on ~0.9% of rows (down
to −2.7 minutes). "Arriving in −2.7 minutes" is meaningless on a page, so `predict.py`
now clamps at 0.

Also fixed along the way: `train.py`'s held-out day was hardcoded to `2026-06-17`, which
silently produced an empty split on any newer dataset. It now defaults to the last day
present in the data, with `--test-day` to override.

One thing checked and deliberately left alone: `predict.py` builds pandas `category`
dtypes from the single live request's rows, not from the training categories, which
looks like a classic silent-encoding bug. It was tested directly — scikit-learn matches
categoricals by *value*, not by code — so it is correct as written.

## 9. File map — what lives where

| file | role |
|---|---|
| `services/collector/collector.py` | polls the TTC API, writes raw JSONL (`arrivalTimes` + `positions`) |
| `services/collector/fetch_route_map.py` | one-off script, builds route ID → route number lookup |
| `services/processing/detect_arrivals.py` | turns raw polling into arrival events (the label logic, §3) |
| `services/processing/build_features.py` | turns raw polling + arrivals into `training.csv` |
| `services/processing/positions_features.py` | the GPS as-of join (§6.4) — research only, not in the model |
| `services/ml/train.py` | fits models, evaluates MAE overall and by bucket, saves `model.joblib` |
| `services/api/predict.py` | serving-time feature building + inference |
| `services/api/app.py` | thin Flask wrapper around `predict.py` |

## 10. Reproducing this

The pipeline needs a Python env pinned to the same versions `atlas` runs
(`scikit-learn==1.5.2`, `pandas==2.2.3`) — a model pickled by a newer scikit-learn will
not load on the API host.

```bash
# 1. one-off: route ID -> route number lookup (needs API_KEY)
cd services/collector && python fetch_route_map.py

# 2. build the training set (GPS flags optional; research only)
cd services/processing
python build_features.py ../../data/raw/arrival-times/*.jsonl \
  -o ../../data/processed/training.csv

# 3. train + evaluate (held-out day defaults to the last day in the data)
cd services/ml
python train.py ../../data/processed/training.csv --model-out model.joblib
```

## 11. Next steps

1. **Retrain on a schedule.** The single largest measured win was recency (2.287 →
   1.999), and it will decay again. This is a cron job, not a research project.
2. **Widen the training window.** 8 days was chosen to iterate quickly; ~80 days of
   arrivals are archived on `atlas`. Worth checking whether more history helps or
   whether seasonality makes older data actively misleading.
3. **Leave the GPS join alone until there's a real trajectory match.** Per-vehicle
   tracking by `vehicleId` with distance measured *along the route* is the only version
   of this that can work (§6.4). Treat it as a new piece of work, not a fix.
4. **Don't invest further in live trend features.** Plumbing reading-history into the
   API is buildable, but §6.2 measured the ceiling at roughly one second of MAE. The
   infrastructure would cost more than the accuracy it buys.
5. **`spark_features.py` is now stale.** It was a parallel reimplementation of the older
   `build_features.py` logic and was never updated. Given `CLAUDE.md` already lists Spark
   as a simplification candidate at this data scale, deleting it is probably better than
   syncing it.
