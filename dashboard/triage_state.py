"""
Analyst triage state: which alerts have been triaged, by whom, when, and
with what notes.

This is stored in its own file instead of inside triage_report.json, because
main.py rewrites the report on every run. Keeping analyst work separate means
re-running the pipeline never wipes anyone's notes.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

STATE_PATH = Path(__file__).resolve().parent.parent / "output" / "triage_state.json"

MAX_NOTES_LENGTH = 2000
MAX_ANALYST_LENGTH = 60


def load_state(path=STATE_PATH):
    """Return {alert_id: {...}} for every alert an analyst has touched."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def save_state(state, path=STATE_PATH):
    """
    Write the state file. Writing to a temp file first and then renaming it
    means a crash mid-write can't leave a half-written, corrupted JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def mark_triaged(alert_id, notes, analyst, path=STATE_PATH):
    """Mark an alert as triaged (or update its notes if it already is)."""
    state = load_state(path)
    previous = state.get(alert_id, {})
    state[alert_id] = {
        "triaged": True,
        "notes": notes.strip()[:MAX_NOTES_LENGTH],
        "analyst": analyst.strip()[:MAX_ANALYST_LENGTH] or "unknown",
        # Keep the original triage time if this is just a notes update.
        "triaged_at": previous.get("triaged_at") if previous.get("triaged") else now_utc(),
        "updated_at": now_utc(),
    }
    save_state(state, path)
    return state[alert_id]


def reopen(alert_id, path=STATE_PATH):
    """Send an alert back to the open queue. Notes are kept for history."""
    state = load_state(path)
    entry = state.get(alert_id, {})
    entry.update({"triaged": False, "triaged_at": None, "updated_at": now_utc()})
    state[alert_id] = entry
    save_state(state, path)
    return entry
