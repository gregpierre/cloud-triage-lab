"""
Unit tests for the triage pipeline. Uses only the standard library.

Run from the project root:
    python -m unittest discover tests
"""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from enrichment import enrich_alert
from scorer import prioritize_alerts, score_alert, score_to_priority
from validator import check_runbook, load_runbooks, validate_alerts

INVENTORY = {
    "accounts": {
        "111": {"name": "prod", "environment": "production"},
        "222": {"name": "dev", "environment": "development"},
    },
    "resources": {
        "bucket-pii": {
            "data_classification": "restricted",
            "internet_exposed": True,
            "connected_resources": [],
        },
        "bucket-website": {
            "data_classification": "public",
            "internet_exposed": True,
            "expected_public": True,
            "connected_resources": [],
        },
    },
}


def make_alert(resource_id="bucket-pii", account_id="111", severity="HIGH",
               alert_type="S3_PUBLIC_BUCKET"):
    return {
        "alert_id": "TEST-1",
        "alert_type": alert_type,
        "severity": severity,
        "resource_id": resource_id,
        "account_id": account_id,
        "region": "us-east-1",
        "resource_owner": "test-team",
    }


class TestEnrichment(unittest.TestCase):
    def test_sensitive_prod_bucket_has_high_blast_radius(self):
        enriched = enrich_alert(make_alert(), INVENTORY)
        self.assertEqual(enriched["enrichment"]["blast_radius_level"], "High")
        self.assertEqual(enriched["enrichment"]["environment"], "production")

    def test_unknown_resource_is_flagged(self):
        enriched = enrich_alert(make_alert(resource_id="mystery"), INVENTORY)
        notes = " ".join(enriched["enrichment"]["notes"])
        self.assertIn("not found in asset inventory", notes)

    def test_mitre_fields_are_added(self):
        enriched = enrich_alert(make_alert(), INVENTORY)
        self.assertEqual(enriched["enrichment"]["mitre_id"], "T1530")
        self.assertEqual(enriched["enrichment"]["mitre_tactic"], "Collection")

    def test_original_alert_is_not_modified(self):
        alert = make_alert()
        enrich_alert(alert, INVENTORY)
        self.assertNotIn("enrichment", alert)


class TestScorer(unittest.TestCase):
    def test_priority_thresholds(self):
        self.assertEqual(score_to_priority(100), "critical")
        self.assertEqual(score_to_priority(85), "critical")
        self.assertEqual(score_to_priority(84), "high")
        self.assertEqual(score_to_priority(40), "medium")
        self.assertEqual(score_to_priority(39), "low")

    def test_expected_public_bucket_scores_lower(self):
        pii = score_alert(enrich_alert(make_alert(), INVENTORY))
        website = score_alert(enrich_alert(make_alert(resource_id="bucket-website"), INVENTORY))
        self.assertGreater(pii["scoring"]["risk_score"], website["scoring"]["risk_score"])

    def test_score_is_capped_at_100(self):
        scored = score_alert(enrich_alert(make_alert(severity="CRITICAL"), INVENTORY))
        self.assertLessEqual(scored["scoring"]["risk_score"], 100)

    def test_alerts_are_sorted_critical_first(self):
        alerts = [
            enrich_alert(make_alert(account_id="222", severity="LOW"), INVENTORY),
            enrich_alert(make_alert(severity="CRITICAL"), INVENTORY),
        ]
        ordered = prioritize_alerts(alerts)
        self.assertEqual(ordered[0]["severity"], "CRITICAL")


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_runbook(self, name, alert_type, reviewed, sections):
        body = "\n".join(f"## {s}\nSome steps.\n" for s in sections)
        (self.dir / name).write_text(
            f"---\nalert_type: {alert_type}\nlast_reviewed: {reviewed}\n---\n\n{body}"
        )

    def test_complete_runbook_is_covered(self):
        self.write_runbook("a.md", "TYPE_A", "2026-10-01",
                           ["Overview", "Triage", "Containment", "Remediation", "Escalation"])
        result = check_runbook("TYPE_A", load_runbooks(self.dir), today=date(2026, 10, 15))
        self.assertEqual(result["status"], "COVERED")

    def test_missing_section_is_partial(self):
        self.write_runbook("a.md", "TYPE_A", "2026-10-01",
                           ["Overview", "Triage", "Remediation", "Escalation"])
        result = check_runbook("TYPE_A", load_runbooks(self.dir), today=date(2026, 10, 15))
        self.assertEqual(result["status"], "PARTIAL")
        self.assertIn("Missing required section: Containment", result["gaps"])

    def test_stale_runbook_is_partial(self):
        self.write_runbook("a.md", "TYPE_A", "2025-01-01",
                           ["Overview", "Triage", "Containment", "Remediation", "Escalation"])
        result = check_runbook("TYPE_A", load_runbooks(self.dir), today=date(2026, 10, 15))
        self.assertEqual(result["status"], "PARTIAL")
        self.assertTrue(result["stale"])
        self.assertEqual(result["review_age_days"], 652)

    def test_stale_runbooks_listed_in_summary(self):
        self.write_runbook("a.md", "S3_PUBLIC_BUCKET", "2025-01-01",
                           ["Overview", "Triage", "Containment", "Remediation", "Escalation"])
        _, summary = validate_alerts([make_alert()], self.dir, today=date(2026, 10, 15))
        self.assertEqual(summary["stale_runbooks"][0]["alert_type"], "S3_PUBLIC_BUCKET")

    def test_no_runbook_is_missing(self):
        result = check_runbook("TYPE_B", load_runbooks(self.dir))
        self.assertEqual(result["status"], "MISSING")


if __name__ == "__main__":
    unittest.main()
