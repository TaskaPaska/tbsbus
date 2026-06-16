"""Collector-ის კონფიგურაცია/ცვლადები"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# რეპოზიტორიის root-ი ორი დონით უკანაა (services/collector/ = root).
REPO_ROOT = Path(__file__).resolve().parents[2]
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

# ციკლში იტერაციისას HTTP requests-ებს შორის ინტერვალები, რომ API არ გადაიტვირთოს.
INTER_REQUEST_DELAY = _float("INTER_REQUEST_DELAY", 0.25)

# JSONL-ის ფორმატით (gitignore-შია). ფაილები დღეებადაა გაყოფილი.
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data" / "raw"))

# რომელი გაჩერებები უნდა განახლდეს, აგენერირებს select_stops.py.
TRACKED_STOPS_FILE = Path(os.getenv("TRACKED_STOPS_FILE", COLLECTOR_DIR / "tracked_stops.json"))

# რამდენი გაჩერება უნდა შეირჩიოს ავტომატური სელექტორის მიერ.
TARGET_STOP_COUNT = _int("TARGET_STOP_COUNT", 30)