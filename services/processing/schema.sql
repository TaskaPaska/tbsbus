-- PostgreSQL + PostGIS სქემა — ფაზა 2 ETL-ის სამიზნე საცავი.
--
-- დიზაინი: JSONL რჩება დაუმუშავებელ (raw), ხელახლა-გაშვებად ლოგად; ეს ბაზა არის
-- *queryable* საცავი, რომელშიც load_to_db.py ანაწილებს (unroll) payload-ებს ტიპიზებულ
-- სვეტებად. detect_arrivals / build_features კითხულობს აქედან (ან პირდაპირ JSONL-დან).
--
-- src_date თითო ჩანაწერზე = წყარო-ფაილის დღე → ჩატვირთვა იდემპოტენტურია (იხ. load_to_db.py:
-- ხელახლა ჩატვირთვისას ჯერ იშლება იმ დღის სტრიქონები, მერე ჩაიწერება ხელახლა).

CREATE EXTENSION IF NOT EXISTS postgis;

-- 1) გაჩერებების განზომილება (dimension). წყარო: collector/tracked_stops.json.
--    geom — PostGIS წერტილი (geography, WGS84) — distance/რუკის გეო-მოთხოვნებისთვის.
CREATE TABLE IF NOT EXISTS stop (
    id           text PRIMARY KEY,
    name         text,
    lat          double precision,
    lon          double precision,
    routes       text[],
    geom         geography(Point, 4326)
);

-- 2) ჩასვლის დროების snapshot — payload-ის ცალკეული ელემენტი (თითო მოსალოდნელი ავტობუსი
--    თითო poll-ში). ეს არის ML-ის სასწავლო მონაცემის ნედლი წყარო.
CREATE TABLE IF NOT EXISTS arrival_snapshot (
    id           bigserial PRIMARY KEY,
    ts           timestamptz NOT NULL,
    src_date     date        NOT NULL,
    stop_id      text        NOT NULL,
    route        text        NOT NULL,   -- shortName
    headsign     text,
    pattern      text        NOT NULL,   -- patternSuffix (მიმართულება), "" თუ არ აქვს
    vehicle_mode text,
    realtime     boolean     NOT NULL,
    rt_min       integer,                -- realtimeArrivalMinutes (ოპერატორის პროგნოზი)
    sched_min    integer                 -- scheduledArrivalMinutes (განრიგი)
);
-- lane-ის სკანი (stop, route, pattern დროის მიხედვით) — arrival detection-ის მთავარი მოთხოვნა.
CREATE INDEX IF NOT EXISTS ix_snap_lane ON arrival_snapshot (stop_id, route, pattern, ts);
CREATE INDEX IF NOT EXISTS ix_snap_date ON arrival_snapshot (src_date);

-- 3) ავტობუსების პოზიციები — locations endpoint-ის payload, unrolled. geom — PostGIS წერტილი.
CREATE TABLE IF NOT EXISTS vehicle_position (
    id           bigserial PRIMARY KEY,
    ts           timestamptz NOT NULL,
    src_date     date        NOT NULL,
    route_id     text        NOT NULL,
    forward      boolean,
    vehicle_id   text,
    lat          double precision,
    lon          double precision,
    heading      double precision,
    next_stop_id text,
    geom         geography(Point, 4326)
);
CREATE INDEX IF NOT EXISTS ix_pos_route ON vehicle_position (route_id, ts);

-- 4) დაფიქსირებული მოსვლები — detect_arrivals.py-ის შედეგი (ML ლეიბლების წყარო/აუდიტი).
CREATE TABLE IF NOT EXISTS arrival_event (
    id               bigserial PRIMARY KEY,
    stop_id          text NOT NULL,
    route            text NOT NULL,
    pattern          text NOT NULL,
    headsign         text,
    arrival_ts       timestamptz NOT NULL,
    delay_min        integer,
    n_readings       integer,
    min_remaining_min integer,
    first_seen_min   integer,
    first_seen_ts    timestamptz
);
CREATE INDEX IF NOT EXISTS ix_event_lane ON arrival_event (stop_id, route, pattern, arrival_ts);
