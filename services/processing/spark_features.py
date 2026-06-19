"""განაწილებული feature engineering Apache Spark-ით — ფაზა 3.

იგივეს აკეთებს, რასაც build_features.py, ოღონდ **განაწილებულად**: arrival_snapshot-ს კითხულობს
Postgres-იდან JDBC-ით (partition-ებად id-ის მიხედვით), ანაწილებს lane-ებს worker-ებზე და
თითო lane-ზე უშვებს *იმავე* `iter_approaches` ლოგიკას (applyInPandas). ანუ განაწილება ნამდვილია,
მაგრამ ML-ის შედეგი უცვლელია — ბირთვი ერთი და იგივე, გადამოწმებული კოდია.

`--master`: dev-ში local[*] (ერთ JVM-ში, java საჭიროა); დემოზე spark://spark-master:7077,
სადაც forge/laptop worker-ები master-ის URL-ით უერთდებიან — კოდის ცვლილების გარეშე.

გაშვება (container-ში, იხ. Dockerfile.spark / docker-compose):
    spark-submit --master spark://spark-master:7077 --py-files detect_arrivals.py \\
        spark_features.py --jdbc jdbc:postgresql://postgres:5432/ttc --out /data/processed/training_spark
"""
import argparse
from datetime import timedelta

import pandas as pd
from pyspark.sql import SparkSession
from pyspark.sql.types import (DoubleType, IntegerType, StructField, StructType, StringType)

# იგივე ლოგიკა/კონსტანტები, რასაც batch ვერსია — --py-files-ით executor-ებზე იგზავნება.
from detect_arrivals import iter_approaches
from build_features import MAX_LABEL_MIN, TBILISI_UTC_OFFSET_H

# applyInPandas-ის გამოსავალი სქემა — build_features.py-ის სვეტები ზუსტად.
OUT_SCHEMA = StructType([
    StructField("stop_id", StringType()),
    StructField("route", StringType()),
    StructField("pattern", StringType()),
    StructField("ts", StringType()),
    StructField("hour", IntegerType()),
    StructField("dow", IntegerType()),
    StructField("rt_min", IntegerType()),
    StructField("sched_min", DoubleType()),   # nullable
    StructField("label_min", DoubleType()),
])


def lane_to_rows(pdf: pd.DataFrame) -> pd.DataFrame:
    """ერთი lane-ის (stop_id, route, pattern) ჩანაწერები -> სასწავლო სტრიქონები.

    ზუსტად იმეორებს build_features.build_from_lanes-ის შიდა ციკლს, ოღონდ ერთ lane-ზე.
    iter_approaches აქ აჭრის მიახლოებებად და გვაძლევს ნამდვილ arrival_ts-ს.
    """
    stop_id = pdf["stop_id"].iloc[0]
    route = pdf["route"].iloc[0]
    pattern = pdf["pattern"].iloc[0]
    # readings = (timestamp, rt_min, sched_min); iter_approaches თავად დაალაგებs დროით.
    readings = list(zip(pd.to_datetime(pdf["ts"]).tolist(),
                        pdf["rt_min"].tolist(),
                        [None if pd.isna(v) else int(v) for v in pdf["sched_min"]]))
    out = []
    for approach, arrival_ts in iter_approaches(readings):
        for ts, rt_min, sched_min in approach:
            label_min = (arrival_ts - ts).total_seconds() / 60.0
            if label_min < 0 or label_min > MAX_LABEL_MIN:
                continue
            local = ts + timedelta(hours=TBILISI_UTC_OFFSET_H)
            out.append((stop_id, route, pattern, ts.isoformat(),
                        int(local.hour), int(local.weekday()),
                        None if rt_min is None else int(rt_min),
                        None if sched_min is None else float(sched_min),
                        round(label_min, 2)))
    return pd.DataFrame(out, columns=[f.name for f in OUT_SCHEMA.fields])


def jdbc_bounds(spark, url, props):
    """id-ის min/max — partition-ებად დაყოფილი JDBC წაკითხვისთვის."""
    q = "(SELECT min(id) lo, max(id) hi FROM arrival_snapshot WHERE realtime) t"
    row = spark.read.jdbc(url, q, properties=props).first()
    return (row["lo"], row["hi"]) if row and row["lo"] is not None else (0, 0)


def main():
    ap = argparse.ArgumentParser(description="Distributed feature engineering with Spark.")
    ap.add_argument("--master", default="local[*]", help="Spark master URL")
    ap.add_argument("--jdbc", default="jdbc:postgresql://postgres:5432/ttc", help="Postgres JDBC URL")
    ap.add_argument("--user", default="ttc")
    ap.add_argument("--password", default="ttc")
    ap.add_argument("--partitions", type=int, default=8, help="JDBC read partitions (id-ის მიხედვით)")
    ap.add_argument("--out", help="output dir for training CSV (coalesced) — local/shared FS")
    ap.add_argument("--out-table", help="output Postgres table (distributed JDBC write — k8s-ში სჯობს)")
    args = ap.parse_args()
    if not args.out and not args.out_table:
        ap.error("მიუთითე --out (CSV) ან --out-table (Postgres) — ერთ-ერთი მაინც")

    spark = (SparkSession.builder.appName("ttc-features").master(args.master)
             .getOrCreate())
    props = {"user": args.user, "password": args.password, "driver": "org.postgresql.Driver"}

    lo, hi = jdbc_bounds(spark, args.jdbc, props)
    print(f"arrival_snapshot id range: {lo}..{hi}", flush=True)

    # partition-ებად დაყოფილი წაკითხვა — თითო partition id-ის ერთ შუალედს კითხულობს.
    snaps = spark.read.jdbc(
        args.jdbc, "(SELECT id, ts, stop_id, route, pattern, rt_min, sched_min "
                   "FROM arrival_snapshot WHERE realtime) t",
        column="id", lowerBound=int(lo), upperBound=int(hi) + 1,
        numPartitions=args.partitions, properties=props)

    # lane-ებად დაჯგუფება და განაწილებული feature-ების აგება.
    rows = (snaps.groupBy("stop_id", "route", "pattern")
            .applyInPandas(lane_to_rows, schema=OUT_SCHEMA)).cache()

    # რიგი არ აქვს მნიშვნელობა — train.py დღის მიხედვით ყოფს, არა რიგის. ამიტომ orderBy არ ვუკეთებთ.
    n = rows.count()
    print(f"training rows: {n:,}", flush=True)

    if args.out:
        (rows.coalesce(1).write.mode("overwrite")
         .option("header", True).option("nullValue", "").csv(args.out))
        print(f"wrote training CSV -> {args.out}", flush=True)
    if args.out_table:
        # განაწილებული JDBC ჩაწერა — shared FS არ სჭირდება (k8s-ში მთავარი გზა).
        rows.write.jdbc(args.jdbc, args.out_table, mode="overwrite", properties=props)
        print(f"wrote training rows -> Postgres table {args.out_table}", flush=True)

    spark.stop()


if __name__ == "__main__":
    main()
