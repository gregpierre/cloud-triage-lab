"""
Tests for the dashboard routes, using Flask's built-in test client.

Run from the project root:
    python -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from dashboard import markdown_lite
from dashboard.app import build_timeline, create_app
from main import run_pipeline


class TestDashboard(unittest.TestCase):
    def setUp(self):
        # Use a temp folder so tests never touch the real output/ files.
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.report_path = tmp / "report.json"
        self.state_path = tmp / "state.json"
        self.report_path.write_text(json.dumps(run_pipeline()))

        app = create_app(report_path=self.report_path, state_path=self.state_path)
        self.client = app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_index_loads(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"WIZ-2026-1001", response.data)

    def test_sidebar_pages_load(self):
        for url in ("/", "/alerts", "/runbooks"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_alerts_page_hides_overview(self):
        html = self.client.get("/alerts").data
        self.assertIn(b"WIZ-2026-1001", html)
        self.assertNotIn(b'id="stats"', html)

    def test_runbooks_page_lists_problems_first(self):
        html = self.client.get("/runbooks").get_data(as_text=True)
        # Both PARTIAL runbooks should be listed before any COVERED one.
        first_covered = html.index("status-covered")
        self.assertLess(html.index("cloudtrail_disabled.md"), first_covered)
        self.assertLess(html.index("sg_open_ssh.md"), first_covered)

    def test_mark_triaged_and_reopen(self):
        response = self.client.post("/api/alerts/WIZ-2026-1001/triage",
                                    json={"analyst": "sam", "notes": "Policy detached."})
        entry = response.get_json()
        self.assertTrue(entry["triaged"])
        self.assertEqual(entry["notes"], "Policy detached.")
        self.assertIsNotNone(entry["triaged_at"])

        entry = self.client.post("/api/alerts/WIZ-2026-1001/reopen").get_json()
        self.assertFalse(entry["triaged"])
        self.assertEqual(entry["notes"], "Policy detached.")  # notes kept

    def test_unknown_alert_is_rejected(self):
        response = self.client.post("/api/alerts/NOT-REAL/triage", json={})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.state_path.exists())

    def test_runbook_renders_as_html(self):
        data = self.client.get("/api/runbooks/ROOT_ACCOUNT_LOGIN").get_json()
        self.assertIn("<h2>Triage</h2>", data["html"])

    def test_runbook_path_traversal_is_blocked(self):
        response = self.client.get("/api/runbooks/..%2F..%2Fmain.py")
        self.assertEqual(response.status_code, 404)

    def test_json_export_includes_triage_notes(self):
        self.client.post("/api/alerts/WIZ-2026-1004/triage",
                         json={"analyst": "sam", "notes": "Confirmed with custodian."})
        response = self.client.get("/export/json")
        self.assertIn("attachment", response.headers["Content-Disposition"])
        export = json.loads(response.data)
        self.assertEqual(export["session_summary"]["triaged"], 1)

    def test_print_report_loads(self):
        response = self.client.get("/export/pdf")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"window.print()", response.data)


class TestTimeline(unittest.TestCase):
    def test_groups_by_day_newest_first(self):
        alerts = [
            {"alert_id": "a", "created_at": "2026-10-10T09:00:00Z"},
            {"alert_id": "b", "created_at": "2026-10-12T08:00:00Z"},
            {"alert_id": "c", "created_at": "2026-10-12T20:00:00Z"},
        ]
        timeline = build_timeline(alerts)
        self.assertEqual([day for day, _ in timeline], ["2026-10-12", "2026-10-10"])
        self.assertEqual([a["alert_id"] for a in timeline[0][1]], ["c", "b"])


class TestMarkdownLite(unittest.TestCase):
    def test_html_is_escaped(self):
        html = markdown_lite.render("Hello <script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_lists_and_inline_code(self):
        html = markdown_lite.render("1. Run `aws s3 ls`\n2. Check **logs**")
        self.assertIn("<ol><li>Run <code>aws s3 ls</code></li>", html)
        self.assertIn("<strong>logs</strong>", html)


if __name__ == "__main__":
    unittest.main()
