"""TTC მონაცემების შეგროვება — ფაზა 1.

გროვდება:
  data/raw/arrival-times/YYYY-MM-DD.jsonl   თითო ჩანაწერი თითო გაჩერებისთვის
  data/raw/positions/YYYY-MM-DD.jsonl       თითო ჩანაწერი თითო მარშრუტისთვის

ინახება მთლიანი payload-ი, ასევე რამდენიმე დამატებითი მონაცემი (timestamp, endpoint, id).
აქედან არაფერი არ იშლება ან არ ხდება ტრანსოფრმაცია, ეს უკანასკნელი ნაწილი მეორე ფაზის ETL-ისთვისაა,
რომელიც ხელახლა გაშვებადია.
"""
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

import config
from kafka_sink import KafkaSink
from ttc_client import TTCClient


# დამხმარე ფუნქციები, რომ timestamp-ები ყოველთვის ერთნაირი ფორმატით იყოს ჩაწერილი (ISO 8601 UTC).
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class JsonlWriter:
    """ფუნქცია, რომელიც ყოველი დღისთვის ახალ ფაილს ქმნის და მონაცემებს აგროვებს."""

    def __init__(self, stream_dir: Path):
        self.stream_dir = stream_dir
        self.stream_dir.mkdir(parents=True, exist_ok=True)
        self._date = None
        self._fh = None

    def write(self, record: Dict[str, Any]) -> None:
        today = utc_date()
        if today != self._date:
            if self._fh:
                self._fh.close()
            self._fh = (self.stream_dir / f"{today}.jsonl").open("a", encoding="utf-8")
            self._date = today
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()  # წამოღებისთანავე ჩაწეროს ფაილში, რომ არ დაიკარგოს მონაცემი პროცესის მოულოდნელი შეჩერებისას
    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None


class Collector:
    def __init__(self):
        # API client-ის ინიციალიზაცია
        self.client = TTCClient.from_env()
        tracked = json.loads(config.TRACKED_STOPS_FILE.read_text(encoding="utf-8"))
        self.stops: List[Dict[str, Any]] = tracked["stops"]
        # ზოგადად უნდა იყოს "route_ids", მაგრამ თუ არ გვაქვს, მარშრუტის სახელი გამოვიყენოთ.
        self.route_ids: List[str] = tracked.get("route_ids") or tracked.get("routes", [])
        self.arrivals = JsonlWriter(config.DATA_DIR / "arrival-times")
        self.positions = JsonlWriter(config.DATA_DIR / "positions")
        # არასავალდებულო Kafka — ცარიელი bootstrap-ზე no-op (მხოლოდ JSONL).
        self.kafka = KafkaSink(config.KAFKA_BOOTSTRAP)
        self._skip_positions: set = set()
        # 500-იანი ერორი სერვერისაც შეიძლება იყოს და ვალიდური მარშრუტის არარსებობაც. ტყუილად რომ არ გავაგზავნოთ
        # რექუესთი, ასეთი მარშრუტი ერთჯერადად გამოიტოვება, მაგრამ ვცდილობთ პერიოდულად მაინც დავუბრუნდეთ,
        # რომ თუ სერვერის პრობლემა იყო, მოგვიანებით მაინც მოვძებნოს.
        self._positions_cycles = 0
        self._running = True
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

    def _stop(self, *_):
        print("\nპროცესი ჩერდება...", flush=True)
        self._running = False

    def poll_arrivals(self) -> int:
        """გაჩერებებზე მოსალოდნელი ავტობუსების წამოღება, შესაბამის ერორებთან გამკლავება."""
        ok = 0
        for stop in self.stops:
            sid = stop["id"]
            try:
                payload = self.client.arrival_times(sid)
                record = {
                    "ts": utc_now_iso(), "endpoint": "arrival-times",
                    "stop_id": sid, "payload": payload,
                }
                self.arrivals.write(record)
                self.kafka.send(config.KAFKA_TOPIC_ARRIVALS, record, key=str(sid))
                ok += 1
            except Exception as e:
                print(f"  ! arrival-times stop {sid}: {e}", flush=True)
            if not self._running:
                break
            time.sleep(config.INTER_REQUEST_DELAY)
        return ok

    def poll_positions(self) -> int:
        """მარშრუტების პოზიციების წამოღება, შესაბამის ერორებთან გამკლავება."""
        ok = 0
        self._positions_cycles += 1
        # თავიდან ვცდილობთ ძველი გამოტოვებული პოზიციების გადამოწმებას
        if (config.POSITIONS_SKIP_RETRY_CYCLES
                and self._positions_cycles % config.POSITIONS_SKIP_RETRY_CYCLES == 0
                and self._skip_positions):
            print(f"  მიმდინარეობს ~ {len(self._skip_positions)} გამოტოვებული პოზიციების თავიდან ცდა", flush=True)
            self._skip_positions.clear()
        directions = (True, False) if config.POSITIONS_BOTH_DIRECTIONS else (True,)
        for route_id in self.route_ids:
            for forward in directions:
                if (route_id, forward) in self._skip_positions:
                    continue  # თუ ისეთი წყვილია რომელზეც ვიცით რომ არ იმუშავებს, გამოვტოვოთ
                try:
                    payload = self.client.positions(route_id, forward=forward)
                    record = {
                        "ts": utc_now_iso(), "endpoint": "positions",
                        "route_id": route_id, "forward": forward, "payload": payload,
                    }
                    self.positions.write(record)
                    self.kafka.send(config.KAFKA_TOPIC_POSITIONS, record, key=str(route_id))
                    ok += 1
                except requests.exceptions.HTTPError as e:
                    if e.response is not None and e.response.status_code == 500:
                        # ჩავინიშნოთ წყვილები რომლებიც დაერორდა 500-ით
                        self._skip_positions.add((route_id, forward))
                        print(f"  ~ positions route {route_id} fwd={forward}: no pattern (500), skipping henceforth", flush=True)
                    else:
                        print(f"  ! positions route {route_id} fwd={forward}: {e}", flush=True)
                except Exception as e:
                    # ჩავინიშოთ წყვილები რომლებიც დაერორდა ნებისმიერი ერორით
                    print(f"  ! positions route {route_id} fwd={forward}: {e}", flush=True)
                if not self._running:
                    return ok
                time.sleep(config.INTER_REQUEST_DELAY)
        return ok

    def run(self) -> None:
        """მთავარი ციკლი, რომელიც პერიოდულად იძახებს მონაცემების წამოღების ფუნქციებს და ინახავს მათ ფაილებში."""
        print(f"Collector started: {len(self.stops)} stops, {len(self.route_ids)} routes.", flush=True)
        print(f"  arrival interval={config.POLL_INTERVAL_SECONDS}s  "
              f"positions interval={config.POSITIONS_POLL_INTERVAL_SECONDS}s  "
              f"-> {config.DATA_DIR}", flush=True)
        print(f"  kafka: {'on -> ' + config.KAFKA_BOOTSTRAP if self.kafka.enabled else 'off (JSONL only)'}",
              flush=True)
        next_positions = 0.0
        while self._running:
            cycle_start = time.monotonic()

            n_arr = self.poll_arrivals()
            n_pos = 0
            if self._running and cycle_start >= next_positions:
                n_pos = self.poll_positions()
                next_positions = time.monotonic() + config.POSITIONS_POLL_INTERVAL_SECONDS

            # თითოეული ინტერვალი მკაცრად მოიცავს 30 წამს, მაგრამ თუ რომელიმე ფუნქციამ გაიწელა,
            # შემდეგი ციკლი არ დაიწყება მანამ, სანამ მიმდინარე ციკლი არ დასრულდება.
            # ეს იცავს API-ს გადატვირთვისგან, რაც შეიძლება მოხდეს ციკლების ერთმანეთთან დამთხვევის შემთხვევაში.
            elapsed = time.monotonic() - cycle_start # მოცემული ციკლის მუშაობას რამდენი ხანი დასჭირდა
            print(f"[{utc_now_iso()}] arrivals={n_arr} positions={n_pos} "
                  f"skip={len(self._skip_positions)} cycle={elapsed:.1f}s", flush=True)

            sleep_for = config.POLL_INTERVAL_SECONDS - elapsed # რამდენი ხანია "დარჩენილი" ამ ციკლში
            while sleep_for > 0 and self._running:
                # sleep ეშვება 1 წამზე ნაკლები ინტერვალებით, რომ უფრო სწრაფად რეაგირებდეს პროცესის შეჩერებაზე
                time.sleep(min(sleep_for, 1.0))
                sleep_for -= 1.0

        self.arrivals.close()
        self.positions.close()
        self.kafka.close()
        print("Stopped cleanly.", flush=True)


def main() -> None:
    if not config.TRACKED_STOPS_FILE.exists():
        sys.exit(f"No tracked stops file at {config.TRACKED_STOPS_FILE}. Run select_stops.py first.")
    Collector().run()


if __name__ == "__main__":
    main()
