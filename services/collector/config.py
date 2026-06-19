"""Collector-ის კონფიგურაცია/ცვლადები"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# რეპოზიტორიის root-ი ორი დონით უკანაა (services/collector/ = root). container-ში ფაილი /app-შია,
# ასე ღრმად აღარ ჩადის — fallback უახლოეს დონეზე (DATA_DIR ისედაც env-ით override-დება).
_parents = Path(__file__).resolve().parents
REPO_ROOT = _parents[2] if len(_parents) > 2 else _parents[-1]
COLLECTOR_DIR = Path(__file__).resolve().parent


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


# რამდენად ხშირად უნდა განახლდეს ჩასვლის დროები თითოეული გაჩერებისთვის.
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)

# რამდენად ხშირად უნდა განახლდეს ავტობუსების მიმდინარე პოზიციები
POSITIONS_POLL_INTERVAL_SECONDS = _int("POSITIONS_POLL_INTERVAL_SECONDS", 60)

# უნდა ჩაწეროს თუ არა ორივე მიმართულების პოზიციები.
POSITIONS_BOTH_DIRECTIONS = os.getenv("POSITIONS_BOTH_DIRECTIONS", "true").lower() == "true"

# ყოველ რამდენ ციკლში სცადოს ხელახლა 500-ით გამოტოვებული (route, forward) წყვილები.
# 0 = არასდროს (ძველი ქცევა). ეს იცავს API-ს დროებითი შეფერხებისგან, რომელიც სხვა შემთხვევაში
# მუდამ გამოტოვებდა ყველა მარშრუტს.
POSITIONS_SKIP_RETRY_CYCLES = _int("POSITIONS_SKIP_RETRY_CYCLES", 60)

# ციკლში იტერაციისას HTTP requests-ებს შორის ინტერვალები, რომ API არ გადაიტვირთოს.
INTER_REQUEST_DELAY = _float("INTER_REQUEST_DELAY", 0.25)

# JSONL-ის ფორმატით (gitignore-შია). ფაილები დღეებადაა გაყოფილი.
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data" / "raw"))

# რომელი გაჩერებები უნდა განახლდეს, აგენერირებს select_stops.py.
TRACKED_STOPS_FILE = Path(os.getenv("TRACKED_STOPS_FILE", COLLECTOR_DIR / "tracked_stops.json"))

# რამდენი გაჩერება უნდა შეირჩიოს ავტომატური სელექტორის მიერ.
TARGET_STOP_COUNT = _int("TARGET_STOP_COUNT", 30)

# --- Kafka (არასავალდებულო, opt-in) ---
# ცარიელი = Kafka გათიშულია, collector მხოლოდ JSONL-ში წერს (ნაგულისხმევი, production-ზე atlas).
# დაყენებისას (მაგ. "kafka:9092"), JSONL-ის *პარალელურად* აქვეყნებს topic-ებშიც.
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "")
KAFKA_TOPIC_ARRIVALS = os.getenv("KAFKA_TOPIC_ARRIVALS", "ttc.arrivals")
KAFKA_TOPIC_POSITIONS = os.getenv("KAFKA_TOPIC_POSITIONS", "ttc.positions")