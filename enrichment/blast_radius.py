"""
Blast radius enrichment.

"Blast radius" answers the question: if this finding is exploited, how much
damage can an attacker do? A raw alert only says *what* is misconfigured.
Enrichment adds *context* - which environment it lives in, what data it
touches, whether it's reachable from the internet, and what else it connects
to - so an analyst can decide how worried to be.
"""

import json
from pathlib import Path

INVENTORY_PATH = Path(__file__).parent / "asset_inventory.json"

# Static knowledge about each alert type: how far the damage can spread,
# what an attacker could do with it, and the matching MITRE ATT&CK technique.
# Some techniques appear under several tactics in ATT&CK; mitre_tactic is the
# one that best describes this specific cloud scenario.
#
# scope values, smallest to largest:
#   resource     - damage is limited to the single resource
#   account      - damage can reach anything in the AWS account
#   organization - damage can reach every account in the AWS Organization
ALERT_TYPE_CONTEXT = {
    "IAM_WILDCARD_POLICY": {
        "scope": "account",
        "attacker_impact": "Any principal with this policy has full admin "
                           "rights and can read, modify, or delete anything "
                           "in the account.",
        "mitre_technique": "T1098.003 - Account Manipulation: Additional Cloud Roles",
        "mitre_tactic": "Persistence",
    },
    "S3_PUBLIC_BUCKET": {
        "scope": "resource",
        "attacker_impact": "Anyone on the internet can download the bucket's "
                           "contents without credentials.",
        "mitre_technique": "T1530 - Data from Cloud Storage",
        "mitre_tactic": "Collection",
    },
    "ROOT_ACCOUNT_LOGIN": {
        "scope": "account",
        "attacker_impact": "Root cannot be restricted by IAM. A compromised "
                           "root session controls the entire account, "
                           "including billing and account closure.",
        "mitre_technique": "T1078.004 - Valid Accounts: Cloud Accounts",
        "mitre_tactic": "Initial Access",
    },
    "CLOUDTRAIL_DISABLED": {
        "scope": "organization",
        "attacker_impact": "API activity is no longer recorded, so later "
                           "attacker actions would be invisible to the SOC.",
        "mitre_technique": "T1562.008 - Impair Defenses: Disable or Modify Cloud Logs",
        "mitre_tactic": "Defense Evasion",
    },
    "SG_OPEN_SSH": {
        "scope": "resource",
        "attacker_impact": "Attached instances accept SSH connections from "
                           "the entire internet and will see constant "
                           "brute-force attempts.",
        "mitre_technique": "T1021.004 - Remote Services: SSH",
        "mitre_tactic": "Lateral Movement",
    },
}

# Points used to turn the context into a single blast radius level.
SCOPE_POINTS = {"resource": 1, "account": 2, "organization": 3}
CLASSIFICATION_POINTS = {"restricted": 2, "confidential": 1, "internal": 0, "public": 0}


def load_inventory(path=INVENTORY_PATH):
    """Load the simulated asset inventory from disk."""
    with open(path) as f:
        return json.load(f)


def calculate_blast_radius_level(scope, environment, classification,
                                 internet_exposed, connected_count):
    """
    Combine the context into a High / Medium / Low blast radius rating.

    Each factor adds points; the total decides the level. Keeping it as a
    simple point system makes it easy to explain why an alert got its rating.
    """
    points = SCOPE_POINTS.get(scope, 1)
    if environment == "production":
        points += 2
    points += CLASSIFICATION_POINTS.get(classification, 0)
    if internet_exposed:
        points += 1
    if connected_count >= 3:
        points += 1

    if points >= 6:
        return "High"
    if points >= 4:
        return "Medium"
    return "Low"


def enrich_alert(alert, inventory):
    """Return a copy of the alert with an added "enrichment" section."""
    accounts = inventory.get("accounts", {})
    resources = inventory.get("resources", {})

    account = accounts.get(alert["account_id"], {})
    resource = resources.get(alert["resource_id"])
    type_context = ALERT_TYPE_CONTEXT.get(alert["alert_type"], {})

    notes = []
    if resource is None:
        # An asset we don't know about is itself worth flagging. Shadow IT
        # and untracked resources are a common root cause of cloud incidents.
        notes.append("Resource not found in asset inventory - owner and data "
                     "classification could not be verified.")
        resource = {}
    if not account:
        notes.append("Account not found in asset inventory.")

    environment = account.get("environment", "unknown")
    classification = resource.get("data_classification", "unknown")
    internet_exposed = resource.get("internet_exposed", False)
    connected = resource.get("connected_resources", [])
    scope = type_context.get("scope", "resource")

    if resource.get("expected_public"):
        notes.append("Public exposure is documented as intentional in the "
                     "asset inventory. Likely an accepted risk, verify and close.")

    enriched = dict(alert)
    enriched["enrichment"] = {
        "account_name": account.get("name", "unknown"),
        "environment": environment,
        "resource_description": resource.get("description", "unknown"),
        "data_classification": classification,
        "internet_exposed": internet_exposed,
        "expected_public": resource.get("expected_public", False),
        "connected_resources": connected,
        "blast_radius_scope": scope,
        "blast_radius_level": calculate_blast_radius_level(
            scope, environment, classification, internet_exposed, len(connected)
        ),
        "attacker_impact": type_context.get("attacker_impact", "Unknown alert type."),
        "mitre_technique": type_context.get("mitre_technique", "n/a"),
        # Just the ID (e.g. "T1530"), for compact badges in the dashboard.
        "mitre_id": type_context.get("mitre_technique", "n/a").split(" ")[0],
        "mitre_tactic": type_context.get("mitre_tactic", "Unknown"),
        "notes": notes,
    }
    return enriched


def enrich_alerts(alerts, inventory=None):
    """Enrich a list of alerts. Loads the inventory if one isn't passed in."""
    if inventory is None:
        inventory = load_inventory()
    return [enrich_alert(alert, inventory) for alert in alerts]
