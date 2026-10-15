"""
Runbook coverage validation.

Detection is only half the job. When an alert fires at 2am, the on-call
analyst needs a runbook that tells them what to do. This module checks each
alert against the runbooks folder and flags three kinds of gaps:

  1. MISSING - no runbook exists for the alert type at all
  2. PARTIAL - a runbook exists but is missing required sections, or
               hasn't been reviewed recently enough to trust
  3. COVERED - a complete, recently reviewed runbook exists
"""

import re
from datetime import date
from pathlib import Path

RUNBOOK_DIR = Path(__file__).resolve().parent.parent / "runbooks"

# Every runbook must have these "## " headings with content under them.
REQUIRED_SECTIONS = ["Overview", "Triage", "Containment", "Remediation", "Escalation"]

# Runbooks older than this are flagged as stale.
MAX_REVIEW_AGE_DAYS = 180


def parse_front_matter(text):
    """
    Read the simple "key: value" block between the --- lines at the top of a
    runbook. Returns (metadata dict, rest of the document).

    This is a tiny hand-rolled parser so the project doesn't need PyYAML.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text

    metadata = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, match.group(2)


def find_sections(body):
    """Return a dict of {section heading: section text} for every "## " heading."""
    sections = {}
    # Split on level-2 headings. The capture group keeps the heading names.
    parts = re.split(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE)
    # parts looks like: [intro, heading1, text1, heading2, text2, ...]
    for i in range(1, len(parts), 2):
        sections[parts[i]] = parts[i + 1].strip()
    return sections


def load_runbooks(runbook_dir=RUNBOOK_DIR):
    """
    Index every runbook by the alert_type declared in its front matter.

    Matching on front matter instead of the filename means a renamed file
    can't silently break coverage.
    """
    runbooks = {}
    for path in sorted(Path(runbook_dir).glob("*.md")):
        metadata, body = parse_front_matter(path.read_text())
        alert_type = metadata.get("alert_type")
        if not alert_type:
            print(f"[validator] warning: {path.name} has no alert_type, skipping")
            continue
        runbooks[alert_type] = {
            "file": path.name,
            "path": path,
            "title": metadata.get("title", path.stem),
            "owner": metadata.get("owner", "unknown"),
            "last_reviewed": metadata.get("last_reviewed"),
            "sections": find_sections(body),
        }
    return runbooks


def check_runbook(alert_type, runbooks, today=None):
    """Validate the runbook for a single alert type and list any gaps."""
    today = today or date.today()
    runbook = runbooks.get(alert_type)

    if runbook is None:
        return {
            "status": "MISSING",
            "runbook_file": None,
            "gaps": [f"No runbook found for alert type {alert_type}"],
        }

    gaps = []
    review_age_days = None

    # Every required section must exist and actually contain something.
    for section in REQUIRED_SECTIONS:
        if section not in runbook["sections"]:
            gaps.append(f"Missing required section: {section}")
        elif not runbook["sections"][section]:
            gaps.append(f"Section is empty: {section}")

    # An outdated runbook can be worse than none - commands and contacts change.
    reviewed = runbook["last_reviewed"]
    if not reviewed:
        gaps.append("No last_reviewed date in front matter")
    else:
        try:
            review_age_days = (today - date.fromisoformat(reviewed)).days
            if review_age_days > MAX_REVIEW_AGE_DAYS:
                gaps.append(f"Stale: last reviewed {review_age_days} days ago "
                            f"(limit is {MAX_REVIEW_AGE_DAYS})")
        except ValueError:
            gaps.append(f"Invalid last_reviewed date: {reviewed}")

    return {
        "status": "PARTIAL" if gaps else "COVERED",
        "runbook_file": runbook["file"],
        "runbook_title": runbook["title"],
        "runbook_owner": runbook["owner"],
        "last_reviewed": reviewed,
        "review_age_days": review_age_days,
        "stale": review_age_days is not None and review_age_days > MAX_REVIEW_AGE_DAYS,
        "gaps": gaps,
    }


def validate_alerts(alerts, runbook_dir=RUNBOOK_DIR, today=None):
    """
    Attach a "runbook_validation" section to every alert and build a
    coverage summary for the whole alert set.
    """
    runbooks = load_runbooks(runbook_dir)

    validated = []
    for alert in alerts:
        result = dict(alert)
        result["runbook_validation"] = check_runbook(alert["alert_type"], runbooks, today)
        validated.append(result)

    # Summarize per alert type so a gap is reported once, not once per alert.
    by_type = {}
    for alert in validated:
        by_type.setdefault(alert["alert_type"], alert["runbook_validation"])

    covered = [t for t, v in by_type.items() if v["status"] == "COVERED"]
    summary = {
        "alert_types_seen": len(by_type),
        "fully_covered": len(covered),
        "coverage_percent": round(100 * len(covered) / len(by_type)) if by_type else 100,
        "gaps": {t: v["gaps"] for t, v in sorted(by_type.items()) if v["gaps"]},
        # Listed separately so the dashboard can show a dedicated warning.
        "max_review_age_days": MAX_REVIEW_AGE_DAYS,
        "stale_runbooks": [
            {"alert_type": t, "file": v["runbook_file"],
             "last_reviewed": v["last_reviewed"], "age_days": v["review_age_days"]}
            for t, v in sorted(by_type.items()) if v.get("stale")
        ],
        # Runbooks that exist but match no current alert type. Not an error,
        # but worth knowing about when cleaning up documentation.
        "unused_runbooks": sorted(set(runbooks) - set(by_type)),
    }
    return validated, summary
