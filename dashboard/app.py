"""
Flask dashboard for the triage report.

The dashboard reads output/triage_report.json, which main.py writes, so the
pipeline logic lives in one place. Analyst work (triage status and notes) is
saved separately in output/triage_state.json by triage_state.py.

Run it from the project root with either:
    python main.py --serve
    python -m dashboard.app        (uses the last saved report)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request

from scorer import PRIORITY_ORDER
from validator import check_runbook, load_runbooks
from validator.runbook_checker import MAX_REVIEW_AGE_DAYS, parse_front_matter

from . import markdown_lite, triage_state

REPORT_PATH = Path(__file__).resolve().parent.parent / "output" / "triage_report.json"


def load_report(path=REPORT_PATH):
    """Load the saved report, or return None if the pipeline hasn't run yet."""
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def merge_triage_state(report, state):
    """Attach each alert's analyst triage info (or a blank default) to the report."""
    for alert in report["alerts"]:
        alert["triage"] = state.get(alert["alert_id"],
                                    {"triaged": False, "notes": "", "analyst": "", "triaged_at": None})
    report["triaged_count"] = sum(1 for a in report["alerts"] if a["triage"]["triaged"])
    return report


def build_timeline(alerts):
    """
    Group alerts by the day they were detected, newest first, for the
    timeline view. Returns [(day, [alerts...]), ...].

    created_at is ISO 8601 ("2026-10-15T02:31:57Z"), which sorts correctly
    as a plain string, and its first 10 characters are the date.
    """
    days = {}
    for alert in sorted(alerts, key=lambda a: a.get("created_at", ""), reverse=True):
        days.setdefault(alert.get("created_at", "unknown")[:10], []).append(alert)
    return list(days.items())


def build_runbook_rows(report):
    """
    One row per alert type for the Runbooks page: the runbook's validation
    result plus how many alerts depend on it. Alert types that appear in the
    report but have no runbook are included too, so MISSING runbooks show up.
    """
    runbooks = load_runbooks()
    alerts = report["alerts"] if report else []
    alert_types = sorted(set(runbooks) | {a["alert_type"] for a in alerts})

    rows = []
    for alert_type in alert_types:
        related = [a for a in alerts if a["alert_type"] == alert_type]
        priorities = [a["scoring"]["priority"] for a in related]
        row = check_runbook(alert_type, runbooks)
        row.update({
            "alert_type": alert_type,
            "alert_count": len(related),
            "open_count": sum(1 for a in related if not a.get("triage", {}).get("triaged")),
            # The most urgent alert relying on this runbook, e.g. "critical".
            "top_priority": min(priorities, key=PRIORITY_ORDER.get) if priorities else None,
        })
        rows.append(row)

    # Problems first (missing, then partial), then by how urgent the alerts are.
    status_order = {"MISSING": 0, "PARTIAL": 1, "COVERED": 2}
    rows.sort(key=lambda r: (status_order[r["status"]], PRIORITY_ORDER.get(r["top_priority"], 9)))
    return rows


def create_app(report_path=REPORT_PATH, state_path=triage_state.STATE_PATH):
    app = Flask(__name__)

    def current_report():
        """Load the report fresh on every request, so re-running main.py and
        refreshing the page shows new results without restarting Flask."""
        report = load_report(report_path)
        if report is not None:
            merge_triage_state(report, triage_state.load_state(state_path))
        return report

    def require_alert(report, alert_id):
        """404 unless the alert exists, so the state file only ever holds real IDs."""
        if report is None or alert_id not in {a["alert_id"] for a in report["alerts"]}:
            abort(404, description=f"Unknown alert {alert_id}")

    # ---------- Pages ----------

    @app.route("/")
    def index():
        """Dashboard: overview stats, warnings, and the alert queue."""
        report = current_report()
        timeline = build_timeline(report["alerts"]) if report else []
        return render_template("index.html", report=report, timeline=timeline,
                               active_page="dashboard")

    @app.route("/alerts")
    def alerts_page():
        """Focused working view: just the filters and the alert list."""
        report = current_report()
        timeline = build_timeline(report["alerts"]) if report else []
        return render_template("index.html", report=report, timeline=timeline,
                               active_page="alerts")

    @app.route("/runbooks")
    def runbooks_page():
        """Every runbook, its validation status, and the alerts that rely on it."""
        rows = build_runbook_rows(current_report())
        counts = {status: sum(1 for r in rows if r["status"] == status)
                  for status in ("COVERED", "PARTIAL", "MISSING")}
        return render_template("runbooks.html", rows=rows, counts=counts,
                               max_age=MAX_REVIEW_AGE_DAYS, active_page="runbooks")

    @app.route("/export/pdf")
    def export_pdf():
        """
        Printable report. The page opens the browser's print dialog, where
        "Save as PDF" produces the file. This avoids needing a PDF library.
        """
        report = current_report()
        if report is None:
            abort(404, description="No report yet. Run python main.py first.")
        return render_template("report_print.html", report=report,
                               exported_at=triage_state.now_utc())

    # ---------- JSON API ----------

    @app.route("/api/report")
    def api_report():
        """Raw JSON, handy for scripting or piping into other tools."""
        report = current_report()
        if report is None:
            abort(404, description="No report yet. Run python main.py first.")
        return jsonify(report)

    @app.route("/api/alerts/<alert_id>/triage", methods=["POST"])
    def api_mark_triaged(alert_id):
        require_alert(load_report(report_path), alert_id)
        body = request.get_json(silent=True) or {}
        entry = triage_state.mark_triaged(
            alert_id, str(body.get("notes", "")), str(body.get("analyst", "")), state_path
        )
        return jsonify(entry)

    @app.route("/api/alerts/<alert_id>/reopen", methods=["POST"])
    def api_reopen(alert_id):
        require_alert(load_report(report_path), alert_id)
        return jsonify(triage_state.reopen(alert_id, state_path))

    @app.route("/api/runbooks/<alert_type>")
    def api_runbook(alert_type):
        """
        Return a runbook rendered as HTML for the in-dashboard viewer.

        The file is looked up through the validator's index (by the
        alert_type in its front matter), never by building a path from the
        URL, so a request like ../../etc/passwd can't read arbitrary files.
        """
        runbook = load_runbooks().get(alert_type)
        if runbook is None:
            abort(404, description=f"No runbook for {alert_type}")
        _, body = parse_front_matter(runbook["path"].read_text())
        return jsonify({
            "alert_type": alert_type,
            "title": runbook["title"],
            "file": runbook["file"],
            "owner": runbook["owner"],
            "last_reviewed": runbook["last_reviewed"],
            "html": markdown_lite.render(body),
        })

    @app.route("/export/json")
    def export_json():
        """Download the whole triage session (alerts + analyst notes) as a file."""
        report = current_report()
        if report is None:
            abort(404, description="No report yet. Run python main.py first.")

        now = datetime.now(timezone.utc)
        export = {
            "exported_at": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "report_generated_at": report["generated_at"],
            "session_summary": {
                "total_alerts": report["total_alerts"],
                "triaged": report["triaged_count"],
                "open": report["total_alerts"] - report["triaged_count"],
                "priority_counts": report["priority_counts"],
                "runbook_coverage": report["runbook_coverage"],
            },
            "alerts": report["alerts"],
        }
        filename = f"triage-session-{now.strftime('%Y%m%d-%H%M')}.json"
        return Response(
            json.dumps(export, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
