"""
Risk scoring and prioritization.

The severity a scanner assigns is a good starting point, but it doesn't know
your environment. A HIGH finding in a sandbox account matters less than the
same finding next to customer data in production. This module starts from
the vendor severity, adjusts it using the enrichment context, and sorts the
queue so the analyst works the most important alert first.
"""

# Starting score for each vendor severity (0-100 scale).
SEVERITY_BASE_SCORE = {
    "CRITICAL": 80,
    "HIGH": 60,
    "MEDIUM": 40,
    "LOW": 20,
    "INFORMATIONAL": 0,
}

# Adjustments applied on top of the base score.
BLAST_RADIUS_MODIFIER = {"High": 20, "Medium": 10, "Low": 0}
ENVIRONMENT_MODIFIER = {"production": 5, "development": -10}
EXPECTED_PUBLIC_MODIFIER = -30

# Final score -> priority bucket. Checked top to bottom.
PRIORITY_THRESHOLDS = [
    (85, "critical"),
    (65, "high"),
    (40, "medium"),
    (0, "low"),
]

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def score_to_priority(score):
    """Map a 0-100 risk score to a priority bucket."""
    for threshold, priority in PRIORITY_THRESHOLDS:
        if score >= threshold:
            return priority
    return "low"


def score_alert(alert):
    """
    Return a copy of the alert with a "scoring" section.

    Every adjustment is recorded in "reasons" so the final number can be
    explained. An analyst should never have to trust a score blindly.
    """
    enrichment = alert.get("enrichment", {})
    severity = alert.get("severity", "LOW").upper()

    base = SEVERITY_BASE_SCORE.get(severity, 20)
    score = base
    reasons = [f"Base score {base} from vendor severity {severity}"]

    blast = enrichment.get("blast_radius_level")
    if blast in BLAST_RADIUS_MODIFIER and BLAST_RADIUS_MODIFIER[blast]:
        score += BLAST_RADIUS_MODIFIER[blast]
        reasons.append(f"+{BLAST_RADIUS_MODIFIER[blast]} {blast} blast radius")

    environment = enrichment.get("environment")
    if environment in ENVIRONMENT_MODIFIER:
        change = ENVIRONMENT_MODIFIER[environment]
        score += change
        reasons.append(f"{change:+d} {environment} environment")

    if enrichment.get("expected_public"):
        score += EXPECTED_PUBLIC_MODIFIER
        reasons.append(f"{EXPECTED_PUBLIC_MODIFIER:+d} exposure documented as intentional")

    # Keep the score on a 0-100 scale.
    score = max(0, min(100, score))

    scored = dict(alert)
    scored["scoring"] = {
        "risk_score": score,
        "priority": score_to_priority(score),
        "reasons": reasons,
    }
    return scored


def prioritize_alerts(alerts):
    """Score every alert and sort them from critical to low."""
    scored = [score_alert(alert) for alert in alerts]
    # Highest score first. Ties are broken by the oldest alert first,
    # since it has been waiting in the queue the longest.
    scored.sort(key=lambda a: (-a["scoring"]["risk_score"], a.get("created_at", "")))
    return scored
