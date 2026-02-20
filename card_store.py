"""
Card Store: Persistent card history across runs.

Stores cards as JSON with timestamps. Enables:
  - Delta detection: "what changed since last run"
  - Staleness tracking: how many consecutive runs a story has appeared
  - Prediction accountability: track hit/miss over time
  - Refresh mode: compare new clusters against existing cards

Storage: output/card_history.json (committed to repo by GitHub Actions)
"""

import json
from datetime import datetime, timezone
from pathlib import Path


HISTORY_PATH = Path("output/card_history.json")
MAX_HISTORY_DAYS = 7  # Keep 7 days of history


def load_history():
    """Load card history. Returns dict with 'runs' list."""
    if not HISTORY_PATH.exists():
        return {"runs": []}
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "runs" not in data:
            return {"runs": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"runs": []}


def get_latest_cards():
    """Get cards from the most recent run. Returns list of card dicts."""
    history = load_history()
    if not history["runs"]:
        return []
    return history["runs"][-1].get("cards", [])


def get_latest_titles():
    """Get set of card titles from most recent run."""
    cards = get_latest_cards()
    return set(c.get("title", "") for c in cards if c.get("title"))


def save_run(topic_cards, run_time, mode="full"):
    """Save current run's cards to history."""
    history = load_history()

    run_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "runtime_seconds": run_time,
        "card_count": len(topic_cards),
        "cards": [card.to_dict() for card in topic_cards],
    }

    history["runs"].append(run_entry)

    # Prune old runs (keep last 7 days worth, ~84 runs at 2hr intervals)
    cutoff = 7 * 24  # max runs to keep
    if len(history["runs"]) > cutoff:
        history["runs"] = history["runs"][-cutoff:]

    HISTORY_PATH.parent.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, indent=2, default=str),
        encoding="utf-8")


def classify_story_delta(new_title, new_whats, existing_cards):
    """Classify a story relative to previous run.
    
    Returns: "new", "continuing", or "updated"
    """
    if not existing_cards:
        return "new"

    # Check title similarity against existing cards
    new_words = set(new_title.lower().split())

    for card in existing_cards:
        old_title = card.get("title", "")
        old_words = set(old_title.lower().split())

        # High overlap = same story
        if len(new_words) > 0 and len(old_words) > 0:
            overlap = len(new_words & old_words) / min(len(new_words), len(old_words))
            if overlap > 0.5:
                # Same story — check if content changed
                old_whats = card.get("whats_happening", card.get("what_happened", ""))
                if new_whats and old_whats:
                    new_content_words = set(new_whats.lower().split())
                    old_content_words = set(old_whats.lower().split())
                    content_overlap = len(new_content_words & old_content_words) / max(len(new_content_words), len(old_content_words), 1)
                    if content_overlap < 0.6:
                        return "updated"
                return "continuing"

    return "new"


def get_story_streak(title, history=None):
    """How many consecutive runs has this story appeared?"""
    if history is None:
        history = load_history()

    streak = 0
    for run in reversed(history["runs"]):
        found = False
        title_words = set(title.lower().split())
        for card in run.get("cards", []):
            card_words = set(card.get("title", "").lower().split())
            if len(title_words) > 0 and len(card_words) > 0:
                overlap = len(title_words & card_words) / min(len(title_words), len(card_words))
                if overlap > 0.5:
                    found = True
                    break
        if found:
            streak += 1
        else:
            break

    return streak
