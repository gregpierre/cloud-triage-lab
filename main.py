"""
cloud-triage-lab: run the full alert triage pipeline.

    load alerts -> enrich (blast radius) -> score & prioritize -> validate runbooks

Usage:
    python main.py            # run the pipeline and print a summary
    python main.py --serve    # run the pipeline, then open the Flask dashboard
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from enrichment import enrich_alerts
from scorer import prioritize_alerts
from validator import validate_alerts

BASE_DIR = Path(__file__).resolve().parent
ALERTS_DIR = BASE_DIR / "alerts"
REPORT_PATH = BASE_DIR / "output" / "triage_report.json"

# Fields every alert must have before it can be triaged.
REQUIRED_FIELDS = [
    "alert_id", "alert_type", "severity", "resource_id",
    "account_id", "region", "resource_owner",
]


def load_alerts(alerts_dir=ALERTS_DIR):
    """
    Load every alert from the JSON files in alerts/.

    A file can hold a single alert object or a list of them. Alerts missing
    required fields are skipped with a warning instead of crashing the run,
    because one malformed alert shouldn't block triage of all the others.
    """
    alerts = []
    for path in sorted(Path(alerts_dir).glob("*.json")):
        with open(path) as f:
            data = json.load(f)
        for alert in data if isinstance(data, list) else [data]:
            missing = [field for field in REQUIRED_FIELDS if field not in alert]
            if missing:
                print(f"[loader] skipping alert in {path.name}, missing: {', '.join(missing)}")
                continue
            alerts.append(alert)
    return alerts


def run_pipeline():
    """Run every stage and return the finished triage report as a dict."""
    alerts = load_alerts()
    alerts = enrich_alerts(alerts)
    alerts = prioritize_alerts(alerts)
    alerts, coverage = validate_alerts(alerts)

    priority_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for alert in alerts:
        priority_counts[alert["scoring"]["priority"]] += 1

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total_alerts": len(alerts),
        "priority_counts": priority_counts,
        "runbook_coverage": coverage,
        "alerts": alerts,
    }


def save_report(report, path=REPORT_PATH):
    """Write the report to disk so the dashboard (or anything else) can read it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)


def print_summary(report):
    """Print the prioritized queue and any runbook gaps to the terminal."""
    print(f"\nTriage queue - {report['total_alerts']} alerts ({report['generated_at']})\n")
    print(f"{'PRIORITY':<10}{'SCORE':>6}  {'ALERT ID':<15}{'TYPE':<22}{'BLAST':<8}{'RUNBOOK':<9}")
    print("-" * 70)
    for alert in report["alerts"]:
        print(
            f"{alert['scoring']['priority'].upper():<10}"
            f"{alert['scoring']['risk_score']:>6}  "
            f"{alert['alert_id']:<15}"
            f"{alert['alert_type']:<22}"
            f"{alert['enrichment']['blast_radius_level']:<8}"
            f"{alert['runbook_validation']['status']:<9}"
        )

    coverage = report["runbook_coverage"]
    print(f"\nRunbook coverage: {coverage['fully_covered']}/{coverage['alert_types_seen']} "
          f"alert types fully covered ({coverage['coverage_percent']}%)")
    for alert_type, gaps in coverage["gaps"].items():
        print(f"  ! {alert_type}")
        for gap in gaps:
            print(f"      - {gap}")
    print(f"\nReport written to {REPORT_PATH.relative_to(BASE_DIR)}")


def main():
    parser = argparse.ArgumentParser(description="Cloud security alert triage pipeline")
    parser.add_argument("--serve", action="store_true", help="start the dashboard after the run")
    parser.add_argument("--port", type=int, default=5000, help="dashboard port (default 5000)")
    args = parser.parse_args()

    report = run_pipeline()
    save_report(report)
    print_summary(report)

    if args.serve:
        # Imported here so the pipeline still runs if Flask isn't installed.
        from dashboard.app import create_app
        print(f"\nDashboard running at http://127.0.0.1:{args.port}")
        create_app().run(port=args.port)


if __name__ == "__main__":
    main()
