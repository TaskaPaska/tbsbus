"""Collector configuration. All values overridable via environment variables / .env."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Repo root = two levels up from this file (services/collector/ -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[2]
COLLECTOR_DIR = Path(__file__).resolve().parent


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


# How often to poll arrival-times for every tracked stop (the primary ML signal).
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)

# How often to poll vehicle positions for the tracked routes (auxiliary; can be slower
# since it's used to confirm/disambiguate arrivals, not as the core ETA series).
POSITIONS_POLL_INTERVAL_SECONDS = _int("POSITIONS_POLL_INTERVAL_SECONDS", 60)

# Poll positions for both route directions (True) or just the forward direction (False).
POSITIONS_BOTH_DIRECTIONS = os.getenv("POSITIONS_BOTH_DIRECTIONS", "true").lower() == "true"

# Polite pause between individual HTTP requests within a cycle, to avoid hammering the API.
INTER_REQUEST_DELAY = _float("INTER_REQUEST_DELAY", 0.25)

# Where raw JSONL snapshots are written (gitignored). One subdir per stream, one file per day.
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "data" / "raw"))

# The set of stops/routes to track, produced by select_stops.py.
TRACKED_STOPS_FILE = Path(os.getenv("TRACKED_STOPS_FILE", COLLECTOR_DIR / "tracked_stops.json"))

# How many stops the auto-selector should pick.
TARGET_STOP_COUNT = _int("TARGET_STOP_COUNT", 30)